"""MySQL durable queue. Run: python -m src.workers.ingestion."""
import json
import logging
import time
import os
from threading import Event, Lock, Thread
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.config.db_session import engine
from src.ingestion.readers import read_document
from src.ingestion.chunker import chunk_blocks
from src.utils.pinecone_service import upsert_chunks

log = logging.getLogger(__name__)
_thread_lock = Lock()
_thread = None
_stop = None


def processing_failure(error):
    """Persist useful diagnostics without provider responses or filesystem paths."""
    if isinstance(error, FileNotFoundError):
        return 'source_file_missing: Upload the document again; its stored original is unavailable.', True
    if isinstance(error, requests.HTTPError) and error.response is not None:
        status = error.response.status_code
        if status == 402:
            return 'embedding_credits: Embedding provider has no available credits.', True
        if status in (401, 403):
            return 'embedding_credentials: Embedding service configuration requires attention.', True
        return f'embedding_http_{status}: Embedding service request failed.', status < 500 and status != 429
    if isinstance(error, ImportError):
        return 'missing_dependency: Document processing dependencies are not installed.', True
    return 'Processing failed: ' + type(error).__name__, isinstance(error, ValueError)


def process_job(session, job):
    doc = session.execute(text('SELECT FileName,FilePath FROM Documents WHERE DocumentID=:doc'),
                          {'doc': job['DocumentID']}).mappings().one()
    chunks = session.execute(text('SELECT ChunkID,ChunkText FROM DocumentChunks WHERE DocumentID=:doc ORDER BY ChunkID'),
                             {'doc': job['DocumentID']}).all()
    if not chunks:
        values = chunk_blocks(read_document(doc['FilePath'], doc['FileName']))
        if not values or len(values) > 20000:
            raise ValueError('Document must produce between 1 and 20000 chunks')
        for chunk in values:
            session.execute(text('''INSERT INTO DocumentChunks (DocumentID,ChunkText,Metadata)
                VALUES (:doc,:body,:metadata)'''), {'doc': job['DocumentID'], 'body': chunk['text'],
                'metadata': json.dumps(chunk['metadata'], ensure_ascii=False)})
        session.commit()
        chunks = session.execute(text('SELECT ChunkID,ChunkText FROM DocumentChunks WHERE DocumentID=:doc ORDER BY ChunkID'),
                                 {'doc': job['DocumentID']}).all()
    # Deterministic vector IDs make partial batch failures safe to retry.
    upsert_chunks([r[0] for r in chunks], [r[1] for r in chunks], str(job['UserID']), job['DocumentID'])


def run_once():
    with engine.connect() as connection:
        with Session(bind=connection) as session:
            jobs = session.execute(text('''SELECT JobID FROM IngestionJobs
                WHERE Status IN ('queued','processing') AND NextAttemptAt<=CURRENT_TIMESTAMP
                ORDER BY CreatedAt LIMIT 100''')).scalars().all()
            session.commit()
            for job_id in jobs:
                lock = 'ingest:' + job_id
                acquired = session.execute(text('SELECT GET_LOCK(:key,0)'), {'key': lock}).scalar()
                session.commit()
                if not acquired:
                    continue
                try:
                    job = session.execute(text('SELECT * FROM IngestionJobs WHERE JobID=:id AND NextAttemptAt<=CURRENT_TIMESTAMP'), {'id': job_id}).mappings().first()
                    if not job or job['Status'] not in ('queued', 'processing'):
                        continue
                    session.execute(text("UPDATE IngestionJobs SET Status='processing',Attempts=Attempts+1,UpdatedAt=CURRENT_TIMESTAMP WHERE JobID=:id"), {'id': job_id})
                    session.commit()
                    try:
                        process_job(session, job)
                        session.execute(text("UPDATE IngestionJobs SET Status='ready',Error=NULL,UpdatedAt=CURRENT_TIMESTAMP WHERE JobID=:id"), {'id': job_id})
                        session.commit()
                    except Exception as exc:
                        session.rollback()
                        log.exception('Ingestion failed for job %s', job_id)
                        message, permanent = processing_failure(exc)
                        status = 'failed' if permanent or job['Attempts'] + 1 >= 3 else 'queued'
                        session.execute(text('''UPDATE IngestionJobs SET Status=:status,Error=:error,
                            NextAttemptAt=DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 30 SECOND),
                            UpdatedAt=CURRENT_TIMESTAMP WHERE JobID=:id'''),
                            {'status': status, 'error': message, 'id': job_id})
                        session.commit()
                    return True
                finally:
                    session.rollback()
                    session.execute(text('SELECT RELEASE_LOCK(:key)'), {'key': lock})
                    session.commit()
    return False


def run_forever(stop=None):
    stop = stop if stop is not None else Event()
    while not stop.is_set():
        try:
            if not run_once():
                stop.wait(2)
        except Exception:
            log.exception('Worker iteration failed')
            stop.wait(5)


def start_worker_thread():
    """Opt out with INGESTION_WORKER_MODE=external when using a separate worker."""
    global _thread, _stop
    mode = os.getenv('INGESTION_WORKER_MODE', 'embedded')
    if mode == 'external':
        return None
    if mode != 'embedded':
        raise ValueError('INGESTION_WORKER_MODE must be embedded or external')
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _stop = Event()
            _thread = Thread(target=run_forever, args=(_stop,), name='document-ingestion', daemon=True)
            _thread.start()
            log.info('Embedded document ingestion worker started')
    return _thread


def stop_worker_thread():
    with _thread_lock:
        if _stop is not None:
            _stop.set()
        if _thread is not None:
            _thread.join(timeout=3)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_forever()

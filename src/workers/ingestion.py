"""MySQL durable queue. Run: python -m src.workers.ingestion."""
import json
import logging
import time
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.config.db_session import engine
from src.ingestion.readers import read_document
from src.ingestion.chunker import chunk_blocks
from src.utils.pinecone_service import upsert_chunks

log = logging.getLogger(__name__)


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
                        permanent = isinstance(exc, (ValueError, FileNotFoundError, ImportError))
                        status = 'failed' if permanent or job['Attempts'] + 1 >= 3 else 'queued'
                        session.execute(text('''UPDATE IngestionJobs SET Status=:status,Error=:error,
                            NextAttemptAt=DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 30 SECOND),
                            UpdatedAt=CURRENT_TIMESTAMP WHERE JobID=:id'''),
                            {'status': status, 'error': 'Processing failed: ' + type(exc).__name__, 'id': job_id})
                        session.commit()
                    return True
                finally:
                    session.rollback()
                    session.execute(text('SELECT RELEASE_LOCK(:key)'), {'key': lock})
                    session.commit()
    return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            if not run_once():
                time.sleep(2)
        except Exception:
            log.exception('Worker iteration failed')
            time.sleep(5)

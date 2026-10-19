"""Persist originals and enqueue ingestion without external API calls."""
import hashlib
import os
import uuid
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from src.ingestion.readers import SUPPORTED
from src.ingestion.chunker import PIPELINE_VERSION

MAX_FILE_BYTES = 20 * 1024 * 1024


def storage_root():
    root = Path(os.getenv('DOCUMENT_STORAGE_DIR', 'storage/documents')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def enqueue_document(session, file, user_id, conversation_id, description=''):
    filename = Path((file.filename or '').replace('\\', '/')).name
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError('Supported formats: PDF, DOCX, TXT, MD, CSV, XLSX')
    if len(filename) > 255:
        raise ValueError('Filename is too long')
    job_id = uuid.uuid4().hex
    path = storage_root() / (job_id + ext)
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open('xb') as target:
            while True:
                block = file.stream.read(65536)
                if not block:
                    break
                size += len(block)
                if size > MAX_FILE_BYTES:
                    raise ValueError('File exceeds 20 MiB')
                digest.update(block)
                target.write(block)
        if not size:
            raise ValueError('Empty document')
        params = {'uid': user_id, 'hash': digest.hexdigest(), 'version': PIPELINE_VERSION}
        existing = session.execute(text('''SELECT JobID,DocumentID,Status FROM IngestionJobs
            WHERE UserID=:uid AND ContentHash=:hash AND PipelineVersion=:version'''), params).mappings().first()
        if existing:
            path.unlink(missing_ok=True)
            job_id, doc_id, status = existing['JobID'], existing['DocumentID'], existing['Status']
        else:
            result = session.execute(text('''INSERT INTO Documents
                (FileName,FilePath,FileType,UploadedBy,FileSizeMB,Description)
                VALUES (:name,:path,:type,:uid,:size,:description)'''),
                {'name': filename, 'path': str(path), 'type': ext[1:].upper(),
                 'uid': user_id, 'size': size / 1048576, 'description': description})
            doc_id = result.lastrowid
            session.execute(text('''INSERT INTO IngestionJobs
                (JobID,DocumentID,UserID,ContentHash,PipelineVersion) VALUES (:job,:doc,:uid,:hash,:version)'''),
                {**params, 'job': job_id, 'doc': doc_id})
            status = 'queued'
        link = {'cid': conversation_id, 'doc': doc_id}
        if session.execute(text('SELECT DocumentID FROM ConversationDocuments WHERE ConversationID=:cid AND DocumentID=:doc'), link).first():
            session.execute(text('UPDATE ConversationDocuments SET IsDeleted=0 WHERE ConversationID=:cid AND DocumentID=:doc'), link)
        else:
            session.execute(text('INSERT INTO ConversationDocuments (ConversationID,DocumentID) VALUES (:cid,:doc)'), link)
        session.commit()
        return {'success': True, 'document_id': doc_id, 'job_id': job_id, 'status': status}
    except Exception as exc:
        session.rollback()
        path.unlink(missing_ok=True)
        if isinstance(exc, IntegrityError):
            raise ValueError('Concurrent upload or conversation removed; retry upload') from None
        raise

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import text
from src.config.db_session import SessionLocal
from src.services.document_service import enqueue_document

upload_bp = Blueprint('upload', __name__, url_prefix='/api')


@upload_bp.route('/upload_pdf/<int:conversation_id>', methods=['POST'])
@upload_bp.route('/conversations/<int:conversation_id>/documents', methods=['POST'])
@jwt_required()
def upload_documents(conversation_id):
    uid = get_jwt_identity()
    files = request.files.getlist('files')
    if not files or len(files) > 10:
        return jsonify(error='Upload between 1 and 10 files'), 400
    description = request.form.get('description', '')
    if len(description) > 500:
        return jsonify(error='Description exceeds 500 characters'), 400
    session = SessionLocal()
    try:
        if not session.execute(text('SELECT ConversationID FROM Conversations WHERE ConversationID=:cid AND UserID=:uid'),
                               {'cid': conversation_id, 'uid': uid}).first():
            return jsonify(error='Conversation not found'), 404
        results = []
        for file in files:
            try:
                results.append(enqueue_document(session, file, uid, conversation_id, description))
            except ValueError as exc:
                results.append({'success': False, 'filename': file.filename, 'error': str(exc)})
        return jsonify(success=any(r['success'] for r in results), conversation_id=conversation_id,
                       results=results), (202 if any(r['success'] for r in results) else 400)
    finally:
        SessionLocal.remove()


@upload_bp.route('/documents/<int:document_id>/status', methods=['GET'])
@jwt_required()
def document_status(document_id):
    session = SessionLocal()
    try:
        row = session.execute(text('''SELECT JobID AS job_id, DocumentID AS document_id,
            Status AS status, Attempts AS attempts, Error AS error FROM IngestionJobs
            WHERE DocumentID=:doc AND UserID=:uid'''),
            {'doc': document_id, 'uid': get_jwt_identity()}).mappings().first()
        return (jsonify(dict(row)), 200) if row else (jsonify(error='Document not found'), 404)
    finally:
        SessionLocal.remove()


@upload_bp.route('/documents/<int:document_id>/retry', methods=['POST'])
@jwt_required()
def retry_document(document_id):
    session = SessionLocal()
    try:
        result = session.execute(text('''UPDATE IngestionJobs SET Status='queued',Attempts=0,
            Error=NULL,NextAttemptAt=CURRENT_TIMESTAMP WHERE DocumentID=:doc AND UserID=:uid AND Status='failed' '''),
            {'doc': document_id, 'uid': get_jwt_identity()})
        session.commit()
        return (jsonify(status='queued'), 202) if result.rowcount else (jsonify(error='Failed document not found'), 404)
    finally:
        SessionLocal.remove()

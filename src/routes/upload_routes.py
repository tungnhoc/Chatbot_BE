from flask import Blueprint, request, jsonify
from src.services.document_service import upload_pdf_service1
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import SQLAlchemyError
from src.schema.uploadpdf_schema import (
    UploadPDFResponseSchema,
    UploadPDFResultSchema,
    UploadPDFSchema
)
from sqlalchemy import text
from src.config.db_session import SessionLocal

upload_bp = Blueprint('upload', __name__, url_prefix='/api')


@upload_bp.route('/upload_pdf/<int:conversation_id>', methods=['POST'])
@jwt_required()
def upload_pdf_for_conversation(conversation_id):

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'message': 'No file selected'}), 400

    user_id = get_jwt_identity()

    try:
        form_schema = UploadPDFSchema(**request.form)
        description = form_schema.description
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Invalid form data: {str(e)}"
        }), 400

    session = SessionLocal()
    results = []
    success_count = 0

    try:
        check_query = text("""
            SELECT ConversationID
            FROM Conversations
            WHERE ConversationID = :cid AND UserID = :uid
        """)
        owned = session.execute(
            check_query,
            {"cid": conversation_id, "uid": user_id}
        ).fetchone()

        if not owned:
            return jsonify({
                "success": False,
                "message": "Conversation not found or not owned by user"
            }), 404
        
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                results.append(
                    UploadPDFResultSchema(
                        success=False,
                        error=f"Invalid file: {file.filename}. Only PDF allowed."
                    ).model_dump()
                )
                continue

            upload_result = upload_pdf_service1(
                session=session,
                file=file,
                uploaded_by=user_id,
                description=description
            )

            if not upload_result.get("success"):
                results.append(
                    UploadPDFResultSchema(
                        success=False,
                        error=upload_result.get("error")
                    ).model_dump()
                )
                continue

            document_id = upload_result["document_id"]
            success_count += 1

            results.append(
                UploadPDFResultSchema(
                    success=True,
                    document_id=document_id,
                    file_url=None,
                    message=f"Uploaded: {file.filename}"
                ).model_dump()
            )

        session.commit()

    except SQLAlchemyError as e:
        session.rollback()
        return jsonify({
            "success": False,
            "message": "Database error",
            "detail": str(e)
        }), 500

    except Exception as e:
        session.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        session.close()

    response = UploadPDFResponseSchema(
        success=success_count > 0,
        conversation_id=conversation_id,
        results=results
    )

    return jsonify(response.model_dump()), (201 if success_count > 0 else 400)

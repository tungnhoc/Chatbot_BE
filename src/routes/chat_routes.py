from flask import Blueprint, request, jsonify
from src.services.chat_service import(
    handle_chat_query,
    get_conversations_list, 
    create_new_conversation,
    load_conversation_history
)
from sqlalchemy import text
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.config.db_session import SessionLocal
from src.schema.conversation_schema import (ConversationCreateSchema,
                                            ConversationListResponseSchema,
                                            ConversationResponseSchema,
                                            RenameConversationRequest,
                                            RenameConversationResponse
                                            )
from src.schema.message_schema import ConversationHistoryResponseSchema, MessageItemSchema
from src.schema.chat_schema import ChatRequestSchema, ChatResponseSchema

chat_bp = Blueprint('chat', __name__, url_prefix='/api')



@chat_bp.route('/conversations', methods=['GET'])
@jwt_required()
def get_conversations():
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'User not loggin in'}), 401

    session = SessionLocal()

    try:
        items = get_conversations_list(session, user_id)

        response_data = ConversationListResponseSchema(conversations=items)

        return jsonify(response_data.model_dump()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@chat_bp.route('/conversations/new', methods=['POST'])
@jwt_required()
def new_conversation():
    data = request.json or {}
    try:
        payload = ConversationCreateSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'User not loggin in'}), 401
    
    session = SessionLocal()
    
    try:
        conv_id = create_new_conversation(session, user_id, payload.title)

        response = ConversationResponseSchema(
            conversation_id=conv_id,
            title=payload.title,
            message="New conversation created"
        )
        return jsonify(response.model_dump()), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/conversations/<int:conv_id>/history', methods=['GET'])
@jwt_required()
def load_history_conversation(conv_id: int):

    limit = request.args.get('limit', default=20, type=int)
    offset = request.args.get('offset', default=0, type=int)

    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'User not loggin in'}), 401
    
    session = SessionLocal()

    try:
        check_query = text("""
            SELECT ConversationID
            FROM Conversations
            WHERE ConversationID = :conv_id AND UserID = :user_id
        """)

        
        result = session.execute(check_query, {'conv_id': conv_id, 'user_id': user_id}).fetchone()

        if not result:
            return jsonify({'error': 'Conversation not found or access denied'}), 404
                       
        messages = load_conversation_history(session, conv_id, offset=offset, limit=limit)
        
        if not messages:
            return jsonify({
                'conversation_id': conv_id,
                'messages': [],
                'has_more': False
            }), 200
        
        count_query = text("""
            SELECT COUNT(*) AS total
            FROM Messages
            WHERE ConversationID = :conv_id
        """)
        total_msgs = session.execute(count_query, {'conv_id': conv_id}).scalar()
        has_more = (offset + limit) < total_msgs

        response_data = ConversationHistoryResponseSchema(
            conversation_id=conv_id,
            messages=[MessageItemSchema(**m) for m in messages],
            has_more=has_more
        )

        return jsonify(response_data.model_dump()), 200

    except Exception as e:
        print(f"Lỗi khi load lịch sử chat: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/conversations/<int:conv_id>/files', methods=['GET'])
@jwt_required()
def load_conversation_files(conv_id: int):
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'User not logged in'}), 401

    session = SessionLocal()

    try:
        query = text("""
            SELECT DocumentID, FileURL, UploadedAt
            FROM ConversationDocuments
            WHERE ConversationID = :conv_id AND IsDeleted = 0
            ORDER BY UploadedAt DESC
        """)
        
        rows = session.execute(query, {'conv_id': conv_id}).mappings().all()

        files = [
            {
                'id': row['DocumentID'],
                'url': row['FileURL'],
                'uploadedAt': row['UploadedAt']
            } for row in rows
        ]

        return jsonify({'success': True, 'files': files}), 200

    except Exception as e:
        print(f"Lỗi load file: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/conversations/<int:conversation_id>', methods=['DELETE'])
@jwt_required()
def delete_conversation(conversation_id):
    user_id = get_jwt_identity()
    session = SessionLocal()

    try:
        check_query = text("""
            SELECT ConversationID FROM Conversations
            WHERE ConversationID = :conversation_id AND UserID = :user_id
        """)
        result = session.execute(check_query, {
            "conversation_id": conversation_id,
            "user_id": user_id
        }).fetchone()

        if not result:
            return jsonify({"error": "Conversation not found or not owned by user"}), 404


        delete_messages = text("""
            DELETE FROM Messages
            WHERE ConversationID = :conversation_id
        """)
        session.execute(delete_messages, {"conversation_id": conversation_id})
        delete_summary = text("""
            DELETE FROM VectorMemorySummary
            WHERE ConversationID = :conversation_id
        """)
        session.execute(delete_summary, {"conversation_id": conversation_id})

        delete_conversation = text("""
            DELETE FROM Conversations
            WHERE ConversationID = :conversation_id
        """)
        session.execute(delete_conversation, {"conversation_id": conversation_id})

        session.commit()
        return jsonify({
            "message": "Conversation deleted successfully",
            "conversation_id": conversation_id
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@chat_bp.route('/conversations/<int:conversation_id>', methods=['PUT'])
@jwt_required()
def rename_conversation(conversation_id):
    user_id = get_jwt_identity()
    try:
        data = RenameConversationRequest(**request.get_json())
    except Exception:
        return jsonify({"error": "Invalid request body"}), 400
    new_title = data.title.strip()
    if not new_title:
        return jsonify({"error": "Title cannot be empty"}), 400
    session = SessionLocal()
    try:
        check_query = text("""
            SELECT ConversationID FROM Conversations
            WHERE ConversationID = :conversation_id AND UserID = :user_id
        """)
        result = session.execute(check_query, {
            "conversation_id": conversation_id,
            "user_id": user_id
        }).fetchone()

        if not result:
            session.close()
            return jsonify({"error": "Conversation not found or not owned by user"}), 404

        # Cập nhật tên mới + updatedAt
        update_query = text("""
            UPDATE Conversations
            SET Title = :new_title,
                UpdatedAt =  NOW()
            WHERE ConversationID = :conversation_id
        """)
        session.execute(update_query, {
            "new_title": new_title,
            "conversation_id": conversation_id
        })

        session.commit()
        name_respon = RenameConversationResponse(
            message="Conversation renamed successfully",
            conversation_id=conversation_id,
            new_title=new_title
        )
        return jsonify(name_respon.model_dump()), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()



@chat_bp.route('/chat', methods=['POST'])
@jwt_required()
def chat():
    user_id = get_jwt_identity()

    if not user_id:
        return jsonify({'error': 'User not loggin in'}), 401
    
    try:
        data = ChatRequestSchema(**request.json)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
    
    session = SessionLocal()
    
    try:
        result = handle_chat_query(
            session=session,
            user_id=user_id,
            query_text=data.query_text,
            conversation_id=data.conversation_id,
            document_ids=data.document_ids,
            title=data.title
        )
        response_schema = ChatResponseSchema(
            conversation_id=result["conversation_id"],
            response=result["response"]
        )
        return jsonify(response_schema.model_dump()), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


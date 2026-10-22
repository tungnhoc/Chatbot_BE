from sqlalchemy import text
from typing import List, Dict
import json
from sqlalchemy.exc import SQLAlchemyError
from src.utils.redis import get_redis_client, get_redis_key
from src.llm.prompt_builder import generate_answer

MAX_MESSAGES_IN_REDIS = 10
KEEP_LAST_MESSAGES = 3


def save_message_to_redis_and_db(
    session, 
    user_id: str, 
    conv_id: int, 
    role: str, 
    text_message: str, 
    is_summary: bool = False
) -> Dict:
    save_message(session, conv_id, role, text_message)
    try:
        client = get_redis_client()
        key = get_redis_key(user_id, conv_id)
        client.rpush(key, json.dumps({'role': role, 'text': text_message}))
        client.ltrim(key, -10, -1)
        client.expire(key, 3600)
    except Exception:
        pass  # MySQL is the durable source of truth.
    return {'success': True}


def get_last_messages_from_redis(user_id: str, conv_id: int, count:int = 5)->List[Dict]:
    try:
        client = get_redis_client()
        redis_key = get_redis_key(user_id, conv_id)
        last_msgs_jsonn = client.lrange(redis_key, -count, -1)
        if not last_msgs_jsonn:
            print(f"No messages found in Redis for conv {conv_id}.")
            return []
        last_messages  = [json.loads(msg) for msg in last_msgs_jsonn]
        print(f"Lấy {len(last_messages )} tin cuối của conv {conv_id} từ Redis")
        return last_messages
    except Exception as e:
        print(f"⚠️ Không thể lấy tin nhắn từ Redis ({e}), trả về danh sách rỗng.")
        return []



def create_new_conversation(session, user_id: str, title: str = 'New Chat')->int:
    insert_conversation = text("""
        INSERT INTO Conversations (UserID, Title, CreatedAt, UpdatedAt)
        VALUES (:user_id, :title, NOW(), NOW())
    """)
    try:
        result = session.execute(insert_conversation,{
                                    'user_id': user_id, 
                                    'title': title
                                 })
        conv_id = result.lastrowid
        if not conv_id:
            raise ValueError("Failed to create conversation.")
        session.commit()
        return conv_id
    except SQLAlchemyError as e:
        session.rollback()
        print(f"Database error: {e}")
        raise e


def get_conversations_list(session, user_id: str, limit: int = 20)->List[Dict]:
    select_conversations_list = text("""
        SELECT ConversationID, Title
        FROM Conversations
        WHERE UserID = :user_id
        ORDER BY UpdatedAt DESC
        LIMIT :limit
    """)
    result = session.execute(select_conversations_list, {'user_id': user_id, 'limit': limit})
    rows = result.mappings().all()
    return [
        {
            "conversation_id": row["ConversationID"],
            "title": row["Title"]
        }
        for row in rows
    ]


def load_conversation_history(session, conversation_id: str, limit: int = 20, offset: int = 0) -> List[Dict]:
    query = text("""
        SELECT m.MessageID,m.Role,m.Text,m.Timestamp,t.TraceID,t.Payload
        FROM Messages m LEFT JOIN ChatTraces t ON t.AssistantMessageID=m.MessageID
        WHERE m.ConversationID = :conversation_id
        ORDER BY m.Timestamp DESC, m.MessageID DESC
        LIMIT :limit OFFSET :offset
    """)

    result = session.execute(query, {
            "conversation_id": conversation_id,
            "limit": limit,
            "offset": offset
        }).mappings().all()

    messages = []
    for row in reversed(result):
        payload = row['Payload'] or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        messages.append({'messageID': row['MessageID'], 'role': row['Role'], 'text': row['Text'],
                         'timestamp': row['Timestamp'], 'sources': payload.get('sources', []),
                         'trace_id': row['TraceID']})

    return messages



def save_message(session, conversation_id: int, role: str, text_content: str):
    insert_msg = text("""
        INSERT INTO Messages (ConversationID, Role, Text, Timestamp)
        VALUES (:conv_id, :role, :text, NOW())
    """)
    session.execute(insert_msg, {'conv_id': conversation_id, 'role': role, 'text': text_content})
    session.commit()


def get_chunks_by_ids(session, chunk_ids: List[int]):
    if not chunk_ids:
        return []

    param_keys = [f"id{i}" for i in range(len(chunk_ids))]
    in_clause = ", ".join(f":{key}" for key in param_keys)

    query = text(f"""
        SELECT ChunkID, ChunkText, Metadata
        FROM DocumentChunks
        WHERE ChunkID IN ({in_clause})
    """)

    params = {f"id{i}": chunk_ids[i] for i in range(len(chunk_ids))}

    result = session.execute(query, params)

    chunks = []
    for row in result.mappings():
        metadata = {}
        if row["Metadata"]:
            try:
                metadata = json.loads(row["Metadata"])
            except:
                metadata = {}

        chunks.append({
            "chunk_id": row["ChunkID"],
            "text": row["ChunkText"],
            "page_num": metadata.get("page"),
            "start_pos": metadata.get("start_pos")
        })

    return chunks



def get_summarys_by_ids(session, summary_ids: List[int]) -> List[str]:
    if not summary_ids:
        return []

    placeholders = ", ".join([f":id{i}" for i in range(len(summary_ids))])

    query = text(f"""
        SELECT SummaryText
        FROM VectorMemorySummary
        WHERE SummaryID IN ({placeholders})
    """)

    params = {f"id{i}": summary_ids[i] for i in range(len(summary_ids))}

    result = session.execute(query, params)

    return [row[0] for row in result.fetchall()]


def join_message_texts(messages: List[Dict]) -> str | None:
    if not messages:
        return None
    return "\n".join([m.get("text", "") for m in messages])


def is_generic_title(title_str: str) -> bool:
    if not title_str or not title_str.strip():
        return True
    lower = title_str.strip().lower()
    return lower in [
        "cuộc trò chuyện mới",
        "đoạn chat mới",
        "trò chuyện mới",
        "new chat",
        "new conversation",
        "chat",
        "untitled",
    ]


def generate_title_from_query(query_text: str) -> str:
    try:
        from src.llm.llm_client import generate_groq_response
        prompt = (
            f"Tạo một tiêu đề ngắn gọn (từ 3 đến 6 từ) phản ánh nội dung chính của câu hỏi sau: '{query_text}'. "
            f"Chỉ trả về tiêu đề (bằng cùng ngôn ngữ với câu hỏi), tuyệt đối không dùng dấu ngoặc kép hay câu dẫn nào khác."
        )
        title = generate_groq_response(prompt).strip().strip('"\'')
        if len(title) > 50:
            title = title[:47] + "..."
        return title if title else query_text[:35]
    except Exception as e:
        print("Lỗi tạo tiêu đề tự động bằng LLM:", e)
        clean = query_text.strip().replace("\n", " ")
        return clean[:35] + ("..." if len(clean) > 35 else "")


def handle_chat_query(session, user_id: str, query_text: str, conversation_id: int = None,
                      document_ids: List[int] = None, title: str = 'New Chat') -> Dict:
    import os
    import time
    import uuid
    from src.utils.pinecone_service import search_document_chunks
    from werkzeug.exceptions import NotFound, Conflict, ServiceUnavailable
    started = time.perf_counter()
    if conversation_id:
        conv = session.execute(text('SELECT Title FROM Conversations WHERE ConversationID=:cid AND UserID=:uid'),
                               {'cid': conversation_id, 'uid': user_id}).first()
        if not conv:
            raise NotFound('Conversation not found')
        title = conv[0]
    else:
        conversation_id = create_new_conversation(session, user_id, title)
    params = {'cid': conversation_id, 'uid': user_id}
    allowed = session.execute(text("""SELECT d.DocumentID,d.FileName,j.Status,j.PipelineVersion
        FROM ConversationDocuments cd JOIN Documents d ON d.DocumentID=cd.DocumentID
        LEFT JOIN IngestionJobs j ON j.DocumentID=d.DocumentID
        WHERE cd.ConversationID=:cid AND cd.IsDeleted=0 AND d.UploadedBy=:uid"""), params).mappings().all()
    by_id = {r['DocumentID']: r for r in allowed}
    selected = list(dict.fromkeys(document_ids)) if document_ids is not None else list(by_id)
    if any(doc not in by_id for doc in selected):
        raise NotFound('Document not found in this conversation')
    if document_ids and any(by_id[doc]['Status'] != 'ready' for doc in selected):
        raise Conflict('Tài liệu được chọn chưa xử lý thành công. Hãy kiểm tra trạng thái hoặc tải lại file trước khi hỏi.')
    if document_ids == [] and by_id and any(doc['Status'] != 'ready' for doc in by_id.values()):
        raise Conflict('Tài liệu trong cuộc trò chuyện chưa xử lý thành công. Chưa thể trả lời dựa trên tài liệu này.')
    if os.getenv('EMBEDDING_BACKEND') == 'gemini':
        from src.ingestion.profile import ingestion_profile
        profile = ingestion_profile()
        if any(by_id[doc]['PipelineVersion'] != profile for doc in selected):
            raise Conflict('Embedding đã thay đổi. Hãy tạo hội thoại mới và tải lại tài liệu để xử lý bằng cấu hình mới.')
    selected = [doc for doc in selected if by_id[doc]['Status'] == 'ready']
    if document_ids is None and by_id and not selected:
        raise Conflict('No ready documents in this conversation')
    retrieved = []
    if selected:
        matches = search_document_chunks(query_text, str(user_id), selected, top_k=8)
        ids = [int(m['chunk_id']) for m in matches]
        if ids:
            bindings = {f'c{i}': cid for i, cid in enumerate(ids)}
            placeholders = ','.join(':'+key for key in bindings)
            # Recheck ownership and readiness in SQL; vector metadata is not an authorization boundary.
            rows = session.execute(text(f"""SELECT c.ChunkID,c.ChunkText,c.Metadata,d.DocumentID,d.FileName
                FROM DocumentChunks c JOIN Documents d ON d.DocumentID=c.DocumentID
                JOIN IngestionJobs j ON j.DocumentID=d.DocumentID
                JOIN ConversationDocuments cd ON cd.DocumentID=d.DocumentID
                WHERE c.ChunkID IN ({placeholders}) AND d.UploadedBy=:uid
                AND cd.ConversationID=:cid AND cd.IsDeleted=0 AND j.Status='ready'"""),
                {**bindings, **params}).mappings().all()
            rows_by_id = {r['ChunkID']: r for r in rows if r['DocumentID'] in selected}
            for match in matches:
                row = rows_by_id.get(int(match['chunk_id']))
                if row:
                    metadata = row['Metadata']
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    retrieved.append({'chunk_id': row['ChunkID'], 'document_id': row['DocumentID'],
                                      'filename': row['FileName'], 'text': row['ChunkText'],
                                      'score': match['score'], **(metadata or {})})
    sources, context = [], []
    budget = 16000
    for chunk in retrieved:
        if len(chunk['text']) > budget:
            continue
        budget -= len(chunk['text'])
        source = {k: v for k, v in chunk.items() if k != 'text'}
        source['id'] = 'S' + str(len(sources) + 1)
        sources.append(source)
        context.append({'source': source, 'text': chunk['text']})
    if selected and not context:
        raise ServiceUnavailable('Không lấy được nội dung tài liệu đã chọn. Vui lòng thử lại sau; hệ thống chưa thể đọc tài liệu này.')
    history = load_conversation_history(session, conversation_id, limit=6)
    recent = '\n'.join(f"{m['role']}: {m['text']}" for m in history)
    # Retrieval failures propagate as errors, rather than producing unsupported document answers.
    answer = generate_answer(query_text, json.dumps(context, ensure_ascii=False), messages_recently=recent)
    trace_id = uuid.uuid4().hex
    payload = {'query': query_text, 'answer': answer, 'retrieved': retrieved, 'context': context,
               'sources': sources, 'latency_ms': round((time.perf_counter()-started)*1000, 2),
               'model': (os.getenv('GROQ_MODEL') or 'openai/gpt-oss-20b'),
               'pipeline_version': 'multiformat-v1', 'prompt_version': 'grounded-v2-readability'}
    from src.llm.llm_client import get_last_usage
    payload['usage'] = get_last_usage()
    payload['embedding_backend'] = os.getenv('EMBEDDING_BACKEND', 'huggingface')
    payload['vector_namespace'] = os.getenv('PINECONE_NAMESPACE', '')
    try:
        for role, body in [('user', query_text), ('assistant', answer)]:
            inserted = session.execute(text('INSERT INTO Messages (ConversationID,Role,Text) VALUES (:cid,:role,:body)'),
                            {'cid': conversation_id, 'role': role, 'body': body})
        session.execute(text('UPDATE Conversations SET UpdatedAt=CURRENT_TIMESTAMP WHERE ConversationID=:cid'), params)
        session.execute(text('INSERT INTO ChatTraces (TraceID,UserID,ConversationID,Payload,AssistantMessageID) VALUES (:id,:uid,:cid,:payload,:message_id)'),
                        {**params, 'id': trace_id, 'message_id': inserted.lastrowid, 'payload': json.dumps(payload, ensure_ascii=False)})
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {'response': answer, 'conversation_id': conversation_id, 'title': title,
            'sources': sources, 'trace_id': trace_id}

from sqlalchemy import text
from typing import List, Dict
import json
from sqlalchemy.exc import SQLAlchemyError
from src.utils.redis import get_redis_client, get_redis_key
from datetime import datetime
from src.llm.prompt_builder import summarize_conversation, generate_answer
from src.utils.pinecone_service import search_chunks, upsert_summary, search_summary
from src.utils.text_preprocess import clean_text

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
    client = get_redis_client()  
    redis_key = get_redis_key(user_id, conv_id)
    
    message = {
        'role': role,
        'text': text_message,
        'timestamp': datetime.now().isoformat()
    }
    client.rpush(redis_key, json.dumps(message))
    current_len = client.llen(redis_key)
    client.expire(redis_key, 40)

    print(f"Current messages in Redis for conv {conv_id}: {current_len}")
    
    summarized = False
    
    if current_len >= MAX_MESSAGES_IN_REDIS and not is_summary:

        all_msgs_json = client.lrange(redis_key, -MAX_MESSAGES_IN_REDIS, -1)
        all_msgs = [json.loads(m) for m in all_msgs_json]


        msgs_to_save = all_msgs[:-KEEP_LAST_MESSAGES]  
        msgs_for_summary = all_msgs  

        history_str = "\n".join([f"{m['role']}: {m['text']}" for m in msgs_for_summary])
        summary_text = summarize_conversation(history_str)  

        batch_insert = text("""
            INSERT INTO Messages (ConversationID, Role, Text, Timestamp)
            VALUES (:conv_id, :role, :text, :timestamp)
        """)

        try:
            for msg in msgs_to_save:
                session.execute(batch_insert, {
                    'conv_id': conv_id,
                    'role': msg['role'],
                    'text': msg['text'],
                    'timestamp': datetime.fromisoformat(msg['timestamp'])
                })
            session.commit()


            insert_summary = text("""
                INSERT INTO VectorMemorySummary (ConversationID, SummaryText, CreatedAt)

                VALUES (:conv_id, :summary_text, NOW())
            """)
            result_summary = session.execute(insert_summary, {
                'conv_id': conv_id, 
                'summary_text': summary_text
            })
            summary_id = result_summary.lastrowid
            session.commit()

            if not summary_id:
                raise ValueError("Failed to create memory summary.")
            
            upsert_summary(summary_text=summary_text,summary_id=summary_id,user_id=user_id, conv_id=conv_id)

            client.ltrim(redis_key, -KEEP_LAST_MESSAGES, -1)
            summarized = True
            print(f"Redis trimmed to {KEEP_LAST_MESSAGES} recent messages for conv {conv_id}")

        except Exception as e:
            session.rollback()
            print("Error saving messages or summary:", e)
        finally:
            session.close()

    return {
        "success": True,
        "message_count": current_len,
        "summarized": summarized
    }


def finalize_conversation(session, user_id: str, conv_id: int):
    client = get_redis_client()

    redis_key = get_redis_key(user_id, conv_id)

    remaining_json = client.lrange(redis_key, 0, -1)
    remaining_msgs = [json.loads(x) for x in remaining_json]

    history_str = "\n".join([f"{m['role']}: {m['text']}" for m in remaining_msgs])
    summary_text = summarize_conversation(history_str)

    try:
        batch_insert = text("""
            INSERT INTO Messages (ConversationID, Role, Text, Timestamp)
            VALUES (:conv_id, :role, :text, :timestamp)
        """)

        for msg in remaining_msgs:
            session.execute(batch_insert, {
                'conv_id': conv_id,
                'role': msg["role"],
                'text': msg["text"],
                'timestamp': datetime.fromisoformat(msg["timestamp"])
            })


        session.commit()

        insert_summary = text("""
            INSERT INTO VectorMemorySummary (ConversationID, SummaryText, CreatedAt)
            VALUES (:conv_id, :summary_text, NOW())
        """)

        result = session.execute(insert_summary, {
            "conv_id": conv_id,
            "summary_text": summary_text
        })

        summary_id = result.lastrowid
        session.commit()

        upsert_summary(summary_text, summary_id, user_id, conv_id)

        return {"success": True}

    except Exception as e:
        session.rollback()
        print(f"Error finalizing conversation {conv_id}: {e}")
        return {"success": False, "error": str(e)}




def get_last_messages_from_redis(user_id: str, conv_id: int, count:int = 5)->List[Dict]:
        client = get_redis_client()
        redis_key = get_redis_key(user_id, conv_id)
        last_msgs_jsonn = client.lrange(redis_key, -count, -1)
        if not last_msgs_jsonn:
            print(f"No messages found in Redis for conv {conv_id}.")
            return []
        last_messages  = [json.loads(msg) for msg in last_msgs_jsonn]
        print(f"Lấy {len(last_messages )} tin cuối của conv {conv_id} từ Redis")
        return last_messages



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
    finally:
        session.close()


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
        SELECT Role, Text, Timestamp
        FROM Messages
        WHERE ConversationID = :conversation_id
        ORDER BY Timestamp DESC
        LIMIT :limit OFFSET :offset
    """)

    result = session.execute(query, {
            "conversation_id": conversation_id,
            "limit": limit,
            "offset": offset
        }).mappings().all()

    messages = [
            {"role": row["Role"], "text": row["Text"], "timestamp": row["Timestamp"]}
            for row in result
        ][::-1]

    return messages



def save_message(session, conversation_id: int, role: str, text: str):
    insert_msg = text("""
        INSERT INTO Messages (ConversationID, Role, Text, Timestamp)
        VALUES (:conv_id, :role, :text, NOW())
    """)
    session.execute(insert_msg, {'conv_id': conversation_id, 'role': role, 'text': text})
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


def handle_chat_query(session, user_id: str, query_text: str, conversation_id: int = None, document_ids: List[int] = None, title: str = 'New Chat') -> Dict:
    
    if not conversation_id:
        conversation_id = create_new_conversation(session, user_id, title)
    else:
        print(f"Sử dụng ConversationID có sẵn: {conversation_id}")
    
    context = []

    if document_ids and len(document_ids) > 0:
        all_chunk_ids = []

        for doc_id in document_ids:
            filename_query = text("""
                SELECT FileName FROM Documents
                WHERE DocumentID = :doc_id AND UploadedBy = :user_id
            """)
            filename_result = session.execute(filename_query, {'doc_id': doc_id, 'user_id': user_id})
            filename_row = filename_result.fetchone()

            if not filename_row:
                print(f"Không tìm thấy document trong DB với DocumentID={doc_id}, UserID={user_id}")
                continue
            filename = filename_row[0]
            faiss_doc_name = f"{filename.replace('.pdf', '')}_{doc_id}"
            try:
                top_chunk_ids = search_chunks(query=query_text, user_id=user_id, document_id=doc_id)
                if top_chunk_ids:
                    all_chunk_ids.extend(top_chunk_ids)
                else:
                    print(f"Không tìm thấy chunk nào phù hợp trong Pipecone cho {faiss_doc_name}.")
            except Exception as e:
                print(f"Lỗi khi tìm vector trong Pipecone: {e}")
                continue

        if all_chunk_ids:
            try:
                chunks = get_chunks_by_ids(session, all_chunk_ids)
                if not chunks:
                    print("Không lấy được chunk nào từ DB.")
                else:
                    for chunk in chunks:
                        page = chunk.get('page_num', 'N/A')
                        text_snippet = chunk['text'][:300] + '...' if len(chunk['text']) > 300 else chunk['text']
                        context.append(f"[Page {page}] {text_snippet}")
                    print(" lấy được chunk nào từ DB.")
            except Exception as e:
                print(f"Lỗi khi lấy chunk từ DB: {e}")
        else:
            print("Không có chunk_id nào được tìm thấy để lấy context.")
    else:
        print("Không có document nào được cung cấp → bỏ qua phần tìm context.")
    print(" tiep tuc di.")

    summary_ids = search_summary(query=query_text, user_id=user_id, conv_id=conversation_id)

    if summary_ids:
        get_summary = get_summarys_by_ids(session, summary_ids)
    else:
        get_summary = []
    
    get_last_messages = get_last_messages_from_redis(user_id, conversation_id, count=3)
    messages_recently = join_message_texts(get_last_messages)

    print("redis ok")
    print("\nĐang gọi Grok LLM...")
    try:
        llm_response = generate_answer(
            user_query=query_text,
            retrieved_context = "\n".join(context) if context else None,
            conversation_summary="\n".join(get_summary) if get_summary else None,
            # conversation_summary=None,
            messages_recently="\n".join(messages_recently ) if messages_recently  else None
            # messages_recently= None
        )
        print("LLM trả về phản hồi thành công.")
    except Exception as e:
        print(f"Lỗi khi gọi LLM: {e}")
        llm_response = "Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi của bạn."

    print("\nĐang lưu tin nhắn vào Redis/DB...")
    try:
        save_message_to_redis_and_db(
            session=session, 
            user_id=user_id,
            conv_id=conversation_id,
            role='user',
            text_message=query_text,
            is_summary=False
        )
        save_message_to_redis_and_db(
            session=session, 
            user_id=user_id,
            conv_id=conversation_id,
            role='assistant',
            text_message=llm_response,
            is_summary=False
        )
        print("Tin nhắn đã được lưu.")
    except Exception as e:
        print(f"Lỗi khi lưu message: {e}")
    return {
        "response": llm_response,
        "conversation_id": conversation_id
    }    



    
   
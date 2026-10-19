from src.utils.pipecone_chunk_clinet import get_pipecone_chunk_index
from src.utils.pipecone_summary_clinet import get_pipecone_summary_index
from typing import List, Tuple, Dict
from src.utils.embedding_utils import get_embeddings
import os


def _namespace():
    value = os.getenv('PINECONE_NAMESPACE', '')
    if os.getenv('EMBEDDING_BACKEND') == 'local-onnx' and not value:
        raise ValueError('Use a separate PINECONE_NAMESPACE for local embeddings and re-ingest documents')
    return {'namespace': value} if value else {}


def upsert_chunks(chunk_ids: List[str], texts: List[str], user_id:str, document_id: int):
    index = get_pipecone_chunk_index()
    if len(chunk_ids) != len(texts):
        raise ValueError('Chunk/text count mismatch')
    for start in range(0, len(texts), 32):
        embeddings = get_embeddings(texts[start:start+32])
        vectors = []
        for chunk_id, embedding in zip(chunk_ids[start:start+32], embeddings):
            vectors.append({'id': f'pdf_{user_id}_{document_id}_{chunk_id}',
                'values': embedding.tolist(), 'metadata': {
                    'user_id': str(user_id), 'document_id': document_id, 'chunk_id': chunk_id}})
        index.upsert(vectors=vectors, **_namespace())
    print("Thành công upsert chunk lên Pipecone")


def search_document_chunks(query, user_id, document_ids, top_k=8):
    if not document_ids:
        return []
    response = get_pipecone_chunk_index().query(
        vector=get_embeddings(query)[0].tolist(), top_k=top_k, include_metadata=True,
        filter={'user_id': {'$eq': str(user_id)}, 'document_id': {'$in': document_ids}}, **_namespace())
    return [{'chunk_id': int(m['metadata']['chunk_id']), 'score': float(m['score'])}
            for m in response['matches']]



def search_chunks(query: str, user_id: str, document_id:int, top_k: int=3):
    index = get_pipecone_chunk_index()
    query_emb = get_embeddings(query)[0].tolist()
    filter_body = {
        "user_id": user_id,
        "document_id": document_id
    }

    response = index.query(
        vector=query_emb,
        top_k=top_k,
        include_metadata=True,
        filter=filter_body
    )
    chunk_ids = [match["metadata"]["chunk_id"] for match in response["matches"]]
    print(f"len {len(chunk_ids)} {chunk_ids}")
    return chunk_ids


def upsert_summary(summary_text:str, summary_id: str,user_id: str,conv_id: int):
    index = get_pipecone_summary_index()
    embedding = get_embeddings(summary_text)[0]
    vector = {
        "id": f"summary_{user_id}_{conv_id}_{summary_id}",
        "values": embedding.tolist(),
        "metadata": {
            "summary_id": summary_id,
            "user_id": user_id,
            "conv_id": conv_id,
        }
    }
    index.upsert([vector])
    print("Thành công upsert summary lên Pipecone")

def search_summary(query: str, user_id: str, conv_id:int, top_k: int=3):
    index = get_pipecone_summary_index()

    query_emb = get_embeddings(query)[0].tolist()

    filter_body = {
        "user_id": user_id,
        "conv_id": conv_id
    }

    response = index.query(
        vector=query_emb,
        top_k=top_k,
        include_metadata=True,
        filter=filter_body
    )
    matches = response.get("matches", [])
    if not matches: 
        print("No summary found for this conversation yet.")
        return []

    summary_ids = [m["metadata"]["summary_id"] for m in matches]

    print(f"len {len(summary_ids)} {summary_ids}")
    return summary_ids

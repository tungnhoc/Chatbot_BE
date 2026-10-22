import hashlib
import json
import os
from src.ingestion.chunker import PIPELINE_VERSION


def ingestion_profile():
    if os.getenv('EMBEDDING_BACKEND', 'huggingface') != 'gemini':
        return PIPELINE_VERSION
    from src.utils.gemini_embeddings import settings
    model, dimension = settings()
    profile = [model, dimension, os.getenv('PINECONE_NAMESPACE', ''),
               os.getenv('PIPECONE_PDF_CHUNK_INDEX', '')]
    return PIPELINE_VERSION + '-' + hashlib.sha256(json.dumps(profile).encode()).hexdigest()[:16]

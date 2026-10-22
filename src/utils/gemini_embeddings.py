"""Gemini REST embeddings: one vector per chunk; never aggregate separate chunks."""
import os
import time
import numpy as np
import requests


def settings():
    model = os.getenv('GEMINI_EMBEDDING_MODEL', 'gemini-embedding-2').removeprefix('models/')
    if model not in {'gemini-embedding-2', 'gemini-embedding-001'}:
        raise ValueError('Unsupported GEMINI_EMBEDDING_MODEL')
    dimension = int(os.getenv('GEMINI_EMBEDDING_DIMENSION', '768'))
    if dimension not in {768, 1536, 3072}:
        raise ValueError('GEMINI_EMBEDDING_DIMENSION must be 768, 1536 or 3072')
    return model, dimension


def encode(texts, task_type='RETRIEVAL_DOCUMENT'):
    model, dimension = settings()
    if not texts:
        return np.empty((0, dimension), dtype=np.float32)
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        raise ValueError('GEMINI_API_KEY is required for Gemini embeddings')
    if task_type not in {'RETRIEVAL_DOCUMENT', 'RETRIEVAL_QUERY'}:
        raise ValueError('Unsupported embedding task type')
    vectors = []
    for content in texts:
        if model == 'gemini-embedding-2':
            content = (f'task: search result | query: {content}' if task_type == 'RETRIEVAL_QUERY'
                       else f'title: none | text: {content}')
        payload = {'model': f'models/{model}', 'content': {'parts': [{'text': content}]},
                   'outputDimensionality': dimension}
        if model == 'gemini-embedding-001':
            payload['taskType'] = task_type
        for attempt in range(3):
            try:
                response = requests.post(
                    f'https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent',
                    headers={'x-goog-api-key': key}, json=payload, timeout=(10, 60))
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                response.raise_for_status()
                vector = np.asarray(response.json()['embedding']['values'], dtype=np.float32)
                if vector.shape != (dimension,) or not np.isfinite(vector).all():
                    raise ValueError('Gemini returned an invalid embedding dimension or values')
                norm = np.linalg.norm(vector)
                if not np.isfinite(norm) or norm <= 0:
                    raise ValueError('Gemini returned an invalid zero embedding')
                vectors.append(vector / norm)
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    return np.asarray(vectors, dtype=np.float32).reshape(len(texts), dimension)

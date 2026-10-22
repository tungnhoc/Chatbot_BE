import os
import time
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()
MODEL_ID = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
API_URL = f'https://router.huggingface.co/hf-inference/models/{MODEL_ID}/pipeline/feature-extraction'


def get_embeddings(texts, task_type='RETRIEVAL_DOCUMENT'):
    texts = [texts] if isinstance(texts, str) else texts
    backend = os.getenv('EMBEDDING_BACKEND', 'huggingface')
    if backend == 'gemini':
        from src.utils.gemini_embeddings import encode
        return encode(texts, task_type)
    if backend not in {'huggingface', 'local-onnx'}:
        raise ValueError('EMBEDDING_BACKEND must be huggingface, local-onnx or gemini')
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    if os.getenv('EMBEDDING_BACKEND', 'huggingface') == 'local-onnx':
        from src.utils.local_embeddings import encode
        return encode(texts)
    token = os.getenv('HF_TOKEN')
    if not token:
        raise ValueError('HF_TOKEN is required for embeddings')
    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers={'Authorization': f'Bearer {token}'},
                                     json={'inputs': texts}, timeout=(10, 60))
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                data = data.get('embeddings')
            result = np.asarray(data, dtype=np.float32)
            if result.ndim == 1 and len(texts) == 1:
                result = result.reshape(1, -1)
            if result.shape != (len(texts), 384) or not np.isfinite(result).all():
                raise ValueError('Embedding response must contain one finite 384D vector per input')
            return result
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

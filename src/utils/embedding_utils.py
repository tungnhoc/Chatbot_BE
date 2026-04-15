import numpy as np
import os
import requests
from dotenv import load_dotenv

load_dotenv()

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
API_URL = f"https://router.huggingface.co/hf-inference/models/{MODEL_ID}/pipeline/feature-extraction"

headers = {
    "Authorization": f"Bearer {os.environ['HF_TOKEN']}",
    "Content-Type": "application/json"
}

def get_embeddings(texts):
    if isinstance(texts, str):
        texts = [texts]
    payload = {"inputs": texts}

    response = requests.post(API_URL, headers=headers, json=payload)

    try:
        data = response.json()
    except:
        raise Exception(f"Invalid JSON response: {response.text}")

    if isinstance(data, dict) and "error" in data:
        raise Exception(f"HuggingFace API Error: {data['error']}")

    if "embeddings" in data:
        return np.array(data["embeddings"], dtype=np.float32)

    return np.array(data, dtype=np.float32)

# embs = get_embeddings("hello world")

# print("Embedding shape:", embs.shape)     # (1, 384)
# print("Vector dimension:", len(embs[0]))  # 384

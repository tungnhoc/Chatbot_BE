"""Optional CPU embeddings. Keep local/hosted vector populations in separate namespaces."""
import os
from functools import lru_cache
from pathlib import Path
import numpy as np

MODEL_ID = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'


@lru_cache(maxsize=1)
def resources():
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
    import onnxruntime as ort
    root = Path(os.getenv('EMBEDDING_CACHE_DIR', 'storage/models')).resolve()
    options = dict(repo_id=MODEL_ID, revision=REVISION, cache_dir=str(root), token=False)
    tokenizer = Tokenizer.from_file(hf_hub_download(filename='tokenizer.json', **options))
    tokenizer.enable_truncation(max_length=128)
    tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
    weights = hf_hub_download(filename='onnx/model_quint8_avx2.onnx', **options)
    settings = ort.SessionOptions()
    settings.intra_op_num_threads = 2
    session = ort.InferenceSession(weights, sess_options=settings, providers=['CPUExecutionProvider'])
    return tokenizer, session


def encode(texts):
    tokenizer, session = resources()
    encodings = tokenizer.encode_batch(texts)
    tokens = np.asarray([e.ids for e in encodings], dtype=np.int64)
    mask = np.asarray([e.attention_mask for e in encodings], dtype=np.int64)
    types = np.asarray([e.type_ids for e in encodings], dtype=np.int64)
    candidates = {'input_ids': tokens, 'attention_mask': mask, 'token_type_ids': types}
    outputs = session.run(None, {i.name: candidates[i.name] for i in session.get_inputs()})[0]
    if outputs.ndim == 3:
        weights = mask[:, :, None].astype(np.float32)
        vectors = (outputs * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
    else:
        vectors = outputs
    result = np.asarray(vectors, dtype=np.float32)
    if result.shape != (len(texts), 384) or not np.isfinite(result).all():
        raise ValueError('Local model returned invalid embeddings')
    return result

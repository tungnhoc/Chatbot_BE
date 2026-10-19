import re

PIPELINE_VERSION = 'multiformat-v1'


def chunk_blocks(blocks, size=1000, overlap=150):
    if not 0 <= overlap < size:
        raise ValueError('Require 0 <= overlap < size')
    chunks = []
    for block in blocks:
        text = block['text']
        # A long table row is rejected instead of silently separating its values from headers.
        if block['content_type'] == 'table':
            if len(text) > 8000:
                raise ValueError('Table row exceeds 8000 characters')
            pieces = [(0, text)]
        else:
            pieces = []
            start = 0
            while start < len(text):
                end = min(start + size, len(text))
                if end < len(text):
                    breaks = list(re.finditer(r'\n\s*\n|(?<=[.!?])\s+', text[start:end]))
                    if breaks and breaks[-1].end() > size // 2:
                        end = start + breaks[-1].end()
                pieces.append((start, text[start:end]))
                if end == len(text):
                    break
                start = max(start + 1, end - overlap)
        for start, value in pieces:
            if value.strip():
                chunks.append({'text': value.strip(), 'metadata': {
                    **block['source'], 'content_type': block['content_type'],
                    'start_pos': start, 'pipeline_version': PIPELINE_VERSION}})
    return chunks

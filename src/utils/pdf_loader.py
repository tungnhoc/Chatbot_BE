import os
from io import BytesIO
from typing import List, Dict

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

import PyPDF2


def load_pdf_text(pdf_path: str) -> List[Dict[str, any]]:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File PDF không tồn tại: {pdf_path}")
    
    pages_data = []
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    pages_data.append({'page': i + 1, 'text': text.strip()})
            return pages_data
        except Exception as e:
            print(f"⚠️ Lỗi đọc PDF bằng pdfplumber ({e}), chuyển sang PyPDF2")
            pages_data = []

    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text = page.extract_text() or ""
            pages_data.append({'page': page_num + 1, 'text': text.strip()})  
    
    return pages_data


def load_pdf_text_from_bytes(pdf_bytes: bytes) -> List[Dict[str, any]]:
    pages = []
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    pages.append({'page': i + 1, 'text': text.strip()})
            return pages
        except Exception as e:
            print(f"⚠️ Lỗi đọc PDF bằng pdfplumber ({e}), chuyển sang PyPDF2")
            pages = []

    reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({
            "page": i + 1,
            "text": text.strip()
        })

    return pages



def split_text_into_chunks(pages_data: List[Dict[str, str]], chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, any]]:
   
    chunks = []
    for page_info in pages_data:
        page_text = page_info['text']
        page_num = page_info['page']
        
        for i in range(0, len(page_text), chunk_size - overlap):
            chunk = page_text[i:i + chunk_size]
            if len(chunk.strip()) > 50: 
                chunks.append({
                    'text': chunk.strip(),
                    'page_num': page_num,
                    'start_pos': i
                })
    
    return chunks


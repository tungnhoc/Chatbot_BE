import os
import json
from datetime import datetime
from typing import List, Tuple, Dict
from werkzeug.utils import secure_filename
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from src.utils.pdf_loader import load_pdf_text, split_text_into_chunks, load_pdf_text_from_bytes
from src.utils.text_preprocess import preprocess_text
from src.utils.pinecone_service import upsert_chunks
import traceback



def save_pdf_metadata(session, uploaded_by: str, filename: str, filepath: str, filetype: str, filesize_mb: float, description: str = " " ) -> int:
    try:
        insert_pdf = text("""
            INSERT INTO Documents (FileName, FilePath, FileType, UploadedBy, UploadedAt, FileSizeMB, Description)
            VALUES (:filename, :filepath, :filetype, :uploaded_by, NOW(), :filesize_mb, :description)
        """)
        result = session.execute(insert_pdf, {
            'filename': filename,
            'filepath': filepath,
            'filetype': "PDF",  
            'uploaded_by': int(uploaded_by),
            'filesize_mb': filesize_mb,
            'description': description
        })
        document_id = result.lastrowid
        session.commit()  
        
        if not document_id:
            raise Exception("Failed to retrieve DocumentID after insertion.")
        
        return document_id
    except SQLAlchemyError as e:
        session.rollback()
        print(f"Database error: {e}")
        raise

    


def process_and_save_chunks1(session, document_id: int, pdf_bytes: bytes):
    try:
        pages_data = load_pdf_text_from_bytes(pdf_bytes)
        chunks = split_text_into_chunks(pages_data)

        chunk_ids = []
        texts = []

        for chunk in chunks:
            processed_text = preprocess_text(chunk['text'])

            metadata = json.dumps({
                "page": chunk['page_num'],
                "start_pos": chunk['start_pos']
            })

            insert_stmt = text("""
                INSERT INTO DocumentChunks (DocumentID, ChunkText, Metadata, CreatedAt)
                VALUES (:document_id, :chunk_text, :metadata, NOW())
            """)

            result = session.execute(insert_stmt, {
                "document_id": document_id,
                "chunk_text": processed_text,
                "metadata": metadata,
            })

            cid = result.lastrowid
            if cid:
                chunk_ids.append(cid)
                texts.append(processed_text)

        session.commit()
        return chunk_ids, texts

    except Exception as e:
        session.rollback()
        raise e




def upload_pdf_service1(session, file, uploaded_by: str, filename: str = None, description: str = ""):
    if not filename:
        filename = secure_filename(file.filename)

    if not filename.lower().endswith(".pdf"):
        return {"success": False, "message": "Only PDF files are allowed."}

    pdf_bytes = file.read()

    # Tính size
    file_size_mb = len(pdf_bytes) / (1024 * 1024)

    try:
        document_id = save_pdf_metadata(
            session,
            uploaded_by,
            filename,
            filepath=filename,     
            filetype="PDF",
            filesize_mb=file_size_mb,
            description=description
        )
        print("Save metadata OK")
        chunk_ids, texts = process_and_save_chunks1(session, document_id, pdf_bytes)
        print(f"Step 2: Generated {len(chunk_ids)} chunks")
        if not chunk_ids:
            raise ValueError("No chunks generated.")
        print("Step 3: Upserting to Pinecone...")
        upsert_chunks(chunk_ids, texts, user_id=uploaded_by, document_id=document_id)
        print("Step 4: Pinecone upsert OK")
        return {
            "success": True,
            "document_id": document_id,
            "message": f'PDF "{filename}" uploaded successfully with {len(chunk_ids)} chunks.'
        }

    except Exception as e:
        traceback.print_exc()   
        return {"success": False, "error": str(e)}

   



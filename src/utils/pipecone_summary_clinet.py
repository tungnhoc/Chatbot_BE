from pinecone import Pinecone
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PIPECONE_API_KEY")
INDEX_NAME = os.getenv("PIPECONE_PDF_SUMMARY_INDEX")

pc = None
index = None

def get_pipecone_summary_index():
    global pc, index
    
    if index is not None:
        return index
    
    if not API_KEY or not INDEX_NAME:
        raise ValueError("Thiếu biến môi trường PIPECONE_API_KEY hoặc PIPECONE_PDF_SUMMARY_INDEX")
    
    pc = Pinecone(api_key=API_KEY)
    index = pc.Index(INDEX_NAME)
    return index


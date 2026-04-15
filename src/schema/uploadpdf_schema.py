from pydantic import BaseModel, Field
from typing import Optional, List

class UploadPDFSchema(BaseModel):
    description: Optional[str] = Field(default="pdf")

class UploadPDFResultSchema(BaseModel):
    success: bool
    document_id: Optional[int] = None
    file_url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None

class UploadPDFResponseSchema(BaseModel):
    success: bool
    conversation_id: int
    results: List[UploadPDFResultSchema]


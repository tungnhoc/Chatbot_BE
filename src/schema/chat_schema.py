from pydantic import BaseModel, Field
from typing import List, Optional

class ChatRequestSchema(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=8000)
    conversation_id: Optional[int] = None
    document_ids: Optional[List[int]] = Field(default=None, max_length=100)
    title: str = "New chat"


class ChatResponseSchema(BaseModel):
    conversation_id: int
    response: str
    title: Optional[str] = None
    sources: List[dict] = Field(default_factory=list)
    trace_id: Optional[str] = None

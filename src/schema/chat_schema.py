from pydantic import BaseModel, Field
from typing import List, Optional

class ChatRequestSchema(BaseModel):
    query_text: str = Field(..., min_length=1)
    conversation_id: Optional[int] = None
    document_ids: List[int] = []
    title: str = "New chat"


class ChatResponseSchema(BaseModel):
    conversation_id: int
    response: str

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class MessageItemSchema(BaseModel):
    messageID: Optional[int] = None
    sources: List[dict] = Field(default_factory=list)
    trace_id: Optional[str] = None
    role: str
    text: str
    timestamp: datetime

    model_config = {
        "from_attributes": True
    }

class ConversationHistoryResponseSchema(BaseModel):
    conversation_id: int
    messages: List[MessageItemSchema]
    has_more: bool
    model_config = {
        "from_attributes": True
    }
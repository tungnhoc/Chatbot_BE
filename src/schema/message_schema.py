from pydantic import BaseModel
from datetime import datetime
from typing import List


class MessageItemSchema(BaseModel):
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
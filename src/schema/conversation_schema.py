from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class ConversationCreateSchema(BaseModel):
    title: str = Field(default="New Chat", max_length=255)


class ConversationResponseSchema(BaseModel):
    conversation_id: int
    title: str
    message: str

    model_config = {
        "from_attributes": True  
    }

class ConversationListItemSchema(BaseModel):
    conversation_id: int
    title: str

    model_config = {
        "from_attributes": True
    }


class ConversationListResponseSchema(BaseModel):
    conversations: List[ConversationListItemSchema] 


class RenameConversationRequest(BaseModel):
    title: str

class RenameConversationResponse(BaseModel):
    message: str
    conversation_id: int
    new_title: str

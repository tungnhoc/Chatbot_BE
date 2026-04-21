from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class UserRegisterSchema(BaseModel):
    username: Optional[str] = None
    email: EmailStr
    password: str = Field(min_length=6)

class UserLoginSchema(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str

class UserOutSchema(BaseModel):
    UserId: int
    Email: EmailStr
    Role: str

    model_config = {"from_attributes": True}





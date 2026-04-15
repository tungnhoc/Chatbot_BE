from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from src.config.base import Base


class Messages(Base):
    __tablename__ = "Messages"

    MessageID = Column(Integer, primary_key=True, autoincrement=True)

    ConversationID = Column(
        Integer,
        ForeignKey("Conversations.ConversationID", ondelete="CASCADE"),
        nullable=False
    )

    Role = Column(String(20))       
    Text = Column(Text)              

    Timestamp = Column(
        DateTime,
        server_default=func.now()
    )

    def save(self, session):
        session.add(self)
        session.commit()
        session.refresh(self)

    def delete(self, session):
        session.delete(self)
        session.commit()

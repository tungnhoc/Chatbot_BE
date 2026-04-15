from sqlalchemy import Column, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.sql import func
from src.config.base import Base


class VectorMemorySummary(Base):
    __tablename__ = "VectorMemorySummary"

    SummaryID = Column(Integer, primary_key=True, autoincrement=True)

    ConversationID = Column(
        Integer,
        ForeignKey("Conversations.ConversationID", ondelete="CASCADE"),
        nullable=False
    )

    SummaryText = Column(Text)        
    Embedding = Column(LONGBLOB)     

    CreatedAt = Column(
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

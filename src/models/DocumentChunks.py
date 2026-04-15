from sqlalchemy import Column, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.sql import func
from src.config.base import Base


class DocumentChunks(Base):
    __tablename__ = "DocumentChunks"

    ChunkID = Column(Integer, primary_key=True, autoincrement=True)

    DocumentID = Column(
        Integer,
        ForeignKey("Documents.DocumentID", ondelete="CASCADE"),
        nullable=False
    )

    ChunkText = Column(Text)         
    Embedding = Column(LONGBLOB)     
    Metadata = Column(Text)          
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

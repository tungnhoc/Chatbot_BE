from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from src.config.base import Base


class Conversations(Base):
    __tablename__ = "Conversations"

    ConversationID = Column(Integer, primary_key=True, autoincrement=True)

    UserID = Column(
        Integer,
        ForeignKey("Users.UserID", ondelete="CASCADE"),
        nullable=False
    )

    Title = Column(String(255))
    Summary = Column(String)  

    CreatedAt = Column(
        DateTime,
        server_default=func.now()
    )

    UpdatedAt = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    def save(self, session):
        session.add(self)
        session.commit()
        session.refresh(self)

    def delete(self, session):
        session.delete(self)
        session.commit()

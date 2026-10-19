from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from src.config.base import Base
from werkzeug.security import generate_password_hash, check_password_hash


class User(Base):
    __tablename__ = "Users"

    UserID = Column(Integer, primary_key=True, autoincrement=True)

    UserName = Column(String(100), nullable=False)
    Email = Column(String(255), unique=True)
    PasswordHash = Column(String(255))

    CreatedAt = Column(
        DateTime,
        server_default=func.now()
    )

    Role = Column(
        String(20),
        nullable=False,
        server_default="user"
    )

    def __repr__(self):
        return f"<User(UserName={self.UserName}, Email={self.Email})>"

    def set_password(self, password):
        self.PasswordHash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.PasswordHash, password)

    @classmethod
    def get_by_emails(cls, session, email):
        return session.query(cls).filter_by(Email=email).first()

    def save(self, session):
        session.add(self)
        session.commit()
        session.refresh(self)

    def delete(self, session):
        session.delete(self)
        session.commit()

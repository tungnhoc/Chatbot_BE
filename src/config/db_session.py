from sqlalchemy.orm import scoped_session, sessionmaker
from src.config.database import get_database_engine

engine = get_database_engine()

SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

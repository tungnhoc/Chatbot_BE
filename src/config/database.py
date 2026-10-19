import os
from functools import lru_cache
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()


@lru_cache(maxsize=1)
def get_database_engine():
    url = os.getenv('DATABASE_URL') or URL.create(
        'mysql+pymysql', username=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'), host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT', '3306')), database=os.getenv('MYSQL_DB'))
    return create_engine(url, pool_pre_ping=True, echo=False)

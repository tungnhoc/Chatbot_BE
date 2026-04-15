# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

def get_database_engine():
    try:
        server = os.getenv("MYSQL_HOST")
        port =  os.getenv("MYSQL_PORT", "3306")
        database = os.getenv("MYSQL_DB")
        username = os.getenv("MYSQL_USER")
        password = os.getenv("MYSQL_PASSWORD")

        connection_url = (
            f"mysql+pymysql://{username}:{password}@{server}:{port}/{database}"
        )

        engine = create_engine(
            connection_url,
            pool_pre_ping=True,
            echo=True  
        )

        print("Kết nối MySQL Railway thành công")
        return engine

    except Exception as e:
        print(f"❌ Lỗi kết nối MySQL: {e}")
        return None

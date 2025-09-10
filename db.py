import pymysql
import os

def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", "root"),
        database=os.getenv("DB_NAME", "12306_ticket"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )

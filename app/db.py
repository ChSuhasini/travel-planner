import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    # Use SSL only in production (when SSL_MODE env var is set)
    ssl_mode = os.getenv("SSL_MODE", "disable")
    
    connection = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT"),
        sslmode=ssl_mode
    )
    return connection
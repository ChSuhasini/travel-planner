import pytest
from fastapi.testclient import TestClient
from app.main import app
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_test_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def clean_db():
    yield
    conn = get_test_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM trips")
    conn.commit()
    cur.close()
    conn.close()
import os
import psycopg2
import psycopg2.extras

# Used only when running locally on your laptop (no DATABASE_URL set)
LOCAL_DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "admin123",
    "dbname": "civic_app"
}


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Running on Render (or anywhere DATABASE_URL is set)
        return psycopg2.connect(database_url)
    else:
        # Running locally on your laptop
        return psycopg2.connect(**LOCAL_DB_CONFIG)
import psycopg2
import psycopg2.extras

# EDIT THESE to match your own PostgreSQL setup
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "admin123",   # <-- put your PostgreSQL password here
    "dbname": "civic_app"      # <-- create this database first in pgAdmin
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)

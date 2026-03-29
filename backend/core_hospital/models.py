from pathlib import Path
from sqlalchemy import MetaData
from database import engine

SCHEMA_PATH = Path(__file__).with_name("multi_hospital_schema.sql")
metadata = MetaData()


def apply_schema() -> None:
    """Apply SQL schema script so all required tables exist."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    raw_conn = engine.raw_connection()
    try:
        raw_conn.executescript(sql)
        raw_conn.commit()
    finally:
        raw_conn.close()


def load_tables() -> MetaData:
    """Apply schema and reflect current database tables."""
    apply_schema()
    metadata.clear()
    metadata.reflect(bind=engine)
    return metadata


# Eagerly load so main.py can use TABLES immediately.
load_tables()
TABLES = metadata.tables

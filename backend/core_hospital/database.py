from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use a dedicated DB file for the multi-hospital schema so legacy tables
# in hospital.db do not conflict with new tenant-aware columns.
SQLALCHEMY_DATABASE_URL = "sqlite:///./hospital_multi.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

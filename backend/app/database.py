"""
database.py — SQLAlchemy engine and session factory.
Uses DATABASE_URL env var (defaults to SQLite file) so switching to Postgres
is a one-line .env change.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Decision: default to SQLite for zero-setup demos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stockpulse.db")

# SQLite needs check_same_thread=False for FastAPI's threaded usage
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

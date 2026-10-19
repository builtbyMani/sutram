"""SQLite engine in WAL mode (locked per STACK.md: sync SQLAlchemy 2.0, single-user demo)."""

import os
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .models import Base

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "forensics.db"))

DATA_DIR.mkdir(parents=True, exist_ok=True)

# quote() the path so Windows-style or space-containing paths stay valid in the URL
engine = create_engine(
    f"sqlite:///{quote(str(DB_PATH))}",
    connect_args={"check_same_thread": False},
)

with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL;"))
    conn.commit()

Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

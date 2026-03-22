from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select, text
import os
from pathlib import Path

# Database path
DB_DIR = Path("data")
DB_PATH = DB_DIR / "media_archivist.db"

class MediaFile(SQLModel, table=True):
    abs_path: str = Field(primary_key=True)
    file_size: int
    sha256_hash: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="pending")  # pending/hashing/completed

# SQLite engine with WAL mode
sqlite_url = f"sqlite:///{DB_PATH}"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def init_db():
    if not DB_DIR.exists():
        DB_DIR.mkdir(parents=True)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.exec(text("PRAGMA journal_mode=WAL;"))
        session.commit()

def get_session():
    with Session(engine) as session:
        yield session

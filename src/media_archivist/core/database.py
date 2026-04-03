from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select, text
import os
from pathlib import Path
from datetime import datetime

# Database path
DB_DIR = Path("data")
DB_PATH = DB_DIR / "media_archivist.db"

class MediaFile(SQLModel, table=True):
    abs_path: str = Field(primary_key=True)
    file_size: int
    sha256_hash: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="pending")  # pending/hashing/completed/error
    discovery_task_id: Optional[int] = Field(default=None, index=True)

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str  # e.g., "Scan /home/user", "Hash Session #123"
    task_type: str  # scan, hash, cleanup, archive
    status: str = Field(default="running")  # running, completed, failed
    progress: float = Field(default=0.0)    # 0.0 to 100.0
    total_items: int = Field(default=0)
    completed_items: int = Field(default=0)
    message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# SQLite engine with WAL mode
sqlite_url = f"sqlite:///{DB_PATH}"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def init_db():
    if not DB_DIR.exists():
        DB_DIR.mkdir(parents=True)
    
    SQLModel.metadata.create_all(engine)
    
    # Handle migrations for existing DBs
    with Session(engine) as session:
        session.exec(text("PRAGMA journal_mode=WAL;"))
        
        # Add discovery_task_id to MediaFile if missing
        try:
            session.exec(text("ALTER TABLE mediafile ADD COLUMN discovery_task_id INTEGER"))
        except Exception:
            pass # Column already exists
            
        # Add new columns to Task if missing
        new_task_cols = [
            ("task_type", "TEXT"),
            ("total_items", "INTEGER DEFAULT 0"),
            ("completed_items", "INTEGER DEFAULT 0"),
            ("created_at", "DATETIME")
        ]
        for col_name, col_type in new_task_cols:
            try:
                session.exec(text(f"ALTER TABLE task ADD COLUMN {col_name} {col_type}"))
            except Exception:
                pass
                
        session.commit()

def get_session():
    with Session(engine) as session:
        yield session

def update_task_progress(task_id: int, progress: float, completed: int, total: int, message: str = None, status: str = "running"):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if task:
            task.progress = progress
            task.completed_items = completed
            task.total_items = total
            task.message = message
            task.status = status
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()

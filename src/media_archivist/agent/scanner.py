import os
from pathlib import Path
from sqlmodel import Session, select
from media_archivist.core.database import engine, MediaFile, Task
import asyncio
from typing import Optional
from datetime import datetime

async def scan_directory(dir_path: str, task_id: Optional[int] = None):
    """
    Scans the given directory and its subdirectories for files.
    Inserts or updates each file path and its size into the database with 'pending' status.
    """
    p = Path(dir_path)
    if not p.is_dir():
        print(f"Error: {dir_path} is not a directory.")
        return

    # Count files first for progress
    file_list = []
    for root, _, files in os.walk(dir_path):
        for name in files:
            file_list.append(os.path.abspath(os.path.join(root, name)))
    
    total = len(file_list)
    if task_id:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.total_items = total
                session.add(task)
                session.commit()

    for idx, file_path in enumerate(file_list):
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            continue

        with Session(engine) as session:
            statement = select(MediaFile).where(MediaFile.abs_path == file_path)
            existing_file = session.exec(statement).first()
            
            if existing_file:
                if existing_file.file_size != file_size:
                    existing_file.file_size = file_size
                    existing_file.status = "pending"
                existing_file.discovery_task_id = task_id
                session.add(existing_file)
            else:
                new_file = MediaFile(
                    abs_path=file_path, 
                    file_size=file_size, 
                    status="pending",
                    discovery_task_id=task_id
                )
                session.add(new_file)
            
            if task_id and (idx % 10 == 0 or idx == total - 1):
                task = session.get(Task, task_id)
                if task:
                    task.completed_items = idx + 1
                    task.progress = ((idx + 1) / total) * 100 if total > 0 else 100
                    task.message = f"Scanned {idx + 1}/{total} files"
                    task.updated_at = datetime.utcnow()
                    session.add(task)
            
            session.commit()
    
    if task_id:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                task.status = "completed"
                task.progress = 100.0
                task.updated_at = datetime.utcnow()
                session.add(task)
                session.commit()

    print(f"Finished scanning {dir_path}")

import os
from pathlib import Path
from sqlmodel import Session, select
from media_archivist.core.database import engine, MediaFile
import asyncio

async def scan_directory(dir_path: str):
    """
    Scans the given directory and its subdirectories for files.
    Inserts or updates each file path and its size into the database with 'pending' status.
    """
    p = Path(dir_path)
    if not p.is_dir():
        print(f"Error: {dir_path} is not a directory.")
        return

    # Using standard os.walk as it's generally fast for local file systems
    # For large directories, this can be optimized with more sophisticated methods.
    for root, dirs, files in os.walk(dir_path):
        for name in files:
            file_path = os.path.abspath(os.path.join(root, name))
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                continue

            with Session(engine) as session:
                # Check if file already exists in DB
                statement = select(MediaFile).where(MediaFile.abs_path == file_path)
                existing_file = session.exec(statement).first()
                
                if existing_file:
                    # Update size if it changed
                    if existing_file.file_size != file_size:
                        existing_file.file_size = file_size
                        existing_file.status = "pending"
                        session.add(existing_file)
                else:
                    # New file
                    new_file = MediaFile(abs_path=file_path, file_size=file_size, status="pending")
                    session.add(new_file)
                
                session.commit()
    print(f"Finished scanning {dir_path}")

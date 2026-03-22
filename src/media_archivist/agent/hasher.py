import hashlib
import asyncio
from sqlmodel import Session, select, func
from media_archivist.core.database import engine, MediaFile, Task
from datetime import datetime

def update_task_progress(name: str, progress: float, message: str = None, status: str = "running"):
    with Session(engine) as session:
        statement = select(Task).where(Task.name == name)
        task = session.exec(statement).first()
        if not task:
            task = Task(name=name)
        task.progress = progress
        task.message = message
        task.status = status
        task.updated_at = datetime.utcnow()
        session.add(task)
        session.commit()

def calculate_sha256(file_path: str):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None

async def hash_pending_files():
    """Finds files with 'pending' status and calculates their SHA-256 hash."""
    print("Background Hasher Agent started.")
    while True:
        with Session(engine) as session:
            # Calculate total progress
            total = session.exec(select(func.count(MediaFile.abs_path))).one()
            done = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "completed")).one()
            
            if total > 0:
                progress = (done / total) * 100
                update_task_progress("hashing", progress, f"Processed {done}/{total} files.")

            statement = select(MediaFile).where(MediaFile.status == "pending").limit(10)
            pending_files = session.exec(statement).all()
            
            if not pending_files:
                if total > 0 and done == total:
                    update_task_progress("hashing", 100.0, "All files hashed.", "completed")
                await asyncio.sleep(5)
                continue

            for media_file in pending_files:
                media_file.status = "hashing"
                session.add(media_file)
                session.commit()

                loop = asyncio.get_running_loop()
                file_hash = await loop.run_in_executor(None, calculate_sha256, media_file.abs_path)
                
                if file_hash:
                    media_file.sha256_hash = file_hash
                    media_file.status = "completed"
                    print(f"  [HASHED] {media_file.abs_path}")
                else:
                    media_file.status = "error"
                
                session.add(media_file)
                session.commit()
        
        await asyncio.sleep(0.1)

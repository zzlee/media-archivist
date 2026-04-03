import hashlib
import asyncio
import os
from sqlmodel import Session, select, func
from media_archivist.core.database import engine, MediaFile, Task, update_task_progress
from datetime import datetime
from typing import Optional

def calculate_sha256(file_path: str):
    sha256_hash = hashlib.sha256()
    try:
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None

async def hash_pending_files(task_id: int, discovery_task_id: Optional[int] = None):
    """Finds files with 'pending' status and calculates their SHA-256 hash."""
    print(f"Background Hasher Agent started (Task {task_id}).")
    while True:
        with Session(engine) as session:
            # Base filters
            stmt_total = select(func.count(MediaFile.abs_path)).where(MediaFile.status != "error")
            stmt_done = select(func.count(MediaFile.abs_path)).where(MediaFile.status == "completed")
            
            if discovery_task_id:
                stmt_total = stmt_total.where(MediaFile.discovery_task_id == discovery_task_id)
                stmt_done = stmt_done.where(MediaFile.discovery_task_id == discovery_task_id)
            
            total = session.exec(stmt_total).one()
            done = session.exec(stmt_done).one()
            
            if total > 0:
                progress = (done / total) * 100
                update_task_progress(task_id, progress, done, total, f"Processed {done}/{total} files.")

            # Get next batch
            stmt_pending = select(MediaFile).where(MediaFile.status == "pending").limit(10)
            if discovery_task_id:
                stmt_pending = stmt_pending.where(MediaFile.discovery_task_id == discovery_task_id)
            
            pending_files = session.exec(stmt_pending).all()
            
            if not pending_files:
                if total > 0 and done >= total:
                    update_task_progress(task_id, 100.0, done, total, "All files hashed.", "completed")
                    break # Finish this hashing session
                await asyncio.sleep(2)
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
                else:
                    media_file.status = "error"
                
                session.add(media_file)
                session.commit()
        
        await asyncio.sleep(0.1)

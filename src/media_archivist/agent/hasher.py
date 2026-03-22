import hashlib
import asyncio
from sqlmodel import Session, select
from media_archivist.core.database import engine, MediaFile

def calculate_sha256(file_path: str):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # Read in chunks for memory efficiency
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None

async def hash_pending_files():
    """
    Finds files with 'pending' status and calculates their SHA-256 hash.
    """
    while True:
        with Session(engine) as session:
            statement = select(MediaFile).where(MediaFile.status == "pending").limit(10)
            pending_files = session.exec(statement).all()
            
            if not pending_files:
                print("No pending files to hash. Waiting...")
                await asyncio.sleep(5)
                continue

            for media_file in pending_files:
                # Update status to 'hashing'
                media_file.status = "hashing"
                session.add(media_file)
                session.commit()

                # Calculate hash
                # Using run_in_executor to avoid blocking the event loop for CPU-bound task
                loop = asyncio.get_running_loop()
                file_hash = await loop.run_in_executor(None, calculate_sha256, media_file.abs_path)
                
                if file_hash:
                    media_file.sha256_hash = file_hash
                    media_file.status = "completed"
                else:
                    media_file.status = "error" # Handle errors gracefully
                
                session.add(media_file)
                session.commit()
                print(f"Calculated hash for: {media_file.abs_path}")
        
        await asyncio.sleep(0.1) # Brief pause between batches

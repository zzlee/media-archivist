import typer
import asyncio
import uvicorn
import os
import shutil
from datetime import datetime
from typing import List, Optional
from media_archivist.core.database import init_db, engine, MediaFile, Task
from media_archivist.agent.scanner import scan_directory
from media_archivist.agent.hasher import hash_pending_files
from sqlmodel import Session, select, func, col

app = typer.Typer(help="MediaArchivist: Efficient media management tool.")

def update_task_progress(name: str, progress: float, message: str = None, status: str = "running"):
    """Update progress for a specific task in the database."""
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

def reset_stuck_hashing():
    with Session(engine) as session:
        statement = select(MediaFile).where(MediaFile.status == "hashing")
        stuck_files = session.exec(statement).all()
        if stuck_files:
            print(f"Found {len(stuck_files)} interrupted tasks. Resuming...")
            for f in stuck_files:
                f.status = "pending"
                session.add(f)
            session.commit()

@app.command()
def start(directories: Optional[List[str]] = typer.Argument(None, help="Directories to scan.")):
    """Start scanning and background hashing."""
    init_db()
    reset_stuck_hashing()
    
    async def run_agent():
        tasks = []
        if directories:
            print(f"Scanning directories: {', '.join(directories)}...")
            tasks.extend([scan_directory(d) for d in directories])
        
        # We don't track scan_directory yet, as it's usually fast
        tasks.append(hash_pending_files())
        await asyncio.gather(*tasks)
    
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        update_task_progress("hashing", 0.0, "Interrupted by user", "failed")
        print("\nStopping MediaArchivist agent...")

@app.command()
def cleanup(
    no_dry_run: bool = typer.Option(False, "--no-dry-run", help="Actually delete files."),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion.")
):
    """Automatically delete duplicates, keeping the version with the shortest path."""
    init_db()
    is_dry_run = not no_dry_run
    
    if is_dry_run:
        print("--- PREVIEW MODE (DRY RUN) ---")
    else:
        print("--- ACTUAL DELETION MODE ---")
        update_task_progress("cleanup", 0.0, "Starting cleanup...")

    with Session(engine) as session:
        statement = (
            select(MediaFile.sha256_hash)
            .where(MediaFile.status == "completed")
            .group_by(MediaFile.sha256_hash)
            .having(func.count(MediaFile.abs_path) > 1)
        )
        duplicate_hashes = session.exec(statement).all()
        
        if not duplicate_hashes:
            print("No duplicates found.")
            if not is_dry_run: update_task_progress("cleanup", 100.0, "No duplicates found.", "completed")
            return

        total_hashes = len(duplicate_hashes)
        for idx, h in enumerate(duplicate_hashes):
            files = session.exec(select(MediaFile).where(MediaFile.sha256_hash == h)).all()
            files.sort(key=lambda x: len(x.abs_path))
            delete_files = files[1:]
            
            for df in delete_files:
                if not is_dry_run:
                    if not force:
                        confirm = typer.confirm(f"Delete {df.abs_path}?")
                        if not confirm: continue
                    try:
                        if os.path.exists(df.abs_path): os.remove(df.abs_path)
                        session.delete(df)
                    except Exception as e: print(f"Error: {e}")
            
            if not is_dry_run:
                progress = (idx + 1) / total_hashes * 100
                update_task_progress("cleanup", progress, f"Processed {idx+1}/{total_hashes} groups.")
            
            session.commit()

        if not is_dry_run:
            update_task_progress("cleanup", 100.0, "Cleanup completed successfully.", "completed")

@app.command()
def archive(
    target_dir: str = typer.Argument(..., help="Target directory."),
    no_dry_run: bool = typer.Option(False, "--no-dry-run", help="Actually move files."),
):
    """Move and organize unique files into target_dir/YYYY/MM/DD structure."""
    init_db()
    target_path = os.path.abspath(target_dir)
    is_dry_run = not no_dry_run

    if not is_dry_run:
        update_task_progress("archive", 0.0, f"Starting archive to {target_path}...")
        if not os.path.exists(target_path): os.makedirs(target_path)

    with Session(engine) as session:
        all_files = session.exec(select(MediaFile).where(MediaFile.status == "completed")).all()
        if not all_files:
            print("No files to archive.")
            if not is_dry_run: update_task_progress("archive", 100.0, "No files found.", "completed")
            return

        total_files = len(all_files)
        for idx, mf in enumerate(all_files):
            if not os.path.exists(mf.abs_path): continue
            
            dt = datetime.fromtimestamp(os.path.getmtime(mf.abs_path))
            dest_dir = os.path.join(target_path, dt.strftime("%Y/%m/%d"))
            filename = os.path.basename(mf.abs_path)
            intended_path = os.path.join(dest_dir, filename)
            
            if mf.abs_path == intended_path: continue
            
            final_dest = intended_path
            name, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(final_dest):
                final_dest = os.path.join(dest_dir, f"{name}_{counter}{ext}")
                counter += 1

            if not is_dry_run:
                try:
                    if not os.path.exists(dest_dir): os.makedirs(dest_dir, exist_ok=True)
                    shutil.move(mf.abs_path, final_dest)
                    old_mf_data = mf.model_dump()
                    session.delete(mf)
                    session.commit()
                    old_mf_data['abs_path'] = final_dest
                    new_mf = MediaFile(**old_mf_data)
                    session.add(new_mf)
                    session.commit()
                    progress = (idx + 1) / total_files * 100
                    update_task_progress("archive", progress, f"Moved {idx+1}/{total_files} files.")
                except Exception as e: print(f"Error: {e}")
            else:
                print(f" [MOVE] {mf.abs_path} -> {final_dest}")

        if not is_dry_run:
            update_task_progress("archive", 100.0, "Archive completed successfully.", "completed")

@app.command()
def doctor(no_dry_run: bool = typer.Option(False, "--no-dry-run")):
    """Health check."""
    init_db()
    with Session(engine) as session:
        all_records = session.exec(select(MediaFile)).all()
        for record in all_records:
            if not os.path.exists(record.abs_path):
                if not no_dry_run: print(f"[DRY] Orphaned: {record.abs_path}")
                else: session.delete(record)
        session.commit()

@app.command()
def list_files(status: Optional[str] = None, limit: int = 100):
    """List paths."""
    init_db()
    with Session(engine) as session:
        results = session.exec(select(MediaFile).limit(limit)).all()
        for f in results: print(f"{f.status:<12} | {f.abs_path}")

@app.command()
def web(host: str = "0.0.0.0", port: int = 8000):
    """Start the Web API and Dashboard."""
    init_db()
    uvicorn.run("media_archivist.web.app:app", host=host, port=port, reload=True)

@app.command()
def status():
    """Check current processing status."""
    init_db()
    with Session(engine) as session:
        total = session.exec(select(func.count(MediaFile.abs_path))).one()
        done = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "completed")).one()
        print(f"Total files: {total}")
        print(f"Completed: {done}")
        tasks = session.exec(select(Task)).all()
        for t in tasks:
            print(f"Task {t.name}: {t.status} ({t.progress:.1f}%) - {t.message}")

if __name__ == "__main__":
    app()

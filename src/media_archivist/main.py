import typer
import asyncio
import uvicorn
import os
from typing import List, Optional
from media_archivist.core.database import init_db, engine, MediaFile
from media_archivist.agent.scanner import scan_directory
from media_archivist.agent.hasher import hash_pending_files
from sqlmodel import Session, select, func

app = typer.Typer(help="MediaArchivist: Efficient media management tool.")

@app.command()
def start(directories: List[str] = typer.Argument(..., help="List of directories to scan")):
    """
    Start scanning one or more directories and background hashing.
    """
    print(f"Starting MediaArchivist for: {', '.join(directories)}...")
    init_db()
    
    async def run_agent():
        scan_tasks = [scan_directory(d) for d in directories]
        await asyncio.gather(
            *scan_tasks,
            hash_pending_files()
        )
    
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\nStopping MediaArchivist agent...")

@app.command()
def cleanup(
    dry_run: bool = typer.Option(True, "--no-dry-run", help="Actually delete files. Default is dry-run."),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation.")
):
    """
    Automatically delete duplicates, keeping the version with the shortest path.
    """
    init_db()
    if dry_run:
        print("--- DRY RUN MODE (No files will be deleted) ---")
    
    with Session(engine) as session:
        # Find hashes with more than 1 occurrence
        statement = (
            select(MediaFile.sha256_hash)
            .where(MediaFile.status == "completed")
            .group_by(MediaFile.sha256_hash)
            .having(func.count(MediaFile.abs_path) > 1)
        )
        duplicate_hashes = session.exec(statement).all()
        
        if not duplicate_hashes:
            print("No duplicates found.")
            return

        total_to_delete = 0
        total_saved_space = 0

        for h in duplicate_hashes:
            files_statement = select(MediaFile).where(MediaFile.sha256_hash == h)
            files = session.exec(files_statement).all()
            
            # Rule: Keep the one with the shortest path length
            files.sort(key=lambda x: len(x.abs_path))
            keep_file = files[0]
            delete_files = files[1:]
            
            print(f"\nGroup: {h}")
            print(f"  [KEEP] {keep_file.abs_path}")
            
            for df in delete_files:
                print(f"  [DELETE] {df.abs_path} ({df.file_size} bytes)")
                total_to_delete += 1
                total_saved_space += df.file_size
                
                if not dry_run:
                    if not force:
                        confirm = typer.confirm(f"Delete {df.abs_path}?")
                        if not confirm:
                            continue
                    
                    try:
                        os.remove(df.abs_path)
                        session.delete(df)
                        print(f"    - Deleted.")
                    except Exception as e:
                        print(f"    - Error deleting {df.abs_path}: {e}")
            
            session.commit()

        print(f"\nSummary:")
        print(f"  Total files to delete: {total_to_delete}")
        print(f"  Estimated space to save: {total_saved_space / (1024*1024):.2f} MB")
        
        if dry_run:
            print("\nTo actually delete these files, run: sudo uv run archivist cleanup --no-dry-run")

@app.command()
def web(host: str = "0.0.0.0", port: int = 8000):
    """
    Start the Web API and Dashboard.
    """
    print(f"Starting Web UI at http://{host}:{port}...")
    init_db()
    uvicorn.run("media_archivist.web.app:app", host=host, port=port, reload=True)

@app.command()
def status():
    """
    Check current processing status.
    """
    init_db()
    with Session(engine) as session:
        total_files = session.exec(select(func.count(MediaFile.abs_path))).one()
        pending_count = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "pending")).one()
        hashing_count = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "hashing")).one()
        completed_count = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "completed")).one()
        error_count = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "error")).one()

        print(f"Total files: {total_files}")
        print(f"Pending: {pending_count}")
        print(f"Hashing: {hashing_count}")
        print(f"Completed: {completed_count}")
        print(f"Error: {error_count}")

if __name__ == "__main__":
    app()

import typer
import asyncio
import uvicorn
from typing import List
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
        # Create scan tasks for all provided directories
        scan_tasks = [scan_directory(d) for d in directories]
        
        # Run all scans and the continuous hasher concurrently
        await asyncio.gather(
            *scan_tasks,
            hash_pending_files()
        )
    
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\nStopping MediaArchivist agent...")

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

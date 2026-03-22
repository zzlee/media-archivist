import typer
import asyncio
import uvicorn
import os
import shutil
from datetime import datetime
from typing import List, Optional
from media_archivist.core.database import init_db, engine, MediaFile
from media_archivist.agent.scanner import scan_directory
from media_archivist.agent.hasher import hash_pending_files
from sqlmodel import Session, select, func, col

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
def list_files(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status: pending, hashing, completed, error"),
    path: Optional[str] = typer.Option(None, "--path", help="Only show paths containing this string"),
    exclude: Optional[str] = typer.Option(None, "--exclude", help="Exclude paths containing this string"),
    limit: int = typer.Option(100, "--limit", help="Limit the number of files shown. Use 0 for all.")
):
    """
    List paths currently managed in the database with powerful filtering.
    """
    init_db()
    with Session(engine) as session:
        statement = select(MediaFile)
        if status: statement = statement.where(MediaFile.status == status)
        if path: statement = statement.where(col(MediaFile.abs_path).contains(path))
        if exclude: statement = statement.where(col(MediaFile.abs_path).not_like(f"%{exclude}%"))
        if limit > 0: statement = statement.limit(limit)
        results = session.exec(statement).all()
        if not results:
            print("No files found matching the criteria.")
            return
        print(f"{'Status':<12} | {'Path'}")
        print("-" * 50)
        for f in results:
            print(f"{f.status:<12} | {f.abs_path}")
        if limit > 0:
            count_statement = select(func.count(MediaFile.abs_path))
            if status: count_statement = count_statement.where(MediaFile.status == status)
            if path: count_statement = count_statement.where(col(MediaFile.abs_path).contains(path))
            if exclude: count_statement = count_statement.where(col(MediaFile.abs_path).not_like(f"%{exclude}%"))
            total_matches = session.exec(count_statement).one()
            if total_matches > limit:
                print(f"\n... and {total_matches - limit} more matching files. Use --limit 0 to see all.")

@app.command()
def doctor(
    no_dry_run: bool = typer.Option(False, "--no-dry-run", help="Actually remove orphaned records. Default is preview."),
):
    """
    Health check: Find orphaned records and reset stuck hashing tasks.
    """
    init_db()
    is_dry_run = not no_dry_run
    if is_dry_run:
        print("--- DOCTOR PREVIEW MODE (DRY RUN) ---")
    else:
        print("--- DOCTOR REPAIR MODE ---")

    with Session(engine) as session:
        statement = select(MediaFile)
        all_records = session.exec(statement).all()
        if not all_records:
            print("Database is empty.")
            return

        orphaned_count = 0
        stuck_count = 0
        
        for record in all_records:
            # 1. Check for orphaned records (File missing on disk)
            if not os.path.exists(record.abs_path):
                print(f"  [ORPHANED] {record.abs_path}")
                orphaned_count += 1
                if not is_dry_run:
                    session.delete(record)
            
            # 2. Check for stuck 'hashing' status
            elif record.status == "hashing":
                print(f"  [STUCK] {record.abs_path} (Resetting to pending)")
                stuck_count += 1
                if not is_dry_run:
                    record.status = "pending"
                    session.add(record)
        
        if not is_dry_run:
            session.commit()
            print(f"\nSummary: Removed {orphaned_count} orphans, Reset {stuck_count} stuck tasks.")
        else:
            print(f"\nSummary: Found {orphaned_count} orphans and {stuck_count} stuck tasks to fix.")
            if orphaned_count > 0 or stuck_count > 0:
                print(f"To repair, run: sudo .venv/bin/archivist doctor --no-dry-run")

@app.command()
def cleanup(
    no_dry_run: bool = typer.Option(False, "--no-dry-run", help="Actually delete files. If not set, only a preview is shown."),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation.")
):
...
if __name__ == "__main__":
    app()

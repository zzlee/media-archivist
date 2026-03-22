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
    Health check: Find and remove database records for files that no longer exist on disk.
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
        for record in all_records:
            if not os.path.exists(record.abs_path):
                print(f"  [ORPHANED] {record.abs_path}")
                orphaned_count += 1
                if not is_dry_run:
                    session.delete(record)
        if not is_dry_run:
            session.commit()
            print(f"\nSuccessfully removed {orphaned_count} orphaned records.")
        else:
            print(f"\nFound {orphaned_count} orphaned records to remove.")

@app.command()
def cleanup(
    no_dry_run: bool = typer.Option(False, "--no-dry-run", help="Actually delete files. If not set, only a preview is shown."),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation.")
):
    """
    Automatically delete duplicates, keeping the version with the shortest path.
    """
    init_db()
    is_dry_run = not no_dry_run
    if is_dry_run:
        print("--- PREVIEW MODE (DRY RUN) ---")
    else:
        print("--- ACTUAL DELETION MODE ---")
    
    with Session(engine) as session:
        statement = (
            select(MediaFile.sha256_hash)
            .where(MediaFile.status == "completed")
            .group_by(MediaFile.sha256_hash)
            .having(func.count(MediaFile.abs_path) > 1)
        )
        duplicate_hashes = session.exec(statement).all()
        if not duplicate_hashes:
            print("No duplicates found in the database.")
            return
        for h in duplicate_hashes:
            files_statement = select(MediaFile).where(MediaFile.sha256_hash == h)
            files = session.exec(files_statement).all()
            files.sort(key=lambda x: len(x.abs_path))
            keep_file = files[0]
            delete_files = files[1:]
            print(f"\nGroup: {h}")
            print(f"  [KEEP] {keep_file.abs_path}")
            for df in delete_files:
                print(f"  [DELETE] {df.abs_path}")
                if not is_dry_run:
                    if not force:
                        confirm = typer.confirm(f"Are you sure you want to delete {df.abs_path}?")
                        if not confirm: continue
                    try:
                        if os.path.exists(df.abs_path):
                            os.remove(df.abs_path)
                        session.delete(df)
                        print(f"    - Deleted.")
                    except Exception as e:
                        print(f"    - Error: {e}")
            session.commit()

@app.command()
def archive(
    target_dir: str = typer.Argument(..., help="Target directory to move and organize files."),
    no_dry_run: bool = typer.Option(False, "--no-dry-run", help="Actually move files. Default is preview."),
):
    """
    Move and organize unique files into target_dir/YYYY/MM/DD structure.
    """
    init_db()
    target_path = os.path.abspath(target_dir)
    is_dry_run = not no_dry_run

    if is_dry_run:
        print(f"--- PREVIEW MODE: Organizing files into {target_path} ---")
    else:
        print(f"--- ACTUAL ARCHIVE MODE: Moving files to {target_path} ---")
        if not os.path.exists(target_path):
            os.makedirs(target_path)

    with Session(engine) as session:
        statement = select(MediaFile).where(MediaFile.status == "completed")
        all_files = session.exec(statement).all()

        if not all_files:
            print("No completed files found in database to archive.")
            return

        for mf in all_files:
            if not os.path.exists(mf.abs_path):
                continue

            # Get file date (Modification time)
            mtime = os.path.getmtime(mf.abs_path)
            dt = datetime.fromtimestamp(mtime)
            rel_dir = dt.strftime("%Y/%m/%d")
            dest_dir = os.path.join(target_path, rel_dir)
            filename = os.path.basename(mf.abs_path)
            
            # Intended path (if it were the only file)
            intended_path = os.path.join(dest_dir, filename)
            
            # CRITICAL FIX: If file is already at its intended destination, skip it
            if mf.abs_path == intended_path:
                continue

            name, ext = os.path.splitext(filename)
            final_dest = intended_path
            
            # Handle collision with OTHER files
            counter = 1
            while os.path.exists(final_dest):
                # If we are in dry-run, we might see the file itself if we don't have the PK check above
                final_dest = os.path.join(dest_dir, f"{name}_{counter}{ext}")
                counter += 1

            print(f"  [MOVE] {mf.abs_path} -> {final_dest}")

            if not is_dry_run:
                try:
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)
                    
                    shutil.move(mf.abs_path, final_dest)
                    
                    # Update database: Since abs_path is PK, delete and re-insert
                    old_mf_data = mf.model_dump()
                    session.delete(mf)
                    session.commit()
                    
                    old_mf_data['abs_path'] = final_dest
                    new_mf = MediaFile(**old_mf_data)
                    session.add(new_mf)
                    session.commit()
                except Exception as e:
                    print(f"    - Error moving {mf.abs_path}: {e}")

    if is_dry_run:
        print(f"\nTo actually archive these files, run: sudo .venv/bin/archivist archive {target_dir} --no-dry-run")

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

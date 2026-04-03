import typer
import asyncio
import uvicorn
import os
import shutil
from datetime import datetime
from typing import List, Optional
from media_archivist.core.database import init_db, engine, MediaFile, Task, update_task_progress
from media_archivist.agent.scanner import scan_directory
from media_archivist.agent.hasher import hash_pending_files
from media_archivist.agent.extractor import process_archives
from sqlmodel import Session, select, func, col

app = typer.Typer(help="MediaArchivist: Efficient media management tool.")

# Default temp directory for unpacking
TEMP_UNPACK_DIR = os.path.join("data", "_temp_unpacked")


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
def start(
    directories: Optional[List[str]] = typer.Argument(
        None, help="Directories to scan."
    ),
):
    """Start scanning and background hashing."""
    init_db()
    reset_stuck_hashing()

    with Session(engine) as session:
        scan_task_id = None
        if directories:
            scan_task = Task(
                name=f"Scan: {', '.join(directories[:2])}{'...' if len(directories) > 2 else ''}",
                task_type="scan"
            )
            session.add(scan_task)
            session.commit()
            session.refresh(scan_task)
            scan_task_id = scan_task.id

        hash_task = Task(
            name=f"Hashing (Session {datetime.now().strftime('%H:%M:%S')})",
            task_type="hash"
        )
        session.add(hash_task)
        session.commit()
        session.refresh(hash_task)
        hash_task_id = hash_task.id

    async def run_agent():
        tasks = []
        if directories and scan_task_id:
            print(f"Scanning directories: {', '.join(directories)}...")
            tasks.append(asyncio.gather(*[scan_directory(d, scan_task_id) for d in directories]))

        tasks.append(hash_pending_files(hash_task_id, scan_task_id))
        await asyncio.gather(*tasks)

    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        if scan_task_id:
            update_task_progress(scan_task_id, 0.0, 0, 0, "Interrupted", "failed")
        update_task_progress(hash_task_id, 0.0, 0, 0, "Interrupted", "failed")
        print("\nStopping MediaArchivist agent...")


@app.command()
def unpack(
    directories: List[str] = typer.Argument(..., help="Directories to search for archives."),
    temp_dir: str = typer.Option(TEMP_UNPACK_DIR, help="Where to extract files."),
):
    """Find archives in directories, unpack them, and then scan/hash the contents."""
    init_db()
    
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    with Session(engine) as session:
        unpack_task = Task(
            name=f"Unpack archives from: {', '.join(directories[:2])}",
            task_type="unpack"
        )
        session.add(unpack_task)
        session.commit()
        session.refresh(unpack_task)
        unpack_task_id = unpack_task.id

    async def run_pipeline():
        print(f"Searching and unpacking archives in: {', '.join(directories)}...")
        # Step 1: Unpack
        await process_archives(directories, temp_dir, unpack_task_id)
        
        # Step 2: Create tasks for the unpacked files
        with Session(engine) as session:
            scan_task = Task(name="Scan unpacked files", task_type="scan")
            session.add(scan_task)
            session.commit()
            session.refresh(scan_task)
            scan_task_id = scan_task.id

            hash_task = Task(name="Hash unpacked files", task_type="hash")
            session.add(hash_task)
            session.commit()
            session.refresh(hash_task)
            hash_task_id = hash_task.id

        # Step 3: Scan and Hash
        print(f"Scanning unpacked files in {temp_dir}...")
        await scan_directory(temp_dir, scan_task_id)
        await hash_pending_files(hash_task_id, scan_task_id)
        print("Unpack and ingestion pipeline completed.")

    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        print("\nInterrupted.")


@app.command()
def cleanup(
    no_dry_run: bool = typer.Option(
        False, "--no-dry-run", help="Actually delete files."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion."),
):
    """Automatically delete duplicates, keeping the version with the shortest path."""
    init_db()
    is_dry_run = not no_dry_run

    if is_dry_run:
        print("--- PREVIEW MODE (DRY RUN) ---")
    else:
        print("--- ACTUAL DELETION MODE ---")
        with Session(engine) as session:
            cleanup_task = Task(
                name=f"Cleanup ({datetime.now().strftime('%H:%M:%S')})",
                task_type="cleanup"
            )
            session.add(cleanup_task)
            session.commit()
            session.refresh(cleanup_task)
            task_id = cleanup_task.id

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
            if not is_dry_run:
                update_task_progress(task_id, 100.0, 0, 0, "No duplicates found.", "completed")
            return

        total_hashes = len(duplicate_hashes)
        for idx, h in enumerate(duplicate_hashes):
            files = session.exec(
                select(MediaFile).where(MediaFile.sha256_hash == h)
            ).all()
            
            # Keep the oldest file (earliest creation/birth time)
            # If times are equal, fall back to shortest path as a tie-breaker
            def get_file_creation_time(f):
                try:
                    stat = os.stat(f.abs_path)
                    # Use st_birthtime if available (BSD, macOS, some Linux filesystems)
                    if hasattr(stat, 'st_birthtime'):
                        return stat.st_birthtime
                    # Fallback to ctime (Creation time on Windows, Metadata change time on Linux)
                    return stat.st_ctime
                except OSError:
                    return float('inf')

            files.sort(key=lambda x: (get_file_creation_time(x), len(x.abs_path)))
            delete_files = files[1:]

            for df in delete_files:
                if not is_dry_run:
                    if not force:
                        confirm = typer.confirm(f"Delete {df.abs_path}?")
                        if not confirm:
                            continue
                    try:
                        if os.path.exists(df.abs_path):
                            os.remove(df.abs_path)
                        session.delete(df)
                    except Exception as e:
                        print(f"Error: {e}")

            if not is_dry_run:
                progress = (idx + 1) / total_hashes * 100
                update_task_progress(
                    task_id, progress, idx + 1, total_hashes, f"Processed {idx + 1}/{total_hashes} groups."
                )

            session.commit()

        if not is_dry_run:
            update_task_progress(
                task_id, 100.0, total_hashes, total_hashes, "Cleanup completed successfully.", "completed"
            )


@app.command()
def archive(
    target_dir: str = typer.Argument(..., help="Target directory."),
    no_dry_run: bool = typer.Option(
        False, "--no-dry-run", help="Actually process files."
    ),
    copy: bool = typer.Option(
        False, "--copy", "-c", help="Copy files instead of moving."
    ),
):
    """Organize unique files into target_dir/YYYY/MM/DD structure."""
    init_db()
    target_path = os.path.abspath(target_dir)
    is_dry_run = not no_dry_run

    if not is_dry_run:
        with Session(engine) as session:
            archive_task = Task(
                name=f"Archive to {os.path.basename(target_path)} ({datetime.now().strftime('%H:%M:%S')})",
                task_type="archive"
            )
            session.add(archive_task)
            session.commit()
            session.refresh(archive_task)
            task_id = archive_task.id
        
        if not os.path.exists(target_path):
            os.makedirs(target_path)

    with Session(engine) as session:
        all_files = session.exec(
            select(MediaFile).where(MediaFile.status == "completed")
        ).all()
        if not all_files:
            print("No files to archive.")
            if not is_dry_run:
                update_task_progress(task_id, 100.0, 0, 0, "No files found.", "completed")
            return

        total_files = len(all_files)
        for idx, mf in enumerate(all_files):
            if not os.path.exists(mf.abs_path):
                continue

            dt = datetime.fromtimestamp(os.path.getmtime(mf.abs_path))
            dest_dir = os.path.join(target_path, dt.strftime("%Y/%m/%d"))
            filename = os.path.basename(mf.abs_path)
            intended_path = os.path.join(dest_dir, filename)

            if mf.abs_path == intended_path:
                continue

            final_dest = intended_path
            name, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(final_dest):
                final_dest = os.path.join(dest_dir, f"{name}_{counter}{ext}")
                counter += 1

            if not is_dry_run:
                try:
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)
                    if copy:
                        # shutil.copy2 preserves metadata (mtime, atime, etc.)
                        shutil.copy2(mf.abs_path, final_dest)
                    else:
                        # shutil.move preserves attributes on the same filesystem
                        shutil.move(mf.abs_path, final_dest)
                    old_mf_data = mf.model_dump()
                    session.delete(mf)
                    session.commit()
                    old_mf_data["abs_path"] = final_dest
                    new_mf = MediaFile(**old_mf_data)
                    session.add(new_mf)
                    session.commit()
                    
                    progress = (idx + 1) / total_files * 100
                    update_task_progress(
                        task_id,
                        progress,
                        idx + 1,
                        total_files,
                        f"{'Copied' if copy else 'Moved'} {idx + 1}/{total_files} files.",
                    )
                except Exception as e:
                    print(f"Error: {e}")
            else:
                action = "COPY" if copy else "MOVE"
                print(f" [{action}] {mf.abs_path} -> {final_dest}")

        if not is_dry_run:
            update_task_progress(
                task_id, 100.0, total_files, total_files, "Archive completed successfully.", "completed"
            )


@app.command()
def doctor(no_dry_run: bool = typer.Option(False, "--no-dry-run")):
    """Health check."""
    init_db()
    with Session(engine) as session:
        all_records = session.exec(select(MediaFile)).all()
        for record in all_records:
            if not os.path.exists(record.abs_path):
                if not no_dry_run:
                    print(f"[DRY] Orphaned: {record.abs_path}")
                else:
                    session.delete(record)
        session.commit()


@app.command()
def list_files(status: Optional[str] = None, limit: int = 100):
    """List paths."""
    init_db()
    with Session(engine) as session:
        statement = select(MediaFile)
        if status:
            statement = statement.where(MediaFile.status == status)
        results = session.exec(statement.limit(limit)).all()
        for f in results:
            print(f"{f.status:<12} | {f.abs_path}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search pattern for file paths (case-insensitive)."),
    status: Optional[str] = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(100, help="Limit results."),
):
    """Search for files by path pattern (like grep)."""
    init_db()
    with Session(engine) as session:
        # Use col().ilike for case-insensitive search if supported, 
        # but standard SQLite LIKE is case-insensitive for ASCII.
        statement = select(MediaFile).where(col(MediaFile.abs_path).contains(query))
        if status:
            statement = statement.where(MediaFile.status == status)

        results = session.exec(statement.limit(limit)).all()
        if not results:
            print(f"No files found matching: {query}")
            return

        print(f"Found {len(results)} matches (limit {limit}):")
        for f in results:
            h = f.sha256_hash[:8] if f.sha256_hash else "--------"
            print(f"{f.status:<10} | {h} | {f.abs_path}")



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
        done = session.exec(
            select(func.count(MediaFile.abs_path)).where(
                MediaFile.status == "completed"
            )
        ).one()
        print(f"--- Global Status ---")
        print(f"Total files: {total}")
        print(f"Completed: {done}")
        
        print(f"\n--- Recent Tasks ---")
        tasks = session.exec(select(Task).order_by(Task.updated_at.desc()).limit(10)).all()
        for t in tasks:
            t_type = (t.task_type or "unknown").upper()
            print(f"[{t_type}] {t.name}")
            print(f"  Status: {t.status} | Progress: {t.progress:.1f}% ({t.completed_items}/{t.total_items})")
            print(f"  Message: {t.message}")
            print(f"  Updated: {t.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 20)


if __name__ == "__main__":
    app()

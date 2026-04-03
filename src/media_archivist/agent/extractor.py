import os
import zipfile
import tarfile
import py7zr
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from sqlmodel import Session
from media_archivist.core.database import engine, Task, update_task_progress

SUPPORTED_ARCHIVES = {".zip", ".tar", ".gz", ".7z", ".rar"}

def is_archive(file_path: str) -> bool:
    """Check if file has a supported archive extension."""
    ext = "".join(Path(file_path).suffixes).lower()
    return any(ext.endswith(s) for s in SUPPORTED_ARCHIVES) or Path(file_path).suffix.lower() in SUPPORTED_ARCHIVES

async def extract_archive(archive_path: str, target_dir: str, task_id: Optional[int] = None) -> List[str]:
    """Extracts an archive to the target directory and returns a list of extracted file paths."""
    archive_path = os.path.abspath(archive_path)
    target_dir = os.path.abspath(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    
    extracted_paths = []
    ext = "".join(Path(archive_path).suffixes).lower()
    
    try:
        if ext.endswith(".zip"):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
                extracted_paths = [os.path.join(target_dir, f) for f in zip_ref.namelist()]
        elif ext.endswith(".tar.gz") or ext.endswith(".tgz") or ext.endswith(".tar"):
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                tar_ref.extractall(target_dir)
                extracted_paths = [os.path.join(target_dir, f) for f in tar_ref.getnames()]
        elif ext.endswith(".7z"):
            with py7zr.SevenZipFile(archive_path, mode='r') as seven_z:
                seven_z.extractall(target_dir)
                extracted_paths = [os.path.join(target_dir, f) for f in seven_z.getnames()]
        else:
            return []
            
        # Filter for actual files only (exclude directories)
        full_paths = [os.path.abspath(p) for p in extracted_paths]
        existing_files = [p for p in full_paths if os.path.isfile(p)]
        return existing_files

    except Exception as e:
        print(f"Error extracting {archive_path}: {e}")
        return []

async def process_archives(source_dirs: List[str], temp_dir: str, task_id: Optional[int] = None):
    """Scan for archives (or handle direct file paths) and unpack them into the temp_dir."""
    archive_files = []
    for d in source_dirs:
        if os.path.isfile(d):
            if is_archive(d):
                archive_files.append(d)
        elif os.path.isdir(d):
            for root, _, files in os.walk(d):
                for f in files:
                    p = os.path.join(root, f)
                    if is_archive(p):
                        archive_files.append(p)
    
    total = len(archive_files)
    if not archive_files:
        if task_id:
            update_task_progress(task_id, 100.0, 0, 0, "No archives found.", "completed")
        return []

    results = []
    for idx, archive in enumerate(archive_files):
        # Create a specific subfolder for each archive in temp_dir
        archive_name = Path(archive).stem
        dest = os.path.join(temp_dir, f"{archive_name}_{idx}")
        
        extracted = await extract_archive(archive, dest, task_id)
        results.extend(extracted)
        
        if task_id:
            progress = ((idx + 1) / total) * 100
            update_task_progress(task_id, progress, idx + 1, total, f"Unpacked {idx + 1}/{total} archives.")
            
    if task_id:
        update_task_progress(task_id, 100.0, total, total, f"Finished unpacking {total} archives.", "completed")
    
    return results

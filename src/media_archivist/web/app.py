from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select, func
from media_archivist.core.database import engine, MediaFile, get_session
from typing import List, Dict

app = FastAPI(title="MediaArchivist API")

@app.get("/", response_class=HTMLResponse)
def dashboard(session: Session = Depends(get_session)):
    """
    Returns a simple HTML dashboard for viewing duplicates and processing status.
    """
    # Get duplicates
    duplicate_hashes_statement = (
        select(MediaFile.sha256_hash)
        .where(MediaFile.status == "completed")
        .group_by(MediaFile.sha256_hash)
        .having(func.count(MediaFile.abs_path) > 1)
    )
    duplicate_hashes = session.exec(duplicate_hashes_statement).all()
    
    duplicates_data = []
    for h in duplicate_hashes:
        files_statement = select(MediaFile).where(MediaFile.sha256_hash == h)
        files = session.exec(files_statement).all()
        duplicates_data.append({
            "hash": h,
            "count": len(files),
            "files": [f.abs_path for f in files]
        })

    # Prepare HTML content for duplicates
    groups_html = ""
    for group in duplicates_data:
        files_list_html = "".join([f"<li>{path}</li>" for path in group["files"]])
        groups_html += f"""
        <div class="duplicate-group">
            <div><span class="count">{group["count"]} copies</span> <span class="hash">{group["hash"]}</span></div>
            <ul>
                {files_list_html}
            </ul>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MediaArchivist Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 2rem; background-color: #f4f4f9; color: #333; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 0.5rem; }}
            
            /* Status Section */
            .status-container {{ background: white; padding: 1.5rem; margin-bottom: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1rem; }}
            .stat-card {{ text-align: center; padding: 1rem; background: #f8f9fa; border-radius: 6px; }}
            .stat-value {{ font-size: 1.5rem; font-weight: bold; color: #3498db; }}
            .stat-label {{ font-size: 0.8rem; color: #7f8c8d; text-transform: uppercase; }}
            
            /* Progress Bar */
            .progress-wrapper {{ background: #eee; border-radius: 10px; height: 20px; width: 100%; overflow: hidden; margin-top: 1rem; }}
            .progress-bar {{ background: #3498db; height: 100%; width: 0%; transition: width 0.5s ease-in-out; display: flex; align-items: center; justify-content: center; color: white; font-size: 0.75rem; font-weight: bold; }}
            
            /* Duplicates Section */
            .duplicate-group {{ background: white; padding: 1.5rem; margin-bottom: 1.5rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-left: 5px solid #e74c3c; }}
            .hash {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; color: #7f8c8d; font-size: 0.85rem; margin-left: 1rem; }}
            ul {{ list-style: none; padding-left: 0; margin-top: 1rem; }}
            li {{ padding: 0.75rem 0; border-bottom: 1px solid #ecf0f1; word-break: break-all; font-size: 0.95rem; }}
            li:last-child {{ border-bottom: none; }}
            .count {{ background: #e74c3c; color: white; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.8rem; font-weight: bold; text-transform: uppercase; }}
            .summary {{ margin-bottom: 1rem; color: #7f8c8d; font-style: italic; }}
        </style>
    </head>
    <body>
        <h1>MediaArchivist Dashboard</h1>
        
        <div class="status-container">
            <div class="stats-grid">
                <div class="stat-card">
                    <div id="stat-total" class="stat-value">-</div>
                    <div class="stat-label">Total Files</div>
                </div>
                <div class="stat-card">
                    <div id="stat-completed" class="stat-value">-</div>
                    <div class="stat-label">Completed</div>
                </div>
                <div class="stat-card">
                    <div id="stat-pending" class="stat-value">-</div>
                    <div class="stat-label">Pending</div>
                </div>
                <div class="stat-card">
                    <div id="stat-hashing" class="stat-value">-</div>
                    <div class="stat-label">Hashing</div>
                </div>
            </div>
            <div class="progress-wrapper">
                <div id="progress-bar" class="progress-bar">0%</div>
            </div>
        </div>

        <h2>Duplicates Found</h2>
        <p class="summary">Found {len(duplicates_data)} groups of duplicate files.</p>
        <div id="duplicates">
            {groups_html}
        </div>

        <script>
            async function updateStatus() {{
                try {{
                    const response = await fetch('/status');
                    const data = await response.json();
                    
                    document.getElementById('stat-total').innerText = data.total;
                    document.getElementById('stat-completed').innerText = data.completed;
                    document.getElementById('stat-pending').innerText = data.pending;
                    document.getElementById('stat-hashing').innerText = data.hashing;
                    
                    const percent = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;
                    const progressBar = document.getElementById('progress-bar');
                    progressBar.style.width = percent + '%';
                    progressBar.innerText = percent + '%';
                    
                    // Auto-refresh more frequently if things are still hashing/pending
                    if (data.pending > 0 || data.hashing > 0) {{
                        setTimeout(updateStatus, 2000);
                    }} else {{
                        setTimeout(updateStatus, 10000);
                    }}
                }} catch (error) {{
                    console.error('Error updating status:', error);
                    setTimeout(updateStatus, 5000);
                }}
            }}
            updateStatus();
        </script>
    </body>
    </html>
    """
    return html_content

@app.get("/duplicates")
def get_duplicates(session: Session = Depends(get_session)):
    """
    Returns a list of duplicate files grouped by their SHA-256 hash.
    Only includes completed files.
    """
    # Find hashes that appear more than once
    duplicate_hashes_statement = (
        select(MediaFile.sha256_hash)
        .where(MediaFile.status == "completed")
        .group_by(MediaFile.sha256_hash)
        .having(func.count(MediaFile.abs_path) > 1)
    )
    duplicate_hashes = session.exec(duplicate_hashes_statement).all()
    
    result = []
    for h in duplicate_hashes:
        files_statement = select(MediaFile).where(MediaFile.sha256_hash == h)
        files = session.exec(files_statement).all()
        result.append({
            "hash": h,
            "count": len(files),
            "files": [f.abs_path for f in files]
        })
    
    return result

@app.get("/status")
def get_status(session: Session = Depends(get_session)):
    """
    Returns processing status.
    """
    total = session.exec(select(func.count(MediaFile.abs_path))).one()
    completed = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "completed")).one()
    pending = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "pending")).one()
    hashing = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "hashing")).one()
    error = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "error")).one()
    
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "hashing": hashing,
        "error": error
    }

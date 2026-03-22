from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select, func
from media_archivist.core.database import engine, MediaFile, get_session
from typing import List, Dict

app = FastAPI(title="MediaArchivist API")

COMMON_STYLE = """
    :root { --primary: #3498db; --bg: #f4f4f9; --text: #333; --card-bg: #fff; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 1rem; background-color: var(--bg); color: var(--text); line-height: 1.5; }
    .container { max-width: 800px; margin: 0 auto; }
    h1 { color: #2c3e50; border-bottom: 2px solid var(--primary); padding-bottom: 0.5rem; font-size: 1.5rem; }
    .btn { display: inline-block; background: var(--primary); color: white; padding: 0.8rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 1rem; transition: opacity 0.2s; border: none; cursor: pointer; width: 100%; text-align: center; }
    @media (min-width: 600px) { .btn { width: auto; } h1 { font-size: 2rem; } body { padding: 2rem; } }
    .btn:active { opacity: 0.8; }
    .card { background: var(--card-bg); padding: 1.2rem; margin-bottom: 1.5rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
"""

@app.get("/", response_class=HTMLResponse)
def dashboard(session: Session = Depends(get_session)):
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Archivist Dashboard</title>
        <style>
            {COMMON_STYLE}
            .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.8rem; margin-bottom: 1rem; }}
            @media (min-width: 480px) {{ .stats-grid {{ grid-template-columns: repeat(4, 1fr); }} }}
            .stat-card {{ text-align: center; padding: 0.8rem; background: #f8f9fa; border-radius: 8px; border: 1px solid #eee; }}
            .stat-value {{ font-size: 1.2rem; font-weight: bold; color: var(--primary); }}
            .stat-label {{ font-size: 0.7rem; color: #7f8c8d; text-transform: uppercase; margin-top: 0.2rem; }}
            .progress-wrapper {{ background: #eee; border-radius: 20px; height: 24px; width: 100%; overflow: hidden; margin-top: 1rem; }}
            .progress-bar {{ background: var(--primary); height: 100%; width: 0%; transition: width 0.5s ease; display: flex; align-items: center; justify-content: center; color: white; font-size: 0.8rem; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Archivist Status</h1>
            
            <div class="card">
                <div class="stats-grid">
                    <div class="stat-card"><div id="stat-total" class="stat-value">-</div><div class="stat-label">Total</div></div>
                    <div class="stat-card"><div id="stat-completed" class="stat-value">-</div><div class="stat-label">Done</div></div>
                    <div class="stat-card"><div id="stat-pending" class="stat-value">-</div><div class="stat-label">Wait</div></div>
                    <div class="stat-card"><div id="stat-hashing" class="stat-value">-</div><div class="stat-label">Hash</div></div>
                </div>
                <div class="progress-wrapper">
                    <div id="progress-bar" class="progress-bar">0%</div>
                </div>
            </div>

            <div style="text-align: center;">
                <a href="/duplicates-view" class="btn">Manage Duplicates</a>
            </div>
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
                    const pb = document.getElementById('progress-bar');
                    pb.style.width = percent + '%'; pb.innerText = percent + '%';
                    setTimeout(updateStatus, (data.pending > 0 || data.hashing > 0) ? 2000 : 10000);
                }} catch (e) {{ setTimeout(updateStatus, 5000); }}
            }}
            updateStatus();
        </script>
    </body>
    </html>
    """
    return html_content

@app.get("/duplicates-view", response_class=HTMLResponse)
def duplicates_view(session: Session = Depends(get_session)):
    duplicate_hashes_statement = (
        select(MediaFile.sha256_hash)
        .where(MediaFile.status == "completed")
        .group_by(MediaFile.sha256_hash)
        .having(func.count(MediaFile.abs_path) > 1)
    )
    duplicate_hashes = session.exec(duplicate_hashes_statement).all()
    duplicates_data = []
    for h in duplicate_hashes:
        files = session.exec(select(MediaFile).where(MediaFile.sha256_hash == h)).all()
        duplicates_data.append({"hash": h, "count": len(files), "files": [f.abs_path for f in files]})

    groups_html = ""
    for group in duplicates_data:
        files_list_html = "".join([f"<li>{path}</li>" for path in group["files"]])
        groups_html += f"""
        <div class="duplicate-group">
            <div style="margin-bottom:0.5rem;"><span class="badge">{group["count"]} copies</span></div>
            <div class="hash">{group["hash"]}</div>
            <ul>{files_list_html}</ul>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Duplicates View</title>
        <style>
            {COMMON_STYLE}
            .duplicate-group {{ background: white; padding: 1rem; margin-bottom: 1rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 6px solid #e74c3c; }}
            .hash {{ font-family: monospace; color: #7f8c8d; font-size: 0.75rem; word-break: break-all; background: #f8f9fa; padding: 0.4rem; border-radius: 4px; }}
            ul {{ list-style: none; padding-left: 0; margin-top: 0.8rem; }}
            li {{ padding: 0.6rem 0; border-bottom: 1px solid #ecf0f1; word-break: break-all; font-size: 0.85rem; color: #444; }}
            li:last-child {{ border-bottom: none; }}
            .badge {{ background: #e74c3c; color: white; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.75rem; font-weight: bold; }}
            .back-link {{ display: inline-block; margin-bottom: 1rem; color: var(--primary); text-decoration: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/" class="back-link">← Dashboard</a>
            <h1>Duplicates</h1>
            <p style="color: #7f8c8d; font-size: 0.9rem; margin-bottom: 1.5rem;">Found {len(duplicates_data)} groups.</p>
            <div>{groups_html}</div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.get("/status")
def get_status(session: Session = Depends(get_session)):
    total = session.exec(select(func.count(MediaFile.abs_path))).one()
    completed = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "completed")).one()
    pending = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "pending")).one()
    hashing = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "hashing")).one()
    error = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "error")).one()
    return {"total": total, "completed": completed, "pending": pending, "hashing": hashing, "error": error}

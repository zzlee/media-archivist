from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select, func
from media_archivist.core.database import engine, MediaFile, Task, get_session
from typing import List, Dict

app = FastAPI(title="MediaArchivist API")

COMMON_STYLE = """
    :root { --primary: #3498db; --bg: #f4f4f9; --text: #333; --card-bg: #fff; --accent: #e74c3c; --success: #2ecc71; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 1rem; background-color: var(--bg); color: var(--text); line-height: 1.5; }
    .container { max-width: 800px; margin: 0 auto; }
    h1, h2 { color: #2c3e50; border-bottom: 2px solid var(--primary); padding-bottom: 0.5rem; font-size: 1.5rem; }
    .btn { display: inline-block; background: var(--primary); color: white; padding: 0.8rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 1rem; transition: opacity 0.2s; border: none; cursor: pointer; width: 100%; text-align: center; }
    @media (min-width: 600px) { .btn { width: auto; } h1 { font-size: 2rem; } body { padding: 2rem; } }
    .card { background: var(--card-bg); padding: 1.2rem; margin-bottom: 1.5rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .progress-wrapper { background: #eee; border-radius: 20px; height: 20px; width: 100%; overflow: hidden; margin-top: 0.5rem; position: relative; }
    .progress-bar { background: var(--primary); height: 100%; width: 0%; transition: width 0.5s ease; display: flex; align-items: center; justify-content: center; color: white; font-size: 0.7rem; font-weight: bold; }
    .task-item { margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid #eee; }
    .task-item:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
    .task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem; }
    .task-name { font-weight: bold; text-transform: capitalize; }
    .task-status { font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 10px; background: #eee; }
    .status-completed { background: var(--success); color: white; }
    .status-running { background: var(--primary); color: white; }
    .task-msg { font-size: 0.8rem; color: #7f8c8d; margin-top: 0.3rem; }
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
            .stat-label {{ font-size: 0.7rem; color: #7f8c8d; text-transform: uppercase; }}
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
                    <div class="stat-card"><div id="stat-error" class="stat-value">-</div><div class="stat-label">Error</div></div>
                </div>
            </div>

            <h2>Active Tasks</h2>
            <div class="card" id="tasks-container">
                <p style="color: #7f8c8d; text-align: center;">Loading tasks...</p>
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
                    document.getElementById('stat-error').innerText = data.error;
                    
                    const tasksContainer = document.getElementById('tasks-container');
                    if (data.tasks.length === 0) {{
                        tasksContainer.innerHTML = '<p style="color: #7f8c8d; text-align: center;">No active tasks.</p>';
                    }} else {{
                        tasksContainer.innerHTML = data.tasks.map(task => `
                            <div class="task-item">
                                <div class="task-header">
                                    <span class="task-name">${{task.name}}</span>
                                    <span class="task-status status-${{task.status}}">${{task.status}}</span>
                                </div>
                                <div class="progress-wrapper">
                                    <div class="progress-bar" style="width: ${{task.progress}}%">${{Math.round(task.progress)}}%</div>
                                </div>
                                <div class="task-msg">${{task.message || ''}}</div>
                            </div>
                        `).join('');
                    }}
                    
                    setTimeout(updateStatus, 2000);
                } catch (e) {{ setTimeout(updateStatus, 5000); }}
            }}
            updateStatus();
        </script>
    </body>
    </html>
    """
    return html_content

@app.get("/duplicates-view", response_class=HTMLResponse)
def duplicates_view(session: Session = Depends(get_session)):
    duplicate_hashes = session.exec(
        select(MediaFile.sha256_hash)
        .where(MediaFile.status == "completed")
        .group_by(MediaFile.sha256_hash)
        .having(func.count(MediaFile.abs_path) > 1)
    ).all()
    
    groups_html = ""
    for h in duplicate_hashes:
        files = session.exec(select(MediaFile).where(MediaFile.sha256_hash == h)).all()
        files_list_html = "".join([f"<li>{path}</li>" for path in [f.abs_path for f in files]])
        groups_html += f'<div class="duplicate-group"><div class="badge">{len(files)} copies</div><div class="hash">{h}</div><ul>{files_list_html}</ul></div>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Duplicates View</title>
        <style>
            {COMMON_STYLE}
            .duplicate-group {{ background: white; padding: 1rem; margin-bottom: 1rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 6px solid var(--accent); }}
            .hash {{ font-family: monospace; color: #7f8c8d; font-size: 0.75rem; word-break: break-all; background: #f8f9fa; padding: 0.4rem; border-radius: 4px; }}
            ul {{ list-style: none; padding-left: 0; margin-top: 0.8rem; }}
            li {{ padding: 0.6rem 0; border-bottom: 1px solid #ecf0f1; word-break: break-all; font-size: 0.85rem; color: #444; }}
            li:last-child {{ border-bottom: none; }}
            .badge {{ display: inline-block; background: var(--accent); color: white; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.75rem; font-weight: bold; margin-bottom: 0.5rem; }}
            .back-link {{ display: inline-block; margin-bottom: 1rem; color: var(--primary); text-decoration: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/" class="back-link">← Dashboard</a>
            <h1>Duplicates</h1>
            <div>{groups_html if groups_html else '<p style="text-align:center; color:#7f8c8d;">No duplicates found.</p>'}</div>
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
    error = session.exec(select(func.count(MediaFile.abs_path)).where(MediaFile.status == "error")).one()
    
    # Get all active tasks
    tasks = session.exec(select(Task).order_by(Task.updated_at.desc())).all()
    
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "error": error,
        "tasks": [t.model_dump() for f in [tasks] for t in f]
    }

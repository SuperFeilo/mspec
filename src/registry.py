import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from config import get_registry_path, load_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT DEFAULT 'idle',
    current_phase TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checkpoint TIMESTAMP,
    session_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    tag TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS agent_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT REFERENCES projects(id),
    session_id TEXT REFERENCES sessions(id),
    agent TEXT,
    model TEXT,
    prompt TEXT,
    status TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_calls_project ON agent_calls(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_calls_session ON agent_calls(session_id);
"""


def get_connection() -> sqlite3.Connection:
    path = get_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def register_project(project_id: str, name: str, path: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO projects (id, name, path, status) VALUES (?, ?, ?, 'idle')",
        (project_id, name, path),
    )
    conn.commit()
    conn.close()


def update_project_status(project_id: str, status: str, current_phase: str | None = None):
    conn = get_connection()
    if current_phase:
        conn.execute(
            "UPDATE projects SET status = ?, current_phase = ? WHERE id = ?",
            (status, current_phase, project_id),
        )
    else:
        conn.execute(
            "UPDATE projects SET status = ? WHERE id = ?",
            (status, project_id),
        )
    conn.commit()
    conn.close()


def update_checkpoint(project_id: str):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE projects SET status = 'checkpointed', last_checkpoint = ?, session_count = session_count + 1 WHERE id = ?",
        (now, project_id),
    )
    conn.commit()
    conn.close()


def add_session(project_id: str, session_id: str, tag: str, summary: str | None = None, duration: int | None = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (id, project_id, tag, summary, duration_seconds) VALUES (?, ?, ?, ?, ?)",
        (session_id, project_id, tag, summary, duration),
    )
    conn.commit()
    conn.close()


def add_agent_call(project_id: str, session_id: str, agent: str, model: str, prompt: str, status: str, tokens_in: int, tokens_out: int, duration_ms: int):
    conn = get_connection()
    conn.execute(
        "INSERT INTO agent_calls (project_id, session_id, agent, model, prompt, status, tokens_input, tokens_output, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, agent, model, prompt, status, tokens_in, tokens_out, duration_ms),
    )
    conn.commit()
    conn.close()


def get_all_projects():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_project_sessions(project_id: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_agent_stats(project_id: str, session_id: str | None = None):
    conn = get_connection()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM agent_calls WHERE project_id = ? AND session_id = ? ORDER BY created_at DESC",
            (project_id, session_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_calls WHERE project_id = ? ORDER BY created_at DESC LIMIT 50",
            (project_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

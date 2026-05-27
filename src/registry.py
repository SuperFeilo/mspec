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

CREATE TABLE IF NOT EXISTS stall_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    stub_name TEXT,
    stall_count INTEGER,
    patterns TEXT,
    context TEXT,
    output_snippet TEXT,
    elapsed_sec INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT,
    stub_name TEXT NOT NULL,
    stub_path TEXT,
    bp_id TEXT,
    title TEXT,
    agent TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL DEFAULT 'starting',
    exit_code INTEGER,
    error TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    output_preview TEXT,
    files_changed_json TEXT,
    active_pid INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    context_json TEXT
);

CREATE TABLE IF NOT EXISTS build_steps (
    id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT,
    description TEXT,
    status TEXT DEFAULT 'not_started',
    context TEXT,
    context_tokens INTEGER,
    contract_inputs TEXT,
    contract_outputs TEXT,
    tests_json TEXT,
    latest_run_id TEXT REFERENCES runs(id),
    sort_order INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_stub ON runs(stub_name);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_build_steps_project ON build_steps(project_id);
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


def delete_project_record(project_id: str) -> bool:
    """Remove a project and its sessions/agent_calls from the registry."""
    conn = get_connection()
    conn.execute("DELETE FROM agent_calls WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM sessions WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    deleted = conn.total_changes > 0
    conn.close()
    return deleted


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


# ════════════════════════════════════════════════════════════════
#  Run & Build Step Registry DAO
# ════════════════════════════════════════════════════════════════

def create_run(project_id: str, run_id: str, session_id: str, stub_name: str,
               agent: str, model: str, stub_path: str = None, bp_id: str = None,
               title: str = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute("""
        INSERT INTO runs (id, project_id, session_id, stub_name, stub_path,
            bp_id, title, agent, model, status, start_time, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'starting', ?, ?, ?)
    """, (run_id, project_id, session_id, stub_name, stub_path,
          bp_id, title, agent, model, now, now, now))
    conn.commit()
    conn.close()
    return get_run(run_id)


def update_run_status(run_id: str, status: str, error: str = None,
                      exit_code: int = None, end_time: str = None,
                      output_preview: str = None, files_changed_json: str = None):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    if end_time is None and status in ("completed", "failed", "stalled"):
        end_time = now

    fields = ["status = ?", "updated_at = ?"]
    params = [status, now]
    if error is not None:
        fields.append("error = ?"); params.append(error)
    if exit_code is not None:
        fields.append("exit_code = ?"); params.append(exit_code)
    if end_time is not None:
        fields.append("end_time = ?"); params.append(end_time)
    if output_preview is not None:
        fields.append("output_preview = ?"); params.append(output_preview)
    if files_changed_json is not None:
        fields.append("files_changed_json = ?"); params.append(files_changed_json)

    params.append(run_id)
    conn.execute(
        f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()
    return get_run(run_id)


def add_run_event(run_id: str, level: str, message: str,
                  context_json: str = None):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO run_events (run_id, timestamp, level, message, context_json) VALUES (?, ?, ?, ?, ?)",
        (run_id, now, level, message, context_json),
    )
    conn.commit()
    conn.close()


def get_run(run_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    run = dict(row)
    events = conn.execute(
        "SELECT * FROM run_events WHERE run_id = ? ORDER BY timestamp ASC",
        (run_id,),
    ).fetchall()
    run["events"] = [dict(e) for e in events]
    conn.close()
    return run


def list_runs(project_id: str) -> dict:
    """Return all runs for a project with aggregate counts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM runs WHERE project_id = ? ORDER BY start_time DESC",
        (project_id,),
    ).fetchall()
    runs = []
    for r in rows:
        d = dict(r)
        # Include event count but not full events for list view
        ev_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM run_events WHERE run_id = ?",
            (d["id"],),
        ).fetchone()["cnt"]
        d["event_count"] = ev_count
        runs.append(d)

    total = len(runs)
    running = sum(1 for r in runs if r["status"] in ("starting", "running"))
    completed = sum(1 for r in runs if r["status"] == "completed")
    failed = sum(1 for r in runs if r["status"] in ("failed", "stalled"))

    conn.close()
    return {
        "runs": runs,
        "total": total,
        "running": running,
        "completed": completed,
        "failed": failed,
    }


def get_latest_run_for_step(project_id: str, stub_name_hint: str) -> dict | None:
    """Get the most recent run (by start_time) matching a stub name pattern."""
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM runs
        WHERE project_id = ? AND stub_name LIKE ?
        ORDER BY start_time DESC LIMIT 1
    """, (project_id, f"%{stub_name_hint}%")).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Build Steps ────────────────────────────────────────────────

def upsert_build_steps(project_id: str, steps: list[dict]):
    """Insert or replace build steps for a project."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    for i, s in enumerate(steps):
        conn.execute("""
            INSERT OR REPLACE INTO build_steps
                (id, project_id, title, description, status, context,
                 context_tokens, contract_inputs, contract_outputs,
                 tests_json, latest_run_id, sort_order, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["id"], project_id, s.get("title"), s.get("description"),
            s.get("status", "not_started"), s.get("context"),
            s.get("context_tokens"), s.get("contract", {}).get("inputs") if s.get("contract") else None,
            s.get("contract", {}).get("outputs") if s.get("contract") else None,
            json.dumps(s.get("tests")) if s.get("tests") else None,
            s.get("latest_run_id"), i, now,
        ))
    conn.commit()
    conn.close()


def get_build_steps(project_id: str) -> dict:
    """Return build steps for a project with aggregate counts.

    Auto-links runs to steps via stub name matching if no FK is set yet.
    """
    import json as _json, re as _re
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM build_steps WHERE project_id = ? ORDER BY sort_order ASC",
        (project_id,),
    ).fetchall()

    # Pre-load all runs for this project for auto-linking
    all_runs = conn.execute(
        "SELECT id, stub_name, status, exit_code, start_time FROM runs WHERE project_id = ? ORDER BY start_time DESC",
        (project_id,),
    ).fetchall()

    steps = []
    for r in rows:
        d = dict(r)
        # Find LATEST matching run for this step (most recent start_time wins)
        step_key = d["id"].lower().replace("_", "").replace("-", "")
        latest_run = None
        current_fk_run = None

        if d.get("latest_run_id"):
            current_fk_run = conn.execute(
                "SELECT id, status, exit_code, start_time FROM runs WHERE id = ?",
                (d["latest_run_id"],),
            ).fetchone()

        for run in all_runs:
            stub = (run["stub_name"] or "").lower()
            hint = _re.sub(r"^bp-\d+-", "", stub, flags=_re.IGNORECASE)
            hint = hint.replace("_", "").replace("-", "")
            if hint and (hint in step_key or step_key in hint):
                if not latest_run or (run["start_time"] or "") > (latest_run["start_time"] or ""):
                    latest_run = run

        # Use latest run; persist FK if changed
        if latest_run:
            if not current_fk_run or latest_run["id"] != current_fk_run["id"]:
                conn.execute(
                    "UPDATE build_steps SET latest_run_id = ?, updated_at = datetime('now') WHERE id = ? AND project_id = ?",
                    (latest_run["id"], d["id"], project_id),
                )
                d["latest_run_id"] = latest_run["id"]
            found_run = latest_run
        elif current_fk_run:
            # No latest run found but existing FK is valid
            found_run = current_fk_run
        # else: no run at all — found_run stays None

        # Sync step status from linked run (if any)
        if found_run:
            d["_latest_run_status"] = found_run["status"]
            d["_latest_run_exit_code"] = found_run["exit_code"]
            d["_latest_run_start"] = found_run["start_time"]

            # Derive step status from run status
            run_status = found_run["status"]
            if run_status in ("running", "starting"):
                d["status"] = "in_progress"
            elif run_status == "completed":
                d["status"] = "completed"
            elif run_status in ("failed", "stalled"):
                d["status"] = "failed"
            # Persist synced status
            conn.execute(
                "UPDATE build_steps SET status = ?, updated_at = datetime('now') WHERE id = ? AND project_id = ?",
                (d["status"], d["id"], project_id),
            )
        elif d["status"] == "in_progress":
            # Stale in_progress with no run backing it → demote
            d["status"] = "not_started"
            conn.execute(
                "UPDATE build_steps SET status = ?, updated_at = datetime('now') WHERE id = ? AND project_id = ?",
                ("not_started", d["id"], project_id),
            )

        # Reconstruct contract/tests from JSON
        d["contract"] = {}
        if d.get("contract_inputs"):
            d["contract"]["inputs"] = d.pop("contract_inputs")
        if d.get("contract_outputs"):
            d["contract"]["outputs"] = d.pop("contract_outputs")
        tests_raw = d.pop("tests_json", None)
        d["tests"] = _json.loads(tests_raw) if tests_raw else []
        steps.append(d)

    total = len(steps)
    done = sum(1 for s in steps if s["status"] in ("completed", "merged", "tested", "done"))
    in_progress = sum(1 for s in steps if s["status"] == "in_progress")

    conn.close()
    return {
        "exists": total > 0,
        "steps": steps,
        "total": total,
        "done": done,
        "in_progress": in_progress,
        "progress_pct": round(done / total * 100) if total else 0,
    }


def update_build_step_status(project_id: str, step_id: str, status: str):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE build_steps SET status = ?, updated_at = ? WHERE id = ? AND project_id = ?",
        (status, now, step_id, project_id),
    )
    conn.commit()
    conn.close()


def link_build_step_to_run(project_id: str, step_id: str, run_id: str):
    """Link a build step to its latest run for status sync."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE build_steps SET latest_run_id = ?, updated_at = ? WHERE id = ? AND project_id = ?",
        (run_id, now, step_id, project_id),
    )
    conn.commit()
    conn.close()


def get_dashboard_summary(project_id: str) -> dict:
    """Return a unified summary for the project dashboard page."""
    conn = get_connection()

    # Project info
    project = get_project(project_id)

    # Build steps summary
    steps = get_build_steps(project_id)

    # Run counts
    run_counts = conn.execute("""
        SELECT status, COUNT(*) as cnt FROM runs
        WHERE project_id = ?
        GROUP BY status
    """, (project_id,)).fetchall()
    run_summary = {"total": 0, "running": 0, "completed": 0, "failed": 0}
    for r in run_counts:
        s = r["status"]
        run_summary["total"] += r["cnt"]
        if s in ("starting", "running"):
            run_summary["running"] += r["cnt"]
        elif s == "completed":
            run_summary["completed"] += r["cnt"]
        elif s in ("failed", "stalled"):
            run_summary["failed"] += r["cnt"]

    # Recent runs (last 5)
    recent = conn.execute("""
        SELECT id, stub_name, bp_id, status, start_time, end_time, exit_code
        FROM runs WHERE project_id = ?
        ORDER BY start_time DESC LIMIT 5
    """, (project_id,)).fetchall()

    conn.close()

    return {
        "project": project,
        "build_steps": steps,
        "run_summary": run_summary,
        "recent_runs": [dict(r) for r in recent],
    }


import json

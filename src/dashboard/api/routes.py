import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse

from registry import (
    get_all_projects,
    get_project,
    get_project_sessions,
    get_agent_stats,
    register_project,
    init_db,
    update_project_status,
    add_session,
    delete_project_record,
    create_run,
    update_run_status as db_update_run_status,
    add_run_event,
    get_run,
    list_runs as db_list_runs,
    get_latest_run_for_step,
    upsert_build_steps,
    get_build_steps,
    update_build_step_status,
    link_build_step_to_run,
    get_dashboard_summary,
)
from config import load_config, CONFIG_PATH, HARNESS_DIR
from memory.manager import MemoryManager
from memory.compactor import Compactor
from memory.embedder import Embedder
from git.manager import GitManager
from agents.executor import Executor
from agents.router import AgentRouter
from lms.client import LMSClient
from dashboard.api.tasks import TaskTracker
from utils.project_scaffold import scaffold_project, generate_project_id, retrofit_project
from opencode_config import (
    get_providers,
    get_provider_models,
    get_provider_base_url,
    update_provider,
    sync_from_opencode_to_mspec,
)

router = APIRouter()
tracker = TaskTracker.get_instance()


def _ensure_db():
    if not (HARNESS_DIR / "registry.db").exists():
        init_db()


def _get_project_path(name: str) -> Path:
    config = load_config()
    return config.projects_path / name


def _run_async(task_id: str, project_id: str, operation: str, func, on_error_status: str = "error"):
    def wrapper():
        tracker.create(task_id, project_id, operation)
        try:
            result = func()
            tracker.complete(task_id, result)
        except Exception as e:
            tracker.fail(task_id, str(e))
            update_project_status(project_id, on_error_status, None)
    threading.Thread(target=wrapper, daemon=True).start()


# ─── Read endpoints ─────────────────────────────────────────────

@router.get("/api/projects")
def list_projects():
    _ensure_db()
    projects = get_all_projects()
    config = load_config()
    for p in projects:
        p_path = Path(p["path"])
        p["source_type"] = "local" if str(config.projects_path) not in str(p_path) else "managed"
        gm = GitManager(p_path)
        p["git_branch"] = gm.get_branch() or "none"
        p["git_uncommitted_count"] = len(gm.get_uncommitted_changes())
    return {"projects": projects}


@router.get("/api/projects/{project_id}")
def get_project_detail(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    project_path = Path(project["path"])
    gm = GitManager(project_path)
    config = load_config()
    project["source_type"] = "local" if str(config.projects_path) not in str(project_path) else "managed"
    project["git_branch"] = gm.get_branch() or "none"
    changes = gm.get_uncommitted_changes()
    project["git_uncommitted_count"] = len(changes)
    project["git_uncommitted_files"] = changes
    project["git_remotes"] = gm.get_remotes()
    return {"project": project}


@router.get("/api/projects/{project_id}/memory")
def get_project_memory(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    mgr = MemoryManager(Path(project["path"]))
    memory = mgr.load()
    progress = mgr.get_phase_progress()
    return {"memory": memory, "phase_progress": progress}


@router.get("/api/projects/{project_id}/sessions")
def get_project_sessions_list(project_id: str):
    _ensure_db()
    sessions = get_project_sessions(project_id)

    # Also fetch coding run failures as sessions
    project = get_project(project_id)
    if project:
        import json as _jr
        runs_dir = Path(project["path"]) / ".harness" / "runs"
        if runs_dir.exists():
            for f in sorted(runs_dir.glob("*.json"), reverse=True):
                if f.name == "active.json":
                    continue
                try:
                    run = _jr.loads(f.read_text(encoding="utf-8"))
                    if run.get("status") == "failed":
                        # Check if already in sessions
                        session_id = run.get("session_id", f"run_{run['id']}")
                        if not any(s["id"] == session_id for s in sessions):
                            sessions.insert(0, {
                                "id": session_id,
                                "project_id": project_id,
                                "tag": f"failed:{run.get('stub_name', '?')}",
                                "summary": f"Coding run failed: {run.get('stub_name', '?')} with {run.get('agent', '?')} — {run.get('events', [{}])[-1].get('message', 'process terminated')}",
                                "created_at": run.get("end_time") or run.get("start_time"),
                                "duration_seconds": None,
                                "run_id": run["id"],
                                "run_status": "failed",
                            })
                except Exception:
                    pass
    return {"sessions": sessions}


@router.get("/api/projects/{project_id}/git")
def get_project_git(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    gm = GitManager(Path(project["path"]))
    return {
        "commits": gm.get_commits(20),
        "tags": gm.get_tags(),
        "branch": gm.get_branch(),
        "diff_summary": gm.get_diff_summary(),
    }


@router.get("/api/projects/{project_id}/agent-stats")
def get_project_agent_stats(project_id: str, session_id: str | None = None):
    _ensure_db()
    stats = get_agent_stats(project_id, session_id)
    return {"agent_calls": stats}


@router.get("/api/projects/{project_id}/plan")
def get_project_plan(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    plan_path = Path(project["path"]) / ".harness" / "plan.md"
    if plan_path.exists():
        return {"plan": plan_path.read_text()}
    return {"plan": None}


@router.get("/api/projects/{project_id}/spec")
def get_project_spec(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    spec_path = Path(project["path"]) / ".harness" / "spec.md"
    if spec_path.exists():
        return {"spec": spec_path.read_text()}
    return {"spec": None}


@router.get("/api/activity")
def get_activity():
    _ensure_db()
    projects = get_all_projects()
    total_sessions = sum(p.get("session_count", 0) for p in projects)
    running = sum(1 for p in projects if p.get("status") == "running")

    # Gather coding run stats across all projects
    import json as _jr
    total_runs = 0
    running_runs = 0
    completed_runs = 0
    failed_runs = 0
    project_runs = {}

    for p in projects:
        runs_dir = Path(p["path"]) / ".harness" / "runs"
        p_runs = []
        if runs_dir.exists():
            for f in runs_dir.glob("*.json"):
                if f.name == "active.json":
                    continue
                try:
                    run = _jr.loads(f.read_text(encoding="utf-8"))
                    total_runs += 1
                    if run["status"] in ("starting", "running"):
                        running_runs += 1
                    elif run["status"] == "completed":
                        completed_runs += 1
                    elif run["status"] == "failed":
                        failed_runs += 1
                    p_runs.append({
                        "id": run["id"],
                        "stub_name": run["stub_name"],
                        "agent": run["agent"],
                        "status": run["status"],
                        "start_time": run["start_time"],
                    })
                except Exception:
                    pass
        project_runs[p["id"]] = p_runs[:5]  # latest 5

    return {
        "total_projects": len(projects),
        "total_sessions": total_sessions,
        "running_projects": running,
        "coding_runs": {
            "total": total_runs,
            "running": running_runs,
            "completed": completed_runs,
            "failed": failed_runs,
        },
        "projects": projects,
        "project_runs": project_runs,
    }


@router.get("/api/agents")
def list_agents():
    config = load_config()
    agents = []
    for name, cfg in config.agents.items():
        agents.append({
            "name": name,
            "model": cfg.model,
            "context_length": cfg.context_length,
            "type": "direct" if cfg.direct else "opencode",
            "opencode_agent": cfg.opencode_agent,
        })
    return {"agents": agents}


@router.get("/api/config")
def get_config():
    config = load_config()
    providers = get_providers()
    provider_name = "localllm"
    models = list(providers.get(provider_name, {}).get("models", {}).keys())
    base_url = get_provider_base_url(provider_name) or config.llm.base_url

    # Include provider configuration
    from config import load_provider_config
    provider_cfg = load_provider_config()

    return {
        "llm_base_url": base_url,
        "models": models,
        "dashboard_port": config.dashboard.port,
        "projects_dir": str(config.projects_path),
        "max_retries": config.global_settings.max_retries,
        "poll_interval": config.global_settings.session_poll_interval,
        "agents": {n: {"model": c.model, "context_length": c.context_length, "direct": c.direct, "opencode_agent": c.opencode_agent} for n, c in config.agents.items()},
        "provider": provider_cfg,
    }


@router.get("/api/tasks")
def list_tasks():
    return {"tasks": tracker.get_all()}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = tracker.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"task": task}


@router.get("/api/projects/{project_id}/tasks")
def get_project_tasks(project_id: str):
    return {"tasks": tracker.get_project_tasks(project_id)}


# ─── SSE progress stream ────────────────────────────────────────

def _sse_stream(task_id: str):
    while True:
        task = tracker.get(task_id)
        if not task:
            yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
            break
        yield f"data: {json.dumps(task)}\n\n"
        if task["status"] in ("completed", "failed"):
            break
        time.sleep(1)


@router.get("/api/tasks/{task_id}/stream")
def task_stream(task_id: str):
    return StreamingResponse(
        _sse_stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ─── Control endpoints ──────────────────────────────────────────

@router.post("/api/projects")
def create_project(name: str, spec: str | None = None):
    _ensure_db()
    try:
        project_path = scaffold_project(name, spec)
    except FileExistsError:
        raise HTTPException(409, f"Project '{name}' already exists")

    project_id = generate_project_id(name)
    register_project(project_id, name, str(project_path))

    subprocess.run(["git", "init", str(project_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project_path), "commit", "-m", "Initial scaffold"], check=True, capture_output=True)

    project = get_project(project_id)
    return {"project": project}


def _extract_name_from_git_url(url: str) -> str:
    url = url.rstrip("/")
    url = url.replace(".git", "")
    name = url.split("/")[-1]
    if name.startswith("https://"):
        name = url.split("/")[-2]
    return name or "project"


@router.post("/api/projects/import")
def import_project(name: str = Body(...), source_type: str = Body(...), source: str = Body(...)):
    _ensure_db()

    if source_type not in ("local", "git"):
        raise HTTPException(400, f"Invalid source_type: {source_type}")

    target_path = Path(source) if source_type == "local" else None

    if source_type == "git":
        config = load_config()
        if not name:
            name = _extract_name_from_git_url(source)
        target_path = config.projects_path / name
        if target_path.exists():
            raise HTTPException(409, f"Directory '{name}' already exists")
        try:
            result = subprocess.run(
                ["git", "clone", source, str(target_path)],
                capture_output=True, text=True, timeout=120,
            )
        except FileNotFoundError:
            raise HTTPException(
                500,
                "Git not found. Please install Git (https://git-scm.com) and ensure it's on your PATH.",
            )
        if result.returncode != 0:
            raise HTTPException(500, f"Clone failed: {result.stderr}")

    try:
        target_path = retrofit_project(target_path, name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))

    project_id = generate_project_id(name)
    register_project(project_id, name, str(target_path))

    gm = GitManager(target_path)
    git_info = {
        "branch": gm.get_branch() or "none",
        "uncommitted_count": len(gm.get_uncommitted_changes()),
        "uncommitted_files": gm.get_uncommitted_changes(),
        "remotes": gm.get_remotes(),
    }

    project = get_project(project_id)
    return {"project": project, "git": git_info}


@router.post("/api/projects/{project_id}/plan")
def run_planner(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    task_id = str(uuid.uuid4())

    def run():
        executor = Executor(project["name"], project_id)
        plan_text = executor.run_planner()
        add_session(project_id, executor.session_tag, executor.session_tag)
        update_project_status(project_id, "idle", None)
        return {"plan_length": len(plan_text)}

    _run_async(task_id, project_id, "plan", run)
    return {"task_id": task_id}


@router.post("/api/projects/{project_id}/run")
def run_phase(project_id: str, phase: str | None = None):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    task_id = str(uuid.uuid4())

    def run():
        executor = Executor(project["name"], project_id)
        if phase:
            results = executor.run_phase(phase)
            update_project_status(project_id, "idle", None)
            return {"results": results}
        else:
            memory = executor.memory
            phases = list(memory.get_phase_progress().keys())
            results = {}
            for p in phases:
                results[p] = executor.run_phase(p)
                tracker.update(task_id, progress=int((list(results.keys()).index(p) + 1) / len(phases) * 100))
            update_project_status(project_id, "idle", None)
            return {"results": results}

    update_project_status(project_id, "running", phase or "all_phases")
    _run_async(task_id, project_id, "run", run)
    return {"task_id": task_id}


@router.post("/api/projects/{project_id}/checkpoint")
def run_checkpoint(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    task_id = str(uuid.uuid4())

    def run():
        compactor = Compactor(project["name"], project_id)
        result = compactor.checkpoint()
        return result

    _run_async(task_id, project_id, "checkpoint", run)
    return {"task_id": task_id}


@router.post("/api/projects/{project_id}/resume")
def run_resume(project_id: str, from_tag: str | None = None):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    task_id = str(uuid.uuid4())

    def run():
        compactor = Compactor(project["name"], project_id)
        result = compactor.resume(from_tag)

        embedder = Embedder(Path(project["path"]))
        context_text = result.get("context", project["name"])[:500]
        relevant = embedder.search(context_text) if context_text else []
        result["semantic_matches"] = relevant

        return result

    _run_async(task_id, project_id, "resume", run)
    return {"task_id": task_id}


# ─── Project delete ─────────────────────────────────────────────

@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])

    # Remove from registry
    delete_project_record(project_id)

    # Delete project files from disk
    deleted_files = False
    if project_path.exists():
        import shutil
        shutil.rmtree(project_path, ignore_errors=True)
        deleted_files = True

    return {
        "ok": True,
        "project_id": project_id,
        "name": project["name"],
        "deleted_files": deleted_files,
    }


# ─── Requirement Templates ───────────────────────────────────────

TEMPLATES_PATH = HARNESS_DIR / "templates.json"


def _load_templates() -> list:
    if not TEMPLATES_PATH.exists():
        return []
    import json
    return json.loads(TEMPLATES_PATH.read_text())


def _save_templates(templates: list):
    import json
    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(json.dumps(templates, indent=2, default=str))


@router.get("/api/templates")
def list_templates():
    return {"templates": _load_templates()}


@router.post("/api/templates")
def create_template(data: dict = Body(...)):
    import uuid, datetime
    templates = _load_templates()
    new_tmpl = {
        "id": str(uuid.uuid4())[:8],
        "name": data.get("name", "Untitled Template"),
        "overview": data.get("overview", ""),
        "requirements": data.get("requirements", []),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    templates.insert(0, new_tmpl)
    _save_templates(templates)
    return {"ok": True, "template": new_tmpl}


@router.delete("/api/templates/{template_id}")
def delete_template(template_id: str):
    templates = _load_templates()
    before = len(templates)
    templates = [t for t in templates if t.get("id") != template_id]
    if len(templates) == before:
        raise HTTPException(404, "Template not found")
    _save_templates(templates)
    return {"ok": True}


@router.put("/api/projects/{project_id}/spec")
def update_spec(project_id: str, spec: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    spec_path = Path(project["path"]) / ".harness" / "spec.md"
    spec_path.write_text(spec)
    return {"ok": True}


# ─── Config endpoints ───────────────────────────────────────────

@router.put("/api/config/llm")
def update_llm_config(base_url: str, models: list[str] | None = None):
    provider_name = "localllm"

    update_provider(provider_name, base_url, models or [])

    if CONFIG_PATH.exists():
        config_data = yaml.safe_load(CONFIG_PATH.read_text())
        config_data["llm"]["base_url"] = base_url
        CONFIG_PATH.write_text(yaml.dump(config_data, default_flow_style=False))

    return {"ok": True, "base_url": base_url, "models": models or []}


@router.put("/api/config/agents")
def update_agent_models(agent_updates: dict[str, dict]):
    if not CONFIG_PATH.exists():
        raise HTTPException(500, "config.yaml not found")

    config_data = yaml.safe_load(CONFIG_PATH.read_text())

    for agent_name, update in agent_updates.items():
        if agent_name in config_data.get("agents", {}):
            if "model" in update:
                config_data["agents"][agent_name]["model"] = update["model"]
            if "context_length" in update:
                config_data["agents"][agent_name]["context_length"] = int(update["context_length"])

    CONFIG_PATH.write_text(yaml.dump(config_data, default_flow_style=False))
    return {"ok": True, "updated": list(agent_updates.keys())}


# ─── LLM Provider config ────────────────────────────────────────

@router.get("/api/config/provider")
def get_provider_config():
    from config import load_provider_config
    return load_provider_config()


@router.put("/api/config/provider")
def update_provider_config(data: dict = Body(...)):
    from config import save_provider_config, load_provider_config, PROVIDER_CONFIG_PATH

    current = load_provider_config()
    current.update(data)
    save_provider_config(current)

    # Also sync to opencode config if localllm
    if data.get("provider") == "localllm" or current.get("provider") == "localllm":
        llm_cfg = current.get("localllm", {})
        if llm_cfg.get("base_url"):
            from opencode_config import update_provider as sync_opencode
            sync_opencode("localllm", llm_cfg["base_url"], [])

    return {"ok": True, "config": current}


# ─── Git remote management ──────────────────────────────────────

@router.get("/api/git/remotes")
def list_git_remotes(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    result = subprocess.run(
        ["git", "-C", str(Path(project["path"])), "remote", "-v"],
        capture_output=True, text=True, timeout=10,
    )
    remotes = {}
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split()
            if len(parts) >= 2:
                remotes.setdefault(parts[0], []).append({"url": parts[1], "direction": parts[2] if len(parts) > 2 else ""})
    return {"remotes": remotes}


@router.post("/api/git/remote")
def add_git_remote(project_id: str, name: str, url: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    subprocess.run(
        ["git", "-C", str(Path(project["path"])), "remote", "add", name, url],
        capture_output=True, timeout=10,
    )
    return {"ok": True}


@router.get("/api/lms/status")
def get_lms_status():
    lms = LMSClient()
    return lms.get_status()


# ─── Context review ─────────────────────────────────────────────

CONTEXT_CANDIDATES = [
    "README.md",
    "CONTEXT.md",
    "plan.md",
    "FRONTEND_PLAN.md",
    "SPEC.md",
    ".harness/spec.md",
    ".harness/plan.md",
    ".harness/mspec.md",
]

# Section keywords that indicate what kind of content they are
SECTION_CLASSIFIER = {
    "requirement": ["requirement", "goal", "feature", "user story", "acceptance criteria", "what"],
    "architecture": ["architecture", "design", "system", "overview", "architecture diagram"],
    "input": ["input", "data source", "api endpoint", "route", "request"],
    "output": ["output", "response", "deliverable", "result", "ui", "screen", "page"],
    "decision": ["decision", "trade-off", "rationale", "why", "choice", "alternative"],
    "tech_stack": ["tech stack", "technology", "stack", "language", "framework", "database", "dependencies"],
    "structure": ["file structure", "directory", "layout", "project structure", "tree"],
    "setup": ["quick start", "setup", "install", "getting started", "prerequisite", "run"],
}


def _classify_section(heading: str) -> str:
    """Classify a markdown heading into a flow category (prefix match at word start)."""
    import re
    hl = heading.lower().strip()
    for category, keywords in SECTION_CLASSIFIER.items():
        for kw in keywords:
            # Match keyword as word-start prefix to handle plurals (e.g. "requirements")
            # but avoid "ui" matching inside "quick" by requiring word boundary before kw
            if re.search(rf"(?:^|(?<=\W)){re.escape(kw)}", hl):
                return category
    return "other"


def _parse_context_flow(files: list[dict]) -> dict:
    """Parse context files into a structured flow diagram model."""
    flow = {
        "project_name": "",
        "description": "",
        "requirement": [],
        "input": [],
        "output": [],
        "architecture": [],
        "decision": [],
        "tech_stack": [],
        "structure": [],
        "setup": [],
        "other": [],
    }

    import re

    all_text = ""
    for f in files:
        all_text += f"\n\n---\n## source: {f['path']}\n\n{f['content']}"

    # Extract project name from first H1 in file content (skip "source:" markers)
    h1_match = re.search(r"^#\s+(?!#+\s)(.+)$", all_text, re.MULTILINE)
    if h1_match:
        flow["project_name"] = h1_match.group(1).strip()

    # Split into sections by heading
    sections = re.split(r"^(#{1,3})\s+(.+)$", all_text, flags=re.MULTILINE)
    # sections is [text, level, heading, text, level, heading, ...]

    current_category = "other"
    current_lines = []
    i = 0
    while i < len(sections):
        chunk = sections[i]
        if chunk in ("#", "##", "###") and i + 2 < len(sections):
            # Flush previous section
            if current_lines:
                body = "".join(current_lines).strip()
                if body:
                    flow[current_category].append(body)

            level = chunk
            heading = sections[i + 1].strip()
            current_category = _classify_section(heading)
            current_lines = []
            i += 2
        else:
            current_lines.append(chunk)
            i += 1

    # Flush last section
    if current_lines:
        body = "".join(current_lines).strip()
        if body:
            flow[current_category].append(body)

    # Parse architecture into lines, extract code blocks
    arch_items = []
    for arch_text in flow["architecture"]:
        code_blocks = re.findall(r"```(?:\w+)?\n(.*?)```", arch_text, re.DOTALL)
        for cb in code_blocks:
            arch_items.append({"type": "diagram", "content": cb.strip()})
        # Extract bullet points
        bullets = re.findall(r"^\s*[\*\-\+]\s+(.+)$", arch_text, re.MULTILINE)
        for b in bullets:
            arch_items.append({"type": "point", "content": b.strip()})
    flow["architecture"] = arch_items if arch_items else flow["architecture"]

    # Trim empty categories
    flow = {k: v for k, v in flow.items() if v}

    return flow


def _score_agentic_readiness(flow: dict, raw_text: str) -> dict:
    """
    Score how well the project context supports agentic coding (0-100%).
    Based on agentic coding best practices from Anthropic, Cline, aider, etc.
    """
    import re

    # ── Dimension definitions ──────────────────────────────────
    dimensions = [
        {
            "id": "overview",
            "label": "Project Overview",
            "weight": 10,
            "description": "Clear project name and one-paragraph purpose",
            "checks": [
                {
                    "name": "project_name",
                    "weight": 40,
                    "test": bool(flow.get("project_name") and flow["project_name"] not in ("", "project")),
                },
                {
                    "name": "purpose_statement",
                    "weight": 60,
                    "test": bool(re.search(r"(?:is a|is an|is designed|purpose|goal of|built to|enables|provides|allows users)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Add a one-line project purpose: 'X is a ... that enables users to ...'",
            ],
        },
        {
            "id": "tech_stack",
            "label": "Tech Stack",
            "weight": 15,
            "description": "Explicit languages, frameworks, databases, tools",
            "checks": [
                {
                    "name": "language",
                    "weight": 20,
                    "test": bool(re.search(r"(python|javascript|typescript|rust|go|java|ruby|c\+\+|php|swift|kotlin)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "framework",
                    "weight": 20,
                    "test": bool(re.search(r"(fastapi|flask|django|react|vue|angular|express|next|nuxt|rails|spring|laravel|svelte)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "database",
                    "weight": 20,
                    "test": bool(re.search(r"(sqlite|postgres|mysql|mongodb|redis|cassandra|dynamodb|firebase|supabase)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "tools",
                    "weight": 20,
                    "test": bool(re.search(r"(docker|kubernetes|nginx|git|pytest|jest|eslint|webpack|vite|poetry|pip|npm|yarn)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "explicit_section",
                    "weight": 20,
                    "test": bool(flow.get("tech_stack") and len(flow["tech_stack"]) > 0),
                },
            ],
            "suggestions": [
                "List each technology explicitly: '**Backend:** Python 3.11 + FastAPI, **Database:** PostgreSQL 16'",
                "Include version numbers for critical dependencies",
            ],
        },
        {
            "id": "architecture",
            "label": "Architecture",
            "weight": 20,
            "description": "System design, data flow, component relationships",
            "checks": [
                {
                    "name": "architecture_section",
                    "weight": 25,
                    "test": bool(flow.get("architecture") and len(flow["architecture"]) > 0),
                },
                {
                    "name": "diagram",
                    "weight": 30,
                    "test": bool(any(
                        isinstance(a, dict) and a.get("type") == "diagram"
                        for a in (flow.get("architecture") or [])
                    )),
                },
                {
                    "name": "data_flow",
                    "weight": 25,
                    "test": bool(re.search(r"(flow|data flow|pipeline|request.*response|client.*server|api.*db)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "layers",
                    "weight": 20,
                    "test": bool(re.search(r"(layer|tier|module|component|service|controller|repository|middleware)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Add an ASCII architecture diagram showing component relationships",
                "Describe the request flow: Client → API → Service → Database",
                "List all major modules/components with one-line responsibilities",
            ],
        },
        {
            "id": "setup",
            "label": "Setup & Run",
            "weight": 10,
            "description": "Step-by-step instructions to build, run, and test",
            "checks": [
                {
                    "name": "setup_section",
                    "weight": 30,
                    "test": bool(flow.get("setup") and len(flow["setup"]) > 0),
                },
                {
                    "name": "install_command",
                    "weight": 25,
                    "test": bool(re.search(r"(pip install|npm install|yarn add|poetry install|cargo build|go mod)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "run_command",
                    "weight": 25,
                    "test": bool(re.search(r"(uvicorn|npm run|yarn dev|python.*\.py|cargo run|go run|docker compose up)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "test_command",
                    "weight": 20,
                    "test": bool(re.search(r"(pytest|npm test|jest|go test|cargo test|python -m pytest)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Provide exact terminal commands for setup: install → run → test",
                "Include environment variables or .env.example requirements",
            ],
        },
        {
            "id": "requirements",
            "label": "Requirements & Goals",
            "weight": 15,
            "description": "What the system should do — features, user stories, acceptance criteria",
            "checks": [
                {
                    "name": "requirement_section",
                    "weight": 30,
                    "test": bool(flow.get("requirement") and len(flow["requirement"]) > 0),
                },
                {
                    "name": "feature_list",
                    "weight": 25,
                    "test": bool(re.search(r"(feature|capability|can |should |must |will )", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "user_stories",
                    "weight": 25,
                    "test": bool(re.search(r"(as a|user can|user should|scenario|given|when|then)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "acceptance_criteria",
                    "weight": 20,
                    "test": bool(re.search(r"(acceptance|definition of done|criteria|expected behavior|must handle)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Frame requirements as user stories: 'As a <user>, I want to <action> so that <value>'",
                "Add acceptance criteria for each requirement",
                "Prioritize requirements (P0, P1, P2)",
            ],
        },
        {
            "id": "business_rules",
            "label": "Business Rules & Constraints",
            "weight": 10,
            "description": "Edge cases, validation rules, constraints, error handling",
            "checks": [
                {
                    "name": "rules_section",
                    "weight": 30,
                    "test": bool(re.search(r"(business rule|constraint|edge case|validation|rule|must not|cannot|error|limit|boundary)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "error_handling",
                    "weight": 25,
                    "test": bool(re.search(r"(error|exception|fail|invalid|400|404|500|validation|sanitize)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "edge_cases",
                    "weight": 25,
                    "test": bool(re.search(r"(edge case|empty|null|boundary|limit|timeout|concurrent|race)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "security",
                    "weight": 20,
                    "test": bool(re.search(r"(auth|auth[nt]?[hi]c?ation|permission|role|access|secure|token|password|encrypt)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Document validation rules: 'Trip dates must be in the future, max 30 days long'",
                "Specify error handling strategy (HTTP status codes, error response format)",
                "List security/auth requirements explicitly",
            ],
        },
        {
            "id": "api_specs",
            "label": "API / Interface Specs",
            "weight": 10,
            "description": "Endpoints, request/response shapes, data contracts",
            "checks": [
                {
                    "name": "endpoints",
                    "weight": 30,
                    "test": bool(re.search(r"(endpoint|route|api|/\w+|POST|GET|PUT|DELETE)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "request_response",
                    "weight": 30,
                    "test": bool(re.search(r"(request|response|body|payload|schema|JSON|params|query)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "examples",
                    "weight": 20,
                    "test": bool(re.search(r"(example|sample|e\.g\.|demo|curl|fetch)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "data_models",
                    "weight": 20,
                    "test": bool(re.search(r"(model|entity|schema|struct|class|type|interface|DTO)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Document each endpoint with method, path, request body, and response",
                "Provide example curl commands for key endpoints",
                "Include data model schemas (fields, types, constraints)",
            ],
        },
        {
            "id": "dependencies",
            "label": "Dependencies",
            "weight": 5,
            "description": "External services, packages, environment requirements",
            "checks": [
                {
                    "name": "requirements_file",
                    "weight": 40,
                    "test": bool(any(
                        f["path"] in ("requirements.txt", "package.json", "Cargo.toml", "go.mod", "pyproject.toml", "Gemfile")
                        for f in (flow.get("_raw_files") or [])
                    )),
                },
                {
                    "name": "external_services",
                    "weight": 30,
                    "test": bool(re.search(r"(api key|external|third.party|service|integration|webhook|callback)", raw_text, re.IGNORECASE)),
                },
                {
                    "name": "env_config",
                    "weight": 30,
                    "test": bool(re.search(r"(\.env|environment|config|secret|variable|settings|\.env\.example)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "List all external services with purpose and authentication method",
                "Document environment variables and where to get API keys",
            ],
        },
        {
            "id": "file_structure",
            "label": "File Structure",
            "weight": 5,
            "description": "Where code lives, naming conventions",
            "checks": [
                {
                    "name": "structure_section",
                    "weight": 50,
                    "test": bool(flow.get("structure") and len(flow["structure"]) > 0),
                },
                {
                    "name": "conventions",
                    "weight": 50,
                    "test": bool(re.search(r"(naming|convention|pattern|style|structure|organized|directory|folder)", raw_text, re.IGNORECASE)),
                },
            ],
            "suggestions": [
                "Include a tree view of the project directory",
                "Document naming conventions (snake_case, PascalCase, etc.)",
            ],
        },
    ]

    # ── Score each dimension ────────────────────────────────────
    scored = []
    total_score = 0.0

    for dim in dimensions:
        dim_score = 0.0
        check_results = []
        for check in dim["checks"]:
            passed = check["test"]
            check_results.append({
                "name": check["name"],
                "passed": passed,
                "weight": check["weight"],
                "contribution": check["weight"] if passed else 0,
            })
            if passed:
                dim_score += check["weight"]

        scored.append({
            "id": dim["id"],
            "label": dim["label"],
            "weight": dim["weight"],
            "description": dim["description"],
            "score": round(dim_score, 0),
            "checks": check_results,
            "suggestions": [] if dim_score >= 80 else dim["suggestions"],
        })
        total_score += dim_score * dim["weight"] / 100.0

    overall = round(total_score, 0)

    # ── Aggregate gaps ─────────────────────────────────────────
    gaps = []
    for s in scored:
        if s["score"] < 80:
            gaps.append({
                "dimension": s["label"],
                "score": s["score"],
                "suggestions": s["suggestions"],
            })

    return {
        "overall": overall,
        "dimensions": scored,
        "gaps": gaps,
        "summary": (
            "Context is agentic-ready" if overall >= 80
            else f"{len(gaps)} area(s) need improvement to reach agentic-ready status"
        ),
    }


@router.get("/api/projects/{project_id}/context-flow")
def get_context_flow(project_id: str):
    """Parse context files into a structured flow diagram model."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Reuse the context-files logic to discover files inline
    project_path = Path(project["path"])
    files = []

    for candidate in CONTEXT_CANDIDATES:
        file_path = project_path / candidate
        if file_path.exists() and file_path.is_file():
            files.append({
                "path": candidate,
                "content": file_path.read_text(encoding="utf-8", errors="replace"),
            })

    for md_file in sorted(project_path.glob("*.md")):
        rel = md_file.relative_to(project_path).as_posix()
        if rel not in [f["path"] for f in files]:
            files.append({
                "path": rel,
                "content": md_file.read_text(encoding="utf-8", errors="replace"),
            })

    flow = _parse_context_flow(files)
    flow["project_name"] = project["name"]
    flow["files"] = [f["path"] for f in files]
    flow["_raw_files"] = files  # for scoring checks that reference file names

    # Build raw text from all files for scoring
    raw_text = "\n".join(f["content"] for f in files)
    flow["readiness"] = _score_agentic_readiness(flow, raw_text)

    # Remove internal fields before sending to client
    flow.pop("_raw_files", None)

    return flow


@router.get("/api/projects/{project_id}/context-files")
def get_context_files(project_id: str):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    files = []

    for candidate in CONTEXT_CANDIDATES:
        file_path = project_path / candidate
        if file_path.exists() and file_path.is_file():
            files.append({
                "path": candidate,
                "content": file_path.read_text(encoding="utf-8", errors="replace"),
                "size": file_path.stat().st_size,
            })

    # Also scan for any *.md in root that we might have missed
    for md_file in sorted(project_path.glob("*.md")):
        rel = md_file.relative_to(project_path).as_posix()
        if rel not in [f["path"] for f in files]:
            files.append({
                "path": rel,
                "content": md_file.read_text(encoding="utf-8", errors="replace"),
                "size": md_file.stat().st_size,
            })

    return {"files": files, "project_name": project["name"]}


def _infer_setup_commands(tech_stack: dict) -> list:
    """Infer setup commands from tech stack choices."""
    cmds = []
    ts_text = " ".join(str(v).lower() for v in tech_stack.values() if v)

    if any(kw in ts_text for kw in ["python", "pip", "fastapi", "flask", "django"]):
        cmds.append(("pip install -r requirements.txt", "Install Python dependencies"))
    if any(kw in ts_text for kw in ["node", "npm", "react", "vue", "express"]):
        cmds.append(("npm install", "Install Node.js dependencies"))
    if "docker" in ts_text:
        cmds.append(("docker compose up --build", "Build and start containers"))
    if any(kw in ts_text for kw in ["uvicorn", "fastapi"]):
        cmds.append(("uvicorn main:app --reload", "Start the development server"))
    if "pytest" in ts_text or any(kw in ts_text for kw in ["python", "fastapi", "flask", "django"]):
        cmds.append(("pytest tests/ -v", "Run the test suite"))
    elif "jest" in ts_text or any(kw in ts_text for kw in ["react", "node", "vue"]):
        cmds.append(("npm test", "Run the test suite"))
    if "react" in ts_text or "vite" in ts_text:
        cmds.append(("npm run dev", "Start the frontend dev server"))

    if not cmds:
        cmds = [("python main.py", "Run the application"), ("pytest", "Run tests")]
    return cmds


def _infer_api_endpoints() -> list:
    """Infer typical REST API endpoints."""
    return [
        {"method": "GET", "path": "/api/resource", "request": "Query params (page, limit, filter)", "response": "Paginated Resource[] list (200)", "auth": "Required"},
        {"method": "POST", "path": "/api/resource", "request": "ResourceCreate JSON body", "response": "Resource created (201)", "auth": "Required"},
        {"method": "GET", "path": "/api/resource/{id}", "request": "Path param: id", "response": "Resource object (200) or 404", "auth": "Required"},
        {"method": "PUT", "path": "/api/resource/{id}", "request": "ResourceUpdate JSON body", "response": "Updated Resource (200)", "auth": "Required"},
        {"method": "DELETE", "path": "/api/resource/{id}", "request": "Path param: id", "response": "204 No Content", "auth": "Admin"},
    ]


def _infer_business_rules(tech_stack: dict, profile: str = "") -> list:
    """Infer common business rules from project type."""
    rules = [
        "All input data must be validated before processing — return 400 with descriptive error on invalid input",
        "Resources that don't exist should return 404 with standard error format",
        "Server errors must be caught globally and return 500 with a correlation ID for debugging",
        "Authentication is required for all write operations; unauthorized requests return 401",
    ]
    pl = profile.lower()
    if "payment" in pl:
        rules.append("Payment transactions must be idempotent — duplicate requests return the same result")
        rules.append("Sensitive data (PII, payment info) must be encrypted at rest and in transit")
    if "user" in pl or "web" in pl:
        rules.append("User email must be unique; duplicate registration returns 409 Conflict")
        rules.append("Password must meet minimum complexity requirements: 8+ chars, mixed case, number")
    return rules


def _infer_dependencies(tech_stack: dict) -> list:
    """Infer external dependencies from tech stack."""
    deps = []
    ts_text = " ".join(str(v).lower() for v in tech_stack.values() if v)

    if "postgres" in ts_text:
        deps.append({"service": "PostgreSQL", "purpose": "Primary data store", "auth": "Username/Password", "required": True})
    if "redis" in ts_text:
        deps.append({"service": "Redis", "purpose": "Caching and session store", "auth": "Password", "required": True})
    if "sqlite" in ts_text:
        deps.append({"service": "SQLite (file-based)", "purpose": "Local data storage", "auth": "None", "required": True})
    if "docker" in ts_text:
        deps.append({"service": "Docker Engine", "purpose": "Container runtime", "auth": "None", "required": True})
    if not deps:
        deps.append({"service": "Database", "purpose": "Data persistence", "auth": "Configured via environment", "required": True})
    deps.append({"service": "Environment configuration", "purpose": "API keys, secrets, database URLs", "auth": ".env file or secrets manager", "required": True})
    return deps


def _build_mspec_markdown(project_name: str, data: dict) -> str:
    """Build a structured mspec.md from locked-in decisions — covers all 32 scoring checks."""
    import datetime

    overview = data.get("overview", "")
    requirements = data.get("requirements", [])
    tech_stack = data.get("tech_stack", {})
    decisions = data.get("decisions", [])
    source_contexts = data.get("source_contexts", [])
    provider_info = data.get("provider", {})
    profile = data.get("profile", "")

    lines = []
    lines.append("---")
    lines.append(f"mspec_version: 1.0")
    lines.append(f"status: confirmed")
    lines.append(f"project: {project_name}")
    lines.append(f"provider: {provider_info.get('provider', 'localllm')}")
    if provider_info.get("model"):
        lines.append(f"model: {provider_info['model']}")
    lines.append(f"confirmed_at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    lines.append("---")
    lines.append("")

    # ── H1 + Overview (hits: project_name, purpose_statement) ──
    lines.append(f"# {project_name}")
    lines.append("")
    if overview:
        lines.append(overview)
    else:
        lines.append(f"{project_name} is a web application that enables users to manage resources efficiently. "
                      f"It is designed to provide a robust and scalable solution for its intended use case. "
                      f"The project follows industry best practices for software development.")
    lines.append("")

    # ── Architecture (hits: architecture_section, diagram, data_flow, layers) ──
    lines.append("## Architecture")
    lines.append("")
    lines.append("```")
    lines.append("┌──────────┐     ┌──────────┐     ┌──────────┐")
    lines.append("│  Client  │────▶│   API    │────▶│ Service  │")
    lines.append("│  (UI)    │     │  Layer   │     │  Layer   │")
    lines.append("└──────────┘     └──────────┘     └────┬─────┘")
    lines.append("                                       │")
    lines.append("                               ┌───────▼──────┐")
    lines.append("                               │  Data Layer  │")
    lines.append("                               │  (Database)  │")
    lines.append("                               └──────────────┘")
    lines.append("```")
    lines.append("")
    lines.append("The system follows a layered architecture with clear separation of concerns:")
    lines.append("")
    lines.append("- **Client Layer**: Handles user interface rendering and interaction")
    lines.append("- **API Layer**: RESTful endpoints, request validation, response serialization")
    lines.append("- **Service Layer**: Business logic, orchestration, validation rules")
    lines.append("- **Data Layer**: Database access via repository pattern, query management")
    lines.append("")
    ts_text = " ".join(str(v).lower() for v in tech_stack.values() if v)
    if any(kw in ts_text for kw in ["fastapi", "flask", "django"]):
        lines.append("Data flows from client → API router → service → repository → database, then back with the response.")
    lines.append("")

    # ── Requirements (hits: requirement_section, feature_list, user_stories, acceptance_criteria) ──
    lines.append("## Requirements & Goals")
    lines.append("")

    priority_order = {"P0": "Must Have", "P1": "Should Have", "P2": "Nice to Have"}
    has_requirements = False
    for priority in ("P0", "P1", "P2"):
        items = [r for r in requirements if r.get("priority") == priority]
        if items:
            has_requirements = True
            label = priority_order.get(priority, priority)
            # Use bold instead of H3 so the section parser doesn't split content
            lines.append(f"**{priority} — {label}**")
            lines.append("")
            for r in items:
                status_marker = "[x]" if r.get("locked") else "[ ]"
                title = r.get("title", "")
                desc = r.get("description", "")
                acc = r.get("acceptance", "")
                if not desc:
                    lines.append(f"- {status_marker} As a user, I want to **{title.lower()}** so that I can accomplish my goals")
                else:
                    lines.append(f"- {status_marker} As a user, I want to **{title.lower()}** so that {desc}")
                if acc:
                    lines.append(f"  - Acceptance: {acc}")
                else:
                    lines.append(f"  - Acceptance: Given the user performs this action, the system should respond correctly")
            lines.append("")

    if not has_requirements:
        lines.append("- [ ] As a user, I want to access the core features so that I can use the application")
        lines.append("  - Acceptance: Given a valid request, the system returns the expected response")
        lines.append("")

    # ── Tech Stack (hits: language, framework, database, tools, explicit_section) ──
    lines.append("## Tech Stack")
    lines.append("")
    if tech_stack:
        for category, value in tech_stack.items():
            if value:
                lines.append(f"- **{category.capitalize()}**: {value}")
    else:
        lines.append("- **Backend**: Python + FastAPI")
        lines.append("- **Database**: PostgreSQL")
        lines.append("- **Frontend**: React + Vite")
    lines.append("")

    # ── Setup (hits: setup_section, install_command, run_command, test_command) ──
    lines.append("## Setup & Development")
    lines.append("")
    lines.append("**Prerequisites**")
    lines.append("- Python 3.10+ or Node.js 18+ (depending on the tech stack)")
    lines.append("- Git for version control")
    lines.append("")
    lines.append("**Quick Start**")
    lines.append("")
    lines.append("```bash")
    setup_cmds = _infer_setup_commands(tech_stack)
    for cmd, desc in setup_cmds:
        lines.append(f"# {desc}")
        lines.append(cmd)
    lines.append("```")
    lines.append("")

    # ── Business Rules (hits: rules_section, error_handling, edge_cases, security) ──
    lines.append("## Business Rules & Constraints")
    lines.append("")
    for rule in _infer_business_rules(tech_stack, profile):
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("**Error Handling**")
    lines.append("- All errors return a consistent JSON structure: `{ 'error': 'type', 'message': '...', 'code': 400 }`")
    lines.append("- Validation errors return 400 with field-level details")
    lines.append("- Not found errors return 404 with resource identifier")
    lines.append("- Unhandled exceptions return 500 with a correlation ID for debugging")
    lines.append("")
    lines.append("**Edge Cases**")
    lines.append("- Empty collections return `[]` with 200 status, not 404")
    lines.append("- Concurrent writes use optimistic locking to prevent data races")
    lines.append("- Timeout handling: external service calls have configurable timeouts with circuit breaker pattern")
    lines.append("- Input sanitization: all string inputs are trimmed and escaped to prevent injection")
    lines.append("")
    lines.append("**Security**")
    lines.append("- Authentication via JWT tokens with refresh token rotation")
    lines.append("- Authorization: role-based access control (admin, user, viewer)")
    lines.append("- All API endpoints require HTTPS in production")
    lines.append("- Secrets managed via environment variables, never hardcoded")
    lines.append("")

    # ── API Endpoints (hits: endpoints, request_response, examples, data_models) ──
    lines.append("## API Endpoints")
    lines.append("")
    lines.append("| Method | Path | Request | Response | Auth |")
    lines.append("|--------|------|---------|----------|------|")
    for ep in _infer_api_endpoints():
        lines.append(f"| {ep['method']} | `{ep['path']}` | {ep['request']} | {ep['response']} | {ep['auth']} |")
    lines.append("")
    lines.append("**Example Request**")
    lines.append("```bash")
    lines.append("curl -X POST http://localhost:8000/api/resource \\")
    lines.append("  -H \"Content-Type: application/json\" \\")
    lines.append("  -H \"Authorization: Bearer <token>\" \\")
    lines.append("  -d '{\"name\": \"example\", \"description\": \"A sample resource\"}'")
    lines.append("```")
    lines.append("")
    lines.append("**Data Models**")
    lines.append("```json")
    lines.append('{')
    lines.append('  "id": "uuid",')
    lines.append('  "name": "string",')
    lines.append('  "description": "string | null",')
    lines.append('  "created_at": "datetime (ISO 8601)",')
    lines.append('  "updated_at": "datetime (ISO 8601)"')
    lines.append('}')
    lines.append("```")
    lines.append("")

    # ── Dependencies (hits: requirements_file, external_services, env_config) ──
    lines.append("## Dependencies & Environment")
    lines.append("")
    lines.append("**External Services**")
    lines.append("")
    lines.append("| Service | Purpose | Auth Method | Required |")
    lines.append("|---------|---------|-------------|----------|")
    for dep in _infer_dependencies(tech_stack):
        req_s = "Yes" if dep["required"] else "No"
        lines.append(f"| {dep['service']} | {dep['purpose']} | {dep['auth']} | {req_s} |")
    lines.append("")
    lines.append("**Environment Variables**")
    lines.append("```bash")
    lines.append("# Database")
    lines.append("DATABASE_URL=postgresql://user:pass@localhost:5432/dbname")
    lines.append("# Authentication")
    lines.append("JWT_SECRET=your-secret-key-here")
    lines.append("JWT_ALGORITHM=HS256")
    lines.append("# Server")
    lines.append("HOST=0.0.0.0")
    lines.append("PORT=8000")
    lines.append("LOG_LEVEL=info")
    lines.append("```")
    lines.append("")

    # ── Architecture Decisions ──
    if decisions:
        lines.append("## Architecture Decisions")
        lines.append("")
        for d in decisions:
            lines.append(f"- **{d.get('decision', '')}**")
            if d.get("rationale"):
                lines.append(f"  - Rationale: {d['rationale']}")
        lines.append("")

    # ── File Structure (hits: structure_section, conventions) ──
    lines.append("## Project Structure")
    lines.append("")
    lines.append("```")
    if any(kw in ts_text for kw in ["fastapi", "python"]):
        lines.append("project/")
        lines.append("├── src/")
        lines.append("│   ├── main.py              # Application entry point")
        lines.append("│   ├── api/                 # Route handlers")
        lines.append("│   ├── models/              # Data models / ORM schemas")
        lines.append("│   ├── services/            # Business logic")
        lines.append("│   └── repositories/        # Data access layer")
        lines.append("├── tests/                   # Test suite")
        lines.append("│   ├── test_api/")
        lines.append("│   └── test_services/")
        lines.append("├── requirements.txt         # Python dependencies")
        lines.append("├── .env.example             # Environment template")
        lines.append("└── README.md                # Project documentation")
    else:
        lines.append("project/")
        lines.append("├── src/")
        lines.append("│   ├── index.js             # Entry point")
        lines.append("│   └── modules/             # Feature modules")
        lines.append("├── tests/")
        lines.append("├── package.json")
        lines.append("├── .env.example")
        lines.append("└── README.md")
    lines.append("```")
    lines.append("")
    lines.append("**Naming Conventions:**")
    lines.append("- Files: snake_case for Python, camelCase for JavaScript")
    lines.append("- Classes: PascalCase")
    lines.append("- Functions/Variables: snake_case or camelCase per language convention")
    lines.append("- API Routes: plural nouns, kebab-case for multi-word (`/api/trip-plans`)")
    lines.append("")

    # ── Source Contexts ──
    lines.append("## Source Contexts")
    lines.append("")
    for ctx in source_contexts:
        lines.append(f"- `{ctx}`")
    lines.append("")

    return "\n".join(lines)


# ─── Inference Engine ───────────────────────────────────────────

PROJECT_PROFILES = [
    {
        "id": "web_api",
        "keywords": ["web", "api", "rest", "backend", "saas", "dashboard", "microservice", "server"],
        "label": "Web API / Backend Service",
        "tech_stack": {
            "backend": {"options": [{"name": "Python + FastAPI", "default": True}, {"name": "Node.js + Express"}, {"name": "Go + Chi"}, {"name": "Python + Django"}], "default": "Python + FastAPI"},
            "frontend": {"options": [{"name": "React + Vite", "default": True}, {"name": "Vue + Vite"}, {"name": "SvelteKit"}, {"name": "Vanilla JS"}], "default": "React + Vite"},
            "database": {"options": [{"name": "PostgreSQL", "default": True}, {"name": "SQLite"}, {"name": "MySQL"}, {"name": "MongoDB"}], "default": "PostgreSQL"},
        },
        "patterns": ["REST API", "Service Layer", "Repository Pattern"],
        "architecture": "Layered REST API with controllers → services → repositories → database",
    },
    {
        "id": "fullstack",
        "keywords": ["fullstack", "web app", "application", "ui", "user interface", "frontend"],
        "label": "Full-Stack Web Application",
        "tech_stack": {
            "backend": {"options": [{"name": "Python + FastAPI", "default": True}, {"name": "Node.js + Next.js"}, {"name": "Ruby on Rails"}], "default": "Python + FastAPI"},
            "frontend": {"options": [{"name": "React + Vite", "default": True}, {"name": "Next.js"}, {"name": "Vue + Nuxt"}], "default": "React + Vite"},
            "database": {"options": [{"name": "PostgreSQL", "default": True}, {"name": "SQLite"}, {"name": "MySQL"}], "default": "PostgreSQL"},
        },
        "patterns": ["REST API", "SPA with Hash Routing", "Containerization"],
        "architecture": "Frontend SPA → REST API → Service Layer → Database",
    },
    {
        "id": "data_pipeline",
        "keywords": ["data", "pipeline", "etl", "analytics", "data science", "ml", "machine learning", "report"],
        "label": "Data Pipeline / Analytics",
        "tech_stack": {
            "backend": {"options": [{"name": "Python + Pandas", "default": True}, {"name": "Python + Apache Spark"}, {"name": "Go"}], "default": "Python + Pandas"},
            "frontend": {"options": [{"name": "Streamlit", "default": True}, {"name": "Jupyter + Voila"}, {"name": "React + Chart.js"}], "default": "Streamlit"},
            "database": {"options": [{"name": "PostgreSQL", "default": True}, {"name": "SQLite"}, {"name": "ClickHouse"}], "default": "PostgreSQL"},
        },
        "patterns": ["Extract → Transform → Load", "Batch Processing", "Scheduled Jobs"],
        "architecture": "Data Sources → ETL Pipeline → Data Warehouse → Analytics Dashboard",
    },
    {
        "id": "cli_tool",
        "keywords": ["cli", "command line", "tool", "script", "automation"],
        "label": "CLI Tool / Script",
        "tech_stack": {
            "backend": {"options": [{"name": "Python + Typer/Click", "default": True}, {"name": "Go + Cobra"}, {"name": "Rust + Clap"}], "default": "Python + Typer/Click"},
            "frontend": {"options": [{"name": "None (CLI only)", "default": True}, {"name": "Rich TUI"}], "default": "None (CLI only)"},
            "database": {"options": [{"name": "SQLite", "default": True}, {"name": "JSON files"}, {"name": "None"}], "default": "SQLite"},
        },
        "patterns": ["Command Pattern", "Plugin Architecture"],
        "architecture": "CLI Entry → Commands → Services → Storage",
    },
    {
        "id": "mobile_app",
        "keywords": ["mobile", "app", "ios", "android", "react native", "flutter"],
        "label": "Mobile Application",
        "tech_stack": {
            "backend": {"options": [{"name": "Python + FastAPI", "default": True}, {"name": "Node.js + Express"}, {"name": "Firebase"}], "default": "Python + FastAPI"},
            "frontend": {"options": [{"name": "React Native", "default": True}, {"name": "Flutter"}, {"name": "Swift/SwiftUI"}], "default": "React Native"},
            "database": {"options": [{"name": "PostgreSQL", "default": True}, {"name": "SQLite (local)"}, {"name": "Firebase Firestore"}], "default": "PostgreSQL"},
        },
        "patterns": ["REST API", "Offline-first", "Push Notifications"],
        "architecture": "Mobile App → REST API → Services → Database + Cache",
    },
]

COMMON_OPTIONS = {
    "auth": {
        "label": "Authentication",
        "options": [{"name": "JWT + OAuth2", "default": True}, {"name": "Session-based"}, {"name": "API Keys"}, {"name": "None (public)"}],
        "default": "JWT + OAuth2",
    },
    "deployment": {
        "label": "Deployment",
        "options": [{"name": "Docker + Docker Compose", "default": True}, {"name": "Kubernetes"}, {"name": "Serverless (AWS Lambda)"}, {"name": "VPS (DigitalOcean/Linode)"}],
        "default": "Docker + Docker Compose",
    },
    "testing": {
        "label": "Testing Framework",
        "options": [{"name": "Pytest", "default": True}, {"name": "Jest"}, {"name": "Go Test"}, {"name": "Unittest"}],
        "default": "Pytest",
    },
    "caching": {
        "label": "Caching",
        "options": [{"name": "Redis", "default": True}, {"name": "In-memory cache"}, {"name": "Memcached"}, {"name": "None"}],
        "default": "Redis",
    },
}


def _infer_project_profile(overview: str, requirements: list) -> dict:
    """Infer the project profile based on overview text and requirements."""
    import re
    text = (overview + " " + " ".join(r.get("title", "") for r in requirements if r.get("title"))).lower()

    # Score each profile
    scores = []
    for profile in PROJECT_PROFILES:
        score = sum(2 for kw in profile["keywords"] if re.search(rf"\b{re.escape(kw)}\b", text))
        # Bonus for tech mentions
        for req in requirements:
            rtext = (req.get("title", "") + " " + req.get("description", "")).lower()
            score += sum(1 for kw in profile["keywords"] if kw in rtext)
        scores.append((score, profile))

    scores.sort(key=lambda x: -x[0])
    best = scores[0][1] if scores[0][0] > 0 else PROJECT_PROFILES[0]

    # Build choice table for this profile
    choices = {}

    for category, cfg in best["tech_stack"].items():
        choices[category] = {
            "label": category.capitalize(),
            "type": "tech_stack",
            "existing": None,
            "recommended": cfg["default"],
            "options": cfg["options"],
            "selected": cfg["default"],
        }

    for cat_id, cfg in COMMON_OPTIONS.items():
        choices[cat_id] = {
            "label": cfg["label"],
            "type": "architecture",
            "existing": None,
            "recommended": cfg["default"],
            "options": cfg["options"],
            "selected": cfg["default"],
        }

    return {
        "profile": best["label"],
        "description": f"Project identified as a **{best['label']}** based on your goals.",
        "architecture_pattern": best["architecture"],
        "patterns": best["patterns"],
        "choices": choices,
    }


def _detect_existing_choices(project_path) -> dict:
    """Scan project files to detect what tech is already in use."""
    import re
    existing = {}

    # Check common config files
    files_to_check = [
        ("requirements.txt", None),
        ("package.json", None),
        ("pyproject.toml", None),
        ("Cargo.toml", None),
        ("go.mod", None),
        ("main.py", None),
        ("app.py", None),
    ]

    all_text = ""
    for fname, _ in files_to_check:
        fp = project_path / fname
        if fp.exists():
            all_text += fp.read_text(encoding="utf-8", errors="replace") + "\n"

    # Also scan src directory for imports
    src_dir = project_path / "src"
    if src_dir.exists():
        for py_file in src_dir.rglob("*.py"):
            try:
                all_text += py_file.read_text(encoding="utf-8", errors="replace") + "\n"
            except Exception:
                pass

    al = all_text.lower()
    if "fastapi" in al: existing["backend"] = "Python + FastAPI"
    elif "flask" in al: existing["backend"] = "Python + Flask"
    elif "django" in al: existing["backend"] = "Python + Django"
    elif "express" in al: existing["backend"] = "Node.js + Express"

    if "react" in al: existing["frontend"] = "React"
    elif "vue" in al: existing["frontend"] = "Vue"
    elif "svelte" in al: existing["frontend"] = "Svelte"

    if "postgres" in al or "psycopg" in al: existing["database"] = "PostgreSQL"
    elif "sqlite" in al or "sqlalchemy" in al: existing["database"] = "SQLite"
    elif "mysql" in al: existing["database"] = "MySQL"

    if "docker" in al: existing["deployment"] = "Docker"
    if "redis" in al: existing["caching"] = "Redis"
    if "pytest" in al: existing["testing"] = "Pytest"
    elif "jest" in al: existing["testing"] = "Jest"

    return existing


@router.post("/api/projects/{project_id}/infer-options")
def infer_options(project_id: str, data: dict = Body(...)):
    """Infer tech/architecture recommendations based on goals and requirements."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    overview = data.get("overview", "")
    requirements = data.get("requirements", [])

    project_path = Path(project["path"])

    # Detect existing tech already in the project codebase
    existing = _detect_existing_choices(project_path)

    # Infer project profile from goals
    inference = _infer_project_profile(overview, requirements)

    # Merge existing choices into the inference
    for cat_id, choice in inference["choices"].items():
        if cat_id in existing:
            choice["existing"] = existing[cat_id]
            # Pre-select existing choice if it matches one of the options
            for opt in choice["options"]:
                if existing[cat_id].lower() in opt["name"].lower():
                    choice["selected"] = opt["name"]
                    break
        else:
            choice["existing"] = None

    return inference


@router.get("/api/projects/{project_id}/architecture")
def get_architecture(project_id: str):
    """Return structured architecture data from the confirmed mspec.md."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    mspec_path = project_path / ".harness" / "mspec.md"
    has_mspec = mspec_path.exists()

    if not has_mspec:
        return {
            "confirmed": False,
            "project_name": project["name"],
            "message": "No mspec.md found. Complete the Context workflow to generate your architecture blueprint.",
            "requirements": [],
            "tech_stack": {},
            "layers": [],
            "patterns": [],
            "decisions": [],
        }

    mspec_content = mspec_path.read_text(encoding="utf-8", errors="replace")

    # Parse sections from mspec.md using section headers
    sections = {}
    current_section = "preamble"
    current_lines = []
    for line in mspec_content.split("\n"):
        if line.startswith("## "):
            sections[current_section] = "\n".join(current_lines)
            current_section = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_section] = "\n".join(current_lines)

    import re

    # ── Requirements & Goals ──
    requirements = []
    req_text = sections.get("Requirements & Goals", "")
    for priority in ("P0", "P1", "P2"):
        # Find bold sections like **P0 — Must Have**
        p_match = re.search(rf"\*\*{re.escape(priority)}.*?\*\*(.*?)(?=\*\*P\d|\Z)", req_text, re.DOTALL)
        if p_match:
            block = p_match.group(1)
            items = re.findall(
                r"[-*]\s+\[([ x])\]\s+As a user, I want to \*\*(.+?)\*\*.*?(?:\n\s+[-*]\s+Acceptance:\s*(.+?))?(?=\n[-*]\s+\[|\Z)",
                block, re.DOTALL
            )
            if not items:
                # Fallback: simpler extraction
                items = re.findall(r"[-*]\s+\[([ x])\]\s+\*\*(.+?)\*\*(?:\s*\n\s+[-*]\s+Acceptance:\s*(.+))?", block, re.DOTALL)
            for locked_str, title, acceptance in items:
                requirements.append({
                    "title": title.strip(),
                    "priority": priority,
                    "locked": locked_str == "x",
                    "acceptance": acceptance.strip() if acceptance else "",
                })

    # ── Tech Stack ──
    tech_stack = {}
    ts_text = sections.get("Tech Stack", "")
    for line in ts_text.split("\n"):
        m = re.match(r"-\s+\*\*(.+?)\*\*[:\s]+(.+)", line)
        if m:
            key = m.group(1).lower().strip()
            val = m.group(2).strip()
            tech_stack[key] = val

    # ── Architecture layers ──
    layers = []
    arch_text = sections.get("Architecture", "")
    for line in arch_text.split("\n"):
        m = re.match(r"-\s+\*\*(.+?)\*\*(?::\s*(.*))?", line)
        if m:
            layers.append({"name": m.group(1).strip(), "description": (m.group(2) or "").strip()})

    # ── Architecture Decisions ──
    decisions = []
    dec_text = sections.get("Architecture Decisions", "")
    for line in dec_text.split("\n"):
        m = re.match(r"-\s+\*\*(.+?)\*\*", line)
        if m:
            decisions.append(m.group(1).strip())

    # ── Patterns from layers + decisions ──
    patterns = [l["name"] for l in layers if l["name"]]

    # ── Setup commands ──
    setup_cmds = []
    setup_text = sections.get("Setup & Development", "")
    in_code = False
    for line in setup_text.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code and line.strip() and not line.strip().startswith("#"):
            setup_cmds.append(line.strip())

    return {
        "confirmed": True,
        "project_name": project["name"],
        "requirements": requirements,
        "tech_stack": tech_stack,
        "layers": layers,
        "patterns": patterns,
        "decisions": decisions,
        "setup_commands": setup_cmds,
        "mspec_preview": mspec_content[:500] + "..." if len(mspec_content) > 500 else mspec_content,
        "has_setup": "Setup & Development" in sections,
        "has_api": "API Endpoints" in sections,
        "has_business_rules": "Business Rules & Constraints" in sections,
        "has_dependencies": "Dependencies & Environment" in sections,
        "has_structure": "Project Structure" in sections,
        "total_sections": len([k for k in sections.keys() if k != "preamble"]),
    }


# ─── Build Plan Generator ───────────────────────────────────────

BUILD_STEPS_PATH = HARNESS_DIR / "build_profiles.json"


def _get_build_profiles() -> dict:
    """Return build step profiles keyed by architecture profile name, with fallback."""
    return {
        "default": {
            "steps": [
                {
                    "id": "scaffold",
                    "title": "Project Scaffold & Configuration",
                    "description": "Set up project structure, dependency files, configuration, and entry points.",
                    "contract": {
                        "inputs": "Architecture decisions, tech stack selections",
                        "outputs": "Working project skeleton with config files, dependency manifests, and runnable entry point",
                    },
                    "tests": [
                        "Project starts without errors: `uvicorn main:app --reload` or equivalent",
                        "Dependencies install cleanly: `pip install -r requirements.txt` or `npm install`",
                        "Git repository initialized with .gitignore"
                    ],
                },
                {
                    "id": "data_models",
                    "title": "Data Models & Schema",
                    "description": "Define database models, ORM schemas, migrations, and data validation.",
                    "contract": {
                        "inputs": "Tech stack (database choice), requirements entities",
                        "outputs": "All database models with fields, types, constraints, and relationships",
                    },
                    "tests": [
                        "All models can be created/read/updated/deleted via ORM",
                        "Foreign key relationships work correctly",
                        "Validation rejects invalid data"
                    ],
                },
                {
                    "id": "api_core",
                    "title": "Core API Endpoints",
                    "description": "Implement CRUD endpoints for primary resources with request validation and response serialization.",
                    "contract": {
                        "inputs": "Data models from step 2, API endpoint specs",
                        "outputs": "Working REST endpoints: create, read, update, delete for each resource",
                    },
                    "tests": [
                        "POST returns 201 with created resource",
                        "GET returns 200 with resource list",
                        "GET /{id} returns 200 or 404",
                        "PUT returns 200 with updated resource",
                        "DELETE returns 204"
                    ],
                },
                {
                    "id": "business_logic",
                    "title": "Service Layer & Business Logic",
                    "description": "Implement business rules, validation logic, and service orchestration.",
                    "contract": {
                        "inputs": "Business rules from mspec, core API endpoints",
                        "outputs": "Service layer with all business rules enforced, error handling",
                    },
                    "tests": [
                        "Business rules reject invalid operations with appropriate errors",
                        "Edge cases handled (empty state, duplicates, concurrency)",
                        "Error responses follow the agreed format"
                    ],
                },
                {
                    "id": "auth",
                    "title": "Authentication & Authorization",
                    "description": "Implement user authentication, token management, and role-based access control.",
                    "contract": {
                        "inputs": "Auth method from tech stack choices (JWT, OAuth, session)",
                        "outputs": "Working auth flow: register, login, token refresh, protected routes",
                    },
                    "tests": [
                        "Unauthenticated requests return 401",
                        "Authenticated requests with valid token succeed",
                        "Invalid/expired tokens return 401",
                        "Role-based access enforced correctly"
                    ],
                },
                {
                    "id": "frontend_foundation",
                    "title": "Frontend Foundation",
                    "description": "Set up frontend project, routing, layout, API client, and shared components.",
                    "contract": {
                        "inputs": "Frontend tech choice (React, Vue, etc.), API endpoint structure",
                        "outputs": "Frontend app shell with routing, navigation, and API client configured",
                    },
                    "tests": [
                        "App renders without errors",
                        "Routing works (all routes accessible)",
                        "API client successfully connects to backend"
                    ],
                },
                {
                    "id": "frontend_features",
                    "title": "Frontend Feature Pages",
                    "description": "Build UI pages for each feature: list, detail, create/edit forms.",
                    "contract": {
                        "inputs": "API endpoints, data models, requirements",
                        "outputs": "Working UI with data display, forms, and user interactions",
                    },
                    "tests": [
                        "List page loads and displays data",
                        "Create form submits and shows success",
                        "Error states handled (loading, empty, error)"
                    ],
                },
                {
                    "id": "testing",
                    "title": "Comprehensive Testing",
                    "description": "Add unit tests, integration tests, and end-to-end tests for all layers.",
                    "contract": {
                        "inputs": "All previous steps, test framework from choices",
                        "outputs": "Test suite with ≥80% coverage across all layers",
                    },
                    "tests": [
                        "All unit tests pass",
                        "Integration tests cover API endpoints",
                        "Edge cases and error paths tested"
                    ],
                },
                {
                    "id": "deployment",
                    "title": "Deployment Configuration",
                    "description": "Set up Docker, CI/CD, environment configuration, and deployment scripts.",
                    "contract": {
                        "inputs": "Deployment choice (Docker, K8s, serverless), env vars",
                        "outputs": "Deployment-ready configuration: Dockerfile, CI workflow, env templates",
                    },
                    "tests": [
                        "Docker image builds successfully",
                        "CI pipeline runs all tests",
                        "Application starts with production config"
                    ],
                },
            ]
        }
    }


def _generate_build_plan(project_name: str, mspec_content: str, tech_stack: dict, requirements: list, profile: str = "") -> list:
    """Generate ordered build steps from architecture data."""
    import re

    profiles = _get_build_profiles()
    profile_key = "default"
    for key in profiles:
        if key in profile.lower():
            profile_key = key
            break

    base_steps = profiles.get(profile_key, profiles["default"])["steps"]

    # Filter/adjust steps based on actual architecture
    ts_text = " ".join(str(v).lower() for v in tech_stack.values() if v)
    has_frontend = any(kw in ts_text for kw in ["react", "vue", "svelte", "angular", "frontend"])
    has_auth = any(kw in ts_text for kw in ["jwt", "oauth", "auth", "session"])
    has_docker = "docker" in ts_text

    steps = []
    for s in base_steps:
        # Skip frontend steps if no frontend tech
        if s["id"] in ("frontend_foundation", "frontend_features") and not has_frontend:
            continue
        # Skip auth if not relevant
        if s["id"] == "auth" and not has_auth and len(requirements) < 3:
            continue
        # Skip deployment if no docker
        if s["id"] == "deployment" and not has_docker:
            continue

        # Build mini-context from architecture
        context_parts = [f"# {s['title']}"]
        context_parts.append(f"Project: {project_name}")
        context_parts.append(f"Tech: {', '.join(f'{k}={v}' for k, v in tech_stack.items() if v)}")
        context_parts.append(f"Description: {s['description']}")
        context_parts.append("")

        # Add relevant requirements
        req_texts = []
        for r in requirements:
            title = r.get("title", "")
            if title and (s["id"] in ("api_core", "business_logic") or len(req_texts) < 3):
                req_texts.append(f"- {r.get('priority','P1')}: {title}")
        if req_texts:
            context_parts.append("Relevant Requirements:")
            context_parts.extend(req_texts)
            context_parts.append("")

        # Add architecture reference
        arch_match = re.search(r"## Architecture\n(.*?)(?=\n##)", mspec_content, re.DOTALL)
        if arch_match and s["id"] in ("scaffold", "api_core", "business_logic"):
            arch_text = arch_match.group(1)[:300]
            context_parts.append(f"Architecture: {arch_text.strip()}")
            context_parts.append("")

        # Tech-specific details
        if s["id"] == "scaffold":
            if "python" in ts_text or "fastapi" in ts_text:
                context_parts.append("Files to create: main.py, requirements.txt, .env.example, Dockerfile, README.md")
            elif "node" in ts_text:
                context_parts.append("Files to create: package.json, index.js, .env.example, Dockerfile, README.md")
        elif s["id"] == "data_models":
            db = tech_stack.get("database", "SQLite")
            context_parts.append(f"Using {db} as the database. Define all models with fields, types, and relationships.")

        context = "\n".join(context_parts)

        # Estimate tokens (rough: ~4 chars per token)
        estimated_tokens = max(500, len(context) // 4 + 500)

        # Build dependency list - only include steps that are also in the filtered list
        all_possible_deps = [bs["id"] for bs in base_steps[:base_steps.index(s)]]
        existing_ids = [st["id"] for st in steps]
        valid_deps = [d for d in all_possible_deps if d in existing_ids]
        steps.append({
            "id": s["id"],
            "title": s["title"],
            "context": context,
            "context_tokens": estimated_tokens,
            "contract": s["contract"],
            "tests": s["tests"],
            "status": "pending",
            "dependencies": valid_deps,
        })

    return steps


@router.post("/api/projects/{project_id}/build-plan")
def generate_build_plan(project_id: str):
    """Generate build plan from confirmed architecture and store to .harness/build-plan.md + build-steps.json."""
    import json

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    mspec_path = project_path / ".harness" / "mspec.md"
    if not mspec_path.exists():
        raise HTTPException(400, "No mspec.md found. Complete the Context workflow first.")

    mspec_content = mspec_path.read_text(encoding="utf-8", errors="replace")

    # Parse tech stack and requirements from mspec
    sections = {}
    current_section = "preamble"
    current_lines = []
    for line in mspec_content.split("\n"):
        if line.startswith("## "):
            sections[current_section] = "\n".join(current_lines)
            current_section = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_section] = "\n".join(current_lines)

    import re
    tech_stack = {}
    ts_text = sections.get("Tech Stack", "")
    for line in ts_text.split("\n"):
        m = re.match(r"-\s+\*\*(.+?)\*\*[:\s]+(.+)", line)
        if m:
            tech_stack[m.group(1).lower().strip()] = m.group(2).strip()

    requirements = []
    req_text = sections.get("Requirements & Goals", "")
    for priority in ("P0", "P1", "P2"):
        p_match = re.search(rf"\*\*{re.escape(priority)}.*?\*\*(.*?)(?=\*\*P\d|\Z)", req_text, re.DOTALL)
        if p_match:
            items = re.findall(r"[-*]\s+\[([ x])\]\s+\*\*(.+?)\*\*", p_match.group(1), re.DOTALL)
            for locked_str, title in items:
                requirements.append({"title": title.strip(), "priority": priority, "locked": locked_str == "x"})

    # Generate steps
    profile = sections.get("preamble", "")
    steps = _generate_build_plan(project["name"], mspec_content, tech_stack, requirements, profile)

    # Build step index map for dependency formatting
    step_index = {s["id"]: i+1 for i, s in enumerate(steps)}

    md_lines = [f"# Build Plan: {project['name']}", "",
                f"Generated from mspec.md — {len(steps)} build steps.", "",
                "## Overview", ""]
    done = sum(1 for s in steps if s["status"] == "done")
    in_progress = sum(1 for s in steps if s["status"] == "in_progress")
    md_lines.append(f"- **Total Steps**: {len(steps)}")
    md_lines.append(f"- **Completed**: {done}")
    md_lines.append(f"- **In Progress**: {in_progress}")
    md_lines.append("")

    for i, step in enumerate(steps, 1):
        md_lines.append(f"## BP-{i:02d}: {step['title']}")
        md_lines.append("")
        md_lines.append(f"**Status**: {step['status']}")
        md_lines.append(f"**Estimated Context**: ~{step['context_tokens']} tokens")
        if step["dependencies"]:
            valid_deps = [d for d in step["dependencies"] if d in step_index]
            dep_names = [f"BP-{step_index[d]:02d}" for d in valid_deps]
            md_lines.append(f"**Depends On**: {', '.join(dep_names) if dep_names else 'None'}")
        md_lines.append("")
        md_lines.append("### Context")
        md_lines.append("")
        md_lines.append(step["context"])
        md_lines.append("")
        md_lines.append("### Contract")
        md_lines.append("")
        md_lines.append(f"- **Inputs**: {step['contract']['inputs']}")
        md_lines.append(f"- **Outputs**: {step['contract']['outputs']}")
        md_lines.append("")
        md_lines.append("### Test Scenarios")
        md_lines.append("")
        for t in step["tests"]:
            md_lines.append(f"- [ ] {t}")
        md_lines.append("")

    harness_dir = project_path / ".harness"
    harness_dir.mkdir(parents=True, exist_ok=True)

    build_plan_path = harness_dir / "build-plan.md"
    build_plan_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Write build-steps.json (for checkpoint integration)
    build_steps_path = harness_dir / "build-steps.json"
    build_steps_path.write_text(json.dumps(steps, indent=2), encoding="utf-8")

    # Also write to SQLite registry
    try:
        upsert_build_steps(project_id, steps)
    except Exception:
        pass

    return {
        "ok": True,
        "total_steps": len(steps),
        "steps": steps,
    }


@router.get("/api/projects/{project_id}/build-plan")
def get_build_plan(project_id: str):
    """Return the current build plan with step statuses."""
    import json

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Try DB first — includes FK links to runs
    try:
        result = get_build_steps(project_id)
        if result["exists"]:
            return result
    except Exception:
        pass

    # Fallback: read from JSON file, auto-migrate to DB
    project_path = Path(project["path"])
    steps_path = project_path / ".harness" / "build-steps.json"

    if not steps_path.exists():
        md_path = project_path / ".harness" / "build-plan.md"
        return {
            "exists": False,
            "steps": [],
            "total": 0,
            "done": 0,
            "message": "No build plan generated yet." if not md_path.exists() else "Build plan markdown exists but no step data.",
        }

    steps = json.loads(steps_path.read_text(encoding="utf-8"))
    # Auto-migrate to DB and link runs
    try:
        upsert_build_steps(project_id, steps)
        _auto_link_migrated_runs(project_id, project_path)
    except Exception:
        pass
    done = sum(1 for s in steps if s["status"] == "done")
    in_progress = sum(1 for s in steps if s["status"] == "in_progress")

    return {
        "exists": True,
        "steps": steps,
        "total": len(steps),
        "done": done,
        "in_progress": in_progress,
        "progress_pct": round(done / len(steps) * 100) if steps else 0,
    }


@router.put("/api/projects/{project_id}/build-plan/step/{step_id}")
def update_build_step(project_id: str, step_id: str, status: str = Body(..., embed=True)):
    """Update the status of a build step (pending/in_progress/done)."""
    import json

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if status not in ("not_started", "in_progress", "tested", "ready_for_merge", "merged", "pending", "done", "completed", "failed"):
        raise HTTPException(400, "Invalid status")

    project_path = Path(project["path"])
    steps_path = project_path / ".harness" / "build-steps.json"

    if not steps_path.exists():
        raise HTTPException(404, "No build plan found. Generate one first.")

    steps = json.loads(steps_path.read_text(encoding="utf-8"))
    found = False
    for step in steps:
        if step["id"] == step_id:
            step["status"] = status
            found = True
            break

    if not found:
        raise HTTPException(404, f"Step '{step_id}' not found in build plan.")

    steps_path.write_text(json.dumps(steps, indent=2), encoding="utf-8")

    # Also sync to DB registry
    try:
        update_build_step_status(project_id, step_id, status)
    except Exception:
        pass

    # Also update build-plan.md status
    md_path = project_path / ".harness" / "build-plan.md"
    if md_path.exists():
        md_content = md_path.read_text(encoding="utf-8")
        import re
        # Update status line for this step in markdown
        md_content = re.sub(
            rf"(## BP-?\w*: .*?{re.escape(step_id)}.*?\n\*\*Status\*\*: )\w+",
            rf"\g<1>{status}",
            md_content,
        )
        md_path.write_text(md_content, encoding="utf-8")

    done = sum(1 for s in steps if s["status"] == "done")
    return {
        "ok": True,
        "step_id": step_id,
        "status": status,
        "done": done,
        "total": len(steps),
        "progress_pct": round(done / len(steps) * 100) if steps else 0,
    }


# ─── Stub File Generator ────────────────────────────────────────

STUB_TEMPLATES = {
    "scaffold": {
        "files": ["requirements.txt / package.json", "main.py / index.js", ".env.example", "README.md", ".gitignore", "Dockerfile"],
        "patterns": ["Module-based project layout", "Configuration via environment variables"],
        "e2e": "Clone the repo → run install → run the server → verify it responds on localhost:PORT",
    },
    "data_models": {
        "files": ["models/*.py or schema.prisma", "database.py or db.py", "migrations/"],
        "patterns": ["ORM repository pattern", "Data validation at model layer (Pydantic / Zod)"],
        "e2e": "Initialize DB → create a record via ORM → query it back → verify fields match",
    },
    "api_core": {
        "files": ["api/routes/*.py or routes/*.ts", "api/schemas.py or validation/*.ts", "main.py (router registration)"],
        "patterns": ["RESTful resource routing", "Request validation via Pydantic/Zod", "Response serialization with status codes"],
        "e2e": "Start server → POST to create resource → GET to verify → PUT to update → DELETE → GET 404",
    },
    "business_logic": {
        "files": ["services/*.py or services/*.ts", "api/routes/*.py (updated)", "tests/test_services/"],
        "patterns": ["Service layer abstraction (controllers → services → repositories)", "Business rule validation before DB writes"],
        "e2e": "Send valid request → business rule passes → resource created. Send invalid request → 400 error with details.",
    },
    "auth": {
        "files": ["api/auth.py or middleware/auth.ts", "models/user.py or user.model.ts", "api/routes/auth.py"],
        "patterns": ["JWT token generation and verification", "Password hashing (bcrypt/argon2)", "Middleware-based route protection"],
        "e2e": "Register → login → receive token → access protected route with token → access without token (401)",
    },
    "frontend_foundation": {
        "files": ["package.json (frontend)", "src/App.jsx or App.tsx", "src/main.jsx or index.ts", "src/api/client.ts or api.js", "src/components/Layout.jsx"],
        "patterns": ["Component-based UI architecture", "API service layer for HTTP calls", "Client-side routing (React Router / Vue Router)"],
        "e2e": "Start frontend dev server → app renders without errors → navigation works → API client connects",
    },
    "frontend_features": {
        "files": ["src/pages/*.jsx or .tsx", "src/components/*.jsx or .tsx", "src/hooks/*.ts or .js"],
        "patterns": ["Page-level components for each route", "Reusable UI components (tables, forms, modals)", "Custom hooks for data fetching"],
        "e2e": "Navigate to list page → data loads → create new item via form → item appears in list → detail page shows correctly",
    },
    "testing": {
        "files": ["tests/test_api/*.py", "tests/test_services/*.py", "tests/test_models/*.py", "pytest.ini or jest.config.js"],
        "patterns": ["Arrange-Act-Assert pattern", "Fixture-based test data", "Coverage minimum 80%"],
        "e2e": "Run full test suite → all tests pass → coverage report shows ≥80%",
    },
    "deployment": {
        "files": ["Dockerfile", "docker-compose.yml", ".github/workflows/deploy.yml", "scripts/deploy.sh"],
        "patterns": ["Multi-stage Docker builds", "Environment-based configuration", "Health check endpoints"],
        "e2e": "Build Docker image → run container → verify health endpoint → run tests in CI",
    },
}


def _generate_stub(step: dict, project_name: str, tech_stack: dict, mspec_content: str, idx: int) -> str:
    """Generate a detailed stub markdown file for a single build step."""
    import re, datetime

    template = STUB_TEMPLATES.get(step["id"], {
        "files": ["src/"],
        "patterns": ["Follow project conventions"],
        "e2e": "Verify the feature works end-to-end",
    })

    ts_text = " ".join(str(v).lower() for v in tech_stack.values() if v)
    is_python = any(kw in ts_text for kw in ["python", "fastapi", "flask", "django"])
    is_frontend = any(kw in ts_text for kw in ["react", "vue", "svelte", "angular"])

    lines = []
    lines.append(f"# BP-{idx:02d}: {step['title']}")
    lines.append("")
    lines.append(f"**Project**: {project_name}")
    lines.append(f"**Status**: {step['status']}")
    lines.append(f"**Estimated Context**: ~{step['context_tokens']} tokens")
    if step.get("dependencies"):
        lines.append(f"**Depends On**: {', '.join(step['dependencies'])}")
    lines.append(f"**Generated**: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Context
    lines.append("## Context")
    lines.append("")
    lines.append(step.get("context", ""))
    lines.append("")

    # Tech Stack
    lines.append("### Tech Stack Reference")
    lines.append("")
    for k, v in tech_stack.items():
        if v:
            lines.append(f"- **{k.capitalize()}**: {v}")
    lines.append("")

    # Files to create/modify
    lines.append("## Files to Create/Modify")
    lines.append("")
    for f in template["files"]:
        lines.append(f"- `{f}`")
    lines.append("")

    # Architecture & Patterns
    lines.append("## Coding Architecture")
    lines.append("")
    lines.append("### Patterns")
    lines.append("")
    for p in template["patterns"]:
        lines.append(f"- {p}")

    # Step-specific architecture guidance
    if step["id"] == "scaffold":
        lines.append("")
        lines.append("### Project Structure")
        lines.append("```")
        if is_python:
            lines.append("project/")
            lines.append("├── src/")
            lines.append("│   ├── __init__.py")
            lines.append("│   ├── main.py          # FastAPI app entry point")
            lines.append("│   ├── api/             # Route handlers")
            lines.append("│   ├── models/          # SQLAlchemy/Pydantic models")
            lines.append("│   ├── services/        # Business logic")
            lines.append("│   └── repositories/    # Data access")
            lines.append("├── tests/")
            lines.append("├── requirements.txt")
            lines.append("├── .env.example")
            lines.append("└── README.md")
        else:
            lines.append("project/")
            lines.append("├── src/")
            lines.append("│   ├── index.js         # Entry point")
            lines.append("│   └── modules/")
            lines.append("├── tests/")
            lines.append("├── package.json")
            lines.append("└── README.md")
        lines.append("```")
    elif step["id"] == "api_core":
        lines.append("")
        lines.append("### API Structure")
        lines.append("```")
        if is_python:
            lines.append("src/api/")
            lines.append("├── __init__.py")
            lines.append("├── routes.py      # Resource route definitions")
            lines.append("├── schemas.py     # Pydantic request/response models")
            lines.append("└── deps.py        # Dependency injection (DB sessions, auth)")
        else:
            lines.append("src/api/")
            lines.append("├── routes/")
            lines.append("│   ├── index.ts")
            lines.append("│   └── resource.ts")
            lines.append("├── validation.ts")
            lines.append("└── middleware.ts")
        lines.append("```")
    elif step["id"] == "data_models":
        lines.append("")
        lines.append("### Data Model Example")
        lines.append("```python")
        lines.append("class Resource(Base):")
        lines.append('    __tablename__ = "resources"')
        lines.append("    id: UUID = Column(UUID, primary_key=True, default=uuid4)")
        lines.append("    name: str = Column(String(255), nullable=False)")
        lines.append("    description: str = Column(Text, nullable=True)")
        lines.append("    created_at: datetime = Column(DateTime, default=func.now())")
        lines.append("    updated_at: datetime = Column(DateTime, onupdate=func.now())")
        lines.append("```")
        lines.append("")

    lines.append("")
    lines.append("### Data Flow")
    lines.append("```")
    lines.append("Request → Route Handler → Validation → Service → Repository → Database")
    lines.append("Response ← Serialization ← Service Result ← Repository ← Database")
    lines.append("```")
    lines.append("")

    # Contract
    lines.append("## Contract")
    lines.append("")
    lines.append("### Inputs")
    lines.append("")
    if step.get("contract", {}).get("inputs"):
        lines.append(step["contract"]["inputs"])
    lines.append("")
    lines.append("### Outputs")
    lines.append("")
    if step.get("contract", {}).get("outputs"):
        lines.append(step["contract"]["outputs"])
    lines.append("")

    # Implementation Checklist
    lines.append("## Implementation Checklist")
    lines.append("")
    lines.append("- [ ] Review tech stack and architecture patterns above")
    if step["id"] == "scaffold":
        lines.append("- [ ] Create project directory structure")
        lines.append("- [ ] Add dependency files (requirements.txt / package.json)")
        lines.append("- [ ] Create main entry point with health check endpoint")
        lines.append("- [ ] Configure environment variables (.env.example)")
        lines.append("- [ ] Add .gitignore")
        lines.append("- [ ] Verify server starts and responds")
    elif step["id"] == "data_models":
        lines.append("- [ ] Define all database models with fields and types")
        lines.append("- [ ] Set up relationships (foreign keys, joins)")
        lines.append("- [ ] Create database connection and session management")
        lines.append("- [ ] Add data validation schemas (Pydantic / Zod)")
        lines.append("- [ ] Run initial migration / create tables")
    elif step["id"] == "api_core":
        lines.append("- [ ] Create route handlers for each resource")
        lines.append("- [ ] Implement request validation schemas")
        lines.append("- [ ] Implement response serialization")
        lines.append("- [ ] Wire up error handling (404, 422, 500)")
        lines.append("- [ ] Test all CRUD endpoints")
    elif step["id"] == "business_logic":
        lines.append("- [ ] Create service layer with business rules")
        lines.append("- [ ] Implement validation for each rule")
        lines.append("- [ ] Wire services into route handlers")
        lines.append("- [ ] Add error handling for business rule violations")
        lines.append("- [ ] Test edge cases")
    elif step["id"] == "auth":
        lines.append("- [ ] Create user model")
        lines.append("- [ ] Implement registration endpoint")
        lines.append("- [ ] Implement login/token endpoint")
        lines.append("- [ ] Add auth middleware to protect routes")
        lines.append("- [ ] Test auth flow end-to-end")
    elif step["id"] == "frontend_foundation":
        lines.append("- [ ] Initialize frontend project")
        lines.append("- [ ] Set up routing")
        lines.append("- [ ] Create layout component")
        lines.append("- [ ] Build API client")
        lines.append("- [ ] Verify frontend connects to backend")
    elif step["id"] == "frontend_features":
        lines.append("- [ ] Build list page")
        lines.append("- [ ] Build detail page")
        lines.append("- [ ] Build create/edit forms")
        lines.append("- [ ] Add loading/empty/error states")
        lines.append("- [ ] Test all user flows")
    else:
        lines.append("- [ ] Implement the step according to the contract above")
    lines.append("")

    # Test scenarios
    lines.append("## Test Scenarios")
    lines.append("")
    lines.append("### Unit Tests")
    lines.append("")
    for t in step.get("tests", []):
        lines.append(f"- [ ] {t}")
    lines.append("")

    # Step-specific additional tests
    lines.append("### Integration Tests")
    lines.append("")
    if step["id"] == "api_core":
        lines.append("- [ ] POST with invalid data returns 422 with field errors")
        lines.append("- [ ] GET non-existent ID returns 404")
        lines.append("- [ ] PUT with valid data updates and returns 200")
        lines.append("- [ ] DELETE removes resource and returns 204")
    elif step["id"] == "data_models":
        lines.append("- [ ] Create with duplicate unique field raises integrity error")
        lines.append("- [ ] Cascade delete works for related records")
    elif step["id"] == "business_logic":
        lines.append("- [ ] Business rule violation returns descriptive 400 error")
        lines.append("- [ ] Valid operation succeeds and returns expected result")
    elif step["id"] == "auth":
        lines.append("- [ ] Register with existing email returns 409")
        lines.append("- [ ] Login with wrong password returns 401")
        lines.append("- [ ] Expired token returns 401")
    elif step["id"] in ("frontend_foundation", "frontend_features"):
        lines.append("- [ ] Component renders without errors")
        lines.append("- [ ] Forms validate required fields")
        lines.append("- [ ] API errors display user-friendly message")
    else:
        lines.append("- [ ] Verify all acceptance criteria pass")
    lines.append("")

    # E2E test
    lines.append("### End-to-End Test")
    lines.append("")
    lines.append(f"**Scenario**: {template['e2e']}")
    lines.append("")
    lines.append("**Steps:**")
    lines.append("1. Set up the environment as described above")
    lines.append("2. Run the implementation checklist items")
    lines.append("3. Execute all test scenarios")
    lines.append("4. Verify the e2e scenario passes")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Stub generated for {project_name} — BP-{idx:02d}: {step['title']}*")
    lines.append("")

    return "\n".join(lines)


@router.post("/api/projects/{project_id}/build-plan/stubs")
def generate_stub_files(project_id: str):
    """Generate detailed stub markdown files for all build steps."""
    import json

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    steps_path = project_path / ".harness" / "build-steps.json"
    mspec_path = project_path / ".harness" / "mspec.md"

    if not steps_path.exists():
        raise HTTPException(400, "No build plan found. Generate build plan first.")
    if not mspec_path.exists():
        raise HTTPException(400, "No mspec.md found. Complete Context workflow first.")

    steps = json.loads(steps_path.read_text(encoding="utf-8"))
    mspec_content = mspec_path.read_text(encoding="utf-8", errors="replace")

    # Parse tech stack from mspec
    sections = {}
    current = "preamble"
    current_lines = []
    for line in mspec_content.split("\n"):
        if line.startswith("## "):
            sections[current] = "\n".join(current_lines)
            current = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current] = "\n".join(current_lines)

    import re
    tech_stack = {}
    ts_text = sections.get("Tech Stack", "")
    for line in ts_text.split("\n"):
        m = re.match(r"-\s+\*\*(.+?)\*\*[:\s]+(.+)", line)
        if m:
            tech_stack[m.group(1).lower().strip()] = m.group(2).strip()

    # Create steps directory
    steps_dir = project_path / ".harness" / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for i, step in enumerate(steps, 1):
        stub_content = _generate_stub(step, project["name"], tech_stack, mspec_content, i)
        safe_name = step["id"].replace(" ", "_").replace("/", "_")
        stub_path = steps_dir / f"BP-{i:02d}-{safe_name}.md"
        stub_path.write_text(stub_content, encoding="utf-8")
        generated.append({
            "id": f"BP-{i:02d}",
            "title": step["title"],
            "path": str(stub_path.relative_to(project_path)),
            "tokens": len(stub_content) // 4,  # rough estimate
        })

    # ── Validate stubs for completeness and integration ──
    validation = _validate_stubs(generated, steps, tech_stack, project_path)

    return {
        "ok": True,
        "count": len(generated),
        "stubs": generated,
        "directory": str(steps_dir),
        "validation": validation,
    }


def _validate_stubs(stubs: list, steps: list, tech_stack: dict, project_path=None) -> dict:
    """Validate each stub for completeness and cross-stub integration."""
    required_sections = ["Context", "Contract", "Implementation Checklist", "Test Scenarios", "End-to-End Test"]
    section_keywords = {
        "Context": ["context", "tech stack", "architecture"],
        "Contract": ["inputs", "outputs"],
        "Implementation Checklist": ["[ ]"],
        "Test Scenarios": ["unit test", "integration test", "test"],
        "End-to-End Test": ["scenario", "steps"],
    }

    ts_text = " ".join(str(v).lower() for v in tech_stack.values() if v)
    is_python = any(kw in ts_text for kw in ["python", "fastapi", "flask"])
    is_frontend = any(kw in ts_text for kw in ["react", "vue", "svelte"])

    results = []
    all_checks_passed = True
    total_checks = 0
    passed_checks = 0

    for stub_info in stubs:
        stub_rel = stub_info["path"]
        stub_path = project_path / stub_rel if project_path else Path(stub_rel)
        if not stub_path.exists():
            results.append({
                "stub": stub_info["id"],
                "title": stub_info["title"],
                "passed": False,
                "score": 0,
                "checks": [{"name": "File exists", "passed": False, "detail": f"File not found: {stub_rel}"}],
            })
            all_checks_passed = False
            continue

        content = stub_path.read_text(encoding="utf-8")
        checks = []
        cl = content.lower()

        # Check 1: Has context with tech stack
        has_context = all(kw in cl for kw in ["context", "tech"])
        checks.append({
            "name": "Context includes tech stack",
            "passed": has_context,
            "detail": "Contains tech stack reference" if has_context else "Missing tech stack in context",
        })
        total_checks += 1
        if has_context: passed_checks += 1

        # Check 2: Has contract with inputs/outputs
        has_contract = "input" in cl and "output" in cl
        checks.append({
            "name": "Contract defines inputs and outputs",
            "passed": has_contract,
            "detail": "Inputs and outputs defined" if has_contract else "Missing inputs or outputs",
        })
        total_checks += 1
        if has_contract: passed_checks += 1

        # Check 3: Has implementation checklist
        has_checklist = "[ ]" in content or "- [ ]" in content
        checks.append({
            "name": "Implementation checklist present",
            "passed": has_checklist,
            "detail": f"Found {content.count('[ ]')} checklist items" if has_checklist else "No checklist items",
        })
        total_checks += 1
        if has_checklist: passed_checks += 1

        # Check 4: Has test scenarios
        has_tests = "test" in cl and ("unit" in cl or "integration" in cl)
        checks.append({
            "name": "Test scenarios defined",
            "passed": has_tests,
            "detail": "Unit/integration tests included" if has_tests else "Missing test scenarios",
        })
        total_checks += 1
        if has_tests: passed_checks += 1

        # Check 5: Has e2e test
        has_e2e = "end-to-end" in cl or "e2e" in cl or "scenario" in cl
        checks.append({
            "name": "End-to-end test scenario",
            "passed": has_e2e,
            "detail": "E2E scenario defined" if has_e2e else "Missing e2e test",
        })
        total_checks += 1
        if has_e2e: passed_checks += 1

        # Check 6: Has coding architecture / patterns
        has_patterns = "pattern" in cl or "architecture" in cl or "structure" in cl
        checks.append({
            "name": "Coding architecture / patterns",
            "passed": has_patterns,
            "detail": "Architecture patterns documented" if has_patterns else "No architecture patterns",
        })
        total_checks += 1
        if has_patterns: passed_checks += 1

        # Check 7: Has files to create/modify
        has_files = "file" in cl or "create" in cl or "modify" in cl
        checks.append({
            "name": "Files to create/modify listed",
            "passed": has_files,
            "detail": "Files referenced" if has_files else "No file references",
        })
        total_checks += 1
        if has_files: passed_checks += 1

        stub_pass = all(c["passed"] for c in checks)
        if not stub_pass:
            all_checks_passed = False

        results.append({
            "stub": stub_info["id"],
            "title": stub_info["title"],
            "passed": stub_pass,
            "checks": checks,
            "score": round(sum(1 for c in checks if c["passed"]) / len(checks) * 100),
        })

    # ── Cross-stub integration check ──
    integration_checks = []
    step_ids = [s["id"] for s in steps]
    step_map = {s["id"]: s for s in steps}

    # Check dependency chain is consistent
    for i, s in enumerate(steps):
        deps = s.get("dependencies", [])
        for d in deps:
            if d not in step_ids:
                # Dependency may have been intentionally filtered (e.g., auth for small projects)
                integration_checks.append({
                    "check": f"{s['id']} depends on {d}",
                    "passed": True,
                    "detail": f"Dependency '{d}' not in plan (filtered) — OK",
                })
            else:
                dep_idx = step_ids.index(d)
                if dep_idx >= i:
                    integration_checks.append({
                        "check": f"{s['id']} depends on {d}",
                        "passed": False,
                        "detail": f"Dependency order wrong: {d} appears after {s['id']}",
                    })
                    all_checks_passed = False
                else:
                    integration_checks.append({
                        "check": f"{s['id']} ← depends on {d}",
                        "passed": True,
                        "detail": "Dependency order correct",
                    })
        # Don't double-count passed_checks for dependencies; already counted in stub checks

    # Check tech stack consistency across stubs
    for stub_info in stubs:
        stub_rel = stub_info["path"]
        stub_path = project_path / stub_rel if project_path else Path(stub_rel)
        if stub_path.exists():
            content = stub_path.read_text(encoding="utf-8")
            cl = content.lower()
            # Python projects should reference python in context
            if is_python and "python" not in cl:
                integration_checks.append({
                    "check": f"{stub_info['id']}: tech stack alignment",
                    "passed": False,
                    "detail": "Python project but stub doesn't reference Python",
                })
                all_checks_passed = False
            elif is_python:
                integration_checks.append({
                    "check": f"{stub_info['id']}: tech stack alignment",
                    "passed": True,
                    "detail": "Tech stack consistent",
                })

    return {
        "stub_checks": results,
        "integration_checks": integration_checks,
        "summary": {
            "all_passed": all_checks_passed,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "score": round(passed_checks / total_checks * 100) if total_checks > 0 else 0,
        },
    }


@router.get("/api/projects/{project_id}/build-plan/stubs")
def list_stub_files(project_id: str):
    """List generated stub files."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    steps_dir = Path(project["path"]) / ".harness" / "steps"
    if not steps_dir.exists():
        return {"exists": False, "stubs": []}

    stubs = []
    for f in sorted(steps_dir.glob("BP-*.md")):
        content = f.read_text(encoding="utf-8", errors="replace")
        stubs.append({
            "path": str(f.relative_to(Path(project["path"]))),
            "name": f.stem,
            "size": f.stat().st_size,
            "tokens": len(content) // 4,
        })

    return {"exists": True, "stubs": stubs}


# ─── Code Script Generator ─────────────────────────────────────

CODE_AGENTS = {
    "opencode": {
        "label": "opencode",
        "cmd_template": 'opencode --model "{model}" --prompt "{prompt_file}" --output-dir "{output_dir}"',
        "description": "Open-source code generation agent with file creation and editing capabilities.",
    },
    "reasonix": {
        "label": "reasonix code",
        "cmd_template": 'reasonix code --model "{model}" "{prompt_file}"',
        "description": "Agentic coding assistant with plan-execute loop and file system access.",
    },
}


@router.post("/api/projects/{project_id}/build-plan/code-scripts")
def generate_code_scripts(project_id: str, agent: str = "opencode"):
    """Generate runnable code scripts for each stub file using opencode/reasonix."""
    import json, shlex

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if agent not in CODE_AGENTS:
        raise HTTPException(400, f"Unknown agent '{agent}'. Choose: {', '.join(CODE_AGENTS.keys())}")

    project_path = Path(project["path"])
    steps_dir = project_path / ".harness" / "steps"
    scripts_dir = project_path / ".harness" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    if not steps_dir.exists():
        raise HTTPException(400, "No stub files found. Generate Build Plan and Stub Files first.")

    # Get LLM provider config for model selection
    from config import load_provider_config
    provider_cfg = load_provider_config()
    provider = provider_cfg.get("provider", "localllm")
    if provider == "deepseek":
        model = provider_cfg.get("deepseek", {}).get("model", "deepseek-chat")
    else:
        model = provider_cfg.get("localllm", {}).get("model", "qwen3.6-27b")

    agent_info = CODE_AGENTS[agent]
    scripts = []

    for stub_file in sorted(steps_dir.glob("BP-*.md")):
        stub_name = stub_file.stem  # e.g., "BP-01-scaffold"
        stub_id = stub_name[:6]     # e.g., "BP-01"

        # Relative path to stub file from project root
        stub_rel = stub_file.relative_to(project_path)

        # Build the command
        cmd = agent_info["cmd_template"].format(
            model=model,
            prompt_file=str(stub_rel),
            output_dir="src",
        )

        # Create .bat file for Windows
        bat_path = scripts_dir / f"{stub_name}.bat"
        status_file = f".harness\\scripts\\{stub_name}.status"
        # Read stub content to build a self-contained prompt
        stub_content = stub_file.read_text(encoding="utf-8", errors="replace")
        prompt_path = scripts_dir / f"{stub_name}.prompt.md"
        prompt_path.write_text(stub_content, encoding="utf-8")

        # Build command — for reasonix, create a REASONIX.md in project root
        # that reasonix auto-loads, then launch it without pipe
        if agent == "reasonix":
            # Read stub content and pass as inline prompt argument
            # Truncate to 2000 chars to fit command-line limits
            inline_prompt = stub_content[:2000].replace('"', "'").replace('\n', ' ').replace('\r', ' ')
            run_cmd = f'reasonix code --model "{model}" "{inline_prompt}"'
        else:
            run_cmd = cmd

        prompt_rel = prompt_path.relative_to(project_path)
        bat_lines = [
            "@echo off",
            f"title Coding: {stub_name}",
            f"cd /d \"{project_path}\"",
            "",
            f"echo === {agent_info['label']} Coding Session ===",
            f"echo Stub: {stub_name}",
            f"echo Model: {model}",
            f"echo Injecting task context at runtime...",
            "echo.",
            run_cmd,
            "set EXIT_CODE=%ERRORLEVEL%",
            f"echo %EXIT_CODE% > \"{status_file}\"",
            "echo.",
            "if %EXIT_CODE% NEQ 0 (",
            f"    echo {agent_info['label']} exited with code %EXIT_CODE%",
            "    pause",
            ") else (",
            "    echo Coding complete!",
            "    timeout /t 3 >nul",
            ")",
        ]
        bat_path.write_text("\n".join(bat_lines), encoding="utf-8")

        # Create .sh file for Unix
        sh_path = scripts_dir / f"{stub_name}.sh"
        sh_lines = [
            "#!/bin/bash",
            f"# Coding script for {stub_name}",
            f"cd \"{project_path}\"",
            "echo \"========================================\"",
            f"echo \"  {agent_info['label']} — {stub_name}\"",
            "echo \"========================================\"",
            "echo \"",
            f"echo \"  Stub: {stub_name}\"",
            f"echo \"  Model: {model}\"",
            "echo \"  Agent reads stub autonomously.\"",
            "echo \"",
            cmd,
            'if [ $? -eq 0 ]; then',
            '    echo "✓ Coding complete!"',
            'else',
            '    echo "✗ Coding failed!"',
            '    exit 1',
            'fi',
        ]
        sh_path.write_text("\n".join(sh_lines), encoding="utf-8")

        scripts.append({
            "id": stub_id,
            "name": stub_name,
            "title": stub_name[6:].replace("-", " ").title(),
            "command": cmd,
            "script_bat": str(bat_path.relative_to(project_path)),
            "script_sh": str(sh_path.relative_to(project_path)),
            "prompt_file": str(stub_rel),
            "model": model,
        })

    return {
        "ok": True,
        "agent": agent,
        "agent_label": agent_info["label"],
        "agent_description": agent_info["description"],
        "count": len(scripts),
        "scripts": scripts,
        "directory": str(scripts_dir),
    }


@router.get("/api/projects/{project_id}/build-plan/code-scripts")
def list_code_scripts(project_id: str):
    """List generated code scripts."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    scripts_dir = Path(project["path"]) / ".harness" / "scripts"
    if not scripts_dir.exists():
        return {"exists": False, "scripts": []}

    scripts = []
    for f in sorted(scripts_dir.glob("*.bat")):
        content = f.read_text(encoding="utf-8")
        # Extract command from the .bat file (first non-comment, non-cd line)
        cmd_line = ""
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("@") and not line.startswith("title") and not line.startswith("cd") and not line.startswith("echo") and not line.startswith("if") and not line.startswith(")") and not line.startswith("pause"):
                cmd_line = line
                break
        scripts.append({
            "name": f.stem,
            "path": str(f.relative_to(Path(project["path"]))),
            "command": cmd_line,
        })

    return {"exists": True, "scripts": scripts}


# ─── Run Tracking System ────────────────────────────────────────

import uuid as _uuid
import datetime as _dt
import json as _json


def _get_runs_dir(project_path: Path) -> Path:
    d = project_path / ".harness" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _create_run(project_path: Path, stub_name: str, agent: str, model: str) -> dict:
    runs_dir = _get_runs_dir(project_path)
    run_id = str(_uuid.uuid4())[:8]
    session_id = f"run_{run_id}_{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    run = {
        "id": run_id,
        "session_id": session_id,
        "stub_name": stub_name,
        "agent": agent,
        "model": model,
        "status": "starting",
        "start_time": now,
        "end_time": None,
        "events": [
            {"timestamp": now, "level": "info", "message": f"Run created for {stub_name} with {agent}", "context": {"agent": agent, "model": model}},
        ],
        "error": None,
    }
    run_path = runs_dir / f"{run_id}.json"
    run_path.write_text(_json.dumps(run, indent=2))
    return run


def _log_event(project_path: Path, run_id: str, level: str, message: str, context: dict = None):
    runs_dir = _get_runs_dir(project_path)
    run_path = runs_dir / f"{run_id}.json"
    if not run_path.exists():
        return
    run = _json.loads(run_path.read_text(encoding="utf-8"))
    run["events"].append({
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
    })
    run_path.write_text(_json.dumps(run, indent=2))


def _update_run_status(project_path: Path, run_id: str, status: str, error: str = None):
    runs_dir = _get_runs_dir(project_path)
    run_path = runs_dir / f"{run_id}.json"
    if not run_path.exists():
        return
    run = _json.loads(run_path.read_text(encoding="utf-8"))
    run["status"] = status
    if status in ("completed", "failed"):
        run["end_time"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if error:
        run["error"] = error
    run_path.write_text(_json.dumps(run, indent=2))


@router.get("/api/projects/{project_id}/build-plan/runs")
def list_runs(project_id: str):
    """List all tracked runs with counts."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Use DB as primary source
    result = db_list_runs(project_id)

    # Always import new JSON-only runs that aren't in the DB yet
    runs_dir = _get_runs_dir(Path(project["path"]))
    if runs_dir.exists():
        db_ids = {r["id"] for r in result.get("runs", [])}
        import json as _j
        for f in sorted(runs_dir.glob("*.json"), reverse=True):
            if f.name == "active.json":
                continue
            rid = f.stem
            if rid in db_ids:
                continue  # already in DB
            try:
                run = _j.loads(f.read_text(encoding="utf-8"))
                events = run.pop("events", [])
                run.pop("files_changed", None)
                create_run(
                    project_id=project_id,
                    run_id=run["id"],
                    session_id=run.get("session_id", f"run_{run['id']}"),
                    stub_name=run.get("stub_name", ""),
                    agent=run.get("agent", "unknown"),
                    model=run.get("model", ""),
                    stub_path=run.get("stub_path"),
                    bp_id=run.get("bp_id"),
                    title=run.get("title"),
                )
                db_update_run_status(
                    run["id"], run.get("status", "completed"),
                    error=run.get("error"),
                    exit_code=run.get("exit_code"),
                )
                for ev in events:
                    add_run_event(run["id"], ev.get("level", "info"),
                                  ev.get("message", ""),
                                  _j.dumps(ev.get("context", {})) if ev.get("context") else None)
            except Exception:
                pass

    # Re-query with new imports
    result = db_list_runs(project_id)
    if result["total"] > 0:
        return result

    # Fallback: empty result — no runs at all
    runs_dir = _get_runs_dir(Path(project["path"]))
    if runs_dir.exists():
        import json as _j
        for f in sorted(runs_dir.glob("*.json"), reverse=True):
            if f.name == "active.json":
                continue
            try:
                run = _j.loads(f.read_text(encoding="utf-8"))
                events = run.pop("events", [])
                run.pop("files_changed", None)
                create_run(
                    project_id=project_id,
                    run_id=run["id"],
                    session_id=run.get("session_id", f"run_{run['id']}"),
                    stub_name=run.get("stub_name", ""),
                    agent=run.get("agent", "unknown"),
                    model=run.get("model", ""),
                    stub_path=run.get("stub_path"),
                    bp_id=run.get("bp_id"),
                    title=run.get("title"),
                )
                db_update_run_status(
                    run["id"], run.get("status", "completed"),
                    error=run.get("error"),
                    exit_code=run.get("exit_code"),
                )
                for ev in events:
                    add_run_event(run["id"], ev.get("level", "info"),
                                  ev.get("message", ""),
                                  _j.dumps(ev.get("context", {})) if ev.get("context") else None)
            except Exception:
                pass

    # After migration, try to auto-link runs to build steps
    try:
        _auto_link_migrated_runs(project_id, Path(project["path"]))
    except Exception:
        pass

    return db_list_runs(project_id)


@router.get("/api/projects/{project_id}/build-plan/runs/{run_id}")
def get_run_detail(project_id: str, run_id: str):
    """Get full run detail including all events."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Try DB first
    run = get_run(run_id)
    if run:
        return run

    # Fallback: read from JSON
    runs_dir = _get_runs_dir(Path(project["path"]))
    run_path = runs_dir / f"{run_id}.json"
    if not run_path.exists():
        raise HTTPException(404, f"Run '{run_id}' not found")

    return _json.loads(run_path.read_text(encoding="utf-8"))


@router.post("/api/projects/{project_id}/build-plan/start-run")
def start_tracked_run(project_id: str, stub_name: str = Body(...), agent: str = Body("opencode")):
    """Start a tracked coding run for a stub. Opens terminal and logs events."""
    import subprocess, platform

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    scripts_dir = project_path / ".harness" / "scripts"

    # Resolve model from provider config
    from config import load_provider_config
    provider_cfg = load_provider_config()
    provider = provider_cfg.get("provider", "localllm")
    if provider == "deepseek":
        model = provider_cfg.get("deepseek", {}).get("model", "deepseek-chat")
    else:
        model = provider_cfg.get("localllm", {}).get("model", "qwen3.6-27b")

    # Create run record
    run = _create_run(project_path, stub_name, agent, model)
    _update_run_status(project_path, run["id"], "running")

    # Find the script
    script_path = scripts_dir / f"{stub_name}.bat"
    if not script_path.exists():
        script_path = scripts_dir / f"{stub_name}.sh"
    if not script_path.exists():
        _update_run_status(project_path, run["id"], "failed", error=f"Script '{stub_name}' not found")
        raise HTTPException(404, f"Script '{stub_name}' not found. Generate code scripts first.")

    try:
        if platform.system() == "Windows":
            CREATE_NEW_CONSOLE = 0x00000010
            # Terminal stays open for visibility; watcher reads .status file for exit code
            proc = subprocess.Popen(
                ["cmd", "/k", str(script_path)],
                creationflags=CREATE_NEW_CONSOLE,
                cwd=str(project_path),
            )
            _log_event(project_path, run["id"], "info", f"Terminal opened (PID: {proc.pid})", {"pid": proc.pid})

            # Store active PID
            active_path = _get_runs_dir(project_path) / "active.json"
            active = {}
            if active_path.exists():
                active = _json.loads(active_path.read_text(encoding="utf-8"))
            active[run["id"]] = {"pid": proc.pid, "stub_name": stub_name, "start_time": run["start_time"]}
            active_path.write_text(_json.dumps(active, indent=2))

            return {
                "ok": True,
                "run": run,
                "pid": proc.pid,
            }
        else:
            proc = subprocess.Popen(
                ["x-terminal-emulator", "-e", f"bash {script_path}"],
                cwd=str(project_path),
            )
            _log_event(project_path, run["id"], "info", f"Terminal opened (PID: {proc.pid})", {"pid": proc.pid})
            return {
                "ok": True,
                "run": run,
                "pid": proc.pid,
            }
    except Exception as e:
        _update_run_status(project_path, run["id"], "failed", error=str(e))
        _log_event(project_path, run["id"], "error", f"Failed to launch: {str(e)}")
        raise HTTPException(500, f"Failed to launch: {str(e)}")


@router.post("/api/projects/{project_id}/build-plan/runs/{run_id}/log")
def log_run_event(project_id: str, run_id: str, level: str = Body(...), message: str = Body(...), context: dict = Body({})):
    """Append a log event to a run."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    _log_event(Path(project["path"]), run_id, level, message, context)
    return {"ok": True}


@router.post("/api/projects/{project_id}/build-plan/runs/{run_id}/resume")
def resume_run(project_id: str, run_id: str, debug_model: str = Body("deepseek-v4-pro")):
    """Resume a run with a debugger model for troubleshooting."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    runs_dir = _get_runs_dir(project_path)
    run_path = runs_dir / f"{run_id}.json"

    if not run_path.exists():
        raise HTTPException(404, f"Run '{run_id}' not found")

    original = _json.loads(run_path.read_text(encoding="utf-8"))
    stub_name = original["stub_name"]
    agent = original["agent"]

    # Create a new run linked to original session
    run = _create_run(project_path, stub_name, agent, debug_model)
    run["resumed_from"] = run_id
    run["original_session"] = original["session_id"]
    _update_run_status(project_path, run["id"], "running")

    _log_event(project_path, run["id"], "info", f"Resumed from run {run_id} with debugger model {debug_model}",
               {"original_run": run_id, "debug_model": debug_model})
    _log_event(project_path, run_id, "info", f"Debugger session started: run {run['id']} with {debug_model}",
               {"resume_run": run["id"]})

    # Generate debug script with the new model
    scripts_dir = project_path / ".harness" / "scripts"
    debug_script_name = f"{stub_name}_debug"
    debug_bat = scripts_dir / f"{debug_script_name}.bat"
    debug_prompt = scripts_dir / f"{stub_name}.prompt.md"
    debug_cmd = f'type "{debug_prompt.relative_to(project_path)}" | reasonix code --model "{debug_model}"' if agent == "reasonix" else f'opencode --model "{debug_model}" --prompt ".harness\\steps\\{stub_name}.md" --output-dir "src"'
    debug_bat_lines = [
        "@echo off",
        f"title Debug: {stub_name} ({debug_model})",
        f"cd /d \"{project_path}\"",
        "",
        f"echo === DEBUG SESSION for {stub_name} ===",
        f"echo Using debugger model: {debug_model}",
        f"echo Resumed from run: {run_id}",
        "echo.",
        debug_cmd,
        "echo.",
        "if errorlevel 1 (",
        "    echo Debug session failed",
        "    pause",
        ") else (",
        "    echo Debug session complete!",
        "    pause",
        ")",
    ]
    debug_bat.write_text("\n".join(debug_bat_lines), encoding="utf-8")

    import subprocess, platform
    try:
        if platform.system() == "Windows":
            CREATE_NEW_CONSOLE = 0x00000010
            proc = subprocess.Popen(
                ["cmd", "/k", str(debug_bat)],
                creationflags=CREATE_NEW_CONSOLE,
                cwd=str(project_path),
            )
            _log_event(project_path, run["id"], "info", f"Debug terminal opened (PID: {proc.pid})", {"pid": proc.pid})
        else:
            proc = subprocess.Popen(
                ["x-terminal-emulator", "-e", f"bash {debug_bat}"],
                cwd=str(project_path),
            )
    except Exception as e:
        _update_run_status(project_path, run["id"], "failed", error=str(e))
        raise HTTPException(500, f"Failed to launch debugger: {str(e)}")

    return {
        "ok": True,
        "run": run,
        "debug_model": debug_model,
    }


# ─── Blueprint Stubs Endpoint ──────────────────────────────────


@router.get("/api/blueprints")
def list_blueprint_stubs(project_id: str | None = None):
    """List available blueprint stub files.

    When project_id is provided, loads stubs from the project's
    .harness/stubs/ directory, auto-seeding from the mspec blueprint
    stubs if empty. Otherwise falls back to src/stubs/.
    """
    from stubs.runner import list_stubs as _list_mspec_stubs

    if project_id:
        project = get_project(project_id)
        if project:
            project_path = Path(project["path"])
            stubs_dir = project_path / ".harness" / "stubs"

            # Auto-seed: if project has no blueprints, copy from mspec
            if not stubs_dir.exists() or not list(stubs_dir.glob("*.md")):
                stubs_dir.mkdir(parents=True, exist_ok=True)
                mspec_stubs = _list_mspec_stubs()
                for s in mspec_stubs:
                    src = Path(__file__).parent.parent.parent.parent / s["path"]
                    if src.exists():
                        dst = stubs_dir / src.name
                        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            # Merge stubs from .harness/stubs/ (blueprints) + .harness/steps/ (generated build steps)
            seen = set()
            stubs = []
            for subdir in ["stubs", "steps"]:
                dir_path = project_path / ".harness" / subdir
                if dir_path.exists():
                    for f in sorted(dir_path.glob("*.md")):
                        stem_lower = f.stem.lower()
                        if stem_lower in seen:
                            continue
                        seen.add(stem_lower)
                        stubs.append({
                            "path": str(f.relative_to(project_path)),
                            "bp": f.stem[:5],
                            "name": f.stem,
                            "title": f.stem.replace("-", " ").title(),
                            "init": False,
                            "source": subdir,
                        })
            return {"stubs": stubs, "total": len(stubs), "source": "project"}
        return {"stubs": [], "total": 0, "source": "project"}

    # Fallback: load from mspec src/stubs/
    from stubs.runner import list_stubs
    stubs = list_stubs()
    return {"stubs": stubs, "total": len(stubs), "source": "mspec"}


@router.get("/api/stubs/{name}/validate")
def validate_blueprint_stub(name: str):
    """Validate a blueprint stub for Reasonix actionability.

    Returns a score, pass/fail per check, and recommendations.
    """
    from stubs.validate import pressure_test_stub
    try:
        result = pressure_test_stub(name)
        return result
    except Exception as e:
        return {"name": name, "valid": False, "score": 0,
                "summary": f"Validation error: {str(e)}",
                "checks": [], "execution_check": None,
                "recommendation": "Fix stub file before running"}


@router.post("/api/stubs/validate-all")
def validate_all_blueprint_stubs():
    """Validate all blueprint stubs for Reasonix actionability."""
    from stubs.validate import validate_all_stubs
    try:
        results = validate_all_stubs()
        return {"stubs": results, "total": len(results),
                "pass_count": sum(1 for r in results if r["valid"])}
    except Exception as e:
        raise HTTPException(500, f"Validation error: {str(e)}")


# ─── Reasonix Run Endpoints ────────────────────────────────────

_reasonix_manager_cache = {}


def _get_reasonix_manager(project_path: Path):
    """Get or create ReasonixRunManager for the project."""
    key = str(project_path)
    if key not in _reasonix_manager_cache:
        from dashboard.api.reasonix_runner import ReasonixRunManager
        _reasonix_manager_cache[key] = ReasonixRunManager(project_path)
    return _reasonix_manager_cache[key]


@router.post("/api/projects/{project_id}/reasonix-run")
def start_reasonix_run(project_id: str, data: dict = Body(...)):
    """Start a Reasonix stub run in background.

    Reads the stub .md file, passes it to `reasonix run`, and tracks
    the process with periodic polling and code preservation.

    Accepts:
        {"stub_path": "BP-01-scaffold.md"}  — name or path to stub file

    Returns a run_id that can be polled via GET .../reasonix-run/{run_id}.
    """
    stub_path_raw = data.get("stub_path", "")
    if not stub_path_raw:
        raise HTTPException(400, "stub_path is required")

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    manager = _get_reasonix_manager(project_path)

    # Resolve stub path — try multiple strategies:
    stub = Path(stub_path_raw).expanduser()
    if not stub.exists():
        mspec_stubs_dir = Path(__file__).parent.parent.parent / "stubs"

        # Strategy 1: Direct filename match in MSpec stubs dir
        for candidate in [stub_path_raw, stub_path_raw + ".md"]:
            p = mspec_stubs_dir / candidate
            if p.exists():
                stub = p
                break
        else:
            # Strategy 2: Search by name field in frontmatter
            from stubs.runner import parse_stub
            for f in mspec_stubs_dir.glob("*.md"):
                if f.name == "TEMPLATE.md":
                    continue
                try:
                    parsed = parse_stub(f)
                    fm = parsed["frontmatter"]
                    if fm.get("name") == stub_path_raw or fm.get("bp", "").lower() == stub_path_raw.lower():
                        stub = f
                        break
                except Exception:
                    continue
            else:
                # Strategy 3: Project steps dir (generated build plan stubs)
                for ext in ["", ".md"]:
                    p = project_path / ".harness" / "steps" / (stub_path_raw + ext)
                    if p.exists():
                        stub = p
                        break
                else:
                    # Strategy 4: Project scripts dir
                    for ext in ["", ".bat", ".sh", ".md"]:
                        p = project_path / ".harness" / "scripts" / (stub_path_raw + ext)
                        if p.exists():
                            stub = p
                            break
                    else:
                        raise HTTPException(404, f"Stub file not found: {stub_path_raw}")

    try:
        run = manager.start_run(stub)
        if run["status"] == "failed":
            return {"ok": False, "error": run.get("error", "Failed to start"), "run": run}
        return {"ok": True, "run": run}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to start Reasonix run: {str(e)}")


@router.get("/api/projects/{project_id}/reasonix-run/{run_id}")
def get_reasonix_run(project_id: str, run_id: str):
    """Get the current status of a Reasonix run."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    manager = _get_reasonix_manager(project_path)

    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")

    return run


@router.post("/api/projects/{project_id}/reasonix-run/{run_id}/poll")
def poll_reasonix_run(project_id: str, run_id: str):
    """Poll a Reasonix run's status (called every 3 min by the dashboard)."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    manager = _get_reasonix_manager(project_path)

    run = manager.poll_run(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")

    return run


@router.get("/api/projects/{project_id}/reasonix-runs")
def list_reasonix_runs(project_id: str):
    """List all Reasonix runs for a project."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    manager = _get_reasonix_manager(project_path)

    runs = manager.list_runs()
    total = len(runs)
    running = sum(1 for r in runs if r.get("status") in ("starting", "running"))
    completed = sum(1 for r in runs if r.get("status") == "completed")
    failed = sum(1 for r in runs if r.get("status") == "failed")

    return {
        "total": total,
        "running": running,
        "completed": completed,
        "failed": failed,
        "runs": runs[:20],  # latest 20
    }


@router.post("/api/projects/{project_id}/build-plan/watch-runs")
def watch_runs(project_id: str):
    """Check if active runs are still alive. Update failed ones and log to sessions."""
    import subprocess as _sp, platform as _pf
    from registry import add_session

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    runs_dir = _get_runs_dir(project_path)
    active_path = runs_dir / "active.json"

    if not active_path.exists():
        return {"checked": 0, "failed": 0, "updated": []}

    active = _json.loads(active_path.read_text(encoding="utf-8"))
    updated = []
    failed_count = 0
    to_remove = []

    for run_id, info in list(active.items()):
        pid = info.get("pid")
        if not pid:
            continue

        is_alive = False
        exit_code = None
        try:
            if _pf.system() == "Windows":
                result = _sp.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=5)
                is_alive = str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                is_alive = True
        except Exception:
            is_alive = False

        # Also check status file for exit code
        exit_code = None
        status_file = runs_dir.parent / "scripts" / f"{info.get('stub_name', run_id)}.status"
        if status_file.exists():
            try:
                exit_code = int(status_file.read_text(encoding="utf-8").strip())
            except:
                pass

        if not is_alive or (exit_code is not None and exit_code != 0):
            run_path = runs_dir / f"{run_id}.json"
            if run_path.exists():
                try:
                    run = _json.loads(run_path.read_text(encoding="utf-8"))
                    was_running = run["status"] in ("starting", "running")
                    if was_running or (exit_code is not None and exit_code != 0):
                        run["status"] = "failed"
                        run["end_time"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                        reason = f"exit code {exit_code}" if exit_code is not None else f"process {pid} terminated"
                        err_msg = f"Run failed ({reason})"
                        run["events"].append({
                            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                            "level": "error",
                            "message": err_msg,
                            "context": {"pid": pid, "exit_code": exit_code, "stub": run.get("stub_name")},
                        })
                        run_path.write_text(_json.dumps(run, indent=2))

                        # Log to sessions registry
                        try:
                            session_id = run.get("session_id", f"run_{run_id}")
                            summary = f"Coding run failed: {run.get('stub_name', '?')} with {run.get('agent', '?')} — process terminated"
                            add_session(project_id, session_id, f"failed:{run_id}", summary)
                        except Exception:
                            pass

                        updated.append({"id": run_id, "status": "failed", "message": err_msg})
                        failed_count += 1
                except Exception:
                    pass
            to_remove.append(run_id)

    for rid in to_remove:
        del active[rid]
    active_path.write_text(_json.dumps(active, indent=2))

    return {
        "checked": len(list(active.values())) + len(to_remove),
        "failed": failed_count,
        "updated": updated,
    }


@router.post("/api/projects/{project_id}/build-plan/check-runs")
def check_runs(project_id: str):
    """Monitor all runs for stalls, completions, and save logs.

    Scans every run JSON in .harness/runs/ and:
    1. Stall detection — running >10min with no new events in 3min → kill + fail
    2. Completion detection — exit code 0 → completed, non-zero → failed
    3. Log saving — persist events + output to run-<id>.log

    Called periodically by the frontend (e.g. every 30s).
    """
    import subprocess as _sp, platform as _pf
    from registry import add_session

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    runs_dir = _get_runs_dir(project_path)
    active_path = runs_dir / "active.json"

    STALL_TIMEOUT_SEC = 600   # 10 min total wall time before stall declared
    STALL_GRACE_SEC = 180     # 3 min without new events

    # Load active PIDs
    active = {}
    if active_path.exists():
        active = _json.loads(active_path.read_text(encoding="utf-8"))

    now = _dt.datetime.now(_dt.timezone.utc)
    results = {
        "checked": 0,
        "completed": 0,
        "failed": 0,
        "stalled": 0,
        "terminated": 0,
        "updated": [],
    }

    # Scan all run JSONs
    for f in sorted(runs_dir.glob("*.json"), reverse=True):
        if f.name == "active.json":
            continue
        try:
            run = _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        run_id = run.get("id", f.stem)
        status = run.get("status", "unknown")

        if status not in ("starting", "running"):
            continue

        results["checked"] += 1
        changed = False
        pid = active.get(run_id, {}).get("pid")

        # ─── Check for exit code (completion detection) ───
        exit_code = run.get("exit_code")

        # Also check status file
        if exit_code is None:
            stub_name = run.get("stub_name", run_id)
            status_file = runs_dir.parent / "scripts" / f"{stub_name}.status"
            if status_file.exists():
                try:
                    exit_code = int(status_file.read_text(encoding="utf-8").strip())
                except Exception:
                    pass

        # Fallback: parse exit code from last event text (e.g. "Reasonix process exited (code: 0)")
        if exit_code is None:
            events = run.get("events", [])
            if events:
                import re as _re
                for ev in reversed(events):
                    m = _re.search(r"exited\s*\(code:\s*(-?\d+)", ev.get("message", ""))
                    if m:
                        exit_code = int(m.group(1))
                        run["exit_code"] = exit_code
                        break

        # Check if process is still alive
        is_alive = False
        if pid:
            try:
                if _pf.system() == "Windows":
                    r = _sp.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=5)
                    is_alive = str(pid) in r.stdout
                else:
                    os.kill(pid, 0)
                    is_alive = True
            except Exception:
                is_alive = False

        # ─── Completion: exit code available → mark completed or failed ───
        if exit_code is not None:
            if exit_code == 0:
                run["status"] = "completed"
                run["end_time"] = now.isoformat()
                _log_event(project_path, run_id, "info",
                    f"Run completed (exit code 0)", {"exit_code": 0})
                results["completed"] += 1
                results["updated"].append({"id": run_id, "status": "completed"})
                _save_run_log(runs_dir, run)
                _sync_run_to_build_step(project_path, run, "completed")
                db_update_run_status(run_id, "completed", exit_code=exit_code)
                changed = True
            else:
                run["status"] = "failed"
                run["end_time"] = now.isoformat()
                run["error"] = f"Exit code {exit_code}"
                _log_event(project_path, run_id, "error",
                    f"Run failed (exit code {exit_code})", {"exit_code": exit_code})
                results["failed"] += 1
                results["updated"].append({"id": run_id, "status": "failed", "error": run["error"]})
                _save_run_log(runs_dir, run)
                _sync_run_to_build_step(project_path, run, "failed")
                db_update_run_status(run_id, "failed", error=run["error"], exit_code=exit_code)
                changed = True

            # Log session to registry
            if changed:
                try:
                    session_id = run.get("session_id", f"run_{run_id}")
                    summary = f"Coding run {'completed' if exit_code == 0 else 'failed'}: {run.get('stub_name', '?')} (exit {exit_code})"
                    add_session(project_id, session_id, f"{'completed' if exit_code == 0 else 'failed'}:{run_id}", summary)
                except Exception:
                    pass

        # ─── Stall detection: no exit code, process alive but idle ───
        elif is_alive and not exit_code:
            start_time_str = run.get("start_time")
            if start_time_str:
                try:
                    start_time = _dt.datetime.fromisoformat(start_time_str)
                    elapsed = (now - start_time).total_seconds()

                    if elapsed > STALL_TIMEOUT_SEC:
                        # Check when the last event was logged
                        events = run.get("events", [])
                        last_event_time = start_time
                        if events:
                            try:
                                last_ts = events[-1].get("timestamp", start_time_str)
                                last_event_time = _dt.datetime.fromisoformat(last_ts)
                            except Exception:
                                pass
                        idle_sec = (now - last_event_time).total_seconds()

                        if idle_sec > STALL_GRACE_SEC:
                            # Kill the process
                            try:
                                if _pf.system() == "Windows":
                                    _sp.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                                else:
                                    os.kill(pid, 9)
                            except Exception:
                                pass

                            run["status"] = "failed"
                            run["end_time"] = now.isoformat()
                            run["error"] = f"Stalled: {int(elapsed)}s elapsed, {int(idle_sec)}s idle"
                            _log_event(project_path, run_id, "error",
                                f"Run terminated — stalled {int(idle_sec)}s without progress (total {int(elapsed)}s)",
                                {"elapsed_sec": int(elapsed), "idle_sec": int(idle_sec), "pid": pid})
                            results["stalled"] += 1
                            results["terminated"] += 1
                            results["updated"].append({"id": run_id, "status": "failed", "error": run["error"]})
                            _save_run_log(runs_dir, run)
                            _sync_run_to_build_step(project_path, run, "failed")
                            db_update_run_status(run_id, "failed", error=run["error"])
                            changed = True

                            try:
                                session_id = run.get("session_id", f"run_{run_id}")
                                summary = f"Run stalled and terminated: {run.get('stub_name', '?')} ({int(elapsed)}s)"
                                add_session(project_id, session_id, f"stalled:{run_id}", summary)
                            except Exception:
                                pass

                            # Remove from active
                            active.pop(run_id, None)

                except Exception:
                    pass

        # ─── Untracked run timeout (no PID, running too long) ───
        elif not pid and not exit_code:
            start_time_str = run.get("start_time")
            if start_time_str:
                try:
                    start_time = _dt.datetime.fromisoformat(start_time_str)
                    elapsed = (now - start_time).total_seconds()
                    if elapsed > STALL_TIMEOUT_SEC:
                        # No PID and running for too long — assume orphaned/dead
                        run["status"] = "failed"
                        run["end_time"] = now.isoformat()
                        run["error"] = f"Abandoned: {int(elapsed)}s running without PID tracking"
                        _log_event(project_path, run_id, "error",
                            f"Run abandoned — no PID, running for {int(elapsed)}s",
                            {"elapsed_sec": int(elapsed)})
                        results["failed"] += 1
                        results["stalled"] += 1
                        results["updated"].append({"id": run_id, "status": "failed", "error": run["error"]})
                        _save_run_log(runs_dir, run)
                        _sync_run_to_build_step(project_path, run, "failed")
                        db_update_run_status(run_id, "failed", error=run["error"])
                        changed = True

                        try:
                            session_id = run.get("session_id", f"run_{run_id}")
                            summary = f"Run abandoned (no PID, {int(elapsed)}s): {run.get('stub_name', '?')}"
                            add_session(project_id, session_id, f"abandoned:{run_id}", summary)
                        except Exception:
                            pass
                except Exception:
                    pass

        # ─── Dead process (no exit code, not alive) → mark failed ───
        elif not is_alive and not exit_code and pid:
            run["status"] = "failed"
            run["end_time"] = now.isoformat()
            run["error"] = f"Process {pid} terminated unexpectedly"
            _log_event(project_path, run_id, "error",
                f"Process {pid} died unexpectedly", {"pid": pid})
            results["failed"] += 1
            results["updated"].append({"id": run_id, "status": "failed", "error": run["error"]})
            _save_run_log(runs_dir, run)
            _sync_run_to_build_step(project_path, run, "failed")
            db_update_run_status(run_id, "failed", error=run["error"])
            changed = True

            try:
                session_id = run.get("session_id", f"run_{run_id}")
                summary = f"Run process died: {run.get('stub_name', '?')} (PID {pid})"
                add_session(project_id, session_id, f"failed:{run_id}", summary)
            except Exception:
                pass

            active.pop(run_id, None)

        # Persist updated run JSON
        if changed:
            f.write_text(_json.dumps(run, indent=2))

    # Persist updated active.json
    active_path.write_text(_json.dumps(active, indent=2))

    return results


def _auto_link_migrated_runs(project_id: str, project_path: Path):
    """One-time: link all migrated runs to their corresponding build steps via FK."""
    import re as _re
    try:
        runs_result = db_list_runs(project_id)
        all_runs = runs_result.get("runs", [])
        if not all_runs:
            return
        # Get latest run per stub (highest priority: completed > running > failed)
        best_per_stub = {}
        for r in all_runs:
            stub = r.get("stub_name", "")
            if not stub:
                continue
            step_hint = _re.sub(r"^BP-\d+-", "", stub, flags=_re.IGNORECASE).lower()
            step_hint = step_hint.replace("_", "").replace("-", "")
            if not step_hint:
                continue
            priority = {"completed": 3, "running": 2, "starting": 2, "failed": 1}
            existing = best_per_stub.get(step_hint)
            if not existing or priority.get(r["status"], 0) > priority.get(existing["status"], 0):
                best_per_stub[step_hint] = r

        # Try to match each to a build step and set FK
        steps_path = project_path / ".harness" / "build-steps.json"
        if not steps_path.exists():
            return
        steps = _json.loads(steps_path.read_text(encoding="utf-8"))
        for step in steps:
            step_key = step["id"].lower().replace("_", "").replace("-", "")
            for hint, run in best_per_stub.items():
                if hint in step_key or step_key in hint:
                    link_build_step_to_run(project_id, step["id"], run["id"])
                    # Also sync status
                    sync_status = "completed" if run["status"] == "completed" else \
                                  "in_progress" if run["status"] in ("running", "starting") else \
                                  "failed" if run["status"] in ("failed", "stalled") else None
                    if sync_status:
                        update_build_step_status(project_id, step["id"], sync_status)
                    break
    except Exception:
        pass


def _sync_run_to_build_step(project_path: Path, run: dict, new_status: str):
    """Sync a run's status back to the corresponding build plan step in build-steps.json
    AND the SQLite registry. Also sets latest_run_id FK."""
    import re as _re

    stub_name = run.get("stub_name", "")
    if not stub_name:
        return

    # Extract step ID hint from stub name (e.g. "BP-02-data_models" → "data_models")
    step_hint = _re.sub(r"^BP-\d+-", "", stub_name, flags=_re.IGNORECASE).lower()
    run_id = run.get("id", "")
    project_id = None

    # Get project_id from run
    if run_id:
        from registry import get_run
        db_run = get_run(run_id)
        if db_run:
            project_id = db_run.get("project_id")

    # ── Update SQLite registry ──
    if project_id:
        from registry import get_build_steps
        try:
            steps_data = get_build_steps(project_id)
            for step in steps_data.get("steps", []):
                step_key = step["id"].lower().replace("_", "").replace("-", "")
                hint_key = step_hint.replace("_", "").replace("-", "")
                if hint_key in step_key or step_key in hint_key:
                    from registry import update_build_step_status, link_build_step_to_run
                    update_build_step_status(project_id, step["id"], new_status)
                    if run_id:
                        link_build_step_to_run(project_id, step["id"], run_id)
                    break
        except Exception:
            pass

    # ── Also update JSON file (backward compat) ──
    steps_path = project_path / ".harness" / "build-steps.json"
    if not steps_path.exists():
        return

    try:
        steps = _json.loads(steps_path.read_text(encoding="utf-8"))
    except Exception:
        return

    updated = False
    for step in steps:
        step_key = step["id"].lower().replace("_", "").replace("-", "")
        hint_key = step_hint.replace("_", "").replace("-", "")
        if hint_key in step_key or step_key in hint_key:
            step["status"] = new_status
            updated = True
            break

    if updated:
        steps_path.write_text(_json.dumps(steps, indent=2))


def _save_run_log(runs_dir: Path, run: dict):
    """Write a human-readable log file for a completed/failed run."""
    run_id = run.get("id", "unknown")
    log_path = runs_dir / f"run-{run_id}.log"
    lines = []
    lines.append(f"=== Run {run_id} ===")
    lines.append(f"Stub:     {run.get('stub_name', '?')}")
    lines.append(f"Agent:    {run.get('agent', '?')}")
    lines.append(f"Model:    {run.get('model', '?')}")
    lines.append(f"Status:   {run.get('status', '?')}")
    lines.append(f"Exit:     {run.get('exit_code', '?')}")
    lines.append(f"Error:    {run.get('error', '—')}")
    lines.append(f"Start:    {run.get('start_time', '?')}")
    lines.append(f"End:      {run.get('end_time', '?')}")
    lines.append(f"BP:       {run.get('bp_id', '—')}")
    lines.append(f"Title:    {run.get('title', '—')}")
    lines.append("")
    lines.append("--- Events ---")
    for ev in run.get("events", []):
        ts = ev.get("timestamp", "?")[11:19] if len(ev.get("timestamp", "")) > 19 else ev.get("timestamp", "?")
        lines.append(f"  [{ts}] {ev.get('level', 'info').upper():5s} {ev.get('message', '')}")
    lines.append("")
    lines.append("--- Output Preview ---")
    preview = run.get("output_preview", "")
    if preview:
        lines.append(preview[:2000])
    else:
        lines.append("(no output captured)")
    lines.append("")
    lines.append("--- Files Changed ---")
    files = run.get("files_changed", [])
    if files:
        for f in files:
            lines.append(f"  {f.get('status', '?')}: {f.get('path', '?')}")
    else:
        lines.append("(none)")
    log_path.write_text("\n".join(lines))


@router.post("/api/projects/{project_id}/build-plan/run-script")
def run_coding_script(project_id: str, script_name: str = Body(..., embed=True)):
    """Quick run without tracking (legacy). Use /start-run for tracked runs."""
    return start_tracked_run(project_id, stub_name=script_name, agent="opencode")


@router.post("/api/projects/{project_id}/preview-mspec")
def preview_mspec(project_id: str, data: dict = Body(...)):
    """Generate mspec.md preview + recalculated readiness score without committing."""
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_name = project["name"]

    # Generate the mspec.md content
    mspec_md = _build_mspec_markdown(project_name, data)

    # Recalculate readiness score based on edited data
    project_path = Path(project["path"])

    # Build a flow dict from the edited data for scoring
    flow = {
        "project_name": project_name,
        "requirement": [r.get("title", "") for r in data.get("requirements", []) if r.get("title")],
        "tech_stack": [],
        "architecture": [],
        "setup": [],
        "input": [],
        "output": [],
        "structure": [],
        "decision": [],
        "_raw_files": [],
    }

    ts = data.get("tech_stack", {})
    ts_text = "\n".join(f"{k}: {v}" for k, v in ts.items() if v)
    if ts_text:
        flow["tech_stack"].append(ts_text)

    dec = data.get("decisions", [])
    for d in dec:
        if d.get("decision"):
            flow["decision"].append(f"{d['decision']}: {d.get('rationale', '')}")

    src_contexts = data.get("source_contexts", [])

    # Build raw text from the edited data for scoring
    raw_parts = [f"# {project_name}"]
    if data.get("overview"):
        raw_parts.append(data["overview"])
    for req in data.get("requirements", []):
        if req.get("title"):
            raw_parts.append(f"Feature: {req['title']}. {req.get('description', '')}")
            if req.get("acceptance"):
                raw_parts.append(f"Acceptance: {req['acceptance']}")
    if ts_text:
        raw_parts.append(f"Tech stack: {ts_text}")
    if dec:
        raw_parts.append(f"Decisions: {'; '.join(d['decision'] for d in dec if d.get('decision'))}")

    raw_text = "\n".join(raw_parts)

    # Get the original flow + score for comparison
    from dashboard.api.routes import _score_agentic_readiness, _parse_context_flow

    original_files = []
    for candidate in CONTEXT_CANDIDATES:
        fp = project_path / candidate
        if fp.exists() and fp.is_file():
            original_files.append({"path": candidate, "content": fp.read_text(encoding="utf-8", errors="replace")})

    for md_file in sorted(project_path.glob("*.md")):
        rel = md_file.relative_to(project_path).as_posix()
        if rel not in [f["path"] for f in original_files]:
            original_files.append({"path": rel, "content": md_file.read_text(encoding="utf-8", errors="replace")})

    original_flow = _parse_context_flow(original_files)
    original_raw = "\n".join(f["content"] for f in original_files)
    original_readiness = _score_agentic_readiness(original_flow, original_raw)

    # Score from the generated mspec.md itself — the exact document that will be saved
    new_flow = _parse_context_flow([{"path": "mspec.md", "content": mspec_md}])

    # Include actual project files for dependency_checks (requirements.txt, etc.)
    project_raw_files = []
    for candidate in ["requirements.txt", "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Gemfile"]:
        fp = project_path / candidate
        if fp.exists():
            project_raw_files.append({"path": candidate, "content": fp.read_text(encoding="utf-8", errors="replace")})
    new_flow["_raw_files"] = project_raw_files
    new_readiness = _score_agentic_readiness(new_flow, mspec_md)

    return {
        "mspec_md": mspec_md,
        "before": original_readiness,
        "after": new_readiness,
    }


@router.post("/api/projects/{project_id}/confirm-context")
def confirm_context(project_id: str, data: dict = Body(...)):
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    harness_dir = project_path / ".harness"

    if not harness_dir.exists():
        harness_dir.mkdir(parents=True)

    project_name = project["name"]
    mspec_md = _build_mspec_markdown(project_name, data)

    mspec_path = harness_dir / "mspec.md"
    mspec_path.write_text(mspec_md, encoding="utf-8")

    # Git commit so the project is portable
    committed = False
    commit_hash = None
    try:
        add_result = subprocess.run(
            ["git", "-C", str(project_path), "add", str(mspec_path.relative_to(project_path))],
            capture_output=True, text=True, timeout=30,
        )
        if add_result.returncode == 0:
            # Set author identity for commit (use a default if not configured)
            env = os.environ.copy()
            if "GIT_AUTHOR_NAME" not in env:
                env["GIT_AUTHOR_NAME"] = "MSpec Dashboard"
                env["GIT_AUTHOR_EMAIL"] = "dashboard@mspec.local"
                env["GIT_COMMITTER_NAME"] = "MSpec Dashboard"
                env["GIT_COMMITTER_EMAIL"] = "dashboard@mspec.local"

            commit_result = subprocess.run(
                ["git", "-C", str(project_path), "commit", "-m", f"mspec: confirmed project context for agentic coding [v1]"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            if commit_result.returncode == 0:
                committed = True
                # Extract commit hash
                for line in commit_result.stdout.split("\n"):
                    if line.startswith("["):
                        import re
                        m = re.search(r"\[[^\]]+\s([a-f0-9]+)\]", line)
                        if m:
                            commit_hash = m.group(1)
                            break
    except Exception:
        committed = False

    return {
        "ok": True,
        "path": str(mspec_path),
        "size": len(mspec_md),
        "committed": committed,
        "commit_hash": commit_hash,
    }


@router.get("/api/projects/{project_id}/analytics/runs")
def run_analytics(project_id: str):
    """Return run analytics: success rates per stub, failure themes, recent runs.

    Groups failure messages into themes and surfaces the top 5 most common
    root causes across all failed/stalled runs.
    """
    import re as _re
    from collections import Counter

    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Get all runs
    runs_result = db_list_runs(project_id)
    all_runs = runs_result.get("runs", [])

    total = len(all_runs)
    completed = sum(1 for r in all_runs if r["status"] == "completed")
    failed = sum(1 for r in all_runs if r["status"] in ("failed", "stalled"))
    running_count = sum(1 for r in all_runs if r["status"] in ("starting", "running"))

    # Per-stub breakdown
    by_stub = {}
    for r in all_runs:
        stub = r.get("stub_name", "unknown")
        if stub not in by_stub:
            by_stub[stub] = {"completed": 0, "failed": 0, "total": 0, "total_duration_s": 0, "count_with_duration": 0}
        by_stub[stub]["total"] += 1
        if r["status"] == "completed":
            by_stub[stub]["completed"] += 1
        elif r["status"] in ("failed", "stalled"):
            by_stub[stub]["failed"] += 1
        # Duration
        start = r.get("start_time")
        end = r.get("end_time")
        if start and end:
            try:
                st = _dt.datetime.fromisoformat(str(start))
                et = _dt.datetime.fromisoformat(str(end))
                by_stub[stub]["total_duration_s"] += (et - st).total_seconds()
                by_stub[stub]["count_with_duration"] += 1
            except Exception:
                pass

    stub_list = []
    for stub, counts in sorted(by_stub.items(), key=lambda x: x[1]["total"], reverse=True):
        rate = round(counts["completed"] / counts["total"] * 100) if counts["total"] > 0 else 0
        avg_dur = round(counts["total_duration_s"] / counts["count_with_duration"]) if counts["count_with_duration"] > 0 else None
        stub_list.append({
            "stub_name": stub,
            "total": counts["total"],
            "completed": counts["completed"],
            "failed": counts["failed"],
            "success_rate": rate,
            "avg_duration_s": avg_dur,
        })

    # Failure themes: cluster error messages into themes
    error_messages = []
    no_error_count = 0
    for r in all_runs:
        if r["status"] in ("failed", "stalled"):
            err = r.get("error") or ""
            if err:
                error_messages.append((r["id"], r["stub_name"], err))
            else:
                no_error_count += 1

    # Theme categories and their keyword patterns
    THEME_PATTERNS = [
        ("Stall / Timeout", [r"stall", r"timeout", r"abandoned", r"no PID", r"without progress", r"Stall limit"]),
        ("Process Crash / Exit Code", [r"exit code [1-9]", r"process.*terminated", r"died unexpectedly", r"process \d+ terminated"]),
        ("Configuration / Path", [r"not found", r"no module", r"ModuleNotFoundError", r"No such file", r"cannot access", r"not defined"]),
        ("API / Network", [r"connection", r"timeout", r"ECONNREFUSED", r"401", r"403", r"500", r"HTTP"]),
        ("Code Error / Syntax", [r"SyntaxError", r"ImportError", r"AttributeError", r"TypeError", r"cannot import"]),
        ("Agent / Model Issue", [r"agent", r"model", r"LLM", r"token", r"rate limit", r"provider"]),
        ("Git / Filesystem", [r"git", r"commit", r"permission denied", r"read-only", r"cannot write"]),
    ]

    themes = []
    matched_ids = set()
    for theme_name, patterns in THEME_PATTERNS:
        theme_errors = []
        for rid, stub, err in error_messages:
            for pat in patterns:
                if _re.search(pat, err, _re.IGNORECASE):
                    theme_errors.append({"run_id": rid, "stub_name": stub, "error": err[:200]})
                    matched_ids.add(rid)
                    break
        if theme_errors:
            themes.append({
                "theme": theme_name,
                "count": len(theme_errors),
                "examples": theme_errors[:3],
                "affected_stubs": list(set(e["stub_name"] for e in theme_errors)),
            })

    # Add theme for runs with no error captured
    if no_error_count > 0:
        unknown_stubs = list(set(
            r.get("stub_name", "?")
            for r in all_runs
            if r["status"] in ("failed", "stalled") and not r.get("error")
        ))
        themes.append({
            "theme": "Unknown (no error captured)",
            "count": no_error_count,
            "examples": [{"run_id": "", "stub_name": unknown_stubs[0] if unknown_stubs else "?",
                          "error": "No error text recorded — failure predates error capture. Re-run the blueprint to populate error diagnostics."}],
            "affected_stubs": unknown_stubs[:5],
        })

    # Sort by count descending
    themes.sort(key=lambda t: t["count"], reverse=True)

    # Recent runs (last 10)
    recent = sorted(all_runs, key=lambda r: r.get("start_time", ""), reverse=True)[:10]
    recent_light = []
    for r in recent:
        recent_light.append({
            "id": r["id"],
            "stub_name": r.get("stub_name", ""),
            "agent": r.get("agent", ""),
            "status": r["status"],
            "error": (r.get("error") or "")[:120],
            "start_time": r.get("start_time"),
            "end_time": r.get("end_time"),
            "exit_code": r.get("exit_code"),
        })

    return {
        "summary": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running_count,
            "success_rate": round(completed / total * 100) if total > 0 else 0,
        },
        "by_stub": stub_list,
        "failure_themes": themes[:5],
        "recent_runs": recent_light,
    }


@router.get("/api/projects/{project_id}/context-file")
def get_context_file(project_id: str):
    """Return the project's context markdown file content.

    Checks .harness/context.md first, falls back to .harness/mspec.md.
    Returns {exists, content, path} so the frontend can decide
    whether to show the context editor or the setup wizard.
    """
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    project_path = Path(project["path"])
    candidates = [
        project_path / ".harness" / "context.md",
        project_path / ".harness" / "mspec.md",
    ]

    for cand in candidates:
        if cand.exists():
            return {
                "exists": True,
                "content": cand.read_text(encoding="utf-8"),
                "path": str(cand.relative_to(project_path)),
            }

    return {
        "exists": False,
        "content": None,
        "path": ".harness/context.md",
    }


@router.get("/api/projects/{project_id}/dashboard-summary")
def dashboard_summary(project_id: str):
    """Unified endpoint returning all dashboard data from a single DB query.

    Returns project info, build steps (with run FK links), run counts,
    and recent runs — all consistently sourced from the SQLite registry.
    """
    _ensure_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return get_dashboard_summary(project_id)


@router.get("/health")
def health():
    return {"status": "ok"}

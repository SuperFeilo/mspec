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
    return {
        "total_projects": len(projects),
        "total_sessions": total_sessions,
        "running_projects": running,
        "projects": projects,
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


def _build_mspec_markdown(project_name: str, data: dict) -> str:
    """Build a structured mspec.md from locked-in decisions."""
    import datetime

    requirements = data.get("requirements", [])
    tech_stack = data.get("tech_stack", {})
    decisions = data.get("decisions", [])
    source_contexts = data.get("source_contexts", [])
    provider_info = data.get("provider", {})

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
    lines.append(f"# {project_name}")
    lines.append("")
    lines.append("## Locked Requirements")
    lines.append("")

    priority_order = {"P0": "Must Have", "P1": "Should Have", "P2": "Nice to Have"}
    for priority in ("P0", "P1", "P2"):
        items = [r for r in requirements if r.get("priority") == priority]
        if items:
            label = priority_order.get(priority, priority)
            lines.append(f"### {priority} — {label}")
            lines.append("")
            for r in items:
                status_marker = "[x]" if r.get("locked") else "[ ]"
                lines.append(f"- {status_marker} **{r.get('title', '')}**")
                if r.get("description"):
                    lines.append(f"  - {r['description']}")
                if r.get("acceptance"):
                    lines.append(f"  - Acceptance: {r['acceptance']}")
            lines.append("")

    lines.append("## Tech Stack Decisions")
    lines.append("")
    if tech_stack:
        for category, value in tech_stack.items():
            if value:
                lines.append(f"- **{category.capitalize()}**: {value}")
        lines.append("")

    lines.append("## Architecture Decisions")
    lines.append("")
    if decisions:
        for d in decisions:
            lines.append(f"- **{d.get('decision', '')}**")
            if d.get("rationale"):
                lines.append(f"  - Rationale: {d['rationale']}")
        lines.append("")

    lines.append("## Source Contexts")
    lines.append("")
    for ctx in source_contexts:
        lines.append(f"- `{ctx}`")
    lines.append("")

    return "\n".join(lines)


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


@router.get("/health")
def health():
    return {"status": "ok"}

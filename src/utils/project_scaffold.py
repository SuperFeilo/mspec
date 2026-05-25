import os
import json
from pathlib import Path
from datetime import datetime, timezone

from config import load_config

SPEC_TEMPLATE = """# Project: {name}

## Description

## Requirements

## Tech Stack

## Constraints

## Acceptance Criteria
"""

MEMORY_TEMPLATE = {
    "project": None,
    "spec_version": "1",
    "tech_stack": {},
    "decisions": [],
    "architecture": {"layers": [], "services": []},
    "tasks": [],
    "session_count": 0,
    "last_session": None,
}


def scaffold_project(name: str, spec_content: str | None = None) -> Path:
    config = load_config()
    project_path = config.projects_path / name

    if project_path.exists():
        raise FileExistsError(f"Project '{name}' already exists at {project_path}")

    project_path.mkdir(parents=True)
    harness_dir = project_path / ".harness"
    harness_dir.mkdir()
    (harness_dir / "sessions").mkdir()
    (project_path / "src").mkdir()

    if spec_content:
        (harness_dir / "spec.md").write_text(spec_content)
    else:
        (harness_dir / "spec.md").write_text(SPEC_TEMPLATE.format(name=name))

    memory = dict(MEMORY_TEMPLATE)
    memory["project"] = name
    (harness_dir / "memory.json").write_text(json.dumps(memory, indent=2))

    (harness_dir / "plan.md").write_text(f"# Plan for {name}\n\n_Awaiting planner agent._\n")
    (harness_dir / "context.log").write_text("")

    gitkeep = project_path / "src" / ".gitkeep"
    gitkeep.write_text("")

    gitignore = project_path / ".gitignore"
    gitignore.write_text("__pycache__/\n*.pyc\n.env\nnode_modules/\n")

    return project_path


def get_project_path(name: str) -> Path:
    config = load_config()
    return config.projects_path / name


def generate_project_id(name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"prj_{name}_{ts}"


SPEC_PRIORITY = ["CONTEXT.md", "README.md", "SPEC.md"]


def retrofit_project(path: Path, name: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Project path does not exist: {path}")

    harness_dir = path / ".harness"
    if harness_dir.exists():
        raise FileExistsError(f"Project already has .harness directory at {harness_dir}")

    harness_dir.mkdir(parents=True)
    (harness_dir / "sessions").mkdir(exist_ok=True)

    spec_content = None
    for candidate in SPEC_PRIORITY:
        candidate_path = path / candidate
        if candidate_path.exists():
            spec_content = candidate_path.read_text()
            break

    if spec_content:
        (harness_dir / "spec.md").write_text(spec_content)
    else:
        (harness_dir / "spec.md").write_text(SPEC_TEMPLATE.format(name=name))

    memory = dict(MEMORY_TEMPLATE)
    memory["project"] = name
    (harness_dir / "memory.json").write_text(json.dumps(memory, indent=2))

    (harness_dir / "plan.md").write_text(f"# Plan for {name}\n\n_Awaiting planner agent._\n")
    (harness_dir / "context.log").write_text("")

    return path

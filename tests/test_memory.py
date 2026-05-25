import sys
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.manager import MemoryManager


def create_memory_project():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    (project_path / ".harness").mkdir()
    memory = {
        "project": "test_proj",
        "spec_version": "1",
        "tech_stack": {},
        "decisions": [],
        "architecture": {"layers": [], "services": []},
        "tasks": [],
        "session_count": 0,
        "last_session": None,
    }
    with open(project_path / ".harness" / "memory.json", "w") as f:
        json.dump(memory, f)
    return tmp, project_path


def test_memory_init():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        data = mgr.load()
        assert data["project"] == "test_proj"
        assert data["session_count"] == 0
    finally:
        tmp.cleanup()


def test_memory_add_task():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Create project")
        data = mgr.load()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "T001"
        assert data["tasks"][0]["status"] == "pending"
    finally:
        tmp.cleanup()


def test_memory_add_task_with_acceptance():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Create project", acceptance="Project exists")
        data = mgr.load()
        assert data["tasks"][0]["acceptance"] == "Project exists"
    finally:
        tmp.cleanup()


def test_memory_update_task():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Create project")
        mgr.update_task("T001", status="in_progress")
        data = mgr.load()
        assert data["tasks"][0]["status"] == "in_progress"
    finally:
        tmp.cleanup()


def test_memory_mark_done():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Create project")
        mgr.mark_task_done("T001", files=["main.py"])
        data = mgr.load()
        assert data["tasks"][0]["status"] == "done"
        assert "main.py" in data["tasks"][0]["files"]
    finally:
        tmp.cleanup()


def test_memory_mark_blocked():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Create project")
        mgr.mark_task_blocked("T001", "Dependency missing")
        data = mgr.load()
        assert data["tasks"][0]["status"] == "blocked"
        assert data["tasks"][0]["block_reason"] == "Dependency missing"
    finally:
        tmp.cleanup()


def test_memory_get_tasks_by_phase():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Task 1")
        mgr.add_task("T002", "setup", "Task 2")
        mgr.add_task("T003", "auth", "Task 3")
        setup_tasks = mgr.get_tasks_by_phase("setup")
        assert len(setup_tasks) == 2
        auth_tasks = mgr.get_tasks_by_phase("auth")
        assert len(auth_tasks) == 1
    finally:
        tmp.cleanup()


def test_memory_phase_progress():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_task("T001", "setup", "Task 1")
        mgr.add_task("T002", "setup", "Task 2")
        mgr.add_task("T003", "auth", "Task 3")
        mgr.mark_task_done("T001")
        mgr.mark_task_done("T003")

        progress = mgr.get_phase_progress()
        assert progress["setup"]["done"] == 1
        assert progress["setup"]["total"] == 2
        assert progress["auth"]["done"] == 1
        assert progress["auth"]["total"] == 1
    finally:
        tmp.cleanup()


def test_memory_append_context():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.append_context("builder", "Build task", "Done", 100)
        mgr.append_context("evaluator", "Evaluate", "Pass", 50)
        entries = mgr.get_context_entries()
        assert len(entries) == 2
        assert entries[0]["agent"] == "builder"
        assert entries[1]["agent"] == "evaluator"
    finally:
        tmp.cleanup()


def test_memory_clear_context():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.append_context("builder", "Build", "Done", 100)
        assert len(mgr.get_context_entries()) == 1
        mgr.clear_context()
        assert len(mgr.get_context_entries()) == 0
    finally:
        tmp.cleanup()


def test_memory_add_decision():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.add_decision("Auth design", "Use JWT", "Industry standard")
        data = mgr.load()
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["decision"] == "Use JWT"
    finally:
        tmp.cleanup()


def test_memory_increment_session():
    tmp, project_path = create_memory_project()
    try:
        mgr = MemoryManager(project_path)
        mgr.increment_session_count()
        data = mgr.load()
        assert data["session_count"] == 1
        mgr.increment_session_count()
        data = mgr.load()
        assert data["session_count"] == 2
    finally:
        tmp.cleanup()

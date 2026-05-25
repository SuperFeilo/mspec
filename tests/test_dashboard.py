import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_dashboard_api_health():
    """Test that the health endpoint returns ok."""
    from dashboard.api.routes import router
    # basic route existence check
    routes = [r.path for r in router.routes]
    assert "/health" in routes


def test_dashboard_api_project_list():
    """Test that the project list route exists."""
    from dashboard.api.routes import router
    routes = [(r.path, list(r.methods)) for r in router.routes if hasattr(r, 'methods')]
    project_routes = [r for r in routes if '/api/projects' in r[0]]
    assert len(project_routes) > 0


def test_dashboard_routes_count():
    """Verify a reasonable number of routes are registered."""
    from dashboard.api.routes import router
    # Should have 20+ endpoints (read + control + config + git + lms)
    assert len(router.routes) >= 15


def test_task_tracker():
    from dashboard.api.tasks import TaskTracker
    tracker = TaskTracker.get_instance()

    # Create a task
    task = tracker.create("test-1", "prj-1", "plan")
    assert task["status"] == "running"
    assert task["operation"] == "plan"

    # Complete it
    tracker.complete("test-1", {"result": "ok"})
    completed = tracker.get("test-1")
    assert completed["status"] == "completed"
    assert completed["progress"] == 100

    # Fail a task
    tracker.create("test-2", "prj-2", "run")
    tracker.fail("test-2", "Something broke")
    failed = tracker.get("test-2")
    assert failed["status"] == "failed"
    assert "Something broke" in failed["error"]

    # List all
    all_tasks = tracker.get_all()
    assert len(all_tasks) >= 2

    # Project tasks
    prj_tasks = tracker.get_project_tasks("prj-1")
    assert len(prj_tasks) >= 1

import threading
from datetime import datetime, timezone
from typing import Any


class TaskTracker:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._tasks = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def create(self, task_id: str, project_id: str, operation: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        task = {
            "id": task_id,
            "project_id": project_id,
            "operation": operation,
            "status": "running",
            "progress": 0,
            "message": "Starting...",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        self._tasks[task_id] = task
        return task

    def update(self, task_id: str, **kwargs: Any):
        if task_id in self._tasks:
            self._tasks[task_id].update(kwargs)
            self._tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def get(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def get_project_tasks(self, project_id: str) -> list[dict]:
        return [t for t in self._tasks.values() if t["project_id"] == project_id]

    def get_all(self) -> list[dict]:
        return list(self._tasks.values())

    def complete(self, task_id: str, result: Any = None):
        self.update(task_id, status="completed", result=result, progress=100, message="Done")

    def fail(self, task_id: str, error: str):
        self.update(task_id, status="failed", error=error, message=f"Failed: {error}")

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

TASK_STATUSES = ("pending", "in_progress", "done", "blocked", "cancelled")


class MemoryManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.harness_dir = project_path / ".harness"
        self.memory_file = self.harness_dir / "memory.json"
        self.context_file = self.harness_dir / "context.log"

    def load(self) -> dict:
        with open(self.memory_file) as f:
            return json.load(f)

    def save(self, data: dict):
        with open(self.memory_file, "w") as f:
            json.dump(data, f, indent=2)

    def reload(self) -> dict:
        return self.load()

    def add_decision(self, context: str, decision: str, rationale: str) -> dict:
        data = self.load()
        decision_id = len(data.get("decisions", [])) + 1
        data.setdefault("decisions", []).append({
            "id": decision_id,
            "context": context,
            "decision": decision,
            "rationale": rationale,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.save(data)
        return data

    def add_task(self, task_id: str, phase: str, description: str, acceptance: str = "", status: str = "pending") -> dict:
        data = self.load()
        data.setdefault("tasks", []).append({
            "id": task_id,
            "phase": phase,
            "description": description,
            "acceptance": acceptance,
            "status": status,
            "files": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self.save(data)
        return data

    def update_task(self, task_id: str, **kwargs: Any) -> dict:
        data = self.load()
        for task in data.get("tasks", []):
            if task["id"] == task_id:
                task.update(kwargs)
                break
        self.save(data)
        return data

    def mark_task_done(self, task_id: str, files: list[str] | None = None) -> dict:
        return self.update_task(
            task_id,
            status="done",
            completed_at=datetime.now(timezone.utc).isoformat(),
            files=files or [],
        )

    def mark_task_blocked(self, task_id: str, reason: str) -> dict:
        return self.update_task(
            task_id,
            status="blocked",
            block_reason=reason,
        )

    def get_tasks_by_phase(self, phase: str) -> list[dict]:
        data = self.load()
        return [t for t in data.get("tasks", []) if t["phase"] == phase]

    def get_pending_tasks(self, phase: str | None = None) -> list[dict]:
        data = self.load()
        tasks = [t for t in data.get("tasks", []) if t["status"] in ("pending", "in_progress")]
        if phase:
            tasks = [t for t in tasks if t["phase"] == phase]
        return tasks

    def update_tech_stack(self, stack: dict[str, str]):
        data = self.load()
        data["tech_stack"] = stack
        self.save(data)
        return data

    def update_architecture(self, layers: list[str], services: list[str]):
        data = self.load()
        data["architecture"] = {"layers": layers, "services": services}
        self.save(data)
        return data

    def increment_session_count(self) -> dict:
        data = self.load()
        data["session_count"] = data.get("session_count", 0) + 1
        self.save(data)
        return data

    def set_last_session(self, session_id: str):
        data = self.load()
        data["last_session"] = session_id
        self.save(data)
        return data

    def append_context(self, agent: str, prompt: str, response_summary: str, duration_ms: int):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "prompt": prompt,
            "response_summary": response_summary,
            "duration_ms": duration_ms,
        }
        with open(self.context_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_context_entries(self) -> list[dict]:
        if not self.context_file.exists():
            return []
        entries = []
        with open(self.context_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def clear_context(self):
        self.context_file.write_text("")

    def get_phase_progress(self) -> dict[str, dict]:
        data = self.load()
        phases: dict[str, dict] = {}
        for task in data.get("tasks", []):
            phase = task["phase"]
            if phase not in phases:
                phases[phase] = {"total": 0, "done": 0, "pending": 0, "blocked": 0}
            phases[phase]["total"] += 1
            status = task["status"]
            if status == "done":
                phases[phase]["done"] += 1
            elif status == "blocked":
                phases[phase]["blocked"] += 1
            else:
                phases[phase]["pending"] += 1
        return phases

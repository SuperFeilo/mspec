import subprocess
import time
import re
from pathlib import Path

from config import load_config
from agents.router import AgentRouter
from memory.manager import MemoryManager
from registry import (
    update_project_status,
    add_session,
    add_agent_call,
)


class Executor:
    def __init__(self, project_name: str, project_id: str):
        self.config = load_config()
        self.router = AgentRouter()
        self.project_name = project_name
        self.project_id = project_id
        self.project_path = Path(self.config.projects_dir).expanduser() / project_name
        self.memory = MemoryManager(self.project_path)
        self.session_tag = f"session_{int(time.time())}"

    def _log_agent_call(self, agent: str, model: str, prompt: str, status: str, duration_ms: int, tokens_in: int = 0, tokens_out: int = 0):
        add_agent_call(
            self.project_id,
            self.session_tag,
            agent,
            model,
            prompt[:500],
            status,
            tokens_in,
            tokens_out,
            duration_ms,
        )

    def run_planner(self) -> str:
        spec_path = self.project_path / ".harness" / "spec.md"
        spec = spec_path.read_text()

        update_project_status(self.project_id, "running", "planning")

        start = time.time()
        plan = self.router.plan(spec)
        duration_ms = int((time.time() - start) * 1000)

        plan_path = self.project_path / ".harness" / "plan.md"
        plan_path.write_text(f"# Plan for {self.project_name}\n\n{plan}\n")

        # ─── Critical fix: wire planner output → structured memory tasks ───
        self._parse_plan_into_tasks(plan)

        self._log_agent_call("planner", self.router._get_model("planner"), spec[:500], "success", duration_ms)
        self.memory.append_context("planner", "Generate plan", plan[:500], duration_ms)

        return plan

    def _parse_plan_into_tasks(self, plan_text: str):
        """Parse plan.md text into structured tasks in memory.json.

        Expects format from the planner prompt:
            ## Phase 1: <name>
            - [T001] <description> — <acceptance criteria>
            - [T002] <description> — <acceptance criteria>
        """
        phase_pattern = re.compile(r'##\s+Phase\s+\d+:\s+(.+)')
        task_pattern = re.compile(r'-\s+\[(T\d+)\]\s+(.+?)(?:\s+[—–-]\s+(.+))?$')

        current_phase = None
        tasks_registered = 0

        for line in plan_text.split('\n'):
            phase_match = phase_pattern.match(line.strip())
            if phase_match:
                current_phase = phase_match.group(1).strip()
                continue

            task_match = task_pattern.match(line.strip())
            if task_match and current_phase:
                task_id = task_match.group(1)
                description = task_match.group(2).strip()
                acceptance = (task_match.group(3) or "").strip()

                self.memory.add_task(
                    task_id=task_id,
                    phase=current_phase,
                    description=description,
                    acceptance=acceptance,
                    status="pending",
                )
                tasks_registered += 1

        if tasks_registered == 0:
            # Fallback: if no structured tasks found, register the whole plan as one task
            self.memory.add_task(
                task_id="T001",
                phase="implementation",
                description=plan_text[:500],
                status="pending",
            )

    def run_phase(self, phase_name: str) -> dict:
        update_project_status(self.project_id, "running", phase_name)

        tasks = self.memory.get_tasks_by_phase(phase_name)
        pending = [t for t in tasks if t["status"] in ("pending", "in_progress")]

        results = {"phase": phase_name, "completed": 0, "failed": 0, "blocked": 0}

        for task in pending:
            task_result = self._execute_task(task)
            if task_result == "done":
                results["completed"] += 1
            elif task_result == "blocked":
                results["blocked"] += 1
            else:
                results["failed"] += 1

        return results

    def _execute_task(self, task: dict) -> str:
        task_id = task["id"]
        description = task["description"]

        self.memory.update_task(task_id, status="in_progress")
        self.memory.append_context("executor", f"Starting {task_id}", description, 0)

        project_context = self._build_project_context()
        decisions = self.memory.load().get("decisions", [])

        max_retries = self.config.global_settings.max_retries

        for attempt in range(max_retries):
            build_result = self._build_task(project_context, task, decisions)

            if not build_result.get("response"):
                self.memory.append_context("builder", f"Attempt {attempt+1}", "No response", build_result.get("duration_ms", 0))
                continue

            eval_result = self._evaluate_task(task, build_result["response"])

            if eval_result.get("pass"):
                files = build_result.get("files", [])
                self.memory.mark_task_done(task_id, files=files)
                self.memory.append_context("builder", f"Task {task_id} done", description, build_result.get("duration_ms", 0))
                self._log_agent_call("builder", self.router._get_model("builder"), description, "success", build_result.get("duration_ms", 0))
                return "done"

            feedback = eval_result.get("feedback", "Unknown issues")
            self.memory.append_context("evaluator", f"Attempt {attempt+1} failed", feedback, 0)
            self._log_agent_call("evaluator", self.router._get_model("evaluator"), description, "retry", 0)

            decisions.append({"decision": f"Feedback: {feedback}"})

        self.memory.mark_task_blocked(task_id, f"Failed after {max_retries} attempts")
        self._log_agent_call("builder", self.router._get_model("builder"), description, "failed", 0)
        return "failed"

    def _build_task(self, project_context: str, task: dict, decisions: list[dict]) -> dict:
        result = self.router.build(
            self.project_path,
            project_context,
            task,
            decisions,
        )
        result["files"] = self._detect_changed_files()
        return result

    def _evaluate_task(self, task: dict, generated_content: str) -> dict:
        return self.router.evaluate(
            task.get("description", ""),
            task.get("acceptance", task.get("description", "")),
            generated_content,
        )

    def _build_project_context(self) -> str:
        data = self.memory.load()
        parts = [
            f"Project: {data.get('project', 'unknown')}",
            f"Tech Stack: {data.get('tech_stack', {})}",
        ]
        if data.get("architecture"):
            parts.append(f"Architecture: {data['architecture']}")
        return "\n".join(parts)

    def _detect_changed_files(self) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_path), "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")
        except Exception:
            pass
        return []

    def run_qa(self, task: dict, files: list[str]) -> dict:
        tech_stack = self.memory.load().get("tech_stack", {})
        return self.router.qa(
            task.get("description", ""),
            files,
            tech_stack,
        )

    def run_tests(self, test_commands: list[str]) -> list[dict]:
        results = []
        for cmd in test_commands:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=str(self.project_path),
                    timeout=60,
                )
                results.append({
                    "command": cmd,
                    "returncode": result.returncode,
                    "output": result.stdout[:500],
                    "error": result.stderr[:500],
                    "passed": result.returncode == 0,
                })
            except subprocess.TimeoutExpired:
                results.append({
                    "command": cmd,
                    "returncode": -1,
                    "output": "",
                    "error": "Timeout",
                    "passed": False,
                })
        return results

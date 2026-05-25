import subprocess
import json
import time
import re
from pathlib import Path

from config import load_config


class OpencodeClient:
    def __init__(self):
        self.config = load_config()

    def run_task(self, project_path: Path, agent_name: str, prompt: str, model_override: str | None = None) -> dict:
        agent_config = self.config.agents.get(agent_name)
        if not agent_config:
            raise ValueError(f"Unknown agent: {agent_name}")

        model = model_override or agent_config.model
        opencode_agent = agent_config.opencode_agent or "build"

        cmd = [
            "opencode", "run",
            "--model", model,
            "--agent", opencode_agent,
            "--print-logs",
            prompt,
        ]

        start = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(project_path),
            timeout=300,
        )
        duration_ms = int((time.time() - start) * 1000)

        session_id = self._extract_session_id(result.stderr)
        response = self._extract_response(result.stdout)

        return {
            "session_id": session_id,
            "response": response,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "duration_ms": duration_ms,
        }

    def _extract_session_id(self, stderr: str) -> str | None:
        match = re.search(r'id=(ses_[a-zA-Z0-9]+)', stderr)
        return match.group(1) if match else None

    def _extract_response(self, stdout: str) -> str:
        lines = []
        for line in stdout.split("\n"):
            try:
                data = json.loads(line)
                if data.get("type") == "message.part.delta" and "text" in data:
                    lines.append(data["text"])
            except (json.JSONDecodeError, KeyError):
                continue
        return "\n".join(lines) if lines else stdout[:2000]

    def export_session(self, session_id: str) -> dict | None:
        result = subprocess.run(
            ["opencode", "export", session_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

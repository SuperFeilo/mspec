import json
from pathlib import Path
from datetime import datetime, timezone

from agents.router import AgentRouter
from memory.manager import MemoryManager
from git.manager import GitManager
from registry import update_checkpoint, add_session


class Compactor:
    def __init__(self, project_name: str, project_id: str):
        from config import load_config
        config = load_config()
        self.project_path = Path(config.projects_dir).expanduser() / project_name
        self.project_id = project_id
        self.memory = MemoryManager(self.project_path)
        self.git = GitManager(self.project_path)
        self.router = AgentRouter()

    def checkpoint(self) -> dict:
        entries = self.memory.get_context_entries()
        memory_state = self.memory.load()

        if not entries:
            return self._git_commit("checkpoint: no changes")

        summary = self._compact_session(entries, memory_state)

        session_id = f"session_{int(datetime.now(timezone.utc).timestamp())}"
        tag_name = f"checkpoint_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        summary_path = self.project_path / ".harness" / "sessions" / f"{tag_name}.json"
        summary_path.write_text(json.dumps(summary, indent=2))

        self.memory.set_last_session(session_id)
        self.memory.increment_session_count()

        self._git_commit(f"checkpoint: {summary.get('session_summary', 'session summary')}")
        self.git.tag(tag_name)

        update_checkpoint(self.project_id)
        add_session(self.project_id, session_id, tag_name, json.dumps(summary))

        self.memory.clear_context()

        return {
            "session_id": session_id,
            "tag": tag_name,
            "summary": summary,
        }

    def _compact_session(self, entries: list[dict], memory_state: dict) -> dict:
        from agents.prompts import get_compactor_prompt
        prompt = get_compactor_prompt(entries, memory_state)
        model = self.router._get_model("compactor")
        messages = [
            {"role": "system", "content": "You are a session summarizer. Be concise and structured."},
            {"role": "user", "content": prompt},
        ]
        return self.router.lms.chat_json(model, messages)

    def _git_commit(self, message: str):
        if self.git.has_changes():
            self.git.add([".harness/", "src/"])
            self.git.commit(message)

    def resume(self, from_tag: str | None = None) -> dict:
        memory_state = self.memory.load()
        sessions = []

        if from_tag:
            session_file = self.project_path / ".harness" / "sessions" / f"{from_tag}.json"
            if session_file.exists():
                sessions.append(json.loads(session_file.read_text()))
        else:
            session_dir = self.project_path / ".harness" / "sessions"
            if session_dir.exists():
                session_files = sorted(session_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                for sf in session_files[:3]:
                    sessions.append(json.loads(sf.read_text()))

        context_parts = []
        for s in sessions:
            context_parts.append(s.get("session_summary", ""))
            for d in s.get("decisions_made", []):
                context_parts.append(f"Decision: {d}")

        return {
            "memory_state": memory_state,
            "recent_sessions": sessions,
            "context": "\n\n".join(context_parts),
        }

import json
import math
from pathlib import Path

from lms.client import LMSClient


class Embedder:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.sessions_dir = project_path / ".harness" / "sessions"
        self.embeddings_file = self.sessions_dir / "embeddings.json"
        self.client = LMSClient()

    def _load_embeddings(self) -> dict:
        if self.embeddings_file.exists():
            return json.loads(self.embeddings_file.read_text())
        return {}

    def _save_embeddings(self, data: dict):
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings_file.write_text(json.dumps(data, indent=2))

    def embed_session(self, session_file: Path) -> str | None:
        if not session_file.exists():
            return None

        try:
            session_data = json.loads(session_file.read_text())
            text = self._extract_session_text(session_data)
            if not text:
                return None

            embedding = self.client.embed(text)

            embeddings = self._load_embeddings()
            embeddings[session_file.stem] = {
                "embedding": embedding,
                "summary": session_data.get("session_summary", ""),
                "file": session_file.name,
            }
            self._save_embeddings(embeddings)
            return session_file.stem
        except Exception as e:
            print(f"Embed error for {session_file.name}: {e}")
            return None

    def _extract_session_text(self, session_data: dict) -> str:
        parts = []
        if session_data.get("session_summary"):
            parts.append(session_data["session_summary"])
        if session_data.get("decisions_made"):
            parts.append("Decisions: " + ", ".join(session_data["decisions_made"]))
        if session_data.get("next_steps"):
            parts.append("Next steps: " + ", ".join(session_data["next_steps"]))
        if session_data.get("files_created"):
            parts.append("Files: " + ", ".join(session_data["files_created"]))
        return " ".join(parts)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        embeddings = self._load_embeddings()
        if not embeddings:
            return []

        query_embedding = self.client.embed(query)
        scored = []

        for session_id, data in embeddings.items():
            similarity = self._cosine_similarity(query_embedding, data["embedding"])
            scored.append({
                "session_id": session_id,
                "similarity": similarity,
                "summary": data.get("summary", ""),
                "file": data.get("file", ""),
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def embed_all_sessions(self) -> int:
        if not self.sessions_dir.exists():
            return 0

        existing = self._load_embeddings()
        count = 0

        for session_file in self.sessions_dir.glob("*.json"):
            if session_file.stem not in existing:
                if self.embed_session(session_file):
                    count += 1

        return count

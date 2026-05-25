import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_embedder_init():
    from memory.embedder import Embedder
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        embedder = Embedder(project_path)
        assert embedder.project_path == project_path
        assert embedder.sessions_dir == project_path / ".harness" / "sessions"


def test_embedder_no_sessions():
    from memory.embedder import Embedder
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        embedder = Embedder(project_path)
        results = embedder.search("test query")
        assert results == []


def test_embedder_cosine_similarity():
    from memory.embedder import Embedder
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        embedder = Embedder(project_path)

        # Same vectors = similarity 1.0
        sim = embedder._cosine_similarity([1, 0, 0], [1, 0, 0])
        assert abs(sim - 1.0) < 0.001

        # Orthogonal = similarity 0
        sim = embedder._cosine_similarity([1, 0, 0], [0, 1, 0])
        assert abs(sim) < 0.001

        # Zero vectors = similarity 0
        sim = embedder._cosine_similarity([0, 0], [0, 0])
        assert sim == 0.0


def test_embedder_extract_session_text():
    from memory.embedder import Embedder
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        embedder = Embedder(project_path)

        text = embedder._extract_session_text({
            "session_summary": "Built auth module",
            "decisions_made": ["Use JWT"],
            "files_created": ["auth.py"],
        })
        assert "Built auth module" in text
        assert "JWT" in text
        assert "auth.py" in text


def test_embedder_load_save_embeddings():
    from memory.embedder import Embedder
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        embedder = Embedder(project_path)

        saved = {"session_1": {"embedding": [0.1, 0.2], "summary": "test", "file": "test.json"}}
        embedder._save_embeddings(saved)
        loaded = embedder._load_embeddings()
        assert loaded == saved


def test_embedder_embed_all_no_sessions():
    from memory.embedder import Embedder
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        embedder = Embedder(project_path)
        count = embedder.embed_all_sessions()
        assert count == 0

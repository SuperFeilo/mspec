import sys
import json
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.project_scaffold import retrofit_project, SPEC_PRIORITY


def test_retrofit_creates_harness():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    try:
        result = retrofit_project(project_path, "test_proj")
        assert result == project_path
        assert (project_path / ".harness").exists()
        assert (project_path / ".harness" / "memory.json").exists()
        assert (project_path / ".harness" / "spec.md").exists()
        assert (project_path / ".harness" / "plan.md").exists()
        assert (project_path / ".harness" / "context.log").exists()
        assert (project_path / ".harness" / "sessions").is_dir()
    finally:
        tmp.cleanup()


def test_retrofit_memory_content():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    try:
        retrofit_project(project_path, "test_proj")
        memory = json.loads((project_path / ".harness" / "memory.json").read_text())
        assert memory["project"] == "test_proj"
        assert memory["session_count"] == 0
        assert memory["tasks"] == []
    finally:
        tmp.cleanup()


def test_retrofit_detects_context_md():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    (project_path / "CONTEXT.md").write_text("# Context\n\nThis is the project context.")
    try:
        retrofit_project(project_path, "test_proj")
        spec = (project_path / ".harness" / "spec.md").read_text()
        assert "# Context" in spec
        assert "This is the project context" in spec
    finally:
        tmp.cleanup()


def test_retrofit_detects_readme_md():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    (project_path / "README.md").write_text("# README\n\nProject readme.")
    try:
        retrofit_project(project_path, "test_proj")
        spec = (project_path / ".harness" / "spec.md").read_text()
        assert "# README" in spec
        assert "Project readme" in spec
    finally:
        tmp.cleanup()


def test_retrofit_context_priority_over_readme():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    (project_path / "CONTEXT.md").write_text("# Context priority")
    (project_path / "README.md").write_text("# README fallback")
    try:
        retrofit_project(project_path, "test_proj")
        spec = (project_path / ".harness" / "spec.md").read_text()
        assert "# Context priority" in spec
        assert "# README fallback" not in spec
    finally:
        tmp.cleanup()


def test_retrofit_no_spec_file():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    try:
        retrofit_project(project_path, "test_proj")
        spec = (project_path / ".harness" / "spec.md").read_text()
        assert "test_proj" in spec
    finally:
        tmp.cleanup()


def test_retrofit_existing_harness_error():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    (project_path / ".harness").mkdir()
    try:
        try:
            retrofit_project(project_path, "test_proj")
            assert False, "Should have raised FileExistsError"
        except FileExistsError:
            pass
    finally:
        tmp.cleanup()


def test_retrofit_nonexistent_path_error():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "does_not_exist"
    try:
        try:
            retrofit_project(project_path, "test_proj")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass
    finally:
        tmp.cleanup()


def test_retrofit_does_not_modify_existing_files():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name) / "test_proj"
    project_path.mkdir()
    original_content = "original file content"
    (project_path / "main.py").write_text(original_content)
    try:
        retrofit_project(project_path, "test_proj")
        assert (project_path / "main.py").read_text() == original_content
        harness_files = list((project_path / ".harness").iterdir())
        assert all(f.name.startswith(("memory", "spec", "plan", "context", "sessions")) for f in harness_files)
    finally:
        tmp.cleanup()

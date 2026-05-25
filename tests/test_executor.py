import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_executor_init():
    from agents.executor import Executor

    with TemporaryDirectory() as tmp:
        with patch('agents.executor.load_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.projects_dir = tmp
            mock_cfg.global_settings.max_retries = 3
            mock_config.return_value = mock_cfg

            executor = Executor("test_proj", "prj_001")
            assert executor.project_name == "test_proj"
            assert executor.project_id == "prj_001"
            assert executor.session_tag is not None


def test_executor_build_project_context():
    from agents.executor import Executor
    import json

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        (project_path / ".harness").mkdir()
        with open(project_path / ".harness" / "memory.json", "w") as f:
            json.dump({
                "project": "test_proj",
                "tech_stack": {"lang": "Python"},
                "architecture": {"layers": ["api"], "services": ["fastapi"]},
                "tasks": [],
            }, f)

        with patch('agents.executor.load_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.projects_dir = str(Path(tmp).parent)
            mock_cfg.global_settings.max_retries = 3
            mock_config.return_value = mock_cfg

            executor = Executor("test_proj", "prj_001")
            executor.memory = __import__('memory.manager', fromlist=['MemoryManager']).MemoryManager(project_path)

            context = executor._build_project_context()
            assert "test_proj" in context
            assert "Python" in context
            assert "fastapi" in context


def test_detect_changed_files_no_git():
    from agents.executor import Executor
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        with patch('agents.executor.load_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.projects_dir = str(Path(tmp).parent)
            mock_cfg.global_settings.max_retries = 3
            mock_config.return_value = mock_cfg

            executor = Executor("test_proj", "prj_001")
            files = executor._detect_changed_files()
            assert files == []


def test_parse_plan_into_tasks():
    from agents.executor import Executor
    import json

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        (project_path / ".harness").mkdir()
        with open(project_path / ".harness" / "memory.json", "w") as f:
            json.dump({"project": "test", "tasks": [], "decisions": [], "session_count": 0}, f)

        with patch('agents.executor.load_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.projects_dir = str(Path(tmp).parent)
            mock_cfg.global_settings.max_retries = 3
            mock_config.return_value = mock_cfg

            executor = Executor.__new__(Executor)
            executor.memory = __import__('memory.manager', fromlist=['MemoryManager']).MemoryManager(project_path)

            plan_text = """## Phase 1: Setup
- [T001] Create project scaffold — Basic files exist
- [T002] Configure database — DB connection works

## Phase 2: API
- [T003] Health endpoint — Returns 200
"""
            executor._parse_plan_into_tasks(plan_text)

            tasks = executor.memory.load().get("tasks", [])
            assert len(tasks) == 3
            assert tasks[0]["phase"] == "Setup"
            assert tasks[0]["acceptance"] == "Basic files exist"
            assert tasks[2]["phase"] == "API"


def test_parse_plan_fallback():
    """If no structured tasks found, the parser should create one fallback task."""
    from agents.executor import Executor
    import json

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        (project_path / ".harness").mkdir()
        with open(project_path / ".harness" / "memory.json", "w") as f:
            json.dump({"project": "test", "tasks": [], "decisions": [], "session_count": 0}, f)

        with patch('agents.executor.load_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.projects_dir = str(Path(tmp).parent)
            mock_cfg.global_settings.max_retries = 3
            mock_config.return_value = mock_cfg

            executor = Executor.__new__(Executor)
            executor.memory = __import__('memory.manager', fromlist=['MemoryManager']).MemoryManager(project_path)

            # Plain text with no structure
            executor._parse_plan_into_tasks("Just some unstructured text about the plan.")

            tasks = executor.memory.load().get("tasks", [])
            assert len(tasks) == 1
            assert tasks[0]["id"] == "T001"

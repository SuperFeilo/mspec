import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.prompts import (
    get_planner_prompt,
    get_builder_prompt,
    get_evaluator_prompt,
    get_qa_prompt,
    get_compactor_prompt,
)


def test_planner_prompt():
    prompt = get_planner_prompt("Build a REST API")
    assert "Build a REST API" in prompt
    assert "Phase" in prompt


def test_builder_prompt():
    prompt = get_builder_prompt(
        "Project context here",
        {"id": "T001", "phase": "auth", "description": "JWT middleware", "acceptance": "Returns 401 for invalid tokens"},
        [{"decision": "Use JWT"}],
    )
    assert "T001" in prompt
    assert "JWT middleware" in prompt
    assert "Use JWT" in prompt


def test_evaluator_prompt():
    prompt = get_evaluator_prompt(
        "JWT middleware",
        "Returns 401 for invalid tokens",
        "code content here",
    )
    assert "JWT middleware" in prompt
    assert "code content here" in prompt


def test_qa_prompt():
    prompt = get_qa_prompt(
        "JWT middleware",
        ["src/auth/middleware.py"],
        {"backend": "FastAPI"},
    )
    assert "JWT middleware" in prompt
    assert "middleware.py" in prompt


def test_compactor_prompt():
    prompt = get_compactor_prompt(
        [{"agent": "builder", "prompt": "test"}],
        {"project": "test", "tasks": []},
    )
    assert "builder" in prompt
    assert "test" in prompt


def test_lms_client_init():
    from lms.client import LMSClient
    client = LMSClient()
    assert client.client is not None


def test_opencode_client_init():
    from agents.opencode_client import OpencodeClient
    client = OpencodeClient()
    assert client.config is not None


def test_opencode_extract_session_id():
    from agents.opencode_client import OpencodeClient
    client = OpencodeClient()
    stderr = "INFO session id=ses_abc123xyz created"
    assert client._extract_session_id(stderr) == "ses_abc123xyz"


def test_opencode_extract_session_id_none():
    from agents.opencode_client import OpencodeClient
    client = OpencodeClient()
    assert client._extract_session_id("no session here") is None


def test_agent_router_init():
    from agents.router import AgentRouter
    router = AgentRouter()
    assert router.lms is not None
    assert router.opencode is not None


def test_agent_router_get_model():
    from agents.router import AgentRouter
    router = AgentRouter()
    assert "qwen" in router._get_model("planner")
    assert "qwen" in router._get_model("builder")


def test_lms_get_status_connected():
    from lms.client import LMSClient
    client = LMSClient()
    with patch.object(client.client.models, "list") as mock_list:
        mock_list.return_value.data = [MagicMock(id="model-a"), MagicMock(id="model-b")]
        status = client.get_status()
        assert status["connected"] is True
        assert "model-a" in status["models"]
        assert "model-b" in status["models"]
        assert status["base_url"] == client.config.llm.base_url


def test_lms_get_status_disconnected():
    from lms.client import LMSClient
    from openai import APIConnectionError
    import httpx
    client = LMSClient()
    mock_request = httpx.Request("GET", "http://127.0.0.1:1234/v1/models")
    with patch.object(client.client.models, "list", side_effect=APIConnectionError(request=mock_request)):
        status = client.get_status()
        assert status["connected"] is False
        assert status["models"] == []


def test_lms_get_status_error():
    from lms.client import LMSClient
    client = LMSClient()
    with patch.object(client.client.models, "list", side_effect=TimeoutError("timeout")):
        status = client.get_status()
        assert status["connected"] is False
        assert "error" in status


def test_agent_context_length_default():
    from lms.client import LMSClient
    client = LMSClient()
    length = client._get_context_length("nonexistent_agent")
    assert length == 4096


def test_agent_context_length_override():
    from lms.client import LMSClient
    client = LMSClient()
    planner_length = client._get_context_length("planner")
    assert planner_length == 8192
    builder_length = client._get_context_length("builder")
    assert builder_length == 16384


def test_agent_config_has_context_length():
    from config import load_config
    config = load_config()
    for name, agent in config.agents.items():
        assert hasattr(agent, "context_length"), f"{name} missing context_length"
        assert isinstance(agent.context_length, int)


def test_lms_chat_json_fallback():
    """chat_json should return a safe fallback dict when the LLM returns invalid JSON."""
    from lms.client import LMSClient
    client = LMSClient()
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "not valid json at all"
        mock_create.return_value = mock_response
        result = client.chat_json("test-model", [{"role": "user", "content": "hi"}])
        assert result.get("pass") is False
        assert "parse_error" in result.get("issues", [])


def test_executor_parse_plan_into_tasks():
    """The plan parser should extract phases and tasks from plan text."""
    from agents.executor import Executor
    from tempfile import TemporaryDirectory
    from pathlib import Path

    plan_text = """## Phase 1: Authentication
- [T001] Create JWT middleware — Returns 401 for invalid tokens
- [T002] Add login endpoint — Accepts email+password, returns token

## Phase 2: Database
- [T003] Define User model — Has email, password_hash, created_at
"""
    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        (project_path / ".harness").mkdir()
        import json
        with open(project_path / ".harness" / "memory.json", "w") as f:
            json.dump({"project": "test", "tasks": [], "decisions": [], "session_count": 0}, f)

        executor = Executor.__new__(Executor)
        executor.memory = __import__('memory.manager', fromlist=['MemoryManager']).MemoryManager(project_path)
        executor._parse_plan_into_tasks(plan_text)

        tasks = executor.memory.load().get("tasks", [])
        assert len(tasks) == 3
        assert tasks[0]["id"] == "T001"
        assert tasks[0]["phase"] == "Authentication"
        assert tasks[0]["acceptance"] == "Returns 401 for invalid tokens"


if __name__ == "__main__":
    test_planner_prompt()
    test_builder_prompt()
    test_evaluator_prompt()
    test_qa_prompt()
    test_compactor_prompt()
    test_lms_client_init()
    test_opencode_client_init()
    test_opencode_extract_session_id()
    test_opencode_extract_session_id_none()
    test_agent_router_init()
    test_agent_router_get_model()
    test_lms_get_status_connected()
    test_lms_get_status_disconnected()
    test_lms_get_status_error()
    test_agent_context_length_default()
    test_agent_context_length_override()
    test_agent_config_has_context_length()
    test_lms_chat_json_fallback()
    test_executor_parse_plan_into_tasks()
    print("\nAll P2 tests passed!")

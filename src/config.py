import os
import json
import yaml
from pathlib import Path
from pydantic import BaseModel, Field

HARNESS_DIR = Path.home() / ".harness"
CONFIG_PATH = Path(__file__).parent / "config.yaml"


class AgentConfig(BaseModel):
    model: str
    context_length: int = 4096
    opencode_agent: str | None = None
    direct: bool = False


class LLMConfig(BaseModel):
    base_url: str = "http://127.0.0.1:1234/v1"


class DashboardConfig(BaseModel):
    port: int = 8765


class GlobalConfig(BaseModel):
    max_retries: int = 3
    session_poll_interval: int = 5


class AppConfig(BaseModel):
    agents: dict[str, AgentConfig]
    llm: LLMConfig
    dashboard: DashboardConfig
    projects_dir: str
    global_settings: GlobalConfig = Field(alias="global")

    @property
    def projects_path(self) -> Path:
        return Path(self.projects_dir).expanduser()


def load_config() -> AppConfig:
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)


def get_registry_path() -> Path:
    return HARNESS_DIR / "registry.db"


# ─── LLM Provider Configuration ────────────────────────────────

PROVIDER_CONFIG_PATH = HARNESS_DIR / "provider.json"

DEFAULT_PROVIDER_CONFIG = {
    "provider": "localllm",
    "localllm": {
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "",
    },
    "deepseek": {
        "api_key": "",
        "model": "deepseek-chat",
    },
}


def load_provider_config() -> dict:
    if not PROVIDER_CONFIG_PATH.exists():
        PROVIDER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROVIDER_CONFIG_PATH.write_text(json.dumps(DEFAULT_PROVIDER_CONFIG, indent=2))
        return dict(DEFAULT_PROVIDER_CONFIG)
    return json.loads(PROVIDER_CONFIG_PATH.read_text())


def save_provider_config(data: dict):
    PROVIDER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROVIDER_CONFIG_PATH.write_text(json.dumps(data, indent=2))


def get_active_llm_config() -> dict:
    """Return the active LLM connection details based on provider config."""
    pc = load_provider_config()
    provider = pc.get("provider", "localllm")
    if provider == "deepseek":
        return {
            "provider": "deepseek",
            "api_key": pc.get("deepseek", {}).get("api_key", ""),
            "model": pc.get("deepseek", {}).get("model", "deepseek-chat"),
            "base_url": "https://api.deepseek.com/v1",
        }
    else:
        return {
            "provider": "localllm",
            "base_url": pc.get("localllm", {}).get("base_url", "http://127.0.0.1:1234/v1"),
            "model": pc.get("localllm", {}).get("model", ""),
        }

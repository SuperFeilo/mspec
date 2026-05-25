import json
from pathlib import Path

OPENCODE_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.json"


def get_opencode_config() -> dict:
    if not OPENCODE_CONFIG_PATH.exists():
        return {}
    return json.loads(OPENCODE_CONFIG_PATH.read_text())


def save_opencode_config(data: dict):
    OPENCODE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENCODE_CONFIG_PATH.write_text(json.dumps(data, indent=2))


def get_providers() -> dict:
    config = get_opencode_config()
    return config.get("provider", {})


def get_provider_models(provider_name: str) -> list[str]:
    providers = get_providers()
    provider = providers.get(provider_name, {})
    models = provider.get("models", {})
    return list(models.keys())


def get_provider_base_url(provider_name: str) -> str | None:
    providers = get_providers()
    provider = providers.get(provider_name, {})
    options = provider.get("options", {})
    return options.get("baseURL")


def update_provider(provider_name: str, base_url: str, models: list[str]):
    config = get_opencode_config()
    if "provider" not in config:
        config["provider"] = {}

    models_dict = {}
    for m in models:
        models_dict[m] = {"name": m}

    config["provider"][provider_name] = {
        "name": provider_name.title().replace("_", " "),
        "npm": "@ai-sdk/openai-compatible",
        "models": models_dict,
        "options": {"baseURL": base_url},
    }

    save_opencode_config(config)


def sync_from_opencode_to_mspec(provider_name: str = "localllm"):
    base_url = get_provider_base_url(provider_name)
    models = get_provider_models(provider_name)
    if not base_url:
        return {"synced": False, "reason": "No base URL found"}

    from config import CONFIG_PATH, load_config
    import yaml

    config = load_config()
    config_data = yaml.safe_load(CONFIG_PATH.read_text())

    config_data["llm"]["base_url"] = base_url

    if models and "builder" in config_data.get("agents", {}):
        config_data["agents"]["builder"]["model"] = f"{provider_name}/{models[0]}"
        config_data["agents"]["compactor"]["model"] = f"{provider_name}/{models[0]}"

    CONFIG_PATH.write_text(yaml.dump(config_data, default_flow_style=False))

    return {"synced": True, "base_url": base_url, "models": models}

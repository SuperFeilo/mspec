import json
from openai import OpenAI, APIConnectionError
from config import load_config


class LMSClient:
    def __init__(self):
        config = load_config()
        self.config = config
        self.client = OpenAI(
            base_url=config.llm.base_url,
            api_key="lm-studio",
        )

    def get_status(self) -> dict:
        try:
            models = self.client.models.list()
            return {
                "connected": True,
                "models": [m.id for m in models.data],
                "base_url": self.config.llm.base_url,
            }
        except APIConnectionError:
            return {
                "connected": False,
                "models": [],
                "base_url": self.config.llm.base_url,
            }
        except Exception as e:
            return {
                "connected": False,
                "models": [],
                "base_url": self.config.llm.base_url,
                "error": str(e),
            }

    def _get_context_length(self, agent_name: str = None) -> int:
        if agent_name:
            agent_cfg = self.config.agents.get(agent_name)
            if agent_cfg:
                return agent_cfg.context_length
        return 4096

    def chat(self, model: str, messages: list[dict], temperature: float = 0.3, max_tokens: int | None = None, agent_name: str = None) -> str:
        if max_tokens is None:
            max_tokens = self._get_context_length(agent_name)
        resp = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def chat_json(self, model: str, messages: list[dict], temperature: float = 0.3, max_tokens: int | None = None, agent_name: str = None) -> dict:
        """Call the LLM and parse response as JSON. Returns a dict.

        If the LLM returns malformed JSON, returns a safe fallback dict
        instead of crashing so the executor loop can continue gracefully.
        """
        if max_tokens is None:
            max_tokens = self._get_context_length(agent_name)
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except (json.JSONDecodeError, Exception) as e:
            return {
                "pass": False,
                "feedback": f"LLM returned invalid response: {str(e)}",
                "issues": ["parse_error"],
            }

    def embed(self, text: str) -> list[float]:
        resp = self.client.embeddings.create(
            model="text-embedding-nomic-embed-text-v1.5",
            input=text,
        )
        return resp.data[0].embedding

    def get_usage(self, response) -> tuple[int, int]:
        return response.usage.prompt_tokens, response.usage.completion_tokens

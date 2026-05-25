from config import load_config
from lms.client import LMSClient
from agents.prompts import (
    get_planner_prompt,
    get_builder_prompt,
    get_evaluator_prompt,
    get_qa_prompt,
    get_compactor_prompt,
)
from agents.opencode_client import OpencodeClient


class AgentRouter:
    def __init__(self):
        self.config = load_config()
        self.lms = LMSClient()
        self.opencode = OpencodeClient()

    def _get_model(self, agent_name: str) -> str:
        agent_config = self.config.agents.get(agent_name)
        if not agent_config:
            raise ValueError(f"Unknown agent: {agent_name}")
        return agent_config.model

    def _is_direct(self, agent_name: str) -> bool:
        agent_config = self.config.agents.get(agent_name)
        return agent_config and agent_config.direct

    def plan(self, spec: str) -> str:
        model = self._get_model("planner")
        prompt = get_planner_prompt(spec)
        messages = [
            {"role": "system", "content": "You are a senior architect breaking specs into implementation plans."},
            {"role": "user", "content": prompt},
        ]
        return self.lms.chat(model, messages, agent_name="planner")

    def build(self, project_path, project_context: str, task: dict, decisions: list[dict], model_override: str | None = None) -> dict:
        prompt = get_builder_prompt(project_context, task, decisions)
        return self.opencode.run_task(
            project_path,
            "builder",
            prompt,
            model_override=model_override,
        )

    def evaluate(self, task_description: str, acceptance_criteria: str, generated_content: str) -> dict:
        model = self._get_model("evaluator")
        prompt = get_evaluator_prompt(task_description, acceptance_criteria, generated_content)
        messages = [
            {"role": "system", "content": "You are a code reviewer. Be strict on correctness and quality."},
            {"role": "user", "content": prompt},
        ]
        return self.lms.chat_json(model, messages, agent_name="evaluator")

    def qa(self, task_description: str, files: list[str], tech_stack: dict) -> dict:
        model = self._get_model("qa")
        prompt = get_qa_prompt(task_description, files, tech_stack)
        messages = [
            {"role": "system", "content": "You are a QA engineer. Suggest practical test commands."},
            {"role": "user", "content": prompt},
        ]
        return self.lms.chat_json(model, messages, agent_name="qa")

    def compact(self, context_entries: list[dict], memory_state: dict) -> dict:
        model = self._get_model("compactor")
        prompt = get_compactor_prompt(context_entries, memory_state)
        messages = [
            {"role": "system", "content": "You are a session summarizer. Be concise and structured."},
            {"role": "user", "content": prompt},
        ]
        return self.lms.chat_json(model, messages, agent_name="compactor")

    def embed(self, text: str) -> list[float]:
        return self.lms.embed(text)

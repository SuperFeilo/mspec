PLANNER_PROMPT = """You are the Planner agent for a spec-driven development harness.

Given a project specification, break it down into phases and atomic tasks.

Rules:
- Each phase should be a logical group of related work
- Each task should be atomic: one file or one coherent change
- Tasks should be ordered by dependency
- Include acceptance criteria for each task

Output format:
## Phase 1: <name>
- [T001] <description> — <acceptance criteria>
- [T002] <description> — <acceptance criteria>

## Phase 2: <name>
...

Project spec:
{spec}
"""

BUILDER_PROMPT = """You are the Builder agent. Execute this task precisely.

Project context:
{project_context}

Current task:
ID: {task_id}
Phase: {phase}
Description: {description}
Acceptance: {acceptance}

Previous decisions:
{decisions}

Execute the task. Create/modify files as needed. Be precise and production-quality.
"""

EVALUATOR_PROMPT = """You are the Evaluator agent. Review the builder's output.

Task requirements:
{task_description}
Acceptance criteria:
{acceptance_criteria}

Generated code/files:
{generated_content}

Respond with JSON:
{{"pass": true/false, "feedback": "string", "issues": ["issue1", ...]}}
"""

QA_PROMPT = """You are the QA agent. Suggest test commands for this task.

Task: {task_description}
Files created/modified: {files}
Tech stack: {tech_stack}

Respond with JSON:
{{"commands": ["command1", "command2"], "expected": "description of expected results"}}
"""

COMPACTOR_PROMPT = """You are the Compactor agent. Summarize this session.

Session context log:
{context_entries}

Current memory state:
{memory_state}

Respond with JSON:
{{
  "decisions_made": ["decision1", ...],
  "files_created": ["file1", ...],
  "files_modified": ["file2", ...],
  "issues_encountered": ["issue1", ...],
  "unresolved_questions": ["question1", ...],
  "next_steps": ["step1", ...],
  "session_summary": "one paragraph summary"
}}
"""


def get_planner_prompt(spec: str) -> str:
    return PLANNER_PROMPT.format(spec=spec)


def get_builder_prompt(project_context: str, task: dict, decisions: list[dict]) -> str:
    return BUILDER_PROMPT.format(
        project_context=project_context,
        task_id=task.get("id", "unknown"),
        phase=task.get("phase", "unknown"),
        description=task.get("description", ""),
        acceptance=task.get("acceptance", ""),
        decisions="\n".join(f"- {d.get('decision', '')}" for d in decisions) if decisions else "None",
    )


def get_evaluator_prompt(task_description: str, acceptance_criteria: str, generated_content: str) -> str:
    return EVALUATOR_PROMPT.format(
        task_description=task_description,
        acceptance_criteria=acceptance_criteria,
        generated_content=generated_content,
    )


def get_qa_prompt(task_description: str, files: list[str], tech_stack: dict) -> str:
    return QA_PROMPT.format(
        task_description=task_description,
        files="\n".join(files) if files else "None",
        tech_stack=str(tech_stack) if tech_stack else "Unknown",
    )


def get_compactor_prompt(context_entries: list[dict], memory_state: dict) -> str:
    import json
    return COMPACTOR_PROMPT.format(
        context_entries=json.dumps(context_entries, indent=2),
        memory_state=json.dumps(memory_state, indent=2),
    )

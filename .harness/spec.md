# MSpec — Spec-Driven Local Harness

## Overview

Local harness system for spec-driven full-stack development. Orchestrates LM Studio (qwen3.6) and opencode with multi-agent model routing, persistent memory, and git-backed session management.

## Architecture

- **CLI**: Python (typer + rich)
- **LLM Backend**: LM Studio OpenAI-compatible API (`localhost:1234`)
- **Code Agent**: opencode (per-task spawn/kill)
- **Registry**: SQLite
- **Dashboard**: FastAPI + React (Vite + Tailwind + shadcn/ui)
- **Memory**: JSON + semantic embeddings

## Agent Roles

| Agent | Model | Invocation | Purpose |
|-------|-------|------------|---------|
| Planner | qwen3.6-35b-a3b | Direct LM Studio | Break spec → phases → tasks |
| Builder | qwen3.6-27b | opencode per-task | Write code, create files |
| Evaluator | qwen3.6-35b-a3b | Direct LM Studio | Review output, verify correctness |
| QA | qwen3.6-27b | Direct LM Studio | Test commands, edge cases |
| Compactor | qwen3.6-27b | Direct LM Studio | Session summarization |
| Embedder | nomic-embed-text-v1.5 | Direct LM Studio | Semantic memory search |

## Project Structure

```
~/harness-projects/<name>/
├── .harness/
│   ├── spec.md              # Source of truth
│   ├── memory.json          # Decisions, architecture, task states
│   ├── plan.md              # Generated plan
│   ├── context.log          # Raw session log
│   └── sessions/            # Compacted summaries
├── src/                     # Generated code
└── .git/
```

## CLI Commands

```
harness init <name> [--spec file.md]     # Scaffold project
harness plan <name>                      # Generate plan.md
harness run <name> [phase]              # Execute phase with agent loop
harness checkpoint <name>               # Compact + git commit + tag
harness resume <name> [--from tag]      # Restore context, continue
harness status                          # Terminal status table
harness dashboard [--port 8765]         # Start dashboard
harness spec <name> [show|edit]         # Manage spec
harness agent list|set                  # Agent→model mapping
```

## Implementation Phases

| Phase | Scope | Status |
|-------|-------|--------|
| P0 | CLI scaffold, config, project init, SQLite schema | complete |
| P1 | Memory manager, memory.json schema | complete |
| P2 | Agent router, prompts, LM Studio client, opencode client | complete |
| P3 | Executor loop, task execution, verification, retry | complete |
| P4 | Compaction, git integration, session tagging | complete |
| P5 | Dashboard API routes | complete |
| P6 | React dashboard, 6 pages, polling | complete |
| P7 | Embedding + semantic resume | complete |
| P8 | Dashboard as agentic entry point | complete |

## Dependencies

```
openai>=1.0
GitPython>=3.1
PyYAML>=6.0
typer>=0.9
pydantic>=2.0
rich>=13.0
fastapi>=0.100
httpx>=0.24
uvicorn>=0.24
jinja2>=3.1
```

## Development

```bash
pip install -e .
python src/cli.py --help
```

"""Stub files — self-contained blueprints for autonomous Reasonix execution.

Each stub is a markdown file with YAML frontmatter:

    ---
    bp: "BP-01"
    name: "scaffold"
    title: "Scaffold a new project"
    init: true
    ---

    # BP-01: Scaffold

    Full task context, spec, and instructions follow.
    Everything the AI needs to execute autonomously.

Usage:
    harness reasonix-run stubs/BP-01-scaffold.md
"""

from .runner import run_stub, parse_stub

__all__ = ["run_stub", "parse_stub"]

---
# ─── Blueprint metadata (required) ──────────────────────────────
bp: "BP-NN"           # Blueprint ID, e.g. BP-01, BP-02, …
name: "my-blueprint"  # Short kebab-case identifier
title: "Description"  # One-line title for the task

# ─── Options ────────────────────────────────────────────────────
init: false           # If true, scaffold as a harness project first
intent: "code"        # What the AI should do: "code" (write files) | "plan" (write plan.md) | "scaffold" (create structure)
tech_stack:           # Optional: hint the tech stack to the AI
  lang: "Python"
  framework: "FastAPI"
---

# BP-NN: Your Task Title

## Context

Background information the AI needs to understand the task.
What's the problem? Why are we doing this?

## Task

Clear, step-by-step instructions for the autonomous agent:

1. First step
2. Second step
3. Third step
4. Verification step

## Spec (optional)

Full project specification if this is a scaffold-type blueprint.
Include requirements, architecture, API contracts, etc.

## Constraints

- Must NOT do X
- Must use Y approach
- Performance / security requirements

## Acceptance Criteria

1. Concrete, testable outcome 1
2. Concrete, testable outcome 2
3. Concrete, testable outcome 3

"""Stub validation — pressure-tests blueprint stubs for Reasonix actionability."""
import re
from pathlib import Path
from .runner import parse_stub, list_stubs, STUBS_DIR

# Content patterns that satisfy each required intent
INTENT_PATTERNS = {
    "context": [
        r"##\s*Context",
        r"##\s*Identity",
        r"##\s*Status",
        r"##\s*Overview",
        r"##\s*Background",
    ],
    "task": [
        r"##\s*Task",
        r"##\s*Your Task",
        r"##\s*Assignment",
        r"##\s*Instructions",
        r"##\s*Goals?",
    ],
    "constraints": [
        r"##\s*Constraints",
        r"##\s*Rules",
        r"##\s*Limitations",
        r"##\s*Non-goals",
    ],
    "acceptance": [
        r"##\s*Acceptance Criteria",
        r"##\s*Verification",
        r"##\s*Definition of Done",
        r"##\s*Checks?",
    ],
}

VAGUE_PATTERNS = [
    r"depending on", r"you could", r"you might",
    r"consider", r"perhaps", r"maybe", r"up to you",
    r"as needed", r"if needed", r"appropriate",
    r"suitable", r"various", r"etc\.?", r"kind of",
]

CONCRETE_PATTERNS = [
    r"`[^`]+`", r"```", r"~/harness-projects",
    r"scaffold_project", r"register_project",
    r"git init", r"git commit", r"\.harness",
    r"memory\.json", r"spec\.md", r"plan\.md",
    r"\bStep \d+\b", r"-c user\.name",
    r"DO NOT", r"ALREADY DONE",
    r"write_file", r"run_command",
]


def _check_intent(body: str, intent: str) -> bool:
    patterns = INTENT_PATTERNS[intent]
    for p in patterns:
        if re.search(p, body, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def validate_stub(name: str) -> dict:
    stubs = list_stubs()
    stub_info = next((s for s in stubs if s["name"] == name), None)
    if not stub_info:
        stub_info = next((s for s in stubs if s["bp"] == name or Path(s["path"]).stem == name), None)
    if not stub_info:
        return {"name": name, "valid": False, "score": 0,
                "checks": [{"check": "stub_exists", "passed": False,
                            "severity": "error", "message": f"Stub '{name}' not found"}],
                "summary": "Stub not found"}

    stub_path = STUBS_DIR / Path(stub_info["path"]).name
    if not stub_path.exists():
        stub_path = Path(stub_info["path"]).expanduser()
    parsed = parse_stub(stub_path)
    fm = parsed["frontmatter"]
    body = parsed["body"]

    checks = []

    # Frontmatter
    checks.append({
        "check": "frontmatter", "passed": bool(fm),
        "severity": "error" if not fm else "info",
        "message": "YAML frontmatter present" if fm else "Missing YAML frontmatter",
    })

    # Required intents (flexible section matching)
    for intent in ["context", "task", "constraints", "acceptance"]:
        found = _check_intent(body, intent)
        checks.append({
            "check": f"intent_{intent}",
            "passed": found,
            "severity": "error" if not found else "info",
            "message": f"Section satisfying '{intent}' intent found" if found else f"No section satisfies '{intent}' intent",
        })

    # Body length
    enough = len(body) >= 500
    checks.append({
        "check": "body_length", "passed": enough,
        "severity": "error" if not enough else "info",
        "message": f"Body: {len(body)} chars" if enough else f"Too short: {len(body)} chars",
    })

    # Vague language
    vague = []
    for p in VAGUE_PATTERNS:
        vague.extend(re.findall(p, body, re.IGNORECASE))
    too_vague = len(vague) > 5
    checks.append({
        "check": "no_vague_language", "passed": not too_vague,
        "severity": "warn" if vague else "info",
        "message": f"Vague phrases: {len(vague)}" if not too_vague else f"Excessive vague language: {len(vague)} instances",
    })

    # Concrete details
    concrete = []
    for p in CONCRETE_PATTERNS:
        concrete.extend(re.findall(p, body, re.IGNORECASE))
    has_concrete = len(concrete) >= 3
    checks.append({
        "check": "concrete_details", "passed": has_concrete,
        "severity": "error" if not has_concrete else "info",
        "message": f"Concrete refs: {len(concrete)}" if has_concrete else f"Too abstract: only {len(concrete)} concrete ref(s)",
    })

    # Numbered steps
    has_steps = bool(re.search(r'\bStep \d+\b|\b\d+\.\s+\*\*|^\d+\.\s', body, re.MULTILINE))
    checks.append({
        "check": "numbered_steps", "passed": has_steps,
        "severity": "warn" if not has_steps else "info",
        "message": "Numbered steps present" if has_steps else "No numbered steps",
    })

    # Acceptance checkboxes
    has_checks = "[" in body and "]" in body and ("✅" in body or "- [" in body)
    checks.append({
        "check": "acceptance_checkboxes", "passed": has_checks,
        "severity": "warn" if not has_checks else "info",
        "message": "Acceptance checkboxes present" if has_checks else "No completion checkboxes",
    })

    # Identity / disambiguation
    has_id = bool(re.search(r"(?:is|are)\s+NOT\s+the|You are|This is a|Identity|DISAMBIGUATION", body, re.IGNORECASE))
    checks.append({
        "check": "identity_disambiguation", "passed": has_id,
        "severity": "warn" if not has_id else "info",
        "message": "Identity statement present" if has_id else "No identity/disambiguation",
    })

    # DO NOT / ALREADY DONE
    has_neg = bool(re.search(r"DO NOT|ALREADY DONE|Don't redo|Skip this|handled by|The following are ALREADY", body, re.IGNORECASE))
    checks.append({
        "check": "negative_instructions", "passed": has_neg,
        "severity": "warn" if not has_neg else "info",
        "message": "Negative instructions present" if has_neg else "No DO NOT/ALREADY DONE",
    })

    # ─── Stall-Simulation Checks ─────────────────────────────────

    # 5a. Unresolved {placeholder} variables
    import re as _re
    placeholders = _re.findall(r"\{\w+\}", body)
    checks.append({
        "check": "no_unresolved_placeholders", "passed": len(placeholders) == 0,
        "severity": "error" if placeholders else "info",
        "message": f"No unresolved placeholders" if not placeholders else f"Unresolved: {', '.join(placeholders)}",
    })

    # 5b. Read-before-write patterns (AI asked to read files that don't exist)
    read_before = _re.findall(r"(?:read|open|check|examine)\s+(?:the\s+)?(?:file\s+)?[`'\"][^`'\"]+[`'\"]", body, _re.IGNORECASE)
    checks.append({
        "check": "no_read_before_write", "passed": len(read_before) == 0,
        "severity": "warn" if read_before else "info",
        "message": f"No read-before-write patterns" if not read_before else f"AI asked to read {len(read_before)} file(s) that may not exist",
    })

    # 5c. Question patterns — sentences ending with ? are stall triggers
    questions = _re.findall(r"[A-Z][^.!?]*\?", body)
    meaningful_questions = [q for q in questions if len(q.strip()) > 15]
    checks.append({
        "check": "no_questions_in_stub", "passed": len(meaningful_questions) == 0,
        "severity": "warn" if meaningful_questions else "info",
        "message": f"No questions in stub" if not meaningful_questions else f"{len(meaningful_questions)} question(s) — AI will answer instead of execute",
    })

    # 5d. Concrete file paths
    has_paths = bool(_re.search(r"`[~\/\\][^`]+`|`[a-zA-Z]:\\[^`]+`", body))
    checks.append({
        "check": "concrete_file_paths", "passed": has_paths,
        "severity": "error" if not has_paths else "info",
        "message": "Concrete file paths present" if has_paths else "No concrete file paths — AI won't know where to write",
    })

    # 5e. Open-ended exploration words
    open_ended = ["explore", "investigate", "figure out", "look around", "examine the codebase"]
    found_open = [w for w in open_ended if _re.search(rf"\b{_re.escape(w)}\b", body, _re.IGNORECASE)]
    checks.append({
        "check": "no_open_ended_exploration", "passed": len(found_open) == 0,
        "severity": "error" if found_open else "info",
        "message": f"No exploration instructions" if not found_open else f"Open-ended: {', '.join(found_open)} — AI will explore instead of execute",
    })

    # 5f. Project name / identity specified
    has_name = bool(_re.search(r"Project name|project_name|project is called|project titled", body, _re.IGNORECASE))
    checks.append({
        "check": "project_identity", "passed": has_name,
        "severity": "error" if not has_name else "info",
        "message": "Project identity specified" if has_name else "No project name or identity — AI will ask what to build",
    })

    # Score
    errors = [c for c in checks if c["severity"] == "error" and not c["passed"]]
    warnings = [c for c in checks if c["severity"] == "warn" and not c["passed"]]
    score = max(0, min(100, 100 - len(errors) * 25 - len(warnings) * 10))
    valid = len(errors) == 0

    parts = [f"{'✅' if valid else '❌'} Score: {score}"]
    if errors: parts.append(f"{len(errors)} error(s)")
    if warnings: parts.append(f"{len(warnings)} warning(s)")

    return {"name": stub_info["name"], "title": stub_info["title"],
            "bp": stub_info["bp"], "valid": valid, "score": score,
            "checks": checks, "summary": ", ".join(parts)}


def validate_all_stubs() -> list[dict]:
    return [validate_stub(s["name"]) for s in list_stubs()]


def pressure_test_stub(name: str) -> dict:
    v = validate_stub(name)
    body = ""
    try:
        stub_path = STUBS_DIR / f"{v.get('bp','BP').lower()}-{name}.md"
        if not stub_path.exists():
            # Find by name
            for f in STUBS_DIR.glob("*.md"):
                p = parse_stub(f)
                if p["frontmatter"].get("name") == name:
                    stub_path = f
                    body = p["body"]
                    break
        else:
            body = parse_stub(stub_path)["body"]
    except:
        pass

    steps = len(re.findall(r'^\d+\.\s|^###?\s+Step', body, re.MULTILINE))
    has_tools = "write_file" in body or "run_command" in body or "subprocess" in body
    can_exec = steps <= 5 and has_tools and v["score"] >= 60

    recs = [f"- {c['check']}: {c['message']}" for c in v["checks"] if not c["passed"]]
    if not can_exec:
        if steps > 5: recs.append("- Consolidate to ≤5 steps for single-turn")
        if not has_tools: recs.append("- Add concrete paths/commands/tool references")

    return {**v, "execution_check": {
        "can_execute": can_exec, "step_count": steps,
        "has_tool_calls": has_tools,
        "reason": "Ready for 1-turn" if can_exec else "May need multi-turn or more detail",
    }, "recommendation": "\n".join(recs) if recs else "Stub is ready"}

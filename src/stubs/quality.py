"""Stub quality checker — context injection + pressure testing for Reasonix stubs.

Three-stage pipeline:
  1. Context injection — resolve placeholders, inject project context
  2. Pressure test — simulate Reasonix reading the stub, flag missing info
  3. Validation — structural checks from validate.py

Usage:
    checker = StubQualityChecker()
    result = checker.run_pipeline(stub_path, project_name="my-app", tech_stack={...})
    # result contains stages, pass/fail, recommendations
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .runner import parse_stub, list_stubs, STUBS_DIR


# ─── Stage 1: Context Injection ────────────────────────────────

CONTEXT_SNIPPETS = {
    "project_name": (
        "Project name: {value}\n"
    ),
    "project_path": (
        "Project directory: {value}\n"
    ),
    "tech_stack": (
        "Tech stack:\n{value}\n"
    ),
    "harness_path": (
        "MSpec harness location: {value}\n"
    ),
    "registry_db": (
        "Registry database: {value}\n"
    ),
    "git_state": (
        "Git state: branch={branch}, latest={commit}\n"
    ),
}


def _detect_placeholders(text: str) -> list[str]:
    """Find all {placeholder} variables in text."""
    return re.findall(r"\{(\w+)\}", text)


def _detect_read_before_write(text: str) -> list[str]:
    """Find patterns where the AI is asked to read a file that may not exist."""
    patterns = [
        r"read\s+(?:the\s+)?(?:file\s+)?[`'\"][^`'\"]+[`'\"]",
        r"open\s+(?:the\s+)?(?:file\s+)?[`'\"][^`'\"]+[`'\"]",
        r"check\s+(?:the\s+)?(?:contents?\s+of\s+)?[`'\"][^`'\"]+[`'\"]",
    ]
    matches = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            matches.append(m.group())
    return matches


def _detect_questions_to_ai(text: str) -> list[str]:
    """Find questions the stub asks that the AI might answer instead of execute."""
    # Look for sentences ending with ? — these are questions the AI should not answer
    question_sentences = re.findall(r"[^.!?]*\?", text)
    # Filter out rhetorical questions in section headers
    return [q.strip() for q in question_sentences if len(q.strip()) > 10]


def _detect_missing_context(text: str) -> list[str]:
    """Detect essential context that Reasonix needs but the stub doesn't provide."""
    missing = []
    
    # Check for project name
    if "project name" not in text.lower() and "{project_name}" not in text:
        missing.append("Project name not specified")
    
    # Check for directory
    if "directory" not in text.lower() and "path" not in text.lower() and "{project_path}" not in text:
        missing.append("Target directory not specified")
    
    # Check for tech stack
    if "tech stack" not in text.lower() and "python" not in text.lower() and "framework" not in text.lower():
        missing.append("Tech stack not specified")
    
    # Check for file paths
    if "`" not in text and "~/" not in text and "/" not in text:
        missing.append("No concrete file paths — AI will ask where to create files")
    
    # Check for open-ended verbs
    open_ended = ["explore", "investigate", "understand", "figure out", "look at", "examine"]
    for v in open_ended:
        if re.search(rf"\b{v}\b", text, re.IGNORECASE):
            missing.append(f"Open-ended instruction '{v}' — AI will explore instead of execute")
            break
    
    return missing


class StubContextInjector:
    """Stage 1: Resolve placeholders and inject project context into stubs."""

    def __init__(self):
        self.mspec_root = Path(__file__).parent.parent.parent
        self.harness_dir = Path.home() / ".harness"

    def inject(self, 
               body: str, 
               project_name: Optional[str] = None,
               project_path: Optional[str] = None,
               tech_stack: Optional[dict] = None) -> tuple[str, list[str]]:
        """Inject context into stub body.
        
        Returns (modified_body, injection_log).
        """
        log = []
        
        # Resolve placeholders
        placeholders = _detect_placeholders(body)
        substitutions = {
            "project_name": project_name or "my-project",
            "project_path": project_path or f"~/harness-projects/{project_name or 'my-project'}",
        }
        
        for ph in placeholders:
            if ph in substitutions and substitutions[ph]:
                old_count = body.count("{" + ph + "}")
                body = body.replace("{" + ph + "}", str(substitutions[ph]))
                if old_count > 0:
                    log.append(f"Resolved {{{ph}}} → {substitutions[ph]}")
        
        # Inject project name context if not present
        if project_name and "project name" not in body.lower():
            body += f"\n\n## Project Identity\nProject name: {project_name}\n"
            log.append(f"Injected project name: {project_name}")
        
        # Inject project path context
        if project_path:
            body = body.replace("~/harness-projects/{project_name}", project_path)
            if "project directory" not in body.lower():
                body += f"Project directory: {project_path}\n"
                log.append(f"Injected project path: {project_path}")
        
        # Inject tech stack
        if tech_stack:
            stack_str = "\n".join(f"  - {k}: {v}" for k, v in tech_stack.items())
            if "tech stack" not in body.lower():
                body += f"\nTech stack:\n{stack_str}\n"
                log.append(f"Injected tech stack: {len(tech_stack)} items")
        
        # Add disambiguation if not present
        if "NOT the" not in body and "is a" not in body:
            body = (
                "NOTE: MSpec is a Python-based spec-driven multi-agent coding harness "
                "(NOT the .NET testing framework).\n\n" + body
            )
            log.append("Injected MSpec disambiguation")
        
        return body, log


class StubPressureTest:
    """Stage 2: Pressure test — simulate Reasonix reading and flag stall risks."""

    def test(self, body: str) -> dict:
        """Run pressure tests and return findings."""
        findings = {
            "unresolved_placeholders": [],
            "missing_context": [],
            "read_before_write": [],
            "question_triggers": [],
            "stall_risk": "low",  # low | medium | high
            "recommendations": [],
        }
        
        # 1. Check for unresolved placeholders
        placeholders = _detect_placeholders(body)
        if placeholders:
            findings["unresolved_placeholders"] = placeholders
            findings["recommendations"].append(
                f"Resolve placeholders: {', '.join(placeholders)}"
            )
        
        # 2. Check for missing essential context
        missing = _detect_missing_context(body)
        findings["missing_context"] = missing
        findings["recommendations"].extend(missing)
        
        # 3. Check for read-before-write patterns
        read_before = _detect_read_before_write(body)
        if read_before:
            findings["read_before_write"] = read_before
            findings["recommendations"].append(
                "Avoid asking AI to read files that don't exist yet — include file content directly"
            )
        
        # 4. Check for question patterns that trigger stalls
        questions = _detect_questions_to_ai(body)
        if questions:
            findings["question_triggers"] = questions
            findings["recommendations"].append(
                "Remove questions from the stub — AI will answer them instead of executing"
            )
        
        # 5. Calculate stall risk
        risk_score = 0
        risk_score += len(findings["unresolved_placeholders"]) * 10
        risk_score += len(findings["missing_context"]) * 15
        risk_score += len(findings["read_before_write"]) * 20
        risk_score += len(findings["question_triggers"]) * 5
        
        if risk_score >= 30:
            findings["stall_risk"] = "high"
        elif risk_score >= 15:
            findings["stall_risk"] = "medium"
        
        return findings


# ─── Oneshot Prediction ───────────────────────────────────────

RUN_HISTORY_PATH = STUBS_DIR / "run_history.json"


def predict_oneshot_rate(validation: dict, pressure_findings: dict) -> dict:
    """Calculate predicted one-shot success rate from validation + pressure test.

    Model: start from validation score, then apply adjustments for
    known behavioral risks that the score doesn't capture.

    Returns dict with predicted_rate, breakdown, and rationale.
    """
    score = validation.get("score", 0)
    checks = validation.get("checks", [])

    def _check_passed(name: str) -> bool:
        c = next((ch for ch in checks if ch["check"] == name), None)
        return c["passed"] if c else False

    adjustment = 0
    adjustments_log = []

    # ── Positive signals ────────────────────────────────────────
    if _check_passed("concrete_file_paths"):
        adjustment += 15
        adjustments_log.append(("Concrete file paths present", +15))

    if _check_passed("project_identity"):
        adjustment += 15
        adjustments_log.append(("Project identity specified", +15))

    stall_risk = pressure_findings.get("stall_risk", "high")
    if stall_risk == "low":
        adjustment += 10
        adjustments_log.append(("Low stall risk", +10))

    # ── Negative signals ────────────────────────────────────────
    if stall_risk == "high":
        adjustment -= 25
        adjustments_log.append(("High stall risk", -25))
    elif stall_risk == "medium":
        adjustment -= 10
        adjustments_log.append(("Medium stall risk", -10))

    if not _check_passed("no_open_ended_exploration"):
        adjustment -= 15
        adjustments_log.append(("Open-ended exploration verbs", -15))

    if not _check_passed("identity_disambiguation"):
        adjustment -= 10
        adjustments_log.append(("No identity disambiguation", -10))

    if not _check_passed("no_read_before_write"):
        adjustment -= 10
        adjustments_log.append(("Read-before-write patterns", -10))

    # Pressure-test-specific findings (not in validate checks)
    missing_ctx = pressure_findings.get("missing_context", [])
    if missing_ctx:
        n = len(missing_ctx)
        adjustment -= n * 10
        adjustments_log.append((f"Missing context items ({n})", -10 * n))

    placeholders = pressure_findings.get("unresolved_placeholders", [])
    if placeholders:
        n = len(placeholders)
        adjustment -= n * 15
        adjustments_log.append((f"Unresolved placeholders ({n})", -15 * n))

    questions = pressure_findings.get("question_triggers", [])
    if questions:
        n = len(questions)
        adjustment -= n * 5
        adjustments_log.append((f"Questions in stub ({n})", -5 * n))

    read_before = pressure_findings.get("read_before_write", [])
    if read_before:
        n = len(read_before)
        adjustment -= n * 10
        adjustments_log.append((f"Read-before-write patterns ({n})", -10 * n))

    predicted = max(0, min(100, score + adjustment))

    return {
        "predicted_oneshot_rate": predicted,
        "base_score": score,
        "adjustment": adjustment,
        "adjustments": adjustments_log,
    }


class StubRunRecorder:
    """Persists stub run outcomes to run_history.json for the feedback loop.

    Each record stores: predicted rate, validation score, actual outcome,
    reason, and output preview — enabling calibration analysis over time.
    """

    @staticmethod
    def _load_history() -> list[dict]:
        if RUN_HISTORY_PATH.exists():
            try:
                data = json.loads(RUN_HISTORY_PATH.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else data.get("runs", [])
            except (json.JSONDecodeError, KeyError, TypeError):
                return []
        return []

    @staticmethod
    def _save_history(runs: list[dict]):
        RUN_HISTORY_PATH.write_text(
            json.dumps({"runs": runs, "total": len(runs)}, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def record_run(stub_name: str, stub_bp: str, prediction: dict,
                   actual_outcome: str, reason: str,
                   exit_code: int = 0, output_preview: str = "",
                   intent: str = "code"):
        """Record one stub execution outcome.

        Args:
            stub_name: Name identifier from stub frontmatter
            stub_bp: Blueprint ID (e.g. BP-01)
            prediction: Output from predict_oneshot_rate()
            actual_outcome: "success" | "stall" | "failure"
            reason: Human-readable explanation of what went wrong
            exit_code: Process exit code
            output_preview: First ~200 chars of the AI's response
            intent: "code" | "plan" | "scaffold"
        """
        runs = StubRunRecorder._load_history()
        runs.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stub_name": stub_name,
            "stub_bp": stub_bp,
            "predicted_oneshot_rate": prediction.get("predicted_oneshot_rate", 0),
            "validation_score": prediction.get("base_score", 0),
            "actual_outcome": actual_outcome,
            "reason": reason,
            "intent": intent,
            "exit_code": exit_code,
            "output_preview": output_preview[:200],
        })
        StubRunRecorder._save_history(runs)

    @staticmethod
    def get_history(stub_name: Optional[str] = None) -> list[dict]:
        """Load run history, optionally filtered by stub name."""
        runs = StubRunRecorder._load_history()
        if stub_name:
            return [r for r in runs if r["stub_name"] == stub_name]
        return runs

    @staticmethod
    def get_summary(stub_name: Optional[str] = None) -> dict:
        """Aggregate stats for feedback loop: actual rate vs predicted rate."""
        runs = StubRunRecorder.get_history(stub_name)
        if not runs:
            return {"total_runs": 0}

        total = len(runs)
        successes = sum(1 for r in runs if r["actual_outcome"] == "success")
        stalls = sum(1 for r in runs if r["actual_outcome"] == "stall")
        failures = sum(1 for r in runs if r["actual_outcome"] == "failure")

        avg_predicted = sum(r["predicted_oneshot_rate"] for r in runs) / total
        actual_rate = (successes / total * 100)

        return {
            "total_runs": total,
            "successes": successes,
            "stalls": stalls,
            "failures": failures,
            "actual_success_rate": round(actual_rate, 1),
            "avg_predicted_rate": round(avg_predicted, 1),
            "calibration_delta": round(avg_predicted - actual_rate, 1),
        }


# ─── Full Pipeline ─────────────────────────────────────────────

class StubQualityPipeline:
    """Run the full 3-stage quality pipeline on a stub."""

    def __init__(self):
        self.injector = StubContextInjector()
        self.tester = StubPressureTest()

    def run(self,
            stub_name: str,
            project_name: Optional[str] = None,
            project_path: Optional[str] = None,
            tech_stack: Optional[dict] = None) -> dict:
        """Run all 3 stages.
        
        Returns dict with stages, final verdict, and recommendations.
        """
        # Find the stub
        stubs = list_stubs()
        stub_info = next((s for s in stubs if s["name"] == stub_name), None)
        if not stub_info:
            return {"error": f"Stub '{stub_name}' not found", "passed": False}
        
        stub_file = STUBS_DIR / Path(stub_info["path"]).name
        if not stub_file.exists():
            return {"error": f"Stub file not found", "passed": False}
        
        parsed = parse_stub(stub_file)
        body = parsed["body"]
        fm = parsed["frontmatter"]
        
        stages = []
        
        # Stage 1: Context injection
        injected_body, injection_log = self.injector.inject(
            body, 
            project_name=project_name or fm.get("name"),
            project_path=project_path,
            tech_stack=tech_stack,
        )
        stages.append({
            "name": "Context Injection",
            "status": "done",
            "log": injection_log,
            "detail": f"Resolved {len(injection_log)} items" if injection_log else "No changes needed",
        })
        
        # Stage 2: Pressure test
        pressure = self.tester.test(injected_body)
        stages.append({
            "name": "Pressure Test",
            "status": "done",
            "detail": f"Stall risk: {pressure['stall_risk']}",
            "findings": pressure,
        })
        
        # Stage 3: Validation (from validate.py)
        from .validate import validate_stub
        validation = validate_stub(stub_name)
        stages.append({
            "name": "Validation",
            "status": "done",
            "detail": f"Score: {validation.get('score', 0)}/100",
            "checks": validation.get("checks", []),
        })
        
        # Stage 4: Oneshot prediction
        oneshot = predict_oneshot_rate(validation, pressure)
        stages.append({
            "name": "Oneshot Prediction",
            "status": "done",
            "detail": f"Predicted rate: {oneshot['predicted_oneshot_rate']}%",
            "adjustments": oneshot["adjustments"],
        })
        
        # Final verdict
        has_errors = pressure["stall_risk"] == "high"
        has_validation_errors = validation.get("score", 100) < 50
        passed = not has_errors and not has_validation_errors
        
        return {
            "stub_name": stub_name,
            "stub_title": stub_info.get("title", ""),
            "stub_bp": stub_info.get("bp", ""),
            "frontmatter": fm,
            "stages": stages,
            "passed": passed,
            "stall_risk": pressure["stall_risk"],
            "validation_score": validation.get("score", 0),
            "predicted_oneshot_rate": oneshot["predicted_oneshot_rate"],
            "recommendations": pressure["recommendations"],
            "injected_body": injected_body,
        }


def quality_check_all(project_name: Optional[str] = None,
                      project_path: Optional[str] = None,
                      tech_stack: Optional[dict] = None) -> list[dict]:
    """Run quality pipeline on all stubs."""
    pipeline = StubQualityPipeline()
    results = []
    stubs = list_stubs()
    for s in stubs:
        result = pipeline.run(s["name"], project_name, project_path, tech_stack)
        results.append(result)
    return results

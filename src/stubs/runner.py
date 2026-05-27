"""Stub runner — reads a blueprint stub file and passes it to Reasonix for autonomous execution.

Pattern modeled after:
  - Reasonix  `reasonix run <task>`   — headless one-shot, CI-friendly
  - Claude Code `claude -p "prompt"`  — pipe-in autonomous execution
  - opencode  `opencode run --agent Y "prompt"` — one-shot task execution
"""

import re
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


STUBS_DIR = Path(__file__).parent


# ─── Task text sanitization ────────────────────────────────────

# Characters that break Windows cmd.exe / .CMD argument parsing
# when the task is passed as a command-line argument via `.CMD` shim.
#   `>`  — redirect operator — everything after `>` is lost
#   `"`  — string delimiter — first `"` ends the argument
_SANITIZE_TABLE = str.maketrans({
    '"': "'",
    '>': '',  # strip `>` from version specs — package names alone suffice
})


def _sanitize_task_text(text: str) -> str:
    """Remove characters that break cmd.exe argument parsing.

    `.CMD` shims on Windows route through cmd.exe, which re-parses the
    command line. Double quotes inside the task argument cause it to be
    truncated at the first unescaped `"`. This function replaces them
    with safe equivalents.
    """
    return text.translate(_SANITIZE_TABLE)


# ─── File extraction from AI output ────────────────────────────

def _extract_files_from_output(output: str, project_path: Path) -> list[dict]:
    """Parse fenced code blocks with inline paths from AI output and write files.

    Expected format:
        ```python .harness/bp-01-scaffold/file.py
        content...
        ```

    Each code block starts with three backticks, a language tag, a space,
    and the relative file path. Content follows until the closing ```.

    Returns list of {path, status, error} for each file.
    """
    # Match three formats:
    #   A: ```lang .path/to/file\ncontent...```
    #   B: ```lang\n.path/to/file\ncontent...```
    #   C: ```lang:.path/to/file\ncontent...```  (colon separator)
    pattern = re.compile(
        r"```(\w+)\s*"
        r"(?::\s*(\.?/?[\w./-]+)\s*\n|"      # Format C: colon separator
        r"\s+(\.?/?[\w./-]+)\s*\n|"           # Format A: space separator
        r"\n(\.?/?[\w./-]+)\n)"               # Format B: path on next line
        r"(.*?)```",
        re.DOTALL,
    )
    seen = set()
    results = []

    for match in pattern.finditer(output):
        # path is in group 2 (colon), group 3 (space), or group 4 (next line)
        rel_path = (match.group(2) or match.group(3) or match.group(4) or "").lstrip("/")
        content = match.group(5).strip()
        if not content or rel_path in seen:
            continue
        seen.add(rel_path)
        _write_file(project_path, rel_path, content, results)

    return results


def _write_file(project_path: Path, rel_path: str, content: str,
                results: list[dict]):
    """Helper: write a single file to disk."""
    full_path = project_path / rel_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content + "\n", encoding="utf-8")
        results.append({"path": rel_path, "status": "written", "size": len(content)})
        print(f"  [stub-runner] Wrote {rel_path} ({len(content)} bytes)")
    except Exception as e:
        results.append({"path": rel_path, "status": "error", "error": str(e)})
        print(f"  [stub-runner] FAILED to write {rel_path}: {e}")


# ─── Post-generation code quality verification ─────────────────

_DEPRECATED_API_PATTERNS = [
    (r"datetime\.utcnow", "Use datetime.now(timezone.utc) instead of deprecated utcnow"),
    (r"datetime\.utcfromtimestamp", "Use datetime.fromtimestamp(ts, tz=timezone.utc)"),
    (r"@app\.on_event", "Use lifespan context manager instead of deprecated on_event (see FastAPI lifespan docs)"),
    (r"allow_credentials\s*=\s*True.*allow_origins\s*=\s*\[\s*\"\*\"\s*\]", "Cannot use allow_credentials=True with allow_origins=['*']"),
    # Flag Base.metadata.create_all only when bind= is absent
    (r"Base\.metadata\.create_all\s*\(\s*(?!bind=)", "Call create_all with bind=engine — use Base.metadata.create_all(bind=engine)"),
]

_BARE_EXCEPT = re.compile(r"^\s*except\s*:")


def _verify_code_quality(written_files: list[dict], project_path: Path) -> list[dict]:
    """Run quality checks on written files: syntax, deprecated APIs, bare excepts.

    Returns list of {path, check, passed, message} for each check.
    """
    checks = []
    for entry in written_files:
        if entry.get("status") != "written":
            continue
        fpath = project_path / entry["path"]
        if not fpath.exists() or not fpath.suffix == ".py":
            continue

        content = fpath.read_text(encoding="utf-8")
        fchecks = []

        # 1. Syntax check
        try:
            compile(content, str(fpath), "exec")
            fchecks.append({"check": "syntax", "passed": True, "message": "Valid Python syntax"})
        except SyntaxError as e:
            fchecks.append({"check": "syntax", "passed": False, "message": f"SyntaxError: {e}"})

        # 2. Deprecated APIs
        for pattern, msg in _DEPRECATED_API_PATTERNS:
            if re.search(pattern, content):
                fchecks.append({"check": "deprecated_api", "passed": False, "message": msg})

        # 3. Bare except:
        if _BARE_EXCEPT.search(content):
            fchecks.append({"check": "bare_except", "passed": False,
                            "message": "Bare except: caught — use specific exception types"})

        # 4. Type hints on function defs
        func_defs = re.findall(r"^\s*def\s+\w+\s*\([^)]*\)\s*:", content, re.MULTILINE)
        typed_funcs = re.findall(r"^\s*def\s+\w+\s*\([^)]*\)\s*->\s*\S+\s*:", content, re.MULTILINE)
        if func_defs and len(typed_funcs) < len(func_defs):
            missing = len(func_defs) - len(typed_funcs)
            fchecks.append({"check": "type_hints", "passed": False,
                            f"message": f"{missing}/{len(func_defs)} function(s) missing return type hint"})
        else:
            fchecks.append({"check": "type_hints", "passed": True, "message": "All functions have type hints"})

        # 5. Docstrings on public functions/classes
        public_defs = re.findall(r"^\s*(?:def|class)\s+(?!_)", content, re.MULTILINE)
        docstringed = re.findall(r'^\s*(?:def|class)\s+(?!_)[^:]*:\s*\n\s+"""', content, re.MULTILINE)
        if public_defs and len(docstringed) < len(public_defs):
            missing = len(public_defs) - len(docstringed)
            fchecks.append({"check": "docstrings", "passed": False,
                            f"message": f"{missing}/{len(public_defs)} public def(s)/class(es) missing docstring"})
        else:
            fchecks.append({"check": "docstrings", "passed": True, "message": "All public symbols documented"})

        for c in fchecks:
            c["path"] = entry["path"]
            status = "✅" if c["passed"] else "❌"
            print(f"  [verify] {status} {entry['path']}: {c['check']} — {c['message']}")

        checks.extend(fchecks)

    return checks


# ─── Stall detection heuristics ─────────────────────────────────

_STALL_SIGNALS = [
    r"I need more context",
    r"Please clarify",
    r"what kind of project",
    r"which (language|framework)",
    r"could you provide",
    r"I don't have enough",
    r"Do you want",
    r"what would you like",
    r"I'm ready.*what do you need",
    r"explore the codebase",
    r"explore the workspace",
    r"explore the repository",
    r"let me explore",
    r"let me look",
    r"let me start by",
    r"I'll start by (examining|exploring|reading|looking)",
    r"search for.*pattern",
    r"Need.*context",
    r"not enough context",
    r"ask (a|any) question",
    r"confirm additional context",
    r"what's the project",
    r"may I ask",
    r"how (does|can|should|would) (this|the|I)",
    r"I understand you",
    r"I see you",
    r"It looks like you",
    r"what are you building",
    r"how can I help",
    r"what do you need help with",
]


def _detect_outcome(output: str) -> tuple[str, str]:
    """Classify an AI response as success, stall, or failure.

    Returns (outcome, reason) where outcome is one of:
      "success" — produced files, no stalling
      "stall"   — asked for clarification or explored instead of executing
      "failure" — error or empty response
    """
    if not output or not output.strip():
        return "failure", "Empty response from AI"

    # Check stall signals
    for signal in _STALL_SIGNALS:
        match = re.search(signal, output, re.IGNORECASE)
        if match:
            # Extract the sentence containing the stall
            start = max(0, match.start() - 80)
            snippet = output[start:match.end() + 80]
            return "stall", f"AI stalled: '{snippet.strip()[:150]}...'"

    # Check for error indicators
    if "error:" in output.lower() and "traceback" in output.lower():
        return "failure", "AI encountered an error during execution"

    # Check for code blocks with filenames (sign of actual output)
    if "```" in output and "`./" in output:
        return "success", "AI produced file output with paths"
    if re.search(r"```\w+\s+\./\S+", output):
        return "success", "AI produced file output"

    # Non-code response — AI is talking, not executing
    if len(output.strip()) < 100:
        return "stall", f"Short response ({len(output.strip())} chars) — likely stall"

    # Multi-sentence prose without code blocks = stall
    if "```" not in output:
        return "stall", f"AI responded with prose but no code blocks — likely exploring or acknowledging"

    return "stall", f"AI produced {len(output.strip())} chars without file output"


def parse_stub(path: Path) -> dict:
    """Parse a stub .md file with YAML frontmatter.

    Format:
        ---
        bp: "BP-01"
        name: "scaffold"
        title: "Scaffold a new project"
        init: true
        ---

        # BP-01: Scaffold

        Full body content follows...

    Returns
        {
            "frontmatter": { ... },   # parsed YAML-like dict
            "body": "...",             # everything after the closing ---
            "full_text": "..."         # original file content
        }
    """
    text = path.read_text(encoding="utf-8")

    # Match YAML frontmatter between --- delimiters
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not fm_match:
        # No frontmatter — treat entire file as body
        return {
            "frontmatter": {},
            "body": text.strip(),
            "full_text": text,
        }

    raw_fm = fm_match.group(1)
    body = fm_match.group(2).strip()

    # Simple YAML-like parser (no pyyaml dependency needed at runtime)
    frontmatter = _parse_simple_yaml(raw_fm)

    return {
        "frontmatter": frontmatter,
        "body": body,
        "full_text": text,
    }


def _parse_simple_yaml(raw: str) -> dict:
    """Minimal YAML frontmatter parser using indent-based nesting.

    Handles:
        key: value
        key: "quoted value"
        key: true / false / 123
        list_key:
          - item1
          - item2
        nested_key:
          subkey: value
          subkey2: value2
    """
    lines = raw.split("\n")

    # First pass: build the indent tree with line types
    # (indent, type, key, raw_val)  where type is 'kv' or 'list'
    nodes = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        cline = line[indent:]

        if cline.startswith("- "):
            nodes.append((indent, "list", _parse_scalar(cline[2:].strip())))
        elif ":" in cline:
            key, _, raw_val = cline.partition(":")
            key = key.strip()
            raw_val = raw_val.strip()
            nodes.append((indent, "kv", key, raw_val))
        # else: free text, skip

    # Second pass: build nested structure
    # Stack: [(indent, container)]
    # container is either a dict, list, or the value itself
    result = {}
    stack = [(0, result)]

    for i, node in enumerate(nodes):
        indent = node[0]
        node_type = node[1]

        # Pop stack back to parent level
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        parent_indent, parent = stack[-1]

        if node_type == "kv":
            _, _, key, raw_val = node

            if isinstance(parent, list):
                # Create new dict inside this list
                sub = {}
                parent.append(sub)
                container = sub
            elif isinstance(parent, dict):
                container = parent
            else:
                container = result

            if not raw_val:
                # Check next node at deeper indent to decide dict vs list
                next_indent = nodes[i + 1][0] if i + 1 < len(nodes) else 0
                if next_indent > indent and nodes[i + 1][1] == "list":
                    # Next line is a list item — this should be a list
                    container[key] = []
                    stack.append((indent, container[key]))
                else:
                    # Assume dict
                    sub = {}
                    container[key] = sub
                    stack.append((indent, sub))
            else:
                container[key] = _parse_scalar(raw_val)
                stack.append((indent, container))

        elif node_type == "list":
            _, _, val = node

            if isinstance(parent, list):
                parent.append(val)
            elif isinstance(parent, dict):
                # Find the key in parent whose value is a list
                # Or the last key that doesn't have a proper value yet
                for k, v in list(parent.items()):
                    if isinstance(v, list):
                        v.append(val)
                        break
                else:
                    # Fallback: last key that is None
                    if parent:
                        last_k = list(parent.keys())[-1]
                        parent[last_k] = [val]

    return result


def _parse_scalar(val: str):
    """Parse a YAML scalar value."""
    # Quoted string
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        return val[1:-1]

    # Boolean
    if val.lower() in ("true", "yes", "on"):
        return True
    if val.lower() in ("false", "no", "off"):
        return False
    if val.lower() in ("null", "~", "none"):
        return None

    # Integer
    try:
        return int(val)
    except ValueError:
        pass

    # Float
    try:
        return float(val)
    except ValueError:
        pass

    return val


def find_reasonix() -> Optional[dict]:
    """Find reasonix CLI entry point, returning Node.js + CLI paths.

    Returns None if not found.
    On success returns:
        {"node": str, "cli": str, "label": str}
    """
    # Check npm-installed reasonix package
    npm_dir = Path.home() / "AppData" / "Roaming" / "npm"
    cli_candidates = [
        npm_dir / "node_modules" / "reasonix" / "dist" / "cli" / "index.js",
        npm_dir / "node_modules" / "@reasonix" / "cli" / "dist" / "index.js",
    ]
    for cli in cli_candidates:
        if cli.exists():
            node = shutil.which("node")
            if node:
                return {"node": node, "cli": str(cli), "label": f"node {cli.name}"}

    # Fallback: check npx
    npx = shutil.which("npx")
    if npx:
        return {"node": npx, "cli": "reasonix", "label": "npx reasonix"}

    return None


def run_stub(
    stub_path: Path,
    project_dir: Optional[Path] = None,
    dry_run: bool = False,
    timeout_sec: int = 300,
    project_name: Optional[str] = None,
) -> dict:
    """Execute a stub file through Reasons autonomous run.

    Flow:
        1. Parse the stub file (frontmatter + body)
        2. If init:true, scaffold a harness project first
        3. Run quality pipeline (context injection + pressure test + validation + oneshot prediction)
        4. Build task text from the pipeline's injected body
        5. Call `reasonix run <task>`
        6. Record outcome (predicted vs actual) for feedback loop

    Args:
        stub_path: Path to the .md stub file
        project_dir: If set, run reasonix in this directory context
        dry_run: If True, just print what would be sent (no execution)
        timeout_sec: Timeout for the reasonix subprocess

    Returns:
        {
            "stub": { bp, name, title, ... },
            "action": "dry_run" | "executed" | "error",
            "quality": { quality pipeline output },
            "prediction": { oneshot prediction },
            "command": "...",
            "returncode": int,
            "stdout": "...",
            "stderr": "...",
        }
    """
    stub_path = Path(stub_path).expanduser().resolve()
    if not stub_path.exists():
        raise FileNotFoundError(f"Stub file not found: {stub_path}")

    parsed = parse_stub(stub_path)
    fm = parsed["frontmatter"]

    bp_id = fm.get("bp", stub_path.stem)
    name = fm.get("name", stub_path.stem)
    if project_name:
        name = project_name
    title = fm.get("title", name)
    should_init = fm.get("init", False)
    intent = fm.get("intent", "code")

    # Determine project context (used by quality pipeline)
    project_path = None
    tech_stack = None

    # Handle init:true — scaffold the project using MSpec's own Python API
    if should_init:
        try:
            from utils.project_scaffold import scaffold_project, generate_project_id, get_project_path
            from registry import init_db, register_project
            import subprocess as _sp

            project_path = scaffold_project(name)

            _sp.run(["git", "init", str(project_path)], check=True, capture_output=True)
            _sp.run(["git", "-C", str(project_path), "add", "."], check=True, capture_output=True)
            _sp.run(
                ["git", "-C", str(project_path),
                 "-c", "user.name=MSpec",
                 "-c", "user.email=mspec@harness.local",
                 "commit", "-m", "Initial scaffold"],
                check=True, capture_output=True,
            )

            project_id = generate_project_id(name)
            init_db()
            register_project(project_id, name, str(project_path))

            print(f"[stub-runner] Scaffolded project '{name}' at {project_path}")
            print(f"[stub-runner] Project ID: {project_id}")

            # Read tech stack from the scaffolded memory.json
            mem_path = project_path / ".harness" / "memory.json"
            if mem_path.exists():
                try:
                    mem_data = json.loads(mem_path.read_text(encoding="utf-8"))
                    tech_stack = mem_data.get("tech_stack", {})
                except (json.JSONDecodeError, KeyError):
                    pass

        except FileExistsError:
            print(f"[stub-runner] Project '{name}' already exists — skipping scaffold")
            project_path = get_project_path(name)
        except Exception as e:
            print(f"[stub-runner] Scaffold failed: {e} — continuing with Reasonix task")

    # ── Run quality pipeline ────────────────────────────────────
    from .quality import StubQualityPipeline, StubRunRecorder

    pipeline = StubQualityPipeline()
    quality = pipeline.run(
        stub_name=name,
        project_name=name,
        project_path=str(project_path) if project_path else None,
        tech_stack=tech_stack,
    )

    quality_passed = quality.get("passed", False)
    prediction = {
        "predicted_oneshot_rate": quality.get("predicted_oneshot_rate", 0),
        "base_score": quality.get("validation_score", 0),
        "stall_risk": quality.get("stall_risk", "unknown"),
    }

    # Build the trimmed task text (mandate + injected body + closeout)
    # Note: stub is self-contained — no external file reads needed
    mandate = [
        "EXECUTE: Create the 3 files specified below. No exploration. No questions.",
        f"Project: {name}",
        f"Location: {project_path}" if project_path else f"Name: {name}",
        "",
    ]

    injected_body = quality.get("injected_body", parsed["body"])

    closeout = (
        "---\n"
        "Output each file in a ```python ./path/to/file block. "
        "Then one summary line. That is all."
    )

    task_text = "\n".join([
        *mandate,
        injected_body,
        "",
        closeout,
    ])

    # Sanitize: replace chars that break Windows cmd.exe / .CMD shim parsing
    task_text = _sanitize_task_text(task_text)

    # Determine working directory
    cwd = project_dir or Path.cwd()

    reasonix_cmd = find_reasonix()
    if not reasonix_cmd:
        return {
            "stub": {"bp": bp_id, "name": name, "title": title},
            "action": "error",
            "error": "reasonix CLI not found. Install with: npm install -g reasonix",
            "task_text": task_text if dry_run else None,
            "quality": quality,
            "prediction": prediction,
        }

    # Build the argv for direct Node.js invocation (bypasses .CMD shim
    # which corrupts long arguments via cmd.exe %* expansion)
    # Order: node cli.js run <task> --system <prompt>
    #   <task> = "execute" (minimal — treated as user message)
    #   --system = full task context (treated as instructions)
    rx_argv = [
        reasonix_cmd["node"],
        reasonix_cmd["cli"],
        "run",
        "execute",
        "--system",
        task_text,
    ]

    if dry_run:
        label = reasonix_cmd["label"]
        print(f"[dry-run] Would pass to Reasonix ({label}):")
        print(f"[dry-run] Quality score: {quality.get('validation_score', '?')}/100")
        print(f"[dry-run] Predicted oneshot rate: {prediction['predicted_oneshot_rate']}%")
        print("─" * 60)
        print(task_text)
        print("─" * 60)
        return {
            "stub": {"bp": bp_id, "name": name, "title": title},
            "intent": intent,
            "action": "dry_run",
            "command": f"{label} run execute --system ...",
            "task_text": task_text,
            "quality": quality,
            "prediction": prediction,
        }

    label = reasonix_cmd["label"]
    print(f"[stub-runner] Passing {bp_id}: {title} to Reasonix ({label})...")
    print(f"[stub-runner] Quality score: {quality.get('validation_score', '?')}/100")
    print(f"[stub-runner] Predicted oneshot rate: {prediction['predicted_oneshot_rate']}%")
    print(f"[stub-runner] System prompt: {len(task_text)} chars via --system flag")
    print("─" * 60)

    try:
        proc = subprocess.run(
            rx_argv,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout_sec,
        )

        # ── Classify outcome and record for feedback loop ─────
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout + stderr

        outcome, reason = _detect_outcome(stdout[:1000])

        StubRunRecorder.record_run(
            stub_name=name,
            stub_bp=bp_id,
            prediction=prediction,
            actual_outcome=outcome,
            reason=reason,
            exit_code=proc.returncode,
            output_preview=stdout[:200],
            intent=intent,
        )

        # ── Extract and write files from AI output ─────────────
        written_files = []
        quality_checks = []
        if outcome == "success" and project_path:
            written_files = _extract_files_from_output(stdout, project_path)
            if written_files:
                print(f"  [stub-runner] {len(written_files)} file(s) written to {project_path}")
                quality_checks = _verify_code_quality(written_files, project_path)
                failed_checks = [c for c in quality_checks if not c["passed"]]
                if failed_checks:
                    print(f"  [stub-runner] ⚠ {len(failed_checks)} quality check(s) failed")
                    for c in failed_checks:
                        print(f"    ❌ {c['path']}: {c['check']} — {c['message']}")
                else:
                    print(f"  [stub-runner] ✅ All {len(quality_checks)} quality checks passed")

        return {
            "stub": {"bp": bp_id, "name": name, "title": title},
            "intent": intent,
            "action": "executed",
            "command": f"{label} run execute --system ...",
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "files": written_files,
            "quality_checks": quality_checks,
            "quality": quality,
            "prediction": prediction,
            "outcome": outcome,
            "reason": reason,
        }

    except subprocess.TimeoutExpired:
        StubRunRecorder.record_run(
            stub_name=name,
            stub_bp=bp_id,
            prediction=prediction,
            actual_outcome="failure",
            reason=f"Timed out after {timeout_sec}s",
            exit_code=-1,
            intent=intent,
        )
        return {
            "stub": {"bp": bp_id, "name": name, "title": title},
            "intent": intent,
            "action": "timeout",
            "command": f"{label} run execute --system ...",
            "error": f"Timed out after {timeout_sec}s",
            "quality": quality,
            "prediction": prediction,
            "outcome": "failure",
            "reason": f"Timeout after {timeout_sec}s",
        }
    except FileNotFoundError:
        return {
            "stub": {"bp": bp_id, "name": name, "title": title},
            "intent": intent,
            "action": "error",
            "error": f"reasonix CLI not found: {reasonix_cmd}",
            "quality": quality,
            "prediction": prediction,
        }


def list_stubs() -> list[dict]:
    """List all available stub files in the stubs directory."""
    stubs = []
    for f in sorted(STUBS_DIR.glob("*.md")):
        if f.name == "TEMPLATE.md":
            continue
        parsed = parse_stub(f)
        fm = parsed["frontmatter"]
        stubs.append({
            "path": str(f.relative_to(STUBS_DIR.parent.parent) if STUBS_DIR.parent.parent else f),
            "bp": fm.get("bp", "—"),
            "name": fm.get("name", f.stem),
            "title": fm.get("title", f.stem),
            "init": fm.get("init", False),
        })
    return stubs


if __name__ == "__main__":
    """CLI entry for direct use: python -m src.stubs.runner <file> [project-name]"""
    if len(sys.argv) < 2:
        print("Usage: python -m src.stubs.runner <stub-file> [project-name] [--dry-run] [--history] [--summary]")
        print("  project-name: override the project name from stub frontmatter")
        print("")
        print("Available stubs:")
        for s in list_stubs():
            print(f"  {s['bp']:8s} {s['name']:20s} {s['title']}")
        sys.exit(1)

    # Handle history / summary subcommands
    from .quality import StubRunRecorder

    if "--history" in sys.argv:
        stub_filter = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
        history = StubRunRecorder.get_history(stub_filter)
        print(f"Run history{' for ' + stub_filter if stub_filter else ''}:")
        print(f"  Total: {len(history)} runs")
        for h in history[-10:]:
            print(f"  [{h['actual_outcome']:8s}] {h['stub_name']:12s} "
                  f"pred={h['predicted_oneshot_rate']:3d}% "
                  f"reason={h['reason'][:60]}")
        print(f"\nSummary: {json.dumps(StubRunRecorder.get_summary(stub_filter), indent=2)}")
        sys.exit(0)

    dry_run = "--dry-run" in sys.argv
    stub_path = Path(sys.argv[1])

    # Parse optional project name (skip flags)
    project_name = None
    for arg in sys.argv[2:]:
        if not arg.startswith("--"):
            project_name = arg
            break

    try:
        result = run_stub(stub_path, dry_run=dry_run, project_name=project_name)

        # Print quality summary
        quality = result.get("quality", {})
        prediction = result.get("prediction", {})
        print(f"[stub-runner] Quality score: {quality.get('validation_score', '?')}/100")
        print(f"[stub-runner] Predicted oneshot rate: {prediction.get('predicted_oneshot_rate', '?')}%")
        print(f"[stub-runner] Recommendations: {len(quality.get('recommendations', []))} items")
        for r in quality.get("recommendations", []):
            print(f"  ⚠  {r}")

        if result["action"] == "error":
            print(f"[ERROR] {result.get('error', 'Unknown error')}")
            sys.exit(1)
        elif result["action"] == "executed":
            print("─" * 60)
            print(f"[stub-runner] Return code: {result['returncode']}")
            print(f"[stub-runner] Outcome: {result.get('outcome', 'unknown')}")
            if result.get("reason"):
                print(f"[stub-runner] Reason: {result['reason']}")
            if result["stdout"]:
                print("[stdout]")
                # Show only first 500 chars of stdout in CLI mode
                print(result["stdout"][:500])
                if len(result["stdout"]) > 500:
                    print(f"... [{len(result['stdout']) - 500} more chars]")
            if result["stderr"]:
                print("[stderr]")
                print(result["stderr"])
        elif result["action"] == "dry_run":
            print("[dry-run] Task text prepared (shown above)")
        elif result["action"] == "timeout":
            print(f"[TIMEOUT] {result.get('error', '')}")
            sys.exit(1)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

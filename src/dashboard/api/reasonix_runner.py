"""Background runner for Reasonix stub execution — spawns `reasonix run`, polls every 3min,
logs events, and preserves generated code for git commit.

Integrated with the existing dashboard run-tracking system (.harness/runs/).
"""

import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Reuse the stub parser ─────────────────────────────────────
from stubs.runner import parse_stub, find_reasonix


POLL_INTERVAL_SEC = 180  # 3 minutes
STALL_TIMEOUT_SEC = 300  # 5 minutes max stall before auto-fail
MAX_STALL_RETRIES = 3    # max re-prompt attempts per stall


class ReasonixRunManager:
    """Manages a background Reasonix run with periodic polling and code preservation."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.runs_dir = project_path / ".harness" / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._active_runs: dict[str, dict] = {}  # run_id -> run info

    def start_run(self, stub_path: Path, run_id: Optional[str] = None) -> dict:
        """Start a Reasonix stub run in background, delegating to run_stub().

        Uses the same proven run_stub() from the CLI runner — builds mandate,
        invokes Node.js directly with --system flag, extracts files, verifies
        quality. No terminal window, no chat mode.
        """
        stub_path = Path(stub_path).expanduser().resolve()
        if not stub_path.exists():
            raise FileNotFoundError(f"Stub file not found: {stub_path}")

        # Parse stub
        parsed = parse_stub(stub_path)
        fm = parsed["frontmatter"]
        stub_name = fm.get("name", stub_path.stem)
        bp_id = fm.get("bp", stub_path.stem)
        title = fm.get("title", stub_name)

        # Create run record
        run_id = run_id or str(uuid.uuid4())[:8]
        session_id = f"reasonix_{run_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        now = datetime.now(timezone.utc).isoformat()

        run = {
            "id": run_id, "session_id": session_id,
            "stub_name": stub_name, "stub_path": str(stub_path),
            "bp_id": bp_id, "title": title,
            "agent": "reasonix", "model": "deepseek-v4-flash",
            "status": "starting",
            "start_time": now, "end_time": None,
            "error": None, "exit_code": None,
            "events": [
                {"timestamp": now, "level": "info",
                 "message": f"Reasonix run created for {bp_id}: {title}",
                 "context": {"stub": stub_name, "bp": bp_id}}
            ],
            "files_changed": [], "output_preview": "",
        }
        run_path = self.runs_dir / f"{run_id}.json"
        run_path.write_text(json.dumps(run, indent=2))

        # Spawn background thread — calls run_stub() just like the CLI.
        # No Popen, no terminal window, no chat mode.
        thread = threading.Thread(
            target=self._run_stub_thread,
            args=(run_id, stub_path),
            daemon=True,
        )
        thread.start()
        # Return immediately — thread handles all file updates
        return self.get_run(run_id)

    def _run_stub_thread(self, run_id: str, stub_path: Path):
        """Background: call run_stub() and persist results to run file."""
        from stubs.runner import run_stub

        try:
            result = run_stub(stub_path)
            rd = self.get_run(run_id) or {}
            rd["end_time"] = datetime.now(timezone.utc).isoformat()
            rd["exit_code"] = result.get("returncode", 0)
            rd["output_preview"] = (result.get("stdout") or "")[:500]

            files = result.get("files", [])
            if files:
                rd["files_changed"] = [
                    {"path": f["path"], "status": f.get("status")}
                    for f in files
                ]

            outcome = result.get("outcome", "unknown")
            rd["status"] = "completed" if outcome == "success" else "failed"
            rd["error"] = None if outcome == "success" else (
                result.get("reason") or result.get("error") or f"Outcome: {outcome}"
            )

            events = rd.get("events", [])
            events.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "info" if outcome == "success" else "error",
                "message": f"Run {rd['status']}. Files: {len(files)}. Outcome: {outcome}",
            })
            rd["events"] = events
            (self.runs_dir / f"{run_id}.json").write_text(
                json.dumps(rd, indent=2, default=str)
            )
        except Exception as e:
            self._update_status(run_id, "failed", error=str(e))
            self._log_event(run_id, "error", f"Run failed: {e}")
        """Start a Reasonix stub run in background.

        Flow:
            1. Parse the stub file
            2. Create a run record
            3. Spawn `reasonix run <task>` as a subprocess
            4. Start a poll thread (every 3 min)
            5. Return run metadata

        Args:
            stub_path: Path to the .md stub file
            run_id: Optional run ID (auto-generated if not provided)

        Returns:
            Run metadata dict
        """
        stub_path = Path(stub_path).expanduser().resolve()
        if not stub_path.exists():
            raise FileNotFoundError(f"Stub file not found: {stub_path}")

        # Parse stub
        parsed = parse_stub(stub_path)
        fm = parsed["frontmatter"]
        stub_name = fm.get("name", stub_path.stem)
        bp_id = fm.get("bp", stub_path.stem)
        title = fm.get("title", stub_name)

        # Create run record FIRST (so run_id is available for logging)
        run_id = run_id or str(uuid.uuid4())[:8]
        session_id = f"reasonix_{run_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        now = datetime.now(timezone.utc).isoformat()

        run = {
            "id": run_id,
            "session_id": session_id,
            "stub_name": stub_name,
            "stub_path": str(stub_path),
            "bp_id": bp_id,
            "title": title,
            "agent": "reasonix",
            "model": "deepseek-v4-flash",
            "status": "starting",
            "start_time": now,
            "end_time": None,
            "error": None,
            "exit_code": None,
            "events": [
                {
                    "timestamp": now,
                    "level": "info",
                    "message": f"Reasonix run created for {bp_id}: {title}",
                    "context": {"stub": stub_name, "bp": bp_id},
                }
            ],
            "files_changed": [],
            "output_preview": "",
        }

        # Save initial run file so _log_event can append to it
        run_path = self.runs_dir / f"{run_id}.json"
        run_path.write_text(json.dumps(run, indent=2))

        # Also create in SQLite registry
        try:
            from registry import create_run as db_create_run, get_all_projects
            projects = get_all_projects()
            project_id = next((p["id"] for p in projects
                               if Path(p["path"]) == self.project_path), str(self.project_path))
            db_create_run(
                project_id=project_id,
                run_id=run_id, session_id=session_id,
                stub_name=stub_name, agent="reasonix",
                model="deepseek-v4-flash",
                stub_path=str(stub_path), bp_id=bp_id, title=title,
            )
        except Exception:
            pass

        # Handle init:true — create blueprint output folder inside this project's .harness/
        scaffolded_path = None
        if fm.get("init", False):
            try:
                import subprocess as _sp

                # Folder name follows markdown naming convention: bp-01-scaffold
                bp_folder = f"{bp_id.lower()}-{stub_name}"
                
                # Output goes inside the current project's .harness/ directory
                harness_dir = self.project_path / ".harness"
                bp_dir = harness_dir / bp_folder
                
                # Clean slate: delete old run folder if it exists
                if bp_dir.exists():
                    _sp.run(["cmd", "/c", "rmdir", "/s", "/q", str(bp_dir)], 
                           check=False, capture_output=True)
                    self._log_event(run_id, "info", f"Cleaned previous run at {bp_dir}")
                
                scaffolded_path = bp_dir
                
                # Create directory structure
                bp_dir.mkdir(parents=True, exist_ok=True)
                (bp_dir / "src").mkdir(exist_ok=True)
                (bp_dir / "logs").mkdir(exist_ok=True)
                (bp_dir / "src" / ".gitkeep").write_text("")
                
                # Write initial metadata
                spec_content = f"# Blueprint: {bp_id} — {title}\n\n## Project\n{stub_name}\n\n## Description\n\n## Requirements\n"
                plan_content = f"""# Plan for {bp_id}: {title}

## Phase 1: Project Setup
- [T001] Initialize project structure — Directory tree, config files, and dependencies are in place
- [T002] Configure development environment — Virtual environment, linter, and type checker configured

## Phase 2: Core Implementation
- [T003] Implement core data models — All Pydantic models defined with validation
- [T004] Implement business logic — Core service layer with unit tests passing
- [T005] Implement API endpoints — All REST endpoints return correct responses

## Phase 3: Frontend
- [T006] Build UI components — All React components render without errors
- [T007] Integrate with API — Frontend successfully fetches and displays data

## Phase 4: Testing & Polish
- [T008] Add integration tests — Integration test suite passes
- [T009] Documentation and final review — README, API docs, and handoff notes complete
"""
                
                (bp_dir / "spec.md").write_text(spec_content)
                (bp_dir / "plan.md").write_text(plan_content)
                (bp_dir / "run.log").write_text(f"# Run Log — {bp_id}: {title}\n\nStarted: {now}\nStatus: running\n")
                
                self._log_event(run_id, "info", f"Blueprint output at {bp_dir}")
                self._log_event(run_id, "info", f"Plan written ({len(plan_content)} chars)")

            except Exception as e:
                self._log_event(run_id, "warn", f"Blueprint init failed (continuing): {e}")

        # Build task text — using StubContextInjector for comprehensive context
        from stubs.quality import StubContextInjector
        injector = StubContextInjector()
        
        # Build project context for injection
        tech_stack = {}
        try:
            if scaffolded_path:
                mem_file = scaffolded_path / '.harness' / 'memory.json'
                if mem_file.exists():
                    mem_data = json.loads(mem_file.read_text(encoding="utf-8"))
                    tech_stack = mem_data.get("tech_stack", {})
        except:
            pass
        
        body = parsed["body"]
        bp_folder_name = f"{bp_id.lower()}-{stub_name}" if bp_id else stub_name
        project_path_str = str(scaffolded_path).replace("\\", "/") if scaffolded_path else f".harness/{bp_folder_name}"
        
        # Run context injection
        body, _ = injector.inject(
            body,
            project_name=stub_name,
            project_path=project_path_str,
            tech_stack=tech_stack or {"lang": "Python", "cli": "typer", "registry": "SQLite"},
        )

        # Build task text with mandate prefix (same as runner.py run_stub)
        # The mandate tells AI this is an execution, not a conversation
        task_text = "\n".join([
            f"EXECUTE: Create the files specified below. No exploration. No questions.",
            f"Project: {stub_name}",
            "",
            body,
        ])

        # Find reasonix
        reasonix_cmd = find_reasonix()
        if not reasonix_cmd:
            self._update_status(run_id, "failed", error="reasonix not found on PATH")
            self._log_event(run_id, "error", "reasonix CLI not found. Install: npm install -g reasonix")
            return self.get_run(run_id)

        # Spawn subprocess — use Node.js directly (bypasses .CMD shim
        # which corrupts long args via cmd.exe %* expansion)
        try:
            reasonix_cwd = str(scaffolded_path) if scaffolded_path else str(self.project_path)
            rx_argv = [
                reasonix_cmd["node"],
                reasonix_cmd["cli"],
                "run", "execute", "--system", task_text,
            ]
            # Suppress console window: DETACHED_PROCESS prevents node.exe
            # from inheriting or creating its own console window.
            # CREATE_NO_WINDOW alone doesn't work because node.exe is a
            # console app that creates a window on spawn.
            startupinfo = None
            creation_flags = 0
            if hasattr(subprocess, 'DETACHED_PROCESS'):
                creation_flags |= subprocess.DETACHED_PROCESS
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                creation_flags |= subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(
                rx_argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=reasonix_cwd,
                text=True,
                creationflags=creation_flags,
                startupinfo=startupinfo,
            )

            self._log_event(run_id, "info", f"Process started (PID: {proc.pid})", {"pid": proc.pid})
            self._update_status(run_id, "running")

            # Store active process
            self._active_runs[run_id] = {
                "proc": proc,
                "stub_path": stub_path,
                "stdout_buf": [],
                "stderr_buf": [],
                "poll_thread": None,
            }

            # Also write PID to active.json so check-runs can monitor
            try:
                active_path = self.runs_dir / "active.json"
                active = {}
                if active_path.exists():
                    active = json.loads(active_path.read_text(encoding="utf-8"))
                active[run_id] = {
                    "pid": proc.pid,
                    "stub_name": stub_name,
                    "start_time": now,
                }
                active_path.write_text(json.dumps(active, indent=2))
            except Exception:
                pass

            # Start background output reader + poller
            poll_thread = threading.Thread(
                target=self._poll_loop,
                args=(run_id, proc),
                daemon=True,
            )
            poll_thread.start()
            self._active_runs[run_id]["poll_thread"] = poll_thread

            return self.get_run(run_id)

        except Exception as e:
            self._update_status(run_id, "failed", error=str(e))
            self._log_event(run_id, "error", f"Failed to start Reasonix: {e}")
            return self.get_run(run_id)

    def _poll_loop(self, run_id: str, proc: subprocess.Popen):
        """Background thread: reads output continuously, polls every 3 min for status,
        detects file changes on completion."""
        last_poll_time = time.time()
        output_lines = []

        while True:
            # Read available output (non-blocking) — drain stdout line by line
            try:
                if proc.stdout and not proc.stdout.closed:
                    line = proc.stdout.readline()
                    if line:
                        output_lines.append(line.rstrip())
                        self._update_output_preview(run_id, output_lines[-50:])
                    elif proc.poll() is not None:
                        # No more output AND process is done
                        pass
                    else:
                        # No output yet but process still running — sleep briefly
                        time.sleep(0.5)
                        continue
            except (ValueError, OSError):
                # Pipe already closed
                pass

            # Check if process is done
            poll_result = proc.poll()
            if poll_result is not None:
                exit_code = poll_result
                self._log_event(run_id, "info", f"Reasonix process exited (code: {exit_code})",
                               {"exit_code": exit_code})

                # Drain any remaining output safely
                try:
                    if proc.stdout and not proc.stdout.closed:
                        for line in proc.stdout:
                            if line.strip():
                                output_lines.append(line.rstrip())
                        proc.stdout.close()
                except (ValueError, OSError):
                    pass

                try:
                    if proc.stderr and not proc.stderr.closed:
                        stderr_text = proc.stderr.read()
                        proc.stderr.close()
                    else:
                        stderr_text = ""
                except (ValueError, OSError):
                    stderr_text = ""

                # Final output preview
                full_text = "\n".join(output_lines[-100:])
                if output_lines:
                    self._update_output_preview(run_id, output_lines[-50:])

                # Materialize Reasonix output as files in the project (use FULL output)
                self._materialize_output(run_id, output_lines)

                # Stall detection — with rich info, wall-time tracking, and DB logging
                active_entry = self._active_runs.get(run_id, {})
                stall_info = self._detect_stall(full_text)
                
                if stall_info["stalled"]:
                    # Track stall start time
                    if '_stall_start' not in active_entry:
                        active_entry['_stall_start'] = time.time()
                        active_entry['_stall_count'] = 0
                        active_entry['_stall_history'] = []
                    
                    current_stalls = active_entry.get('_stall_count', 0)
                    elapsed_stall = time.time() - active_entry['_stall_start']
                    
                    # Record stall details
                    stall_record = {
                        "attempt": current_stalls + 1,
                        "patterns": stall_info.get("matched_patterns", []),
                        "context": stall_info.get("context", full_text[:200]),
                        "elapsed_sec": int(elapsed_stall),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    active_entry.setdefault('_stall_history', []).append(stall_record)
                    
                    # FAIL if: over 5 min total OR over max retries
                    if elapsed_stall >= STALL_TIMEOUT_SEC or current_stalls >= MAX_STALL_RETRIES:
                        reason = f"Stall limit exceeded: {current_stalls + 1} attempts over {int(elapsed_stall)}s"
                        self._log_event(run_id, "error", reason, stall_record)
                        self._log_stall_to_db(run_id, stall_record, full_text)
                        self._update_status(run_id, "failed", error=reason)
                        self._active_runs.pop(run_id, None)
                        self._remove_from_active(run_id)
                        break
                    
                    # Re-run with corrective prompt
                    self._log_event(run_id, "warn", 
                        f"Stall #{current_stalls + 1} ({int(elapsed_stall)}s): {stall_info.get('context','')[:100]}",
                        stall_record)
                    active_entry['_stall_count'] = current_stalls + 1
                    
                    follow_up = self._build_follow_up(full_text, run_id)
                    try:
                        reasonix_cmd = find_reasonix()
                        if reasonix_cmd:
                            startupinfo = None
                            cf = 0
                            if hasattr(subprocess, 'DETACHED_PROCESS'):
                                cf |= subprocess.DETACHED_PROCESS
                            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                                cf |= subprocess.CREATE_NO_WINDOW
                            new_proc = subprocess.Popen(
                                [reasonix_cmd["node"], reasonix_cmd["cli"],
                                 "run", "execute", "--system", follow_up],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=str(self.project_path), text=True,
                                creationflags=cf, startupinfo=startupinfo,
                            )
                            self._log_event(run_id, "info", f"Re-spawned Reasonix (PID: {new_proc.pid})")
                            self._active_runs[run_id]['proc'] = new_proc
                            proc = new_proc
                            output_lines = []
                            continue
                    except Exception as e:
                        self._log_event(run_id, "error", f"Re-run failed: {e}")
                
                # Detect file changes
                files_changed = self._detect_file_changes()

                if exit_code == 0:
                    self._update_status(run_id, "completed", exit_code=exit_code)
                    self._log_event(run_id, "info", f"Run completed successfully. Files changed: {len(files_changed)}",
                                   {"files_changed": files_changed})
                else:
                    self._update_status(run_id, "failed", error=f"Exit code: {exit_code}", exit_code=exit_code)
                    self._log_event(run_id, "error", f"Run failed (exit code: {exit_code})",
                                   {"stderr": stderr_text[:500]})

                # Save files changed
                self._update_files_changed(run_id, files_changed)

                # Log final output
                cost_line = ""
                for line in output_lines:
                    if "cost:" in line.lower() or "turns:" in line.lower():
                        cost_line = line
                if cost_line:
                    self._log_event(run_id, "info", f"Run stats: {cost_line}")

                # Write run.log with final status
                try:
                    bp_folder = f"{bp_id.lower()}-{stub_name}"
                    log_path = self.project_path / ".harness" / bp_folder / "run.log"
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    status_text = "completed" if exit_code == 0 else f"failed (exit {exit_code})"
                    log_path.write_text(
                        f"# Run Log — {bp_id}: {title}\n\n"
                        f"Run ID: {run_id}\n"
                        f"Started: {now}\n"
                        f"Completed: {datetime.now(timezone.utc).isoformat()}\n"
                        f"Status: {status_text}\n"
                        f"Exit code: {exit_code}\n"
                        f"Files changed: {len(files_changed)}\n"
                        f"{cost_line}\n\n"
                        f"## Output Preview\n{full_text[-1000:]}\n"
                    )
                except Exception:
                    pass

                # Clean up
                self._active_runs.pop(run_id, None)
                self._remove_from_active(run_id)
                break

            # Check if it's time to poll (every 3 min)
            elapsed = time.time() - last_poll_time
            if elapsed >= POLL_INTERVAL_SEC:
                self._log_event(run_id, "info",
                    f"Still running... {len(output_lines)} output lines captured, "
                    f"{len(self._detect_file_changes())} files changed so far")
                last_poll_time = time.time()

            # Brief sleep to avoid busy-waiting
            time.sleep(2)

    def poll_run(self, run_id: str) -> dict:
        """Manually poll a run's status (called from API)."""
        run = self.get_run(run_id)
        if not run:
            return {"error": "Run not found"}

        # If still running, check process
        if run["status"] in ("starting", "running"):
            active = self._active_runs.get(run_id)
            if active and active["proc"]:
                poll_result = active["proc"].poll()
                if poll_result is not None:
                    # Process exited since last check
                    # The poll thread handles this, but let's force a check
                    pass

        # Update file changes
        files = self._detect_file_changes()
        run["files_changed"] = files

        return run

    def get_run(self, run_id: str) -> Optional[dict]:
        """Get run details from the run file."""
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return None
        return json.loads(run_path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[dict]:
        """List all Reasonix runs."""
        runs = []
        for f in sorted(self.runs_dir.glob("*.json"), reverse=True):
            if f.name == "active.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("agent") == "reasonix":
                    runs.append(data)
            except (json.JSONDecodeError, Exception):
                continue
        return runs

    STALL_PATTERNS = [
        r"I need more",
        r"I need to know",
        r"I need context",
        r"I need additional",
        r"I need you to",
        r"<<<NEEDS_PRO",
        r"NEEDS_PRO",
        r"Could you provide",
        r"Can you provide",
        r"Can you clarify",
        r"Could you clarify",
        r"What type of project",
        r"What should the project",
        r"What would you like",
        r"What do you want",
        r"Please provide",
        r"Please specify",
        r"Do you want me to",
        r"Would you like me to",
        r"Let me know",
        r"Tell me what",
        r"I don't have enough",
        r"I don't know what",
        r"I'm not sure what",
        r"I'm not sure which",
        r"I'm going to need",
    ]

    def _detect_stall(self, output_text: str) -> dict:
        """Detect if Reasonix stalled by asking questions instead of executing.
        
        Returns a dict:
            {"stalled": bool, "patterns": [str], "context": str, "matched_patterns": [str]}
        or {"stalled": False} if no stall detected.
        """
        if not output_text:
            return {"stalled": False}
        text_lower = output_text.lower()
        matched = []
        for pattern in self.STALL_PATTERNS:
            m = re.search(pattern, text_lower)
            if m:
                matched.append(pattern)
        
        if len(matched) >= 2:
            # Extract surrounding context for the first match
            first_match = re.search(matched[0], output_text, re.IGNORECASE)
            ctx_start = max(0, first_match.start() - 60) if first_match else 0
            ctx_end = min(len(output_text), first_match.end() + 120) if first_match else len(output_text)
            context = output_text[ctx_start:ctx_end].strip()
            return {"stalled": True, "patterns": matched, "context": context, "matched_patterns": matched}
        
        if len(matched) == 1:
            has_file_ops = any(op in text_lower for op in ["write_file", "created", "wrote", "run_command"])
            if not has_file_ops:
                first_match = re.search(matched[0], output_text, re.IGNORECASE)
                ctx_start = max(0, first_match.start() - 60) if first_match else 0
                ctx_end = min(len(output_text), first_match.end() + 120) if first_match else len(output_text)
                context = output_text[ctx_start:ctx_end].strip()
                return {"stalled": True, "patterns": matched, "context": context, "matched_patterns": matched}
        
        return {"stalled": False}

    def _build_follow_up(self, stalled_output: str, run_id: str) -> str:
        """Build a corrective follow-up prompt when Reasonix stalls.
        
        Reads the run's original task text and adds corrective instructions
        addressing the specific questions the AI asked.
        """
        # Get the original task
        run_path = self.runs_dir / f"{run_id}.json"
        original_task = ""
        try:
            run_data = json.loads(run_path.read_text(encoding="utf-8"))
            # The task isn't stored in the run — rebuild from the stub
            # Use the critical instruction from the original
        except:
            pass

        # Extract what the AI was asking about
        questions = []
        for pattern in self.STALL_PATTERNS:
            matches = re.finditer(pattern, stalled_output, re.IGNORECASE)
            for m in matches:
                # Get surrounding context
                start = max(0, m.start() - 50)
                end = min(len(stalled_output), m.end() + 100)
                context = stalled_output[start:end].strip()
                questions.append(context)

        follow_up = [
            "## CORRECTIVE FOLLOW-UP — You asked questions instead of executing",
            "",
            "You previously stalled by asking for clarification. This is your final instruction:",
            "",
            "DO NOT ask questions. DO NOT ask for more context.",
            "Everything you need is already in the original task description.",
            "You MUST execute the task now using your file writing and shell tools.",
            "",
            "## Specific answers to your questions:",
        ]

        if questions:
            follow_up.append(f"Your questions included: {'; '.join(questions[:3])}")
            follow_up.append("")
            follow_up.append("The answers are already in the task description above. Read carefully and proceed.")

        follow_up.extend([
            "",
            "## Immediate action required:",
            "- Open the spec file and read it",
            "- Write the plan to plan.md",
            "- DO NOT ask any more questions",
            "- Just execute the task now",
        ])

        return "\n".join(follow_up)


    def _materialize_output(self, run_id: str, output_lines: list[str]):
        """Capture Reasonix's output and materialize code blocks as files.
        
        Parses ```type filename ... ``` blocks and writes each to the 
        blueprint's src/ directory. Also detects plan content.
        """
        if not output_lines:
            return
        
        full_output = "\n".join(output_lines)
        
        # Find stub info
        stub_name = "unknown"; bp_id = "BP"
        run_path = self.runs_dir / f"{run_id}.json"
        if run_path.exists():
            try:
                rd = json.loads(run_path.read_text(encoding="utf-8"))
                stub_name = rd.get("stub_name", "unknown")
                bp_id = rd.get("bp_id", "BP")
            except: pass
        
        bp_folder = f"{bp_id.lower()}-{stub_name}"
        project_dir = self.project_path / ".harness" / bp_folder
        src_dir = project_dir / "src"
        written = []
        
        # Parse ```type filename ... ``` blocks with filename in the fence
        # Handles both: ```python main.py and ```python:main.py and ```main.py
        code_blocks = re.findall(
            r'```(?:\w+)?[:\s]+([^\n]+?)\n(.*?)```', 
            full_output, re.DOTALL
        )
        
        for filename, content in code_blocks:
            filename = filename.strip().strip('"').strip("'")
            content = content.strip()
            if not filename or not content:
                continue
            
            # Determine target directory
            if filename.endswith('.md') and ('Phase' in content or 'T00' in content):
                target = project_dir / filename
            else:
                target = src_dir / filename
            
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content + "\n")
            written.append(f"{target.relative_to(project_dir.parent.parent)} ({len(content)} chars)")
        
        # Fallback: code blocks without filenames (no space after ```type)
        if not written:
            fallback_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', full_output, re.DOTALL)
            for i, block in enumerate(fallback_blocks):
                block = block.strip()
                if not block: continue
                if "## Phase" in block or "- [T" in block:
                    (project_dir / "plan.md").write_text(f"# Plan\n\n{block}\n")
                    written.append(f"plan.md ({len(block)} chars)")
                else:
                    src_dir.mkdir(parents=True, exist_ok=True)
                    (src_dir / f"script_{i+1}.py").write_text(block + "\n")
                    written.append(f"src/script_{i+1}.py ({len(block)} chars)")
        
        # Look for loose filename mentions: # filename.py or ## filename.py
        if not written:
            loose = re.findall(r'(?:^|\n)#+\s*([\w-]+\.(?:py|txt|js|ts|json|yaml|toml))\s*\n(.*?)(?=\n#+\s*[\w-]+\.|\Z)', 
                             full_output, re.DOTALL | re.MULTILINE)
            for filename, content in loose:
                content = content.strip()
                if content and len(content) > 20:
                    target = src_dir / filename.strip()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content + "\n")
                    written.append(f"src/{filename} ({len(content)} chars)")
        
        if written:
            self._log_event(run_id, "info", f"Materialized {len(written)} file(s) from Reasonix output")
            
            # Git track new files
            try:
                import subprocess as _sp_git
                _sp_git.run(["git", "-C", str(self.project_path), "add", "."], 
                           check=False, capture_output=True)
            except:
                pass
            
            # Git add the materialized files to the project
            try:
                import subprocess as _sp_git
                _sp_git.run(["git", "-C", str(self.project_path), "add", "."], 
                           check=False, capture_output=True)
            except:
                pass

    def _log_stall_to_db(self, run_id: str, stall_record: dict, full_output: str):
        """Log stall event to the registry database for failure theme analysis."""
        try:
            from registry import get_connection
            conn = get_connection()
            # Ensure stall_events table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stall_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    stub_name TEXT,
                    stall_count INTEGER,
                    patterns TEXT,
                    context TEXT,
                    output_snippet TEXT,
                    elapsed_sec INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Get stub name from the run file
            stub_name = "unknown"
            run_path = self.runs_dir / f"{run_id}.json"
            if run_path.exists():
                try:
                    run_data = json.loads(run_path.read_text(encoding="utf-8"))
                    stub_name = run_data.get("stub_name", "unknown")
                except:
                    pass
            
            patterns = ";".join(stall_record.get("patterns", []))
            context = stall_record.get("context", "")[:500]
            output_snippet = full_output[:1000]
            elapsed = stall_record.get("elapsed_sec", 0)
            count = stall_record.get("attempt", 1)
            
            conn.execute(
                """INSERT INTO stall_events (run_id, stub_name, stall_count, patterns, context, output_snippet, elapsed_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, stub_name, count, patterns, context, output_snippet, elapsed),
            )
            conn.commit()
            conn.close()
        except Exception as db_err:
            # Don't let DB errors crash the poll loop
            pass

    def _detect_file_changes(self) -> list[dict]:
        """Detect files changed in the project since last git state.

        Returns list of {path, status} dicts.
        """
        changes = []
        try:
            # Track new untracked files
            result = subprocess.run(
                ["git", "-C", str(self.project_path), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    status_code = line[:2].strip()
                    file_path = line[3:].strip()
                    if file_path and not file_path.startswith(".harness/"):
                        changes.append({
                            "path": file_path,
                            "status": "modified" if status_code == "M" else
                                      "added" if status_code in ("??", "A") else
                                      "deleted" if status_code == "D" else status_code,
                        })

            # Also check diff for modified files
            diff_result = subprocess.run(
                ["git", "-C", str(self.project_path), "diff", "--name-only"],
                capture_output=True, text=True, timeout=10,
            )
            if diff_result.returncode == 0:
                for line in diff_result.stdout.strip().split("\n"):
                    if line.strip() and line not in [c["path"] for c in changes]:
                        changes.append({"path": line.strip(), "status": "modified"})
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return changes

    def _update_status(self, run_id: str, status: str, error: Optional[str] = None, exit_code: Optional[int] = None):
        """Update run status in the run file AND the SQLite registry."""
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return
        end_time = datetime.now(timezone.utc).isoformat() if status in ("completed", "failed") else None
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = status
            if end_time:
                run["end_time"] = end_time
            if error:
                run["error"] = error
            if exit_code is not None:
                run["exit_code"] = exit_code
            run_path.write_text(json.dumps(run, indent=2))
        except (json.JSONDecodeError, Exception):
            pass

        # Also update SQLite registry
        try:
            from registry import update_run_status as db_update
            db_update(run_id, status, error=error, exit_code=exit_code)
        except Exception:
            pass

        # Sync to build step if applicable
        try:
            from registry import get_all_projects, get_build_steps, update_build_step_status, link_build_step_to_run
            import re as _re
            projects = get_all_projects()
            pid = next((p["id"] for p in projects if Path(str(p["path"])) == self.project_path), None)
            if pid:
                stub_name = json.loads(run_path.read_text(encoding="utf-8")).get("stub_name", "")
                step_hint = _re.sub(r"^BP-\d+-", "", stub_name, flags=_re.IGNORECASE).lower()
                steps_data = get_build_steps(pid)
                for step in steps_data.get("steps", []):
                    sk = step["id"].lower().replace("_", "").replace("-", "")
                    hk = step_hint.replace("_", "").replace("-", "")
                    if hk in sk or sk in hk:
                        sync_status = "completed" if status == "completed" else \
                                      "in_progress" if status in ("running", "starting") else \
                                      "failed" if status in ("failed", "stalled") else None
                        if sync_status:
                            update_build_step_status(pid, step["id"], sync_status)
                            link_build_step_to_run(pid, step["id"], run_id)
                        break
        except Exception:
            pass

    def _remove_from_active(self, run_id: str):
        """Remove PID from active.json tracking."""
        try:
            active_path = self.runs_dir / "active.json"
            if active_path.exists():
                active = json.loads(active_path.read_text(encoding="utf-8"))
                active.pop(run_id, None)
                active_path.write_text(json.dumps(active, indent=2))
        except Exception:
            pass

    def _log_event(self, run_id: str, level: str, message: str, context: Optional[dict] = None):
        """Append a log event to the run file."""
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["events"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message,
                "context": context or {},
            })
            run_path.write_text(json.dumps(run, indent=2))
        except (json.JSONDecodeError, Exception):
            pass

    def _update_output_preview(self, run_id: str, lines: list[str]):
        """Update the output preview in the run file."""
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["output_preview"] = "\n".join(lines[-20:])
            run_path.write_text(json.dumps(run, indent=2))
        except (json.JSONDecodeError, Exception):
            pass

    def _update_files_changed(self, run_id: str, files: list[dict]):
        """Update the files changed list in the run file."""
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["files_changed"] = files
            run_path.write_text(json.dumps(run, indent=2))
        except (json.JSONDecodeError, Exception):
            pass


# ─── Singleton manager ─────────────────────────────────────────

_manager_instance = None
_manager_lock = threading.Lock()


def get_manager(project_path: Optional[Path] = None) -> ReasonixRunManager:
    """Get or create the singleton ReasonixRunManager."""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = ReasonixRunManager(project_path or Path.cwd())
    return _manager_instance

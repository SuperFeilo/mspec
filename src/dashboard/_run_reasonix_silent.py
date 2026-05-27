"""Silent Reasonix runner — called by dashboard via pythonw.exe (no console window).

Usage: pythonw.exe _run_reasonix_silent.py <task_file> <out_file> <err_file>

Reads task from <task_file>, runs reasonix, writes stdout to <out_file>
and stderr to <err_file>. Exit code is printed as last line of stdout.
"""
import json
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stubs.runner import find_reasonix

task_file = Path(sys.argv[1])
out_file = Path(sys.argv[2])
err_file = Path(sys.argv[3])

task_text = task_file.read_text(encoding="utf-8")

rx = find_reasonix()
if not rx:
    out_file.write_text("ERROR: reasonix CLI not found")
    sys.exit(1)

argv = [rx["node"], rx["cli"], "run", "execute", "--system", task_text]

proc = subprocess.run(
    argv,
    capture_output=True,
    text=True,
    timeout=300,
)

out_file.write_text(proc.stdout or "")
err_file.write_text(proc.stderr or "")

# Exit code as last line of stdout so caller can read it
sys.exit(proc.returncode)

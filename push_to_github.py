#!/usr/bin/env python3
"""Push MSpec to GitHub via API. Set GITHUB_TOKEN env var to your PAT."""

import os, sys, base64, json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = "SuperFeilo/mspec"
BRANCH = "main"
TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("ERROR: Set GITHUB_TOKEN environment variable to your GitHub PAT")
    sys.exit(1)

API = f"https://api.github.com/repos/{REPO}"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "mspec-push"}
SRC = Path(__file__).parent.resolve()
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}


def req(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    r = Request(f"{API}{path}", data=body, headers=HEADERS, method=method)
    try:
        with urlopen(r) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:300]}")
        raise


# 1. Get HEAD
print("HEAD...")
ref = req("GET", f"/git/refs/heads/{BRANCH}")
head_sha = ref["object"]["sha"]
print(f"  HEAD: {head_sha[:7]}")

# 2. Walk files
files = []
for p in SRC.rglob("*"):
    if not p.is_file() or any(d in p.relative_to(SRC).parts for d in SKIP_DIRS):
        continue
    files.append((str(p.relative_to(SRC).as_posix()), p.read_bytes()))
print(f"Files: {len(files)}")

# 3. Blobs
entries = []
for path, content in files:
    b64 = base64.b64encode(content).decode()
    blob = req("POST", "/git/blobs", {"content": b64, "encoding": "base64"})
    entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    print(f"  {blob['sha'][:7]} {path}")

# 4. Tree
tree = req("POST", "/git/trees", {"base_tree": head_sha, "tree": entries})
print(f"Tree: {tree['sha'][:7]}")

# 5. Commit
commit = req("POST", "/git/commits", {
    "message": "Complete MSpec — planner→memory wiring, pyproject.toml, README, CI, error handling",
    "tree": tree["sha"],
    "parents": [head_sha],
})
print(f"Commit: {commit['sha'][:7]}")

# 6. Push
req("PATCH", f"/git/refs/heads/{BRANCH}", {"sha": commit["sha"], "force": True})
print(f"✅ Pushed! https://github.com/{REPO}")

import subprocess
from pathlib import Path


class GitManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path

    def add(self, paths: list[str] | None = None):
        cmd = ["git", "-C", str(self.project_path), "add"]
        if paths:
            cmd.extend(paths)
        else:
            cmd.append(".")
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)

    def commit(self, message: str):
        subprocess.run(
            ["git", "-C", str(self.project_path), "commit", "-m", message],
            check=True, capture_output=True, timeout=30,
        )

    def tag(self, tag_name: str):
        subprocess.run(
            ["git", "-C", str(self.project_path), "tag", tag_name],
            check=True, capture_output=True, timeout=30,
        )

    def has_changes(self) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        return bool(result.stdout.strip())

    def get_commits(self, max_count: int = 10) -> list[dict]:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "log", f"--max-count={max_count}", "--format=%H|%s|%ci"],
            capture_output=True, text=True, timeout=10,
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({
                    "hash": parts[0][:7],
                    "message": parts[1],
                    "date": parts[2],
                })
        return commits

    def get_tags(self) -> list[str]:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "tag", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        return [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]

    def get_diff_summary(self, ref: str = "HEAD") -> str:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "diff", "--stat", ref],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()

    def get_branch(self) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "branch", "--show-current"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()

    def checkout_tag(self, tag_name: str):
        subprocess.run(
            ["git", "-C", str(self.project_path), "checkout", tag_name],
            check=True, capture_output=True, timeout=30,
        )

    def get_uncommitted_changes(self) -> list[dict]:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        changes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            status_code = line[:2]
            file = line[2:].lstrip()
            status_map = {
                "M": "modified", "M ": "modified", " M": "modified", "MM": "modified",
                "A": "added", "A ": "added", " A": "added",
                "D": "deleted", "D ": "deleted", " D": "deleted",
                "R": "renamed", "C": "copied",
                "?": "untracked", "??": "untracked",
            }
            changes.append({
                "status": status_map.get(status_code, status_map.get(status_code[0], status_code)),
                "status_code": status_code,
                "file": file,
            })
        return changes

    def get_remotes(self) -> list[dict]:
        result = subprocess.run(
            ["git", "-C", str(self.project_path), "remote", "-v"],
            capture_output=True, text=True, timeout=10,
        )
        remotes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                remotes.append({"name": parts[0], "url": parts[1], "direction": parts[2] if len(parts) > 2 else ""})
        return remotes

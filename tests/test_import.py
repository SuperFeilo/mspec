import sys
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from git.manager import GitManager


def create_git_project():
    tmp = TemporaryDirectory()
    project_path = Path(tmp.name)
    subprocess.run(["git", "init", str(project_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project_path), "config", "user.email", "test@test.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project_path), "config", "user.name", "Test"], check=True, capture_output=True)
    (project_path / "test.txt").write_text("hello")
    subprocess.run(["git", "-C", str(project_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project_path), "commit", "-m", "init"], check=True, capture_output=True)
    return tmp, project_path


def test_get_uncommitted_changes_empty():
    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        changes = gm.get_uncommitted_changes()
        assert changes == []
    finally:
        tmp.cleanup()


def test_get_uncommitted_changes_modified():
    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        (project_path / "test.txt").write_text("modified content")
        changes = gm.get_uncommitted_changes()
        assert len(changes) == 1
        assert changes[0]["status"] == "modified"
        assert changes[0]["file"] == "test.txt"
    finally:
        tmp.cleanup()


def test_get_uncommitted_changes_untracked():
    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        (project_path / "new_file.txt").write_text("untracked")
        changes = gm.get_uncommitted_changes()
        assert len(changes) == 1
        assert changes[0]["status"] == "untracked"
        assert changes[0]["file"] == "new_file.txt"
    finally:
        tmp.cleanup()


def test_get_uncommitted_changes_multiple():
    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        (project_path / "test.txt").write_text("modified")
        (project_path / "added.txt").write_text("new")
        changes = gm.get_uncommitted_changes()
        assert len(changes) == 2
        statuses = {c["status"] for c in changes}
        assert "modified" in statuses
        assert "untracked" in statuses
    finally:
        tmp.cleanup()


def test_get_remotes_empty():
    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        remotes = gm.get_remotes()
        assert remotes == []
    finally:
        tmp.cleanup()


def test_get_remotes():
    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        subprocess.run(
            ["git", "-C", str(project_path), "remote", "add", "origin", "https://github.com/test/repo.git"],
            check=True, capture_output=True,
        )
        remotes = gm.get_remotes()
        assert len(remotes) >= 1
        assert remotes[0]["name"] == "origin"
        assert "https://github.com/test/repo.git" in remotes[0]["url"]
    finally:
        tmp.cleanup()

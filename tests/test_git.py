import sys
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


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


def test_git_init():
    from git.manager import GitManager

    with TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "test_proj"
        project_path.mkdir()
        subprocess.run(["git", "init", str(project_path)], check=True, capture_output=True)

        gm = GitManager(project_path)
        assert gm.project_path == project_path


def test_git_branch():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        branch = gm.get_branch()
        assert branch == "master" or branch == "main"
    finally:
        tmp.cleanup()


def test_git_has_changes_false():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        assert gm.has_changes() is False
    finally:
        tmp.cleanup()


def test_git_has_changes_true():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        (project_path / "new_file.txt").write_text("new content")
        gm = GitManager(project_path)
        assert gm.has_changes() is True
    finally:
        tmp.cleanup()


def test_git_commits():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        commits = gm.get_commits(5)
        assert len(commits) >= 1
        assert commits[0]["message"] == "init"
    finally:
        tmp.cleanup()


def test_git_tags():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        subprocess.run(
            ["git", "-C", str(project_path), "tag", "v0.1"],
            check=True, capture_output=True,
        )
        gm = GitManager(project_path)
        tags = gm.get_tags()
        assert "v0.1" in tags
    finally:
        tmp.cleanup()


def test_get_uncommitted_changes_empty():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        changes = gm.get_uncommitted_changes()
        assert changes == []
    finally:
        tmp.cleanup()


def test_get_uncommitted_changes_modified():
    from git.manager import GitManager

    tmp, project_path = create_git_project()
    try:
        gm = GitManager(project_path)
        (project_path / "test.txt").write_text("modified content")
        changes = gm.get_uncommitted_changes()
        assert len(changes) == 1
        assert changes[0]["file"] == "test.txt"
    finally:
        tmp.cleanup()


def test_get_remotes():
    from git.manager import GitManager

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
    finally:
        tmp.cleanup()

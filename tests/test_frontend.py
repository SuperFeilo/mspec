import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_frontend_app_exists():
    """Verify the React app entry point exists."""
    frontend_src = Path(__file__).parent.parent / "src" / "dashboard" / "frontend" / "src"
    assert (frontend_src / "App.jsx").exists()
    assert (frontend_src / "main.jsx").exists()
    assert (frontend_src / "index.css").exists()


def test_frontend_pages_exist():
    frontend_pages = Path(__file__).parent.parent / "src" / "dashboard" / "frontend" / "src" / "pages"
    expected_pages = [
        "Home.jsx",
        "NewProject.jsx",
        "ProjectDetail.jsx",
        "ProjectSessions.jsx",
        "ProjectMemory.jsx",
        "ProjectGit.jsx",
        "Activity.jsx",
        "Settings.jsx",
    ]
    for page in expected_pages:
        assert (frontend_pages / page).exists(), f"Missing page: {page}"


def test_frontend_components_exist():
    frontend_components = Path(__file__).parent.parent / "src" / "dashboard" / "frontend" / "src" / "components"
    assert (frontend_components / "Layout.jsx").exists()


def test_frontend_hooks_exist():
    hooks_dir = Path(__file__).parent.parent / "src" / "dashboard" / "frontend" / "src" / "hooks"
    assert (hooks_dir / "useTask.js").exists()


def test_frontend_config_files_exist():
    frontend_dir = Path(__file__).parent.parent / "src" / "dashboard" / "frontend"
    config_files = ["index.html", "package.json", "vite.config.js", "tailwind.config.js", "postcss.config.js"]
    for cfg in config_files:
        assert (frontend_dir / cfg).exists(), f"Missing config: {cfg}"

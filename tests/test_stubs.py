"""Tests for the stub-runner module (src/stubs/runner.py).

Tests cover:
- YAML frontmatter parsing
- Stub file parsing (with/without frontmatter)
- Stub listing
- Runner dry-run mode
- Reasonix availability check
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─── Fixtures ───────────────────────────────────────────────────

SAMPLE_STUB_WITH_FM = """---
bp: "BP-01"
name: "test-stub"
title: "Test stub for unit tests"
init: true
tech_stack:
  lang: "Python"
  framework: "pytest"
---

# BP-01: Test Stub

## Context

This is a test stub for unit testing.

## Task

1. Do something
2. Verify it works

## Acceptance Criteria

- [ ] Task completed
"""

SAMPLE_STUB_NO_FM = """# BP-01: Test Stub

This stub has no frontmatter — should still parse.
"""

SAMPLE_STUB_NESTED = """---
bp: "BP-02"
name: "nested"
config:
  timeout: 30
  retry: true
  tags:
    - test
    - unit
items:
  - item1
  - item2
---

# Body content
"""


# ─── Parse Tests ────────────────────────────────────────────────

def test_parse_stub_with_frontmatter():
    from stubs.runner import parse_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "test-stub.md"
        stub_path.write_text(SAMPLE_STUB_WITH_FM)

        result = parse_stub(stub_path)

        assert result["frontmatter"]["bp"] == "BP-01"
        assert result["frontmatter"]["name"] == "test-stub"
        assert result["frontmatter"]["title"] == "Test stub for unit tests"
        assert result["frontmatter"]["init"] is True
        assert result["frontmatter"]["tech_stack"]["lang"] == "Python"
        assert result["frontmatter"]["tech_stack"]["framework"] == "pytest"
        assert "# BP-01: Test Stub" in result["body"]
        assert "## Acceptance Criteria" in result["body"]


def test_parse_stub_without_frontmatter():
    from stubs.runner import parse_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "no-fm.md"
        stub_path.write_text(SAMPLE_STUB_NO_FM)

        result = parse_stub(stub_path)

        assert result["frontmatter"] == {}
        assert "Test Stub" in result["body"]


def test_parse_stub_nested_yaml():
    from stubs.runner import parse_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "nested.md"
        stub_path.write_text(SAMPLE_STUB_NESTED)

        result = parse_stub(stub_path)

        assert result["frontmatter"]["bp"] == "BP-02"
        assert result["frontmatter"]["name"] == "nested"
        # Nested dict
        assert isinstance(result["frontmatter"]["config"], dict)
        assert result["frontmatter"]["config"]["timeout"] == 30
        assert result["frontmatter"]["config"]["retry"] is True
        # Lists
        assert isinstance(result["frontmatter"]["config"]["tags"], list)
        assert "test" in result["frontmatter"]["config"]["tags"]
        assert isinstance(result["frontmatter"]["items"], list)
        assert "item1" in result["frontmatter"]["items"]


def test_parse_stub_file_not_found():
    from stubs.runner import parse_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "does-not-exist.md"
        import pytest
        with pytest.raises(FileNotFoundError):
            parse_stub(stub_path)


# ─── YAML Parser Tests ──────────────────────────────────────────

def test_parse_simple_yaml_scalars():
    from stubs.runner import _parse_simple_yaml

    result = _parse_simple_yaml("""
name: test
count: 42
rate: 3.14
enabled: true
disabled: false
nothing: null
""")
    assert result["name"] == "test"
    assert result["count"] == 42
    assert result["rate"] == 3.14
    assert result["enabled"] is True
    assert result["disabled"] is False
    assert result["nothing"] is None


def test_parse_simple_yaml_quoted():
    from stubs.runner import _parse_simple_yaml

    result = _parse_simple_yaml('title: "Quoted Title"\n')
    assert result["title"] == "Quoted Title"


def test_parse_simple_yaml_nested():
    from stubs.runner import _parse_simple_yaml

    result = _parse_simple_yaml("""
server:
  host: localhost
  port: 8080
  ssl: true
""")
    assert isinstance(result["server"], dict)
    assert result["server"]["host"] == "localhost"
    assert result["server"]["port"] == 8080
    assert result["server"]["ssl"] is True


def test_parse_simple_yaml_list():
    from stubs.runner import _parse_simple_yaml

    result = _parse_simple_yaml("""
items:
  - alpha
  - beta
  - gamma
""")
    assert isinstance(result["items"], list)
    assert result["items"] == ["alpha", "beta", "gamma"]


# ─── List Stubs Tests ──────────────────────────────────────────

def test_list_stubs():
    from stubs.runner import list_stubs

    stubs = list_stubs()
    assert isinstance(stubs, list)
    # Should find BP-01-scaffold.md
    scaffold = [s for s in stubs if s["name"] == "scaffold"]
    assert len(scaffold) >= 1
    assert scaffold[0]["bp"] == "BP-01"
    assert scaffold[0]["init"] is True


def test_list_stubs_skips_template():
    from stubs.runner import list_stubs

    stubs = list_stubs()
    template = [s for s in stubs if s["name"] == "TEMPLATE"]
    assert len(template) == 0


# ─── Runner Tests ──────────────────────────────────────────────

def test_run_stub_dry_run():
    from stubs.runner import run_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "test.md"
        stub_path.write_text(SAMPLE_STUB_WITH_FM)

        result = run_stub(stub_path, dry_run=True)

        assert result["action"] == "dry_run"
        assert result["stub"]["bp"] == "BP-01"
        assert result["stub"]["name"] == "test-stub"
        assert "task_text" in result
        assert "BP-01" in result["task_text"]


def test_run_stub_file_not_found():
    from stubs.runner import run_stub
    import pytest

    with pytest.raises(FileNotFoundError):
        run_stub(Path("/nonexistent/stub.md"))


def test_run_stub_find_reasonix():
    from stubs.runner import find_reasonix

    # Should return None or a string (depends on environment)
    result = find_reasonix()
    # Just verify it doesn't crash — result could be None or a path
    assert result is None or isinstance(result, str)


# ─── Integration: Full Parse + Body Extraction ─────────────────

def test_body_contains_task_content():
    from stubs.runner import parse_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "test.md"
        stub_path.write_text(SAMPLE_STUB_WITH_FM)

        result = parse_stub(stub_path)
        body = result["body"]

        # The body should contain the key sections from the stub
        assert "## Context" in body
        assert "## Task" in body
        assert "## Acceptance Criteria" in body
        assert "Do something" in body


def test_frontmatter_bool_parsing():
    """Verify that 'true'/'false' strings in frontmatter become Python booleans."""
    from stubs.runner import parse_stub

    with TemporaryDirectory() as tmp:
        stub_path = Path(tmp) / "bool-test.md"
        stub_path.write_text("""---
flag_a: true
flag_b: false
value: "true"
---

# Body
""")
        result = parse_stub(stub_path)
        fm = result["frontmatter"]
        assert fm["flag_a"] is True
        assert fm["flag_b"] is False
        assert fm["value"] == "true"  # quoted = string

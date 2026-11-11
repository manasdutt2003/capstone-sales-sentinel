"""Feed sample hook payloads to the hook scripts, exactly as Claude Code does."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def run_hook(script: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def write(path: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}}


@pytest.mark.parametrize("command", [
    "rm -rf build",
    "rm -fr /tmp/x",
    "rm -r -f build",
    "rm -Rf build",
    "rm --recursive --force build",
    "sudo rm -rf /",
    "ls && rm -rf build",
    "git push --force",
    "git push -f origin main",
    "git push --force-with-lease",
    "git push origin +main",
    "echo KEY=dummy > .env",
    "cp secrets.txt .env.local",
    "touch server.pem",
])
def test_guard_blocks_dangerous_bash(command):
    result = run_hook("guard.py", bash(command))
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize("command", [
    "rm build/old.txt",
    "rm -r build",
    "git push origin main",
    "python -m pytest -q",
    "cp template .env.example",
    "cat README.md",
])
def test_guard_allows_safe_bash(command):
    assert run_hook("guard.py", bash(command)).returncode == 0


@pytest.mark.parametrize("path", [
    ".env", "/repo/.env", ".env.local", ".env.production",
    "certs/server.pem", "id_rsa.key", "cert.PFX",
])
def test_guard_blocks_credential_files(path):
    result = run_hook("guard.py", write(path))
    assert result.returncode == 2
    assert "credential file" in result.stderr


@pytest.mark.parametrize("path", [".env.example", "utils.py", "README.md", "keys.py"])
def test_guard_allows_normal_files(path):
    assert run_hook("guard.py", write(path)).returncode == 0


def test_guard_blocks_edit_tool_too():
    payload = {"tool_name": "Edit", "tool_input": {"file_path": ".env"}}
    assert run_hook("guard.py", payload).returncode == 2


def test_guard_fails_closed_on_bad_input():
    result = subprocess.run(
        [sys.executable, str(HOOKS / "guard.py")],
        input="not json", capture_output=True, text=True,
    )
    assert result.returncode == 2


def test_lint_reports_problems_to_claude(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\nx=1\n")
    result = run_hook("lint.py", {"tool_input": {"file_path": str(bad)}})
    assert result.returncode == 2
    assert "F401" in result.stderr  # unused import
    assert "E225" in result.stderr  # missing whitespace around operator


def test_lint_passes_clean_python(tmp_path):
    good = tmp_path / "good.py"
    good.write_text('"""Fine."""\n\nX = 1\n')
    assert run_hook("lint.py", {"tool_input": {"file_path": str(good)}}).returncode == 0


def test_lint_ignores_markdown(tmp_path):
    md = tmp_path / "notes.md"
    md.write_text("import os\nx=1\n")  # would fail flake8 if it were checked
    assert run_hook("lint.py", {"tool_input": {"file_path": str(md)}}).returncode == 0

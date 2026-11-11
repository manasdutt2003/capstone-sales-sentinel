"""PostToolUse lint hook for Claude Code.

After Claude writes or edits a file, run flake8 (max line length 88) on it,
but only if it is a Python file. Any other file type is ignored (exit 0).

If flake8 reports problems, print them on stderr and exit 2. For a
PostToolUse hook, exit 2 cannot undo the edit (the tool already ran), but
Claude Code feeds stderr back to Claude, so Claude finds out and can fix it.
Exit 0 output is not shown to Claude, which is why a plain "print" would
leave Claude unaware of the problems.
"""

import json
import os
import subprocess
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"lint hook could not parse input: {exc}", file=sys.stderr)
        sys.exit(1)  # non-blocking: a broken lint hook should not stop work

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not path.endswith(".py"):
        sys.exit(0)  # leave Markdown, JSON, etc. alone

    if not os.path.isabs(path):
        path = os.path.join(payload.get("cwd") or os.getcwd(), path)
    if not os.path.exists(path):
        sys.exit(0)

    # sys.executable = the same interpreter running this hook, so flake8 is
    # found even when a bare "flake8" is not on PATH (common on Windows).
    result = subprocess.run(
        [sys.executable, "-m", "flake8", "--max-line-length=88", path],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        sys.exit(0)

    output = (result.stdout + result.stderr).strip()
    if "No module named flake8" in output:
        print("lint hook: flake8 is not installed for "
              f"{sys.executable}. Run: python -m pip install flake8",
              file=sys.stderr)
        sys.exit(1)

    print(
        f"flake8 found problems in {path} (max line length 88). "
        f"Fix them before continuing:\n{output}",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

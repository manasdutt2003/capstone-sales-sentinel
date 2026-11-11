#!/usr/bin/env python3
"""PostToolUse feedback after Edit/Write/MultiEdit.

* .py file with a syntax error  -> {"decision": "block"} so Claude fixes it immediately.
* file under src/ or tests/      -> run the fast test suite and attach the tail as additionalContext
                                    (informational: during the tester's red phase failures are expected).
"""
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path

from _common import PROJECT, emit, read_event


def main() -> int:
    event = read_event()
    tin = event.get("tool_input") or {}
    target = tin.get("file_path") or tin.get("notebook_path") or ""
    if not target:
        return 0
    path = Path(target) if Path(target).is_absolute() else PROJECT / target
    try:
        relpath = path.resolve().relative_to(PROJECT).as_posix()
    except ValueError:
        return 0

    if path.suffix == ".py" and path.exists():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            emit({"decision": "block", "reason": f"[sentinel] {relpath} does not compile:\n{exc.msg}"})
            return 0

    if not relpath.startswith(("src/", "tests/")) or os.environ.get("SENTINEL_SKIP_TEST_HOOK") == "1":
        return 0
    env = {**os.environ, "HYPOTHESIS_PROFILE": "mutation"}   # fast profile for the inner loop
    try:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
                              cwd=PROJECT, capture_output=True, text=True, timeout=120, env=env)
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
        status = "GREEN" if proc.returncode == 0 else "RED"
    except subprocess.TimeoutExpired:
        tail, status = "pytest timed out after 120s", "TIMEOUT"
    emit({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                 "additionalContext": f"[sentinel] test suite after editing {relpath}: {status}\n{tail}"}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

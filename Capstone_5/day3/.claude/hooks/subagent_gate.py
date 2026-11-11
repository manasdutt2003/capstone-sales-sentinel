#!/usr/bin/env python3
"""SubagentStop quality gates (declared as `Stop` in each agent's frontmatter).

coder  : may not stop while the suite is red or `python src/main.py` fails on the sample.
tester : may not stop while (a) a SPEC rule is cited by no test, (b) a test function has no
         assertion (deck slide 6: "Any test with no assert?"), or (c) tests fail to collect.
         Red tests are fine for the tester - that's the point of the red phase.

Blocks at most MAX_BLOCKS times in a row per role (counter in .claude/state) so a genuinely stuck
agent hands control back to the orchestrator instead of looping forever.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import time
from pathlib import Path

from _common import PROJECT, STATE, audit, emit, read_event, role_for

MAX_BLOCKS = 5
DEDUPE_SECONDS = 30   # gate is wired in settings.json AND agent frontmatter; reuse one decision per stop


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timed out: {' '.join(cmd)}"


def assert_free_tests() -> list[str]:
    bad = []
    for py in sorted((PROJECT / "tests").glob("test_*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                has = any(isinstance(n, ast.Assert) for n in ast.walk(node)) or any(
                    isinstance(n, ast.Attribute) and n.attr in ("raises", "warns", "fail") for n in ast.walk(node))
                if not has:
                    bad.append(f"{py.name}::{node.name}")
    return bad


def coder_gate() -> list[str]:
    problems = []
    code, out = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "--tb=line", "-rf"])
    if code != 0:
        problems.append("test suite is RED:\n" + "\n".join(out.splitlines()[-25:]))
    code, out = _run([sys.executable, "src/main.py", "--output-dir", "output/gate", "--quiet"])
    if code != 0:
        problems.append(f"`python src/main.py` exited {code}: {out[-500:]}")
    return problems


def tester_gate() -> list[str]:
    problems = []
    code, out = _run([sys.executable, "tools/spec_coverage.py", "--check"])
    if code != 0:
        problems.append("SPEC rules not cited by any test:\n" + out.splitlines()[-1])
    bad = assert_free_tests()
    if bad:
        problems.append("tests without any assertion: " + ", ".join(bad))
    code, out = _run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"])
    if code not in (0, 5):
        problems.append("tests fail to collect:\n" + "\n".join(out.splitlines()[-15:]))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["coder", "tester"])
    args = ap.parse_args()
    event = read_event()
    role = role_for(event, args.role)
    if role not in ("coder", "tester"):
        return 0
    cache = STATE / f"gate_{role}.last.json"
    try:
        last = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - last["ts"] < DEDUPE_SECONDS and last.get("agent") == event.get("agent_id"):
            if last["output"]:
                emit(last["output"])
            return 0
    except (OSError, ValueError, KeyError):
        pass
    decision = _decide(role)
    STATE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"ts": time.time(), "agent": event.get("agent_id"), "output": decision}), encoding="utf-8")
    if decision:
        emit(decision)
    return 0


def _decide(role: str) -> dict | None:
    counter = STATE / f"gate_{role}.count"
    problems = coder_gate() if role == "coder" else tester_gate()
    if not problems:
        counter.unlink(missing_ok=True)
        audit({"hook": "gate", "role": role, "decision": "pass"})
        return None
    STATE.mkdir(parents=True, exist_ok=True)
    n = int(counter.read_text() or 0) + 1 if counter.exists() else 1
    if n > MAX_BLOCKS:
        counter.unlink(missing_ok=True)
        audit({"hook": "gate", "role": role, "decision": "release", "problems": problems})
        return {"systemMessage": f"[sentinel gate] {role} released after {MAX_BLOCKS} blocked stops; "
                                 f"orchestrator must review:\n" + "\n".join(problems)}
    counter.write_text(str(n))
    audit({"hook": "gate", "role": role, "decision": "block", "attempt": n, "problems": problems})
    return {"decision": "block",
            "reason": f"[sentinel gate {n}/{MAX_BLOCKS}] {role} cannot finish yet:\n- " + "\n- ".join(problems)}

if __name__ == "__main__":
    raise SystemExit(main())

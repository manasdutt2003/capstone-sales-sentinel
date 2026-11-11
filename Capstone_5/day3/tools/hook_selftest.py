#!/usr/bin/env python3
"""Dry-run the Claude Code hooks with synthetic events (no Claude Code needed).

Proves the coder/tester boundary before any agent runs:  python tools/hook_selftest.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard_boundaries.py"

CASES = [
    # (description, agent_type, tool, tool_input, expect_allowed)
    ("coder edits src", "coder", "Edit", {"file_path": "src/sentinel/rules.py"}, True),
    ("coder edits a test", "coder", "Edit", {"file_path": "tests/test_pipeline.py"}, False),
    ("coder writes new test file", "coder", "Write", {"file_path": "tests/test_new.py"}, False),
    ("coder edits SPEC", "coder", "Edit", {"file_path": "SPEC.md"}, False),
    ("coder edits its own guard", "coder", "Edit", {"file_path": ".claude/hooks/ownership.json"}, False),
    ("coder updates TO-DO", "coder", "Edit", {"file_path": "TO-DO.md"}, True),
    ("coder sed -i on a test", "coder", "Bash", {"command": "sed -i 's/assert/#/' tests/test_pipeline.py"}, False),
    ("coder redirects into tests", "coder", "Bash", {"command": "echo 'x' > tests/conftest.py"}, False),
    ("coder git checkout tests", "coder", "Bash", {"command": "git checkout -- tests/"}, False),
    ("coder python open(w) on test", "coder", "Bash",
     {"command": "python -c \"open('tests/test_x.py','w').write('')\""}, False),
    ("coder runs pytest", "coder", "Bash", {"command": "python -m pytest -q tests/ 2>&1"}, True),
    ("coder reads tests", "coder", "Bash", {"command": "cat tests/test_pipeline.py | head -50"}, True),
    ("coder silences output", "coder", "Bash", {"command": "python src/main.py > /dev/null"}, True),
    ("tester edits a test", "tester", "Edit", {"file_path": "tests/test_pipeline.py"}, True),
    ("tester edits src", "tester", "Edit", {"file_path": "src/sentinel/pipeline.py"}, False),
    ("tester edits config", "tester", "Write", {"file_path": "config/pipeline.toml"}, False),
    ("tester tee into src", "tester", "Bash", {"command": "cat x | tee src/sentinel/rules.py"}, False),
    ("tester mv a src file", "tester", "Bash", {"command": "mv src/sentinel/rules.py /tmp/"}, False),
    ("tester runs pipeline", "tester", "Bash", {"command": "python src/main.py --output-dir output/t"}, True),
    ("anyone edits input data", "coder", "Edit", {"file_path": "data/sample_sales_data.csv"}, False),
    ("anyone writes .env", "tester", "Write", {"file_path": ".env"}, False),
    ("orchestrator edits src", "", "Edit", {"file_path": "src/sentinel/rules.py"}, False),
    ("orchestrator edits PLAN", "", "Edit", {"file_path": "PLAN.md"}, True),
    ("Explore agent writes", "Explore", "Write", {"file_path": "README.md"}, False),
    ("absolute path into tests", "coder", "Write", {"file_path": str(ROOT / "tests" / "x.py")}, False),
    ("path traversal into tests", "coder", "Write", {"file_path": "src/../tests/x.py"}, False),
]


def run_case(agent: str, tool: str, tin: dict) -> tuple[bool, str]:
    event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tin, "cwd": str(ROOT),
             "session_id": "selftest"}
    if agent:
        event["agent_type"] = agent
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)}
    env.pop("SENTINEL_HUMAN_OVERRIDE", None)
    p = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True,
                       env=env, timeout=30)
    if p.returncode != 0:
        return False, f"hook crashed: {p.stderr}"
    if not p.stdout.strip():
        return True, "allowed"
    out = json.loads(p.stdout)["hookSpecificOutput"]
    return out["permissionDecision"] != "deny", out.get("permissionDecisionReason", "")


def main() -> int:
    failures = 0
    for desc, agent, tool, tin, expect in CASES:
        ok, why = run_case(agent, tool, tin)
        mark = "PASS" if ok == expect else "FAIL"
        failures += mark == "FAIL"
        verdict = "allow" if ok else "deny "
        print(f"[{mark}] {verdict} {desc:<32} {'' if ok else why[:90]}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} guard cases behave as specified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared helpers for the project hooks (stdlib only, Python >= 3.9)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or HOOK_DIR.parents[1]).resolve()
STATE = PROJECT / ".claude" / "state"

ROLE_BY_AGENT = {"coder": "coder", "tester": "tester"}


def read_event() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def role_for(event: dict, cli_role: str | None = None) -> str:
    """--role (from agent frontmatter) > agent_type (hook input inside a subagent) > main session."""
    if cli_role:
        return cli_role
    agent = (event.get("agent_type") or "").strip().lower()
    if not agent:
        return "orchestrator"
    return ROLE_BY_AGENT.get(agent, "readonly")


def audit(record: dict) -> None:
    """Append-only trail of guard/gate decisions (.claude/state/audit.jsonl)."""
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with (STATE / "audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}) + "\n")
    except OSError:
        pass


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()

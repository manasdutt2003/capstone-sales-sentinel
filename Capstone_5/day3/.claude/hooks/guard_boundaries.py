#!/usr/bin/env python3
"""PreToolUse guard: enforce the coder/tester write boundaries from ownership.json.

Wired twice (belt and braces):
  * .claude/settings.json  -> role derived from the hook input's `agent_type`
  * agent frontmatter       -> explicit `--role coder|tester`

Checks Edit / Write / MultiEdit / NotebookEdit targets, and Bash commands that would write to a
forbidden path (redirection, tee, sed -i, mv, cp, rm, git checkout/restore, python -c open(...,'w'), ...).
Denies with a reason Claude can act on ("hand this to the tester agent"). Exit 0 + JSON always.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from fnmatch import fnmatch
from pathlib import Path

from _common import HOOK_DIR, PROJECT, audit, emit, read_event, role_for

FILE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
WRITE_CMDS = {"tee", "mv", "cp", "rm", "rmdir", "touch", "truncate", "dd", "install", "ln", "chmod", "chown",
              "patch", "unlink", "shred"}
INPLACE_FLAG = re.compile(r"^-(i|-in-place)")
GIT_WRITE = {"checkout", "restore", "apply", "stash", "reset", "rm", "mv", "clean", "am", "cherry-pick", "revert"}
PY_WRITE = re.compile(r"open\([^)]*['\"][wax+]|write_text|write_bytes|unlink|rmtree|os\.remove|shutil\.(move|copy)")
HANDOFF = {
    "src/": "src/ belongs to the CODER agent - describe the needed change in TO-DO.md > Hand-off log instead.",
    "tests/": "tests/ belong to the TESTER agent - if a test looks wrong, add a 'Dispute' entry in TO-DO.md > Hand-off log.",
}


def load_rules() -> dict:
    return json.loads((HOOK_DIR / "ownership.json").read_text(encoding="utf-8"))


def rel(path_str: str, cwd: str | None) -> str | None:
    """Project-relative POSIX path, or None if the path is outside the project."""
    p = Path(path_str)
    if not p.is_absolute():
        p = Path(cwd or PROJECT) / p
    try:
        return Path(os.path.normpath(p)).resolve().relative_to(PROJECT).as_posix()
    except ValueError:
        return None


def allowed(role: str, relpath: str | None, rules: dict) -> tuple[bool, str]:
    spec = rules["roles"][role]
    if relpath is None:
        return (role == "orchestrator"), "path is outside the project"
    if any(fnmatch(relpath, g) for g in rules["always_deny"]):
        return False, f"{relpath} is protected for everyone (input data / generated output / secrets)"
    if role == "orchestrator" and os.environ.get("SENTINEL_HUMAN_OVERRIDE") == "1":
        return True, "human override"
    for g in spec["deny"]:
        if fnmatch(relpath, g) or fnmatch(relpath + "/", g):   # "tests" (the dir itself) counts as tests/*
            hint = next((h for prefix, h in HANDOFF.items() if relpath.startswith(prefix)), "")
            return False, f"role '{role}' may not write {relpath}. {spec['why']} {hint}".strip()
    if any(fnmatch(relpath, g) for g in spec["write"]):
        return True, "allowed"
    return False, f"role '{role}' may only write {spec['write']}; {relpath} is not in that list"


def bash_targets(command: str) -> tuple[bool, list[str]]:
    """Return (is_write_command, path-like tokens). Heuristic, errs on the side of 'write'."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    writes = bool(re.search(r"(^|[^0-9&])>{1,2}\s*[^&\s]", command))   # > file, >> file (not 2>&1)
    for i, tok in enumerate(tokens):
        base = os.path.basename(tok)
        if base in WRITE_CMDS:
            writes = True
        if base in ("sed", "perl", "ruby") and any(INPLACE_FLAG.match(t) for t in tokens[i + 1:i + 4]):
            writes = True
        if base == "git" and i + 1 < len(tokens) and tokens[i + 1] in GIT_WRITE:
            writes = True
        if base.startswith("python") and PY_WRITE.search(command):
            writes = True
    paths = [t for t in tokens if "/" in t or t.endswith((".py", ".md", ".toml", ".json", ".csv"))]
    paths += re.findall(r">{1,2}\s*([^\s;&|]+)", command)
    paths += re.findall(r"""['"]([^'"\s]*/[^'"\s]*)['"]""", command)   # quoted paths inside python -c "..."
    return writes, paths


def decide(event: dict, role: str) -> tuple[bool, str]:
    rules = load_rules()
    tool, tin, cwd = event.get("tool_name", ""), event.get("tool_input", {}) or {}, event.get("cwd")
    if tool in FILE_TOOLS:
        return allowed(role, rel(str(tin.get(FILE_TOOLS[tool], "")), cwd), rules)
    if tool == "Bash" and role != "orchestrator":
        cmd = str(tin.get("command", ""))
        writes, paths = bash_targets(cmd)
        if not writes:
            return True, "read-only command"
        for p in paths:
            if p.strip("'\"") in ("/dev/null", "/dev/stdout", "/dev/stderr"):
                continue
            r = rel(p.strip("'\""), cwd)
            if r is not None and not (PROJECT / r).exists() and not (PROJECT / r).parent.exists():
                continue   # not a real path (e.g. a sed expression like s/a/b/)
            ok, why = allowed(role, r, rules)
            if not ok:
                return False, f"Bash command would modify a protected path. {why}"
        return True, "write within role boundary"
    return True, "not a guarded tool"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["coder", "tester", "orchestrator", "readonly"])
    args = ap.parse_args()
    event = read_event()
    role = role_for(event, args.role)
    try:
        ok, why = decide(event, role)
    except Exception as exc:  # noqa: BLE001 - a crashing guard must fail CLOSED for agents, not open
        ok, why = (role == "orchestrator"), f"guard error ({type(exc).__name__}: {exc}); denied to be safe"
    if not ok:
        audit({"hook": "guard", "role": role, "tool": event.get("tool_name"), "decision": "deny", "reason": why,
               "input": {k: str(v)[:200] for k, v in (event.get("tool_input") or {}).items()}})
        emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                     "permissionDecisionReason": f"[sentinel guard] {why}"}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

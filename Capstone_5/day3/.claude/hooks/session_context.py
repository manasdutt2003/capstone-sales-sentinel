#!/usr/bin/env python3
"""SessionStart: inject a compact project status so every session starts from the same contract."""
from __future__ import annotations

import json
import re
import subprocess
import sys

from _common import PROJECT, STATE, emit, read_event


def main() -> int:
    read_event()
    lines = ["[sentinel] Session context - follow CLAUDE.md. Contract: SPEC.md; status: TO-DO.md; how: PLAN.md; "
             "domain playbook: .claude/skills/sales-data-cleaning/SKILL.md."]
    spec = (PROJECT / "SPEC.md").read_text(encoding="utf-8") if (PROJECT / "SPEC.md").exists() else ""
    if m := re.search(r"\*\*Version:\*\*\s*([\d.]+)", spec):
        lines.append(f"SPEC version {m[1]}.")
    todo = (PROJECT / "TO-DO.md").read_text(encoding="utf-8") if (PROJECT / "TO-DO.md").exists() else ""
    open_items = [ln.strip()[6:] for ln in todo.splitlines() if ln.strip().startswith("- [ ]")]
    lines.append(f"Open TO-DO items: {len(open_items)}" + (" -> " + "; ".join(open_items[:5]) if open_items else ""))
    try:
        out = subprocess.run([sys.executable, "tools/spec_coverage.py", "--json"], cwd=PROJECT,
                             capture_output=True, text=True, timeout=30).stdout
        cov = json.loads(out)
        lines.append(f"Spec coverage {cov['percent']}%" + (f"; uncovered: {', '.join(cov['missing'])}" if cov["missing"] else ""))
    except Exception:  # noqa: BLE001 - context is best-effort
        pass
    audit_file = STATE / "audit.jsonl"
    if audit_file.exists():
        denies = sum(1 for ln in audit_file.read_text(encoding="utf-8").splitlines() if '"deny"' in ln)
        lines.append(f"Guard denials so far: {denies} (see .claude/state/audit.jsonl).")
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Spec traceability: every rule ID defined in SPEC.md must be cited by at least one test.

Rule definitions are bold IDs in SPEC.md bullets, e.g. ``- **R-DUP-03 — Content duplicate**``.
Tests cite rules as ``R-DUP-03`` (docstrings/comments) or ``R_DUP_03`` (test names).

  python tools/spec_coverage.py            # table
  python tools/spec_coverage.py --check    # exit 1 if any rule is uncovered (used by tester's SubagentStop hook)
  python tools/spec_coverage.py --json     # machine-readable (used by the MCP server)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_DEF = re.compile(r"\*\*(R-[A-Z]+-\d{2})\s*[—–-]\s*([^*]+?)\.?\*\*")
RULE_REF = re.compile(r"\bR[-_]([A-Z]+)[-_](\d{2})\b")


def spec_rules(spec: Path = ROOT / "SPEC.md") -> dict[str, str]:
    text = spec.read_text(encoding="utf-8")
    rules: dict[str, str] = {}
    for m in RULE_DEF.finditer(text):
        rules.setdefault(m[1], m[2].strip())
    # bare bold IDs without a title, e.g. "- **R-TXN-01** — ..."
    for m in re.finditer(r"\*\*(R-[A-Z]+-\d{2})\*\*", text):
        rules.setdefault(m[1], "")
    return dict(sorted(rules.items()))


def test_refs(tests_dir: Path = ROOT / "tests") -> dict[str, set[str]]:
    refs: dict[str, set[str]] = defaultdict(set)
    for py in sorted(tests_dir.rglob("test_*.py")):
        for m in RULE_REF.finditer(py.read_text(encoding="utf-8")):
            refs[f"R-{m[1]}-{m[2]}"].add(py.name)
    return refs


def coverage() -> dict:
    rules, refs = spec_rules(), test_refs()
    covered = {r: sorted(refs[r]) for r in rules if r in refs}
    missing = [r for r in rules if r not in refs]
    unknown = sorted(r for r in refs if r not in rules)
    pct = 100.0 * len(covered) / len(rules) if rules else 0.0
    return {"rules": rules, "covered": covered, "missing": missing, "unknown_refs": unknown, "percent": round(pct, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cov = coverage()
    if a.json:
        print(json.dumps(cov, indent=2))
    else:
        for rule, title in cov["rules"].items():
            files = ", ".join(cov["covered"].get(rule, [])) or "-- NOT COVERED --"
            print(f"{rule:<12} {title[:38]:<38} {files}")
        print(f"\nspec coverage: {len(cov['covered'])}/{len(cov['rules'])} rules ({cov['percent']}%)")
        if cov["unknown_refs"]:
            print("tests cite unknown rule IDs:", ", ".join(cov["unknown_refs"]))
    if a.check and (cov["missing"] or cov["unknown_refs"]):
        print("UNCOVERED: " + ", ".join(cov["missing"] + cov["unknown_refs"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

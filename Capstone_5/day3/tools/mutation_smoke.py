#!/usr/bin/env python3
"""Zero-dependency mutation testing ("break the code on purpose — do the tests notice?").

For each mutable site in src/sentinel/*.py we flip ONE operator (e.g. ``>`` -> ``>=``,
``and`` -> ``or``, ``+`` -> ``-``, ``True`` -> ``False``), run the test suite against a
throw-away copy of the project, and count the mutant as KILLED (tests failed) or SURVIVED.
Survivors = weak tests -> each becomes a tester task in TO-DO.md.

The real src/ is never modified (it runs in a temp copy), so this tool respects the
coder/tester boundary. Use mutmut for a full run; this is the fast, portable smoke test.

  python tools/mutation_smoke.py                 # all modules
  python tools/mutation_smoke.py --module rules  # one module
  python tools/mutation_smoke.py --max 40        # cap mutants
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWAP_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
            ast.In: ast.NotIn, ast.NotIn: ast.In}
SWAP_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
SWAP_BOOL = {ast.And: ast.Or, ast.Or: ast.And}


class Sites(ast.NodeVisitor):
    def __init__(self):
        self.sites: list[tuple[str, int, int]] = []   # (kind, lineno, index-in-walk)
        self.i = 0

    def generic_visit(self, node):
        kind = None
        if isinstance(node, ast.Compare) and type(node.ops[0]) in SWAP_CMP:
            kind = f"{type(node.ops[0]).__name__}->{SWAP_CMP[type(node.ops[0])].__name__}"
        elif isinstance(node, ast.BinOp) and type(node.op) in SWAP_BIN:
            kind = f"{type(node.op).__name__}->{SWAP_BIN[type(node.op)].__name__}"
        elif isinstance(node, ast.BoolOp) and type(node.op) in SWAP_BOOL:
            kind = f"{type(node.op).__name__}->{SWAP_BOOL[type(node.op)].__name__}"
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            kind = f"{node.value}->{not node.value}"
        if kind:
            self.sites.append((kind, getattr(node, "lineno", 0), self.i))
        self.i += 1
        super().generic_visit(node)


class Mutator(ast.NodeTransformer):
    def __init__(self, target: int):
        self.target, self.i = target, 0

    def generic_visit(self, node):
        if self.i == self.target:
            if isinstance(node, ast.Compare):
                node.ops[0] = SWAP_CMP[type(node.ops[0])]()
            elif isinstance(node, ast.BinOp):
                node.op = SWAP_BIN[type(node.op)]()
            elif isinstance(node, ast.BoolOp):
                node.op = SWAP_BOOL[type(node.op)]()
            elif isinstance(node, ast.Constant):
                node.value = not node.value
        self.i += 1
        return super().generic_visit(node)


def run_tests(workdir: Path) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"]
    if _has_cov():
        cmd.append("--no-cov")
    env = {**os.environ, "HYPOTHESIS_PROFILE": "mutation"}
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=600, env=env)
    return proc.returncode == 0


def _has_cov() -> bool:
    try:
        import pytest_cov  # noqa: F401
        return True
    except ImportError:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AST mutation smoke test")
    ap.add_argument("--module", help="only mutate src/sentinel/<module>.py")
    ap.add_argument("--max", type=int, default=0, help="max mutants per module (0 = all)")
    ap.add_argument("--fail-under", type=float, default=0.0, help="exit 1 if mutation score below this %")
    a = ap.parse_args(argv)

    modules = sorted((ROOT / "src" / "sentinel").glob("*.py"))
    if a.module:
        modules = [m for m in modules if m.stem == a.module]
    killed = survived = 0
    survivors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mutants-") as tmp:
        work = Path(tmp) / "proj"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("output", ".git", "__pycache__", ".coverage*",
                                                                 ".hypothesis", "*.zip"))
        if not run_tests(work):
            print("baseline test suite is RED - fix that first", file=sys.stderr)
            return 2
        for mod in modules:
            src = mod.read_text(encoding="utf-8")
            tree = ast.parse(src)
            finder = Sites()
            finder.visit(tree)
            sites = finder.sites[: a.max] if a.max else finder.sites
            target_file = work / "src" / "sentinel" / mod.name
            for kind, line, idx in sites:
                mutated = Mutator(idx).visit(ast.parse(src))
                target_file.write_text(ast.unparse(ast.fix_missing_locations(mutated)), encoding="utf-8")
                ok = run_tests(work)
                tag = f"{mod.name}:{line} {kind}"
                if ok:
                    survived += 1
                    survivors.append(tag)
                    print(f"  SURVIVED  {tag}")
                else:
                    killed += 1
                    print(f"  killed    {tag}")
            target_file.write_text(src, encoding="utf-8")
    total = killed + survived
    score = 100.0 * killed / total if total else 100.0
    print(f"\nmutation score: {killed}/{total} killed ({score:.1f}%)")
    if survivors:
        print("survivors -> add tests (tester task):")
        for s in survivors:
            print("  -", s)
    return 1 if score < a.fail_under else 0


if __name__ == "__main__":
    sys.exit(main())

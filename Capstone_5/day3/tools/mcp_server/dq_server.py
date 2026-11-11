#!/usr/bin/env python3
"""`sales-dq` MCP server — gives the coder and tester agents data-quality superpowers.

Tools (all read-only except run_pipeline, which writes only under <project>/output/):
  profile_csv(path)        column-level profile: nulls, date "shapes", non-numeric amounts,
                           value counts, content-duplicate clusters -> edge-case discovery
  run_pipeline(...)        run `python src/main.py` and return exit code + report
  explain_row(id|line)     fate, reason codes and note of one row from the latest ledger
  quarantine_summary()     counts of quarantine reasons from the latest run
  spec_rules()             every rule ID + title from SPEC.md
  spec_coverage()          which rule IDs are / are not cited by tests

Registered in .mcp.json; run manually with:  python tools/mcp_server/dq_server.py
Requires:  pip install "mcp>=1.2"   (works with mcp 1.x FastMCP and 2.x MCPServer)
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
OUTPUT = ROOT / "output"
sys.path.insert(0, str(ROOT / "tools"))
import spec_coverage  # noqa: E402

server = _Server("sales-dq", instructions=(
    "Data-quality tools for the Sales Sentinel project. Use profile_csv to discover edge cases "
    "before writing tests, run_pipeline to execute the cleaner, explain_row to see why a row got "
    "its fate, and spec_coverage to find SPEC rules no test cites yet."))


def _safe(path: str | None, default: Path) -> Path:
    """Resolve a user path and refuse anything outside the project (no reading ~/.ssh via MCP)."""
    p = default if not path else (Path(path) if Path(path).is_absolute() else ROOT / path)
    p = p.resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"path must be inside the project: {p}")
    return p


def _shape(value: str) -> str:
    """'2026-10-21' -> '9999-99-99', 'abc' -> 'aaa': groups formats without listing every value."""
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", value.strip())) or "<empty>"


@server.tool()
def profile_csv(path: str = "data/sample_sales_data.csv", top: int = 10) -> str:
    """Profile a sales CSV: per-column null counts, value 'shapes', non-numeric amounts, store/category
    counts, and content-duplicate clusters. Use this to discover edge cases before writing tests."""
    p = _safe(path, ROOT / "data" / "sample_sales_data.csv")
    text = p.read_bytes().decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text, newline=""))
    header = [h.strip().lower() for h in next(reader, [])]
    rows = [r for r in reader if r and any(c.strip() for c in r)]
    out: dict = {"file": str(p.relative_to(ROOT)), "rows": len(rows), "header": header, "columns": {}}
    ragged = sum(1 for r in rows if len(r) != len(header))
    out["ragged_rows"] = ragged
    cols = {h: [r[i] if i < len(r) else "" for r in rows] for i, h in enumerate(header)}
    for name, values in cols.items():
        info = {
            "empty": sum(1 for v in values if not v.strip()),
            "distinct": len(set(values)),
            "shapes": Counter(_shape(v) for v in values).most_common(top),
        }
        if name == "amount":
            bad = [v for v in values if v.strip() and not re.fullmatch(r"[+-]?\d+(\.\d+)?", v.strip())]
            neg = [v for v in values if re.fullmatch(r"-\d+(\.\d+)?", v.strip())]
            zero = [v for v in values if re.fullmatch(r"[+-]?0+(\.0+)?", v.strip())]
            info |= {"non_numeric": bad, "negative": neg, "zero": zero}
        if name in ("store_id", "category"):
            info["values"] = Counter(values).most_common(top)
        if name == "transaction_id":
            dup = [k for k, c in Counter(values).items() if c > 1]
            info["repeated_ids"] = dup[:top]
        out["columns"][name] = info
    if all(c in cols for c in ("date", "amount", "store_id", "category")):
        clusters: dict[tuple, list[int]] = defaultdict(list)
        for i, key in enumerate(zip(cols["date"], cols["amount"], cols["store_id"], cols["category"])):
            if key[1].strip():
                clusters[key].append(i + 2)
        big = sorted(((len(v), k, v[:5]) for k, v in clusters.items() if len(v) > 1), reverse=True)
        out["content_duplicate_clusters"] = [
            {"size": n, "key": list(k), "first_lines": lines} for n, k, lines in big[:top]]
    return json.dumps(out, indent=2)


@server.tool()
def run_pipeline(input_path: str = "", dedupe_policy: str = "", missing_strategy: str = "",
                 business_date: str = "") -> str:
    """Run `python src/main.py` (output goes to <project>/output/mcp_run). Returns exit code, stdout,
    stderr and the data_quality_report.txt text. Optional overrides mirror the CLI flags."""
    out_dir = OUTPUT / "mcp_run"
    cmd = [sys.executable, str(ROOT / "src" / "main.py"), "--output-dir", str(out_dir)]
    if input_path:
        cmd += ["--input", str(_safe(input_path, ROOT))]
    if dedupe_policy in ("content", "id"):
        cmd += ["--dedupe-policy", dedupe_policy]
    if missing_strategy in ("group_median", "quarantine"):
        cmd += ["--missing-strategy", missing_strategy]
    if business_date:
        cmd += ["--business-date", business_date]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    report = out_dir / "data_quality_report.txt"
    return json.dumps({
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-2000:],
        "report": report.read_text(encoding="utf-8") if report.exists() and proc.returncode in (0, 3) else None,
    }, indent=2)


def _latest_ledger() -> Path:
    candidates = [p for p in OUTPUT.rglob("row_ledger.csv")]
    if not candidates:
        raise FileNotFoundError("no row_ledger.csv yet - call run_pipeline first")
    return max(candidates, key=lambda p: p.stat().st_mtime)


@server.tool()
def explain_row(transaction_id: str = "", line_no: int = 0) -> str:
    """Explain what happened to one input row (by transaction_id or physical line number) using the most
    recent row_ledger.csv: fate, every reason code (with description), duplicate_of and note."""
    sys.path.insert(0, str(ROOT / "src"))
    from sentinel.codes import DESCRIPTIONS

    ledger = _latest_ledger()
    with ledger.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh)
                if (transaction_id and r["transaction_id"].strip() == transaction_id.strip())
                or (line_no and int(r["line_no"]) == line_no)]
    if not rows:
        return json.dumps({"found": False, "ledger": str(ledger.relative_to(ROOT))})
    for r in rows:
        r["explained_codes"] = {c: DESCRIPTIONS.get(c, "?") for c in r["codes"].split("|") if c}
    return json.dumps({"found": True, "ledger": str(ledger.relative_to(ROOT)), "rows": rows}, indent=2)


@server.tool()
def quarantine_summary() -> str:
    """Counts of quarantine reason codes (and example lines) from the most recent run."""
    q = _latest_ledger().parent / "quarantine.csv"
    with q.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for code in r["reason_codes"].split("|"):
            counts[code] += 1
            if len(examples[code]) < 3:
                examples[code].append(f"line {r['line_no']}: {r['amount']!r} {r['date']!r}")
    return json.dumps({"total": len(rows), "by_code": counts.most_common(), "examples": examples}, indent=2)


@server.tool()
def spec_rules() -> str:
    """List every rule ID and title defined in SPEC.md (the contract both agents work from)."""
    return json.dumps(spec_coverage.spec_rules(), indent=2)


@server.tool()
def spec_coverage_report() -> str:
    """Which SPEC rule IDs are cited by at least one test, which are missing, and unknown IDs cited."""
    return json.dumps(spec_coverage.coverage(), indent=2)


if __name__ == "__main__":
    server.run()

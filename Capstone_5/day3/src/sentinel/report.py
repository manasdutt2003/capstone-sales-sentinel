"""Outputs: clean CSV, quarantine, ledger, text report, manifest (SPEC R-OUT-01 … 06)."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from . import __version__
from . import codes as C
from .ingest import REQUIRED_COLUMNS, IngestResult
from .pipeline import PipelineResult
from .rules import format_amount
from .scoring import Money, Score

CLEAN_FILE = "clean_sales.csv"
QUARANTINE_FILE = "quarantine.csv"
LEDGER_FILE = "row_ledger.csv"
REPORT_FILE = "data_quality_report.txt"
MANIFEST_FILE = "run_manifest.json"


# ----------------------------------------------------------------------- atomic write (R-OUT-06)
def atomic_write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return hashlib.sha256(data).hexdigest()


def _csv_text(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


# ----------------------------------------------------------------------- CSV builders
def clean_csv(result: PipelineResult) -> str:
    rows = [[r.clean_row()[c] for c in REQUIRED_COLUMNS] for r in result.kept]
    return _csv_text(list(REQUIRED_COLUMNS), rows)


def quarantine_csv(result: PipelineResult) -> str:
    rows = [
        [str(r.line_no)] + [r.raw.get(c, "") for c in REQUIRED_COLUMNS] + ["|".join(r.errors)]
        for r in result.quarantined
    ]
    return _csv_text(["line_no", *REQUIRED_COLUMNS, "reason_codes"], rows)


def ledger_csv(result: PipelineResult) -> str:
    rows = [
        [str(r.line_no), r.raw.get("transaction_id", ""), r.fate or "", "|".join(r.codes()), r.duplicate_of or "", r.note]
        for r in result.records
    ]
    return _csv_text(["line_no", "transaction_id", "fate", "codes", "duplicate_of", "note"], rows)


# ----------------------------------------------------------------------- text report
def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}%" if whole else "  n/a"


def render_report(
    result: PipelineResult, ingest: IngestResult, sc: Score, mo: Money, input_path: Path, run_at: str
) -> str:
    n = len(result.records)
    kept, dup, quar = result.kept, result.duplicates, result.quarantined
    imputed, fixed = result.imputed, result.fixed
    clean_untouched = result.by_fate(C.KEPT_CLEAN)
    bd = result.business_date.isoformat() if result.business_date else "n/a"
    L: list[str] = []
    add = L.append
    bar = "=" * 66

    add(bar)
    add(f" SALES DATA QUALITY REPORT  -  sales-sentinel v{__version__}")
    add(bar)
    add(f"Input file     : {input_path.name}  (sha256 {ingest.sha256[:12]}..., {ingest.encoding})")
    add(f"Business date  : {bd}  [{result.business_date_source}]")
    add(f"Policies       : dedupe={result.config.dedupe_policy}, missing_amount={result.config.missing_strategy}, "
        f"date_order={result.config.date_order}")
    add(f"Run at (UTC)   : {run_at}")
    add("")
    add("--- REQUIRED SUMMARY " + "-" * 45)
    add(f"Rows processed: {n}")
    add(f"Rows removed: {len(dup)} (duplicates)")
    add(f"Nulls filled: {len(imputed)}")
    add(f"Invalid entries fixed/skipped: {len(fixed) + len(quar)} (fixed {len(fixed)}, skipped {len(quar)})")
    add(f"Overall data quality score: {sc.overall:.1f}/100 ({sc.grade})")
    add("")
    add("--- ROW RECONCILIATION (every row has exactly one fate) " + "-" * 10)
    ok = len(kept) + len(dup) + len(quar) == n
    add(f"  {n} processed = {len(kept)} kept + {len(dup)} duplicates + {len(quar)} quarantined   "
        f"[{'BALANCED' if ok else 'NOT BALANCED'}]")
    add(f"  kept breakdown : clean {len(clean_untouched)} | repaired {len(result.by_fate(C.KEPT_REPAIRED))} "
        f"| imputed {len(result.by_fate(C.KEPT_IMPUTED))}")
    if ingest.blank_lines:
        add(f"  blank lines skipped (not rows): {ingest.blank_lines}")
    if ingest.extra_columns:
        add(f"  extra columns ignored: {', '.join(ingest.extra_columns)}")
    add("")
    add("--- SCORE BREAKDOWN (raw input health, DAMA dimensions) " + "-" * 10)
    w = result.config.weights
    for name in ("completeness", "validity", "consistency", "uniqueness"):
        add(f"  {name:<13} {100 * getattr(sc, name):6.1f}%   weight {w[name]:.2f}")
    add(f"  {'overall':<13} {sc.overall:6.1f}    grade {sc.grade}")
    add("")
    add("--- ISSUES BY CODE " + "-" * 47)
    counts: Counter[str] = Counter()
    for r in result.records:
        counts.update(r.codes())
    groups = (("errors -> quarantined", C.ERRORS), ("duplicates -> removed", C.DUPLICATES),
              ("repairs -> kept", C.REPAIRS), ("warnings -> kept, review", C.WARNINGS))
    for title, family in groups:
        items = sorted((c, k) for c, k in counts.items() if c in family)
        if not items:
            continue
        add(f"  [{title}]")
        for code, k in items:
            add(f"    {code:<22} {k:>4}  {C.DESCRIPTIONS[code]}")
    add("")
    add("--- DUPLICATE CLUSTERS " + "-" * 43)
    if not result.clusters:
        add("  none")
    by_id = {r.txn_id: r for r in result.records if r.txn_id}
    for cl in sorted(result.clusters, key=lambda c: (-c.size, c.survivor_id)):
        d, amt, store, cat = cl.key
        removed_rev = sum((by_id[i].amount for i in cl.removed_ids), start=type(amt)("0"))
        tag = "  <-- suspected POS replay burst" if cl.size >= result.config.burst_threshold else ""
        add(f"  {d} {format_amount(amt):>9} {store} {cat:<12} x{cl.size:<3} kept id {cl.survivor_id}, "
            f"removed revenue {format_amount(removed_rev)}{tag}")
    add("")
    add("--- MONEY RECONCILIATION " + "-" * 41)
    add(f"  raw parseable total     {format_amount(mo.raw_total):>12}")
    add(f"  - duplicates removed    {format_amount(mo.duplicate_total):>12}")
    add(f"  - quarantined           {format_amount(mo.quarantined_total):>12}")
    add(f"  + imputed (estimated)   {format_amount(mo.imputed_total):>12}")
    add(f"  = clean total           {format_amount(mo.clean_total):>12}   [{'BALANCED' if mo.balanced else 'NOT BALANCED'}]")
    observed = mo.clean_total - mo.imputed_total
    add(f"  observed (non-imputed) revenue in clean file: {format_amount(observed)}")
    add("")
    add("--- WARNINGS (rows kept, human review suggested) " + "-" * 17)
    warned = [r for r in kept if r.warnings]
    if not warned:
        add("  none")
    for r in warned:
        add(f"  line {r.line_no:<4} id {r.txn_id:<6} {'|'.join(r.warnings):<24} {r.note}")
    add("")
    add("--- QUARANTINED ROWS (sent back to source) " + "-" * 23)
    if not quar:
        add("  none")
    for r in quar:
        raw = ",".join(r.raw.get(c, "") for c in REQUIRED_COLUMNS)
        add(f"  line {r.line_no:<4} {'|'.join(r.errors):<28} raw: {raw}")
    add("")
    add("--- OUTPUT CONFIDENCE " + "-" * 44)
    add(f"  yield (kept / processed)      {_pct(len(kept), n)}")
    add(f"  kept rows untouched           {_pct(len(clean_untouched), len(kept))}")
    add(f"  kept rows repaired (format)   {_pct(len(result.by_fate(C.KEPT_REPAIRED)), len(kept))}")
    add(f"  kept rows with imputed amount {_pct(len(imputed), len(kept))}")
    add(f"  quarantine rate               {_pct(len(quar), n)}")
    add("")
    add("--- FILES " + "-" * 56)
    for f, desc in ((CLEAN_FILE, "only valid, cleaned rows"), (QUARANTINE_FILE, "rejected rows, raw values + reasons"),
                    (LEDGER_FILE, "fate of every input row"), (REPORT_FILE, "this report"),
                    (MANIFEST_FILE, "hashes + effective config for reproducibility")):
        add(f"  {f:<26} {desc}")
    add(bar)
    return "\n".join(L) + "\n"


def write_outputs(
    out_dir: Path, result: PipelineResult, ingest: IngestResult, sc: Score, mo: Money, input_path: Path
) -> dict[str, str]:
    run_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    hashes = {
        CLEAN_FILE: atomic_write(out_dir / CLEAN_FILE, clean_csv(result)),
        QUARANTINE_FILE: atomic_write(out_dir / QUARANTINE_FILE, quarantine_csv(result)),
        LEDGER_FILE: atomic_write(out_dir / LEDGER_FILE, ledger_csv(result)),
        REPORT_FILE: atomic_write(out_dir / REPORT_FILE, render_report(result, ingest, sc, mo, input_path, run_at)),
    }
    manifest = {
        "tool": "sales-sentinel",
        "version": __version__,
        "run_at_utc": run_at,
        "input": {"name": input_path.name, "sha256": ingest.sha256, "encoding": ingest.encoding},
        "config": {
            "path": result.config.source_path.name if result.config.source_path else None,
            "sha256": result.config.source_sha256 or None,
            "effective": result.config.effective(),
        },
        "business_date": result.business_date.isoformat() if result.business_date else None,
        "counts": {
            "processed": len(result.records),
            "kept": len(result.kept),
            "duplicates_removed": len(result.duplicates),
            "quarantined": len(result.quarantined),
            "nulls_filled": len(result.imputed),
            "fixed": len(result.fixed),
        },
        "score": {"overall": sc.overall, "grade": sc.grade},
        "money": {"raw_total": str(mo.raw_total), "clean_total": str(mo.clean_total), "balanced": mo.balanced},
        "outputs_sha256": hashes,
    }
    hashes[MANIFEST_FILE] = atomic_write(out_dir / MANIFEST_FILE, json.dumps(manifest, indent=2) + "\n")
    return hashes

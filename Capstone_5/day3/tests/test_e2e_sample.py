"""Test module 4/5 — end-to-end on the real sample file (SPEC §4 golden numbers).
Covers: R-OUT-01 R-OUT-02 R-OUT-03 R-OUT-04 R-OUT-05 R-OUT-06 R-INV-03 R-INV-04
        R-DUP-05 R-SCORE-01 R-SCORE-02 R-SCORE-03 R-OPS-03
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from conftest import HEADER, ROOT, SAMPLE, read_csv_rows, run_main
from sentinel.rules import normalize_category, normalize_store, parse_amount, parse_date, parse_txn_id


def report(out):
    return (out / "data_quality_report.txt").read_text(encoding="utf-8")


# --- golden numbers ------------------------------------------------------------------------------
def test_R_OUT_04_required_report_lines_and_golden_numbers(sample_run):
    proc, out = sample_run
    assert proc.returncode == 0, proc.stderr
    text = report(out)
    assert "Rows processed: 200\n" in text
    assert "Rows removed: 70 (duplicates)\n" in text
    assert "Nulls filled: 32\n" in text
    assert "Invalid entries fixed/skipped: 11 (fixed 5, skipped 6)\n" in text
    assert re.search(r"^Overall data quality score: \d{1,3}\.\d/100 \([A-F]\)$", text, re.M)


def test_R_OUT_02_quarantine_has_raw_values_and_reasons(sample_run):
    _, out = sample_run
    q = {r["transaction_id"]: r for r in read_csv_rows(out / "quarantine.csv")}
    assert set(q) == {"10", "13", "21", "38", "44", "68"}
    assert q["10"]["amount"] == "abc" and q["10"]["reason_codes"] == "BAD_AMOUNT"
    assert q["13"]["reason_codes"] == "NEGATIVE_AMOUNT"
    assert q["21"]["date"] == "invalid" and q["21"]["reason_codes"] == "BAD_DATE"
    assert q["68"]["amount"] == "0" and q["68"]["reason_codes"] == "ZERO_AMOUNT"


def test_R_OUT_01_clean_file_contract(sample_run):
    _, out = sample_run
    text = (out / "clean_sales.csv").read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(HEADER)
    rows = read_csv_rows(out / "clean_sales.csv")
    assert len(rows) == 124
    assert rows[0] == {"transaction_id": "1", "date": "2026-10-21", "amount": "150.50",
                       "store_id": "S001", "category": "Electronics"}
    ids = [int(r["transaction_id"]) for r in rows]
    assert ids == sorted(ids), "input order preserved"
    for r in rows:   # independently re-validate every output cell
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"]) and re.fullmatch(r"\d+\.\d{2}", r["amount"])
        for res in (parse_txn_id(r["transaction_id"]), parse_date(r["date"]), parse_amount(r["amount"]),
                    normalize_store(r["store_id"]), normalize_category(r["category"])):
            assert res.errors == [] and res.repairs == []
    by = {r["transaction_id"]: r for r in rows}
    assert by["4"]["date"] == "2026-10-21" and by["71"]["date"] == "2026-10-21"   # reformatted dates
    assert by["3"]["amount"] == "3500.00", "outliers are kept"
    assert "8" not in by, "content duplicate of id 1 removed"


def test_R_OUT_03_ledger_has_one_line_per_input_row(sample_run):
    _, out = sample_run
    ledger = read_csv_rows(out / "row_ledger.csv")
    assert len(ledger) == 200
    assert [int(r["line_no"]) for r in ledger] == list(range(2, 202))
    f = Counter(r["fate"] for r in ledger)
    assert f == {"KEPT_CLEAN": 87, "KEPT_REPAIRED": 5, "KEPT_IMPUTED": 32,
                 "REMOVED_DUPLICATE": 70, "QUARANTINED": 6}
    row8 = next(r for r in ledger if r["transaction_id"] == "8")
    assert row8["duplicate_of"] == "1" and "DUPLICATE_CONTENT" in row8["codes"]
    row3 = next(r for r in ledger if r["transaction_id"] == "3")
    assert "OUTLIER_AMOUNT" in row3["codes"]


def test_R_OUT_05_manifest_hashes_match_files(sample_run):
    _, out = sample_run
    m = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert m["input"]["sha256"] == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    for name, digest in m["outputs_sha256"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert m["counts"]["processed"] == 200 and m["business_date"] == "2026-10-21"


def test_R_OUT_06_no_temp_files_left_behind(sample_run):
    _, out = sample_run
    assert not [p for p in out.iterdir() if p.name.endswith(".tmp")]


# --- R-DUP-05, R-SCORE ----------------------------------------------------------------------------
def test_R_DUP_05_replay_bursts_reported(sample_run):
    text = report(sample_run[1])
    bursts = [ln for ln in text.splitlines() if "suspected POS replay burst" in ln]
    assert len(bursts) == 3 and "x53" in bursts[0]


def test_R_SCORE_01_02_03_breakdown_confidence_and_money_balance(sample_run):
    text = report(sample_run[1])
    for dim in ("completeness", "validity", "consistency", "uniqueness"):
        assert re.search(rf"^\s+{dim}\s+\d+\.\d%", text, re.M), dim
    assert re.search(r"uniqueness\s+65\.0%", text)          # 70 of 200 rows are duplicates
    assert "yield (kept / processed)       62.0%" in text
    assert re.search(r"= clean total\s+[\d.]+\s+\[BALANCED\]", text)
    assert "124 kept + 70 duplicates + 6 quarantined   [BALANCED]" in text


def test_R_SCORE_01_exact_dimensions_hand_computed_from_sample():
    """Hand count on the sample: 1000 required cells, 32 empty amounts; 6 invalid non-empty cells
    (abc, xyz, -50.00, 0.00, 0, 'invalid'); 5 valid-but-non-ISO dates; 70 duplicate rows."""
    from sentinel.config import Config
    from sentinel.ingest import read_csv
    from sentinel.pipeline import run_pipeline
    from sentinel.scoring import score

    sc = score(run_pipeline(read_csv(SAMPLE).rows, Config().validate()))
    assert sc.completeness == 968 / 1000
    assert sc.validity == 962 / 968
    assert sc.consistency == 957 / 962
    assert sc.uniqueness == 130 / 200
    expected = 100 * (0.30 * 968 / 1000 + 0.30 * 962 / 968 + 0.15 * 957 / 962 + 0.25 * 130 / 200)
    assert sc.overall == round(expected, 1) == 90.0 and sc.grade == "A"


def test_R_SCORE_01_weights_change_the_score_and_grades_have_hard_edges():
    from sentinel.config import Config
    from sentinel.ingest import read_csv
    from sentinel.pipeline import run_pipeline
    from sentinel.scoring import grade_for, score

    only_unique = Config(weights={"completeness": 0, "validity": 0, "consistency": 0, "uniqueness": 1}).validate()
    assert score(run_pipeline(read_csv(SAMPLE).rows, only_unique)).overall == 65.0
    assert [grade_for(x) for x in (100, 90, 89.9, 80, 79.9, 70, 60, 59.9, 0)] == \
        ["A", "A", "B", "B", "C", "C", "D", "F", "F"]


# --- R-INV-03 / R-INV-04 ----------------------------------------------------------------------------
def test_R_INV_04_determinism(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_main("--input", str(SAMPLE), "--output-dir", str(a)).returncode == 0
    assert run_main("--input", str(SAMPLE), "--output-dir", str(b)).returncode == 0
    for f in ("clean_sales.csv", "quarantine.csv", "row_ledger.csv"):
        assert (a / f).read_bytes() == (b / f).read_bytes(), f


def test_R_INV_03_fixed_point_on_own_output(sample_run, tmp_path):
    _, out = sample_run
    collided = {r["transaction_id"] for r in read_csv_rows(out / "row_ledger.csv")
                if "IMPUTED_KEY_COLLISION" in r["codes"]}
    second = tmp_path / "second"
    proc = run_main("--input", str(out / "clean_sales.csv"), "--output-dir", str(second),
                    "--business-date", "2026-10-21")
    assert proc.returncode == 0, proc.stderr
    ledger2 = read_csv_rows(second / "row_ledger.csv")
    assert not [r for r in ledger2 if r["fate"] == "QUARANTINED"]
    assert not [r for r in ledger2 if r["fate"] == "KEPT_IMPUTED"]
    removed = {r["transaction_id"] for r in ledger2 if r["fate"] == "REMOVED_DUPLICATE"}
    assert removed <= collided, "only documented imputed-key collisions may dedupe on a second pass"
    # with the id policy the second pass is an exact fixed point
    third = tmp_path / "third"
    assert run_main("--input", str(out / "clean_sales.csv"), "--output-dir", str(third),
                    "--business-date", "2026-10-21", "--dedupe-policy", "id").returncode == 0
    assert (third / "clean_sales.csv").read_bytes() == (out / "clean_sales.csv").read_bytes()


# --- R-OPS-03 ------------------------------------------------------------------------------------------
def test_R_OPS_03_no_network_db_or_ml_imports_in_src():
    banned = re.compile(r"^\s*(import|from)\s+(requests|urllib|http|socket|sqlite3|sqlalchemy|sklearn|torch|"
                        r"tensorflow|pandas|numpy)\b", re.M)
    for py in (ROOT / "src").rglob("*.py"):
        assert not banned.search(py.read_text(encoding="utf-8")), py

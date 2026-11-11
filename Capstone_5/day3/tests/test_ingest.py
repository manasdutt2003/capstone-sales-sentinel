"""Test module 1/5 — ingestion, config and exit codes.
Covers: R-ING-01 R-ING-02 R-ING-03 R-ING-04 R-ING-05 R-ING-06 R-OPS-01 R-OPS-02 R-OPS-04
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from conftest import HEADER, ROOT, SAMPLE, make_csv, read_csv_rows, run_main
from sentinel.ingest import IngestError, parse_bytes, read_csv

GOOD = ["1", "2026-10-21", "10.00", "S001", "Grocery"]


# --- R-ING-02: missing / unreadable input --------------------------------------------
def test_R_ING_02_missing_file_exits_2_without_traceback_or_outputs(tmp_path):
    out = tmp_path / "out"
    proc = run_main("--input", str(tmp_path / "nope.csv"), "--output-dir", str(out))
    assert proc.returncode == 2
    assert proc.stderr.startswith("ERROR:") and "not found" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert not out.exists(), "no output files may be created on input error"


def test_R_ING_02_directory_as_input_is_rejected(tmp_path):
    with pytest.raises(IngestError, match="not a file"):
        read_csv(tmp_path)


# --- R-ING-05: empty input ---------------------------------------------------------------
@pytest.mark.parametrize("content", [b"", b"   \n\n", ("﻿" + ",".join(HEADER) + "\n").encode()])
def test_R_ING_05_empty_or_header_only_is_an_input_error(content):
    with pytest.raises(IngestError):
        parse_bytes(content)


# --- R-ING-04: header rules ----------------------------------------------------------------
def test_R_ING_04_missing_column_is_named(tmp_path):
    p = make_csv(tmp_path / "x.csv", [["1", "2026-10-21", "10", "S001"]], header=HEADER[:4])
    proc = run_main("--input", str(p), "--output-dir", str(tmp_path / "o"))
    assert proc.returncode == 2 and "category" in proc.stderr


def test_R_ING_04_duplicate_header_rejected():
    with pytest.raises(IngestError, match="duplicate"):
        parse_bytes(b"transaction_id,date,amount,amount,store_id,category\n1,2026-10-21,1,1,S001,Grocery\n")


def test_R_ING_04_header_case_spaces_order_and_extra_columns(tmp_path):
    data = (" Category ,STORE_ID,amount,Date,transaction_id,cashier\n"
            "Grocery,S001,10.00,2026-10-21,1,alice\n").encode()
    res = parse_bytes(data)
    assert res.rows[0].fields == dict(zip(HEADER, GOOD))
    assert res.extra_columns == ["cashier"]


# --- R-ING-03: encoding --------------------------------------------------------------------
def test_R_ING_03_bom_is_stripped_and_cp1252_fallback():
    bom = ("﻿" + ",".join(HEADER) + "\n" + ",".join(GOOD) + "\n").encode("utf-8")
    assert parse_bytes(bom).encoding == "utf-8-sig"
    legacy = (",".join(HEADER) + "\n1,2026-10-21,10.00,S001,Groceryé\n").encode("cp1252")
    assert parse_bytes(legacy).encoding == "cp1252"


# --- R-ING-06: row shape ---------------------------------------------------------------------
def test_R_ING_06_blank_lines_skipped_ragged_rows_quarantined(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(",".join(HEADER) + "\n" + ",".join(GOOD) + "\n\n\n2,2026-10-21,5.00,S001\n", encoding="utf-8")
    res = read_csv(p)
    assert res.blank_lines == 2
    assert [r.malformed for r in res.rows] == [False, True]
    assert res.rows[1].line_no == 5, "line numbers are physical file lines"
    out = tmp_path / "o"
    assert run_main("--input", str(p), "--output-dir", str(out)).returncode == 0
    q = read_csv_rows(out / "quarantine.csv")
    assert q[0]["reason_codes"] == "MALFORMED_ROW"


# --- R-ING-01: path precedence, no hardcoded paths -------------------------------------------
def test_R_ING_01_cli_beats_env_beats_config_and_works_from_any_cwd(tmp_path):
    env_dir, cli_dir = tmp_path / "env_out", tmp_path / "cli_out"
    env = {**os.environ, "SALES_SENTINEL_INPUT": str(SAMPLE), "SALES_SENTINEL_OUTPUT_DIR": str(env_dir)}
    # env only, run from an unrelated cwd
    assert run_main(cwd=tmp_path, env=env).returncode == 0
    assert (env_dir / "clean_sales.csv").exists()
    # CLI overrides env
    assert run_main("--output-dir", str(cli_dir), cwd=tmp_path, env=env).returncode == 0
    assert (cli_dir / "clean_sales.csv").exists()


def test_R_ING_01_config_relative_paths_resolve_against_config_file(tmp_path):
    (tmp_path / "data").mkdir()
    make_csv(tmp_path / "data" / "in.csv", [GOOD])
    cfg = tmp_path / "cfgdir" / "p.toml"
    cfg.parent.mkdir()
    cfg.write_text('[paths]\ninput = "../data/in.csv"\noutput_dir = "../out"\n', encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SALES_SENTINEL_")}
    assert run_main("--config", str(cfg), cwd=ROOT, env=env).returncode == 0
    assert (tmp_path / "out" / "clean_sales.csv").exists()


def test_R_ING_01_no_absolute_paths_hardcoded_in_src():
    import re
    for py in (ROOT / "src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not re.search(r"""["'](/home/|/Users/|/mnt/|[A-Za-z]:\\\\)""", text), py


# --- R-OPS-02 / R-OPS-01: config errors and exit codes ---------------------------------------------
@pytest.mark.parametrize("toml", [
    '[dedupe]\npolicy = "fuzzy"\n',
    '[scoring.weights]\ncompleteness = 0.5\nvalidity = 0.5\nconsistency = 0.5\nuniqueness = 0.5\n',
    '[dates]\nbusiness_date = "21/10/2026"\n',
    'this is = = not toml',
])
def test_R_OPS_02_invalid_config_exits_2(tmp_path, toml):
    cfg = tmp_path / "bad.toml"
    cfg.write_text(toml, encoding="utf-8")
    proc = run_main("--config", str(cfg), "--input", str(SAMPLE), "--output-dir", str(tmp_path / "o"))
    assert proc.returncode == 2 and proc.stderr.startswith("ERROR:")


def test_R_OPS_01_strict_quality_gate_exit_3(tmp_path):
    cfg = tmp_path / "gate.toml"
    cfg.write_text("[quality_gate]\nmax_quarantine_rate = 0.01\nmin_score = 0\n", encoding="utf-8")
    args = ("--config", str(cfg), "--input", str(SAMPLE), "--output-dir", str(tmp_path / "o"))
    assert run_main(*args).returncode == 0, "gate is only enforced with --strict"
    proc = run_main(*args, "--strict")
    assert proc.returncode == 3 and "quality gate" in proc.stderr


def test_R_OPS_04_one_summary_line_on_stdout(sample_run):
    proc, _ = sample_run
    assert proc.returncode == 0
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("OK processed=200")


@pytest.mark.parametrize("kwargs, ok", [
    ({"max_age_days": 0}, True), ({"max_age_days": -1}, False),
    ({"future_tolerance_days": 0}, True), ({"future_tolerance_days": -1}, False),
    ({"min_group_size": 1}, True), ({"min_group_size": 0}, False),
    ({"burst_threshold": 2}, True), ({"burst_threshold": 1}, False),
    ({"max_amount": Decimal("0.01")}, True), ({"max_amount": Decimal("0")}, False),
    ({"categories": ()}, False), ({"category_aliases": {"toys": "Toys"}}, False),
    ({"date_order": "YMD"}, False),
])
def test_R_OPS_02_config_validation_boundaries(kwargs, ok):
    from sentinel.config import Config, ConfigError
    if ok:
        Config(**kwargs).validate()
    else:
        with pytest.raises(ConfigError):
            Config(**kwargs).validate()


def test_R_OPS_01_quality_gate_boundary_is_strict(tmp_path):
    """Sample quarantine rate is exactly 6/200 = 3 %: a 3 % limit passes, 2.9 % fails; score 90.0 vs min 90/90.1."""
    def gate(rate, score):
        cfg = tmp_path / f"g_{rate}_{score}.toml"
        cfg.write_text(f"[quality_gate]\nmax_quarantine_rate = {rate}\nmin_score = {score}\n", encoding="utf-8")
        return run_main("--config", str(cfg), "--input", str(SAMPLE), "--output-dir", str(tmp_path / "o"), "--strict").returncode
    assert gate(0.03, 0) == 0 and gate(0.029, 0) == 3
    assert gate(1, 90) == 0 and gate(1, 90.1) == 3

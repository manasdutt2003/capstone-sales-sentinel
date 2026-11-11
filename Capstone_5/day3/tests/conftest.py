"""Shared fixtures. Tests are written from SPEC.md only and cite rule IDs (R-XXX-NN)."""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import settings

# Hypothesis profiles: thorough by default, fast when tools/mutation_smoke.py runs the suite per mutant.
settings.register_profile("default", max_examples=150)
settings.register_profile("mutation", max_examples=20)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SAMPLE = ROOT / "data" / "sample_sales_data.csv"
HEADER = ["transaction_id", "date", "amount", "store_id", "category"]

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def make_csv(path: Path, rows: list[list[str]], header: list[str] | None = HEADER) -> Path:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if header is not None:
        w.writerow(header)
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def run_main(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the real entry point exactly like a user would: python src/main.py ..."""
    return subprocess.run(
        [sys.executable, str(SRC / "main.py"), *args],
        cwd=cwd or ROOT, capture_output=True, text=True, env=env, timeout=60,
    )


@pytest.fixture
def cfg():
    from sentinel.config import Config
    return Config(business_date=None).validate()


@pytest.fixture
def raw_rows():
    """Build RawRow objects from lists, numbering lines like a real file (header = line 1)."""
    from sentinel.ingest import RawRow

    def _build(rows: list[list[str]]):
        return [RawRow(line_no=i + 2, fields=dict(zip(HEADER, r))) for i, r in enumerate(rows)]
    return _build


@pytest.fixture
def sample_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("sample_out")
    proc = run_main("--input", str(SAMPLE), "--output-dir", str(out))
    return proc, out

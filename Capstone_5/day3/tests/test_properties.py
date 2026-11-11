"""Test module 5/5 — property-based fuzzing (Hypothesis): invariants hold for ANY messy input.
Covers: R-INV-01 R-INV-02 R-INV-03 R-INV-04 R-DATE-01 R-AMT-07
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sentinel import codes as C
from sentinel.config import Config
from sentinel.ingest import RawRow
from sentinel.pipeline import run_pipeline
from sentinel.rules import format_amount, parse_amount, parse_date

HEADER = ["transaction_id", "date", "amount", "store_id", "category"]
BD = dt.date(2026, 10, 21)

messy_id = st.one_of(st.integers(1, 40).map(str), st.sampled_from(["", "abc", "0", "-1", "007"]))
messy_date = st.one_of(
    st.just("2026-10-21"), st.just("2026-10-20"), st.just("10/21/26"), st.just("2026/10/21"),
    st.just("20261021"), st.just("invalid"), st.just(""), st.just("2025-02-29"), st.just("03/04/26"),
)
messy_amount = st.one_of(
    st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999.99"), places=2).map(str),
    st.sampled_from(["", "abc", "-50.00", "0", "$1,200.50", "NaN", "19.999", "(5.00)", "150.50"]),
)
messy_store = st.sampled_from(["S001", "S002", "s3", "S004 ", "", "X9", "S000"])
messy_cat = st.sampled_from(["Electronics", "Clothing", "Grocery", "grocery", "Toys", "", " Clothing "])
row = st.tuples(messy_id, messy_date, messy_amount, messy_store, messy_cat).map(list)
SETTINGS = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])  # example count: conftest profiles


def to_raw(rows):
    return [RawRow(line_no=i + 2, fields=dict(zip(HEADER, r))) for i, r in enumerate(rows)]


@SETTINGS
@given(st.lists(row, min_size=1, max_size=60), st.sampled_from(["content", "id"]),
       st.sampled_from(["group_median", "quarantine"]))
def test_R_INV_01_R_INV_02_hold_for_any_batch(rows, policy, strategy):
    """run_pipeline itself raises InvariantError on violation; we also re-check from outside."""
    cfg = Config(business_date=BD, dedupe_policy=policy, missing_strategy=strategy).validate()
    res = run_pipeline(to_raw(rows), cfg)
    assert len(res.kept) + len(res.duplicates) + len(res.quarantined) == len(rows)
    assert all(r.fate is not None for r in res.records)
    ids = [r.txn_id for r in res.kept]
    assert len(ids) == len(set(ids))
    for r in res.quarantined:
        assert r.errors and set(r.errors) <= C.ERRORS


@SETTINGS
@given(st.lists(row, min_size=1, max_size=60))
def test_R_INV_03_R_INV_04_idempotent_and_deterministic(rows):
    cfg = Config(business_date=BD, dedupe_policy="id").validate()
    first = run_pipeline(to_raw(rows), cfg)
    assert [r.fate for r in run_pipeline(to_raw(rows), cfg).records] == [r.fate for r in first.records]
    clean = [[r.clean_row()[h] for h in HEADER] for r in first.kept]
    if not clean:
        return
    second = run_pipeline(to_raw(clean), cfg)
    assert all(r.fate == C.KEPT_CLEAN for r in second.records)
    assert [[r.clean_row()[h] for h in HEADER] for r in second.kept] == clean


@given(st.dates(min_value=dt.date(1950, 1, 1), max_value=dt.date(2099, 12, 31)))
def test_R_DATE_01_every_format_round_trips(d):
    for raw in (d.isoformat(), d.strftime("%Y/%m/%d"), d.strftime("%Y%m%d"), d.strftime("%m/%d/%Y"),
                d.strftime("%m-%d-%Y")):
        assert parse_date(raw, "MDY").value == d, raw


@given(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000.00"), places=2))
def test_R_AMT_07_format_parse_round_trip(x):
    r = parse_amount(format_amount(x))
    assert r.errors == [] and r.repairs == [] and r.value == x

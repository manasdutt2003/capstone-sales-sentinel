"""Test module 3/5 — pipeline behaviour on small hand-built batches.
Covers: R-DUP-01 R-DUP-02 R-DUP-03 R-DUP-04 R-IMP-01 R-IMP-02 R-IMP-03 R-IMP-04
        R-DATE-04 R-AMT-08 R-INV-01 R-INV-02
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from sentinel import codes as C
from sentinel.config import Config
from sentinel.pipeline import InvariantError, PipelineResult, check_invariants, run_pipeline

BD = "2026-10-21"


def fates(result):
    return {r.raw["transaction_id"]: r.fate for r in result.records}


def by_id(result, txn):
    return next(r for r in result.records if r.raw["transaction_id"] == txn)


# --- R-DUP ---------------------------------------------------------------------------------
def test_R_DUP_01_exact_duplicate_removed_first_kept(raw_rows, cfg):
    res = run_pipeline(raw_rows([["1", BD, "10.00", "S001", "Grocery"],
                                 ["1", BD, "10.00", "S001", "Grocery"]]), cfg)
    assert [r.fate for r in res.records] == [C.KEPT_CLEAN, C.REMOVED_DUPLICATE]
    assert res.records[1].duplicate_code == C.DUPLICATE_EXACT and res.records[1].duplicate_of == "1"


def test_R_DUP_01_exact_after_normalisation(raw_rows, cfg):
    """'10/21/26, 10, s001, grocery' is the same sale as the canonical row."""
    res = run_pipeline(raw_rows([["1", BD, "10.00", "S001", "Grocery"],
                                 ["1", "10/21/26", "10", "s001", "grocery"]]), cfg)
    assert res.records[1].duplicate_code == C.DUPLICATE_EXACT


def test_R_DUP_02_id_conflict_is_quarantined(raw_rows, cfg):
    res = run_pipeline(raw_rows([["7", BD, "10.00", "S001", "Grocery"],
                                 ["7", BD, "99.00", "S001", "Grocery"]]), cfg)
    assert res.records[1].fate == C.QUARANTINED
    assert C.ID_CONFLICT in res.records[1].errors and res.records[0].fate == C.KEPT_CLEAN


def test_R_DUP_03_R_DUP_04_content_duplicate_keeps_first_in_file_order(raw_rows, cfg):
    res = run_pipeline(raw_rows([["5", BD, "150.50", "S001", "Electronics"],
                                 ["2", BD, "150.50", "S001", "Electronics"],
                                 ["9", BD, "150.50", "S001", "Clothing"]]), cfg)
    assert fates(res) == {"5": C.KEPT_CLEAN, "2": C.REMOVED_DUPLICATE, "9": C.KEPT_CLEAN}
    assert by_id(res, "2").duplicate_of == "5"
    assert res.clusters[0].size == 2


def test_R_DUP_03_policy_id_keeps_content_duplicates(raw_rows):
    cfg = Config(dedupe_policy="id").validate()
    res = run_pipeline(raw_rows([["1", BD, "150.50", "S001", "Electronics"],
                                 ["2", BD, "150.50", "S001", "Electronics"]]), cfg)
    assert [r.fate for r in res.records] == [C.KEPT_CLEAN, C.KEPT_CLEAN]


def test_R_DUP_03_missing_amount_is_never_duplicate_evidence(raw_rows, cfg):
    rows = [["1", BD, "", "S001", "Grocery"], ["2", BD, "", "S001", "Grocery"]] + \
           [[str(i), BD, f"{i}.00", "S001", "Grocery"] for i in range(10, 13)]
    res = run_pipeline(raw_rows(rows), cfg)
    assert by_id(res, "1").fate == C.KEPT_IMPUTED and by_id(res, "2").fate == C.KEPT_IMPUTED


def test_R_DUP_invalid_rows_do_not_shadow_valid_ones(raw_rows, cfg):
    """A quarantined row must not make a later valid row look like a duplicate."""
    res = run_pipeline(raw_rows([["1", "invalid", "10.00", "S001", "Grocery"],
                                 ["2", BD, "10.00", "S001", "Grocery"]]), cfg)
    assert [r.fate for r in res.records] == [C.QUARANTINED, C.KEPT_CLEAN]


# --- R-IMP ------------------------------------------------------------------------------------
def _grocery(store, *amounts, start=100):
    return [[str(start + i), BD, a, store, "Grocery"] for i, a in enumerate(amounts)]


def test_R_IMP_01_store_category_median_when_group_big_enough(raw_rows, cfg):
    rows = _grocery("S001", "10.00", "20.00", "30.00", "40.00") + [["1", BD, "", "S001", "Grocery"]]
    r = by_id(run_pipeline(raw_rows(rows), cfg), "1")
    assert r.fate == C.KEPT_IMPUTED and r.amount == Decimal("25.00")
    assert r.note.startswith("store_category_median S001/Grocery n=4")


@pytest.mark.parametrize("n, expected_method", [(3, "store_category_median"), (2, "category_median")])
def test_R_IMP_01_min_group_size_boundary(raw_rows, cfg, n, expected_method):
    """min_group_size = 3: a group of exactly 3 is big enough, 2 is not (falls back)."""
    amounts = ["10.00", "20.00", "30.00"][:n]
    rows = _grocery("S001", *amounts) + _grocery("S002", "70.00", "80.00", start=200) + [["1", BD, "", "S001", "Grocery"]]
    assert by_id(run_pipeline(raw_rows(rows), cfg), "1").note.startswith(expected_method)


def test_R_IMP_01_falls_back_to_category_then_global(raw_rows, cfg):
    rows = (_grocery("S001", "10.00", start=100) + _grocery("S002", "20.00", start=200)
            + _grocery("S003", "90.00", start=300) + [["1", BD, "", "S009", "Grocery"]]
            + [["2", BD, "", "S009", "Clothing"]])
    res = run_pipeline(raw_rows(rows), cfg)
    assert by_id(res, "1").note.startswith("category_median Grocery n=3")
    assert by_id(res, "1").amount == Decimal("20.00")
    assert by_id(res, "2").note.startswith("global_median n=3")


def test_R_IMP_01_quarantine_strategy(raw_rows):
    cfg = Config(missing_strategy="quarantine").validate()
    res = run_pipeline(raw_rows([["1", BD, "", "S001", "Grocery"], ["2", BD, "5.00", "S001", "Grocery"]]), cfg)
    assert by_id(res, "1").errors == [C.MISSING_AMOUNT] and by_id(res, "1").fate == C.QUARANTINED


def test_R_IMP_02_missing_amount_with_other_error_is_quarantined(raw_rows, cfg):
    rows = _grocery("S001", "10.00", "20.00", "30.00") + [["1", "invalid", "", "S001", "Grocery"]]
    r = by_id(run_pipeline(raw_rows(rows), cfg), "1")
    assert r.fate == C.QUARANTINED and C.AMOUNT_IMPUTED not in r.repairs


def test_R_IMP_03_medians_use_deduped_observed_values_only(raw_rows, cfg):
    """Ten replayed 10.00 rows must not drag the median down: after dedupe the group is {10, 50, 60}."""
    rows = ([[str(i), BD, "10.00", "S001", "Grocery"] for i in range(10, 20)]
            + _grocery("S001", "50.00", "60.00", start=100)
            + [["1", BD, "", "S001", "Grocery"], ["2", BD, "", "S001", "Grocery"]])
    res = run_pipeline(raw_rows(rows), cfg)
    assert by_id(res, "1").amount == Decimal("50.00") == by_id(res, "2").amount


def test_R_IMP_03_no_observed_amounts_means_quarantine(raw_rows, cfg):
    res = run_pipeline(raw_rows([["1", BD, "", "S001", "Grocery"]]), cfg)
    assert res.records[0].fate == C.QUARANTINED and res.records[0].errors == [C.MISSING_AMOUNT]


def test_R_IMP_04_collision_with_observed_key_is_warned(raw_rows, cfg):
    rows = _grocery("S001", "10.00", "20.00", "30.00") + [["1", BD, "", "S001", "Grocery"]]
    r = by_id(run_pipeline(raw_rows(rows), cfg), "1")
    assert r.amount == Decimal("20.00") and C.IMPUTED_KEY_COLLISION in r.warnings


# --- R-DATE-04 window ----------------------------------------------------------------------------
@pytest.mark.parametrize("date, ok", [
    ("2026-10-21", True), ("2026-10-14", True), ("2026-10-13", False),   # max_age_days = 7 boundary
    ("2026-10-22", False),                                               # future_tolerance_days = 0
    ("2016-10-21", False),                                               # typo year
])
def test_R_DATE_04_window_boundaries(raw_rows, date, ok):
    cfg = Config(business_date=dt.date(2026, 10, 21)).validate()
    r = run_pipeline(raw_rows([["1", date, "10.00", "S001", "Grocery"]]), cfg).records[0]
    assert (C.DATE_OUT_OF_WINDOW not in r.errors) is ok


def test_R_DATE_04_future_tolerance_extends_window(raw_rows):
    cfg = Config(business_date=dt.date(2026, 10, 21), future_tolerance_days=1).validate()
    rows = [["1", "2026-10-22", "1.00", "S001", "Grocery"], ["2", "2026-10-23", "1.00", "S001", "Grocery"]]
    res = run_pipeline(raw_rows(rows), cfg)
    assert [r.fate for r in res.records] == [C.KEPT_CLEAN, C.QUARANTINED]


def test_R_DATE_04_business_date_inferred_as_mode_ties_to_latest(raw_rows, cfg):
    rows = [["1", "2026-10-20", "1.00", "S001", "Grocery"], ["2", "2026-10-21", "2.00", "S001", "Grocery"]]
    res = run_pipeline(raw_rows(rows), cfg)
    assert res.business_date == dt.date(2026, 10, 21) and "inferred" in res.business_date_source


# --- R-AMT-08 outliers --------------------------------------------------------------------------------
def test_R_AMT_08_outlier_flagged_but_kept(raw_rows, cfg):
    rows = [[str(i), BD, f"{100 + i}.00", "S001", "Electronics"] for i in range(1, 9)]
    rows.append(["99", BD, "3500.00", "S001", "Electronics"])
    res = run_pipeline(raw_rows(rows), cfg)
    big = by_id(res, "99")
    assert big.fate == C.KEPT_CLEAN and C.OUTLIER_AMOUNT in big.warnings and "robust_z=" in big.note
    assert sum(C.OUTLIER_AMOUNT in r.warnings for r in res.records) == 1


def test_R_AMT_08_minimum_group_of_five_is_scored(raw_rows, cfg):
    rows = [[str(i), BD, a, "S001", "Grocery"] for i, a in enumerate(["10.00", "11.00", "12.00", "13.00", "500.00"], 1)]
    assert C.OUTLIER_AMOUNT in by_id(run_pipeline(raw_rows(rows), cfg), "5").warnings
    assert C.OUTLIER_AMOUNT not in by_id(run_pipeline(raw_rows(rows[:4]), cfg), "4").warnings


def test_R_AMT_08_threshold_is_strictly_greater(raw_rows):
    """values 10,20,30,40,50 -> median 30, MAD 10; 30 + 10*z/0.6745 sits exactly on the threshold."""
    rows = [[str(i), BD, a, "S001", "Grocery"] for i, a in enumerate(["10.00", "20.00", "30.00", "40.00", "50.00"], 1)]
    z_of_50 = 0.6745 * 20 / 10
    on = run_pipeline(raw_rows(rows), Config(outlier_z=z_of_50).validate())
    below = run_pipeline(raw_rows(rows), Config(outlier_z=z_of_50 - 0.01).validate())
    assert C.OUTLIER_AMOUNT not in by_id(on, "5").warnings
    assert C.OUTLIER_AMOUNT in by_id(below, "5").warnings


def test_R_AMT_08_small_groups_are_not_scored(raw_rows, cfg):
    rows = [["1", BD, "1.00", "S001", "Grocery"], ["2", BD, "2.00", "S001", "Grocery"],
            ["3", BD, "9000.00", "S001", "Grocery"]]
    assert all(C.OUTLIER_AMOUNT not in r.warnings for r in run_pipeline(raw_rows(rows), cfg).records)


# --- diagnose-all + invariants -------------------------------------------------------------------------
def test_R_INV_01_multi_error_row_records_every_problem(raw_rows, cfg):
    r = run_pipeline(raw_rows([["x", "invalid", "abc", "Q1", "Toys"]]), cfg).records[0]
    assert set(r.errors) == {C.BAD_TXN_ID, C.BAD_DATE, C.BAD_AMOUNT, C.BAD_STORE, C.BAD_CATEGORY}


def test_R_INV_01_reconciliation_violation_raises(raw_rows, cfg):
    res = run_pipeline(raw_rows([["1", BD, "1.00", "S001", "Grocery"]]), cfg)
    with pytest.raises(InvariantError, match="ledger"):
        check_invariants(res, processed=2)
    res.records[0].fate = None
    with pytest.raises(InvariantError):
        check_invariants(res, processed=1)


def test_R_INV_02_postcondition_catches_corrupt_clean_row(raw_rows, cfg):
    res = run_pipeline(raw_rows([["1", BD, "1.00", "S001", "Grocery"]]), cfg)
    res.records[0].store = "s1"          # simulate a bug that leaks a non-canonical value
    with pytest.raises(InvariantError, match="post-condition"):
        check_invariants(res, processed=1)

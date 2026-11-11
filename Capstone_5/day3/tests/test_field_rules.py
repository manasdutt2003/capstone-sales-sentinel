"""Test module 2/5 — field rules as Given/When/Then tables (one behaviour per row).
Covers: R-TXN-01 R-DATE-01 R-DATE-02 R-DATE-03 R-AMT-01 R-AMT-02 R-AMT-03 R-AMT-04
        R-AMT-05 R-AMT-06 R-AMT-07 R-STORE-01 R-CAT-01
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from sentinel import codes as C
from sentinel.rules import format_amount, normalize_category, normalize_store, parse_amount, parse_date, parse_txn_id

D = dt.date


# --- R-TXN-01 ------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, value, repairs", [
    ("1", "1", []),
    ("200", "200", []),
    ("007", "7", [C.TXN_ID_NORMALIZED]),
    (" 42 ", "42", [C.TXN_ID_NORMALIZED]),
])
def test_R_TXN_01_valid_ids(raw, value, repairs):
    r = parse_txn_id(raw)
    assert (r.value, r.errors, r.repairs) == (value, [], repairs)


@pytest.mark.parametrize("raw", ["", "  ", "abc", "1.0", "-3", "0", "000", "1e3", "١٢", "12 3"])
def test_R_TXN_01_invalid_ids(raw):
    assert parse_txn_id(raw).errors == [C.BAD_TXN_ID]


# --- R-DATE-01 accepted formats --------------------------------------------------------------
@pytest.mark.parametrize("raw, expected, repaired", [
    ("2026-10-21", D(2026, 10, 21), False),        # canonical: untouched
    ("2026/10/21", D(2026, 10, 21), True),
    ("2026.10.21", D(2026, 10, 21), True),
    ("20261021", D(2026, 10, 21), True),
    ("10/21/26", D(2026, 10, 21), True),
    ("10/21/2026", D(2026, 10, 21), True),
    ("10-21-2026", D(2026, 10, 21), True),
    ("10-21-26", D(2026, 10, 21), True),
    ("2026-10-21T14:05:00", D(2026, 10, 21), True),
    ("2026-10-21 14:05", D(2026, 10, 21), True),
    ("2026-10-21T14:05:00+05:30", D(2026, 10, 21), True),
    ("2024-02-29", D(2024, 2, 29), False),         # leap day in a leap year
])
def test_R_DATE_01_formats_normalise_to_iso(raw, expected, repaired):
    r = parse_date(raw)
    assert r.errors == [] and r.value == expected
    assert (C.DATE_REFORMATTED in r.repairs) is repaired


# --- R-DATE-02 ambiguity ------------------------------------------------------------------------
def test_R_DATE_02_ambiguous_uses_configured_order_and_warns():
    mdy, dmy = parse_date("03/04/26", "MDY"), parse_date("03/04/26", "DMY")
    assert mdy.value == D(2026, 3, 4) and dmy.value == D(2026, 4, 3)
    assert C.AMBIGUOUS_DATE in mdy.warnings and C.AMBIGUOUS_DATE in dmy.warnings


def test_R_DATE_02_same_day_month_is_not_ambiguous():
    assert parse_date("05/05/26").warnings == []


def test_R_DATE_02_only_other_order_valid_is_inferred():
    r = parse_date("21/10/2026", "MDY")
    assert r.value == D(2026, 10, 21) and r.warnings == [C.DATE_ORDER_INFERRED]


# --- R-DATE-03 unparseable ------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["", "invalid", "2025-02-29", "2026-13-01", "13/45/26", "2026-1-5",
                                 "21 Oct 2026", "2026-10-21-01", "'; DROP TABLE sales;--", "📅"])
def test_R_DATE_03_bad_dates(raw):
    assert parse_date(raw).errors == [C.BAD_DATE]


# --- R-AMT-01 missing ---------------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["", "   ", "NULL", "None", "na", "N/A", "NaN", "-"])
def test_R_AMT_01_missing_tokens(raw):
    r = parse_amount(raw)
    assert r.missing and r.errors == [] and r.value is None


# --- R-AMT-02 / R-AMT-07 valid and repaired -------------------------------------------------------------
@pytest.mark.parametrize("raw, value, repairs", [
    ("150.50", "150.50", []),
    ("45", "45.00", []),                                    # formatting is not a repair
    ("$150.50", "150.50", [C.AMOUNT_NORMALIZED]),
    ("₹ 1,200.50", "1200.50", [C.AMOUNT_NORMALIZED]),
    ("19.999", "20.00", [C.AMOUNT_ROUNDED]),
    ("10.005", "10.01", [C.AMOUNT_ROUNDED]),                # half-up, not banker's rounding
    ("10.015", "10.02", [C.AMOUNT_ROUNDED]),
    (".5", "0.50", []),
])
def test_R_AMT_02_and_07_parse_normalise_round(raw, value, repairs):
    r = parse_amount(raw)
    assert r.errors == []
    assert format_amount(r.value) == value
    assert r.repairs == repairs


def test_R_AMT_07_decimal_not_float():
    r = parse_amount("0.10")
    assert isinstance(r.value, Decimal) and r.value + parse_amount("0.20").value == Decimal("0.30")


# --- R-AMT-03..06 errors ------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, code", [
    ("abc", C.BAD_AMOUNT), ("xyz", C.BAD_AMOUNT), ("inf", C.BAD_AMOUNT), ("1e3", C.BAD_AMOUNT),
    ("12.3.4", C.BAD_AMOUNT), ("+", C.BAD_AMOUNT), ("$", C.BAD_AMOUNT), ("1,20", C.BAD_AMOUNT), ("ten", C.BAD_AMOUNT), ("10 USD", C.BAD_AMOUNT),
    ("-50.00", C.NEGATIVE_AMOUNT), ("(50.00)", C.NEGATIVE_AMOUNT), ("-$5", C.NEGATIVE_AMOUNT),
    ("0", C.ZERO_AMOUNT), ("0.00", C.ZERO_AMOUNT), ("-0.00", C.ZERO_AMOUNT), ("0.004", C.ZERO_AMOUNT),
    ("100000.01", C.AMOUNT_ABOVE_CEILING), ("1,234,567.00", C.AMOUNT_ABOVE_CEILING),
])
def test_R_AMT_03_04_05_06_invalid_amounts(raw, code):
    assert code in parse_amount(raw).errors


def test_R_AMT_06_ceiling_boundary_is_inclusive():
    assert parse_amount("100000.00").errors == []
    assert parse_amount("100000.01").errors == [C.AMOUNT_ABOVE_CEILING]
    assert parse_amount("5.01", max_amount=Decimal("5.00")).errors == [C.AMOUNT_ABOVE_CEILING]
    assert parse_amount("0.01").errors == []                      # smallest valid sale


# --- R-STORE-01 ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, value, repaired", [
    ("S001", "S001", False), ("s001", "S001", True), (" S002 ", "S002", True),
    ("S1", "S001", True), ("S-12", "S012", True), ("s_5", "S005", True), ("S999", "S999", False),
])
def test_R_STORE_01_valid(raw, value, repaired):
    r = normalize_store(raw)
    assert r.value == value and r.errors == [] and (r.repairs == [C.STORE_NORMALIZED]) is repaired


@pytest.mark.parametrize("raw", ["", "S000", "S0", "S1000", "001", "X001", "S00A", "Store 1"])
def test_R_STORE_01_invalid(raw):
    assert normalize_store(raw).errors == [C.BAD_STORE]


# --- R-CAT-01 -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, value, repaired", [
    ("Electronics", "Electronics", False), ("electronics", "Electronics", True),
    ("  GROCERY ", "Grocery", True), ("Apparel", "Clothing", True), ("food", "Grocery", True),
])
def test_R_CAT_01_valid(raw, value, repaired):
    r = normalize_category(raw, aliases={"apparel": "Clothing", "food": "Grocery"})
    assert r.value == value and r.errors == [] and (r.repairs == [C.CATEGORY_NORMALIZED]) is repaired


@pytest.mark.parametrize("raw", ["", "Toys", "Electronics!", "Elec tronics"])
def test_R_CAT_01_invalid(raw):
    assert normalize_category(raw).errors == [C.BAD_CATEGORY]

"""Data-quality scoring and money reconciliation (SPEC R-SCORE-01 … 03)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import codes as C
from .ingest import REQUIRED_COLUMNS
from .pipeline import PipelineResult, Record
from .rules import format_amount


@dataclass
class Score:
    completeness: float
    validity: float
    consistency: float
    uniqueness: float
    overall: float
    grade: str


@dataclass
class Money:
    raw_total: Decimal            # every numerically parseable raw amount, any sign
    clean_total: Decimal
    imputed_total: Decimal
    duplicate_total: Decimal
    quarantined_total: Decimal    # parseable amounts on quarantined rows
    balanced: bool


def grade_for(score: float) -> str:
    for threshold, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if score >= threshold:
            return letter
    return "F"


def _canonical(rec: Record, name: str) -> str | None:
    fr = rec.field_results.get(name)
    if fr is None or fr.value is None:
        return None
    if name == "date":
        return fr.value.isoformat()
    if name == "amount":
        return format_amount(fr.value)
    return str(fr.value)


def _cell_valid(rec: Record, name: str) -> bool:
    if rec.malformed:
        return False
    fr = rec.field_results[name]
    if fr.errors:
        return False
    if name == "date" and C.DATE_OUT_OF_WINDOW in rec.errors:
        return False
    return True


def score(result: PipelineResult) -> Score:
    recs = result.records
    n = len(recs)
    total_cells = n * len(REQUIRED_COLUMNS)
    non_empty = valid = canonical = 0
    for rec in recs:
        for name in REQUIRED_COLUMNS:
            raw = rec.raw.get(name, "")
            if raw.strip() == "":
                continue
            non_empty += 1
            if _cell_valid(rec, name):
                valid += 1
                if raw == _canonical(rec, name):
                    canonical += 1
    completeness = non_empty / total_cells if total_cells else 0.0
    validity = valid / non_empty if non_empty else 0.0
    consistency = canonical / valid if valid else 0.0
    uniqueness = 1 - len(result.duplicates) / n if n else 0.0
    w = result.config.weights
    overall = 100 * (
        w["completeness"] * completeness
        + w["validity"] * validity
        + w["consistency"] * consistency
        + w["uniqueness"] * uniqueness
    )
    overall = round(overall, 1)
    return Score(completeness, validity, consistency, uniqueness, overall, grade_for(overall))


def money(result: PipelineResult) -> Money:
    def total(rows, attr="raw_amount_value") -> Decimal:
        return sum((getattr(r, attr) for r in rows if getattr(r, attr) is not None), Decimal("0.00"))

    raw_total = total(result.records)
    clean_total = total(result.kept, "amount")
    imputed_total = total(result.imputed, "amount")
    duplicate_total = total(result.duplicates)
    quarantined_total = total(result.quarantined)
    balanced = raw_total == clean_total - imputed_total + duplicate_total + quarantined_total
    return Money(raw_total, clean_total, imputed_total, duplicate_total, quarantined_total, balanced)

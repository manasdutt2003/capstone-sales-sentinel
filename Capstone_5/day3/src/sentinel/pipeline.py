"""The cleaning pipeline: every input row ends with exactly one fate (SPEC §3.2–3.6).

Stage order (DECISIONS D-07):
  1 validate fields (diagnose-all)  2 infer business date + window check
  3 missing-amount strategy         4 quarantine rows with errors
  5 dedupe (exact / id-conflict / content) on valid rows, file order
  6 impute from post-dedupe observed medians   7 flag outliers
  8 assign fates                    9 check invariants
"""
from __future__ import annotations

import datetime as dt
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from . import codes as C
from .config import Config
from .ingest import REQUIRED_COLUMNS, RawRow
from .rules import (
    CENT,
    FieldResult,
    format_amount,
    normalize_category,
    normalize_store,
    parse_amount,
    parse_date,
    parse_txn_id,
)


class InvariantError(Exception):
    """Accounting / post-condition violated -> exit code 1."""


@dataclass
class Record:
    line_no: int
    raw: dict[str, str]
    malformed: bool = False
    txn_id: str | None = None
    date: dt.date | None = None
    amount: Decimal | None = None
    store: str | None = None
    category: str | None = None
    amount_missing: bool = False
    raw_amount_value: Decimal | None = None      # parseable raw amount (any sign), for money reconciliation
    field_results: dict[str, FieldResult] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_code: str | None = None
    duplicate_of: str | None = None
    fate: str | None = None
    note: str = ""

    # -- helpers -----------------------------------------------------------
    @property
    def kept(self) -> bool:
        return self.fate in C.KEPT_FATES

    def content_key(self) -> tuple:
        return (self.date, self.amount, self.store, self.category)

    def codes(self) -> list[str]:
        out = list(self.errors)
        if self.duplicate_code:
            out.append(self.duplicate_code)
        out += self.repairs + self.warnings
        return list(dict.fromkeys(out))  # de-dupe, keep order

    def clean_row(self) -> dict[str, str]:
        return {
            "transaction_id": self.txn_id or "",
            "date": self.date.isoformat() if self.date else "",
            "amount": format_amount(self.amount) if self.amount is not None else "",
            "store_id": self.store or "",
            "category": self.category or "",
        }


@dataclass
class DuplicateCluster:
    key: tuple
    survivor_id: str
    removed_ids: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return 1 + len(self.removed_ids)


@dataclass
class PipelineResult:
    records: list[Record]
    business_date: dt.date | None
    business_date_source: str
    clusters: list[DuplicateCluster]
    config: Config

    def by_fate(self, fate: str) -> list[Record]:
        return [r for r in self.records if r.fate == fate]

    @property
    def kept(self) -> list[Record]:
        return [r for r in self.records if r.kept]

    @property
    def quarantined(self) -> list[Record]:
        return self.by_fate(C.QUARANTINED)

    @property
    def duplicates(self) -> list[Record]:
        return self.by_fate(C.REMOVED_DUPLICATE)

    @property
    def imputed(self) -> list[Record]:
        return [r for r in self.kept if C.AMOUNT_IMPUTED in r.repairs]

    @property
    def fixed(self) -> list[Record]:
        """Kept rows with at least one non-imputation repair (report 'fixed')."""
        return [r for r in self.kept if any(x != C.AMOUNT_IMPUTED for x in r.repairs)]


# ------------------------------------------------------------------------------ stage 1
def validate_row(raw: RawRow, cfg: Config) -> Record:
    rec = Record(line_no=raw.line_no, raw=dict(raw.fields), malformed=raw.malformed)
    if raw.malformed:
        rec.errors.append(C.MALFORMED_ROW)
        return rec

    results = {
        "transaction_id": parse_txn_id(raw.fields["transaction_id"]),
        "date": parse_date(raw.fields["date"], cfg.date_order),
        "amount": parse_amount(raw.fields["amount"], cfg.max_amount),
        "store_id": normalize_store(raw.fields["store_id"]),
        "category": normalize_category(raw.fields["category"], cfg.categories, cfg.category_aliases),
    }
    rec.field_results = results
    for name in REQUIRED_COLUMNS:
        r = results[name]
        rec.errors += r.errors
        rec.repairs += r.repairs
        rec.warnings += r.warnings

    rec.txn_id = results["transaction_id"].value
    rec.date = results["date"].value
    rec.store = results["store_id"].value
    rec.category = results["category"].value
    amt = results["amount"]
    rec.amount_missing = amt.missing
    rec.raw_amount_value = amt.value
    rec.amount = amt.value if amt.ok else None
    return rec


# ------------------------------------------------------------------------------ stage 2
def infer_business_date(records: list[Record], cfg: Config) -> tuple[dt.date | None, str]:
    if cfg.business_date:
        return cfg.business_date, "configured"
    counts = Counter(r.date for r in records if r.date is not None)
    if not counts:
        return None, "unavailable (no valid dates)"
    best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))  # most frequent, ties -> latest
    return best[0], "inferred (modal date)"


def apply_window(records: list[Record], business_date: dt.date | None, cfg: Config) -> None:
    if business_date is None:
        return
    lo = business_date - dt.timedelta(days=cfg.max_age_days)
    hi = business_date + dt.timedelta(days=cfg.future_tolerance_days)
    for r in records:
        if r.date is not None and not (lo <= r.date <= hi):
            r.errors.append(C.DATE_OUT_OF_WINDOW)


# ------------------------------------------------------------------------------ stage 5
def _same_content(a: Record, b: Record) -> bool:
    return a.content_key() == b.content_key() and a.amount_missing == b.amount_missing


def dedupe(candidates: list[Record], cfg: Config) -> list[DuplicateCluster]:
    by_id: dict[str, Record] = {}
    by_key: dict[tuple, Record] = {}
    clusters: dict[tuple, DuplicateCluster] = {}
    for r in candidates:
        first = by_id.get(r.txn_id)
        if first is not None:
            if _same_content(first, r):
                r.fate, r.duplicate_code, r.duplicate_of = C.REMOVED_DUPLICATE, C.DUPLICATE_EXACT, first.txn_id
            else:
                r.errors.append(C.ID_CONFLICT)
                r.fate = C.QUARANTINED
                r.note = f"transaction_id {r.txn_id} first seen on line {first.line_no}"
            continue
        by_id[r.txn_id] = r
        if cfg.dedupe_policy == "content" and not r.amount_missing:
            key = r.content_key()
            survivor = by_key.get(key)
            if survivor is not None:
                r.fate, r.duplicate_code, r.duplicate_of = C.REMOVED_DUPLICATE, C.DUPLICATE_CONTENT, survivor.txn_id
                clusters.setdefault(key, DuplicateCluster(key, survivor.txn_id)).removed_ids.append(r.txn_id)
                continue
            by_key[key] = r
    return list(clusters.values())


# ------------------------------------------------------------------------------ stage 6
def _median(values: list[Decimal]) -> Decimal:
    return Decimal(statistics.median(values)).quantize(CENT, rounding=ROUND_HALF_UP)


def impute(survivors: list[Record], cfg: Config) -> None:
    observed = [r for r in survivors if not r.amount_missing]
    missing = [r for r in survivors if r.amount_missing]
    if not missing:
        return
    by_group: dict[tuple, list[Decimal]] = defaultdict(list)
    by_cat: dict[str, list[Decimal]] = defaultdict(list)
    for r in observed:
        by_group[(r.store, r.category)].append(r.amount)
        by_cat[r.category].append(r.amount)
    all_values = [r.amount for r in observed]
    key_owner: dict[tuple, Record] = {r.content_key(): r for r in reversed(observed)}  # first observed wins
    k = cfg.min_group_size

    for r in missing:   # medians above are frozen: imputed values never feed other imputations
        group = by_group.get((r.store, r.category), [])
        cat = by_cat.get(r.category, [])
        if len(group) >= k:
            r.amount, r.note = _median(group), f"store_category_median {r.store}/{r.category} n={len(group)}"
        elif len(cat) >= k:
            r.amount, r.note = _median(cat), f"category_median {r.category} n={len(cat)}"
        elif all_values:
            r.amount, r.note = _median(all_values), f"global_median n={len(all_values)}"
        else:
            r.errors.append(C.MISSING_AMOUNT)
            r.fate = C.QUARANTINED
            r.note = "no observed amounts to impute from"
            continue
        r.repairs.append(C.AMOUNT_IMPUTED)
        # R-IMP-04: flag BOTH parties of a key collision (imputed-vs-observed and imputed-vs-imputed);
        # on a re-run either one could be the row that gets removed.
        partner = key_owner.get(r.content_key())
        if partner is None:
            key_owner[r.content_key()] = r
            continue
        r.warnings.append(C.IMPUTED_KEY_COLLISION)
        r.note += f"; key shared with id {partner.txn_id}"
        if C.IMPUTED_KEY_COLLISION not in partner.warnings:
            partner.warnings.append(C.IMPUTED_KEY_COLLISION)
            partner.note = (partner.note + "; " if partner.note else "") + f"key shared with imputed id {r.txn_id}"


# ------------------------------------------------------------------------------ stage 7
def flag_outliers(kept: list[Record], cfg: Config) -> None:
    by_cat: dict[str, list[Record]] = defaultdict(list)
    for r in kept:
        if not r.amount_missing:
            by_cat[r.category].append(r)
    for rows in by_cat.values():
        if len(rows) < 5:
            continue
        values = [float(r.amount) for r in rows]
        med = statistics.median(values)
        mad = statistics.median(abs(v - med) for v in values)
        if mad == 0:
            continue
        for r, v in zip(rows, values):
            z = 0.6745 * (v - med) / mad
            if abs(z) > cfg.outlier_z:
                r.warnings.append(C.OUTLIER_AMOUNT)
                r.note = (r.note + "; " if r.note else "") + f"robust_z={z:.1f}"


# ------------------------------------------------------------------------------ stage 9
def check_invariants(result: PipelineResult, processed: int) -> None:
    recs = result.records
    if len(recs) != processed:
        raise InvariantError(f"ledger has {len(recs)} rows, input had {processed}")
    if any(r.fate is None for r in recs):
        raise InvariantError("some rows have no fate")
    kept, dup, quar = len(result.kept), len(result.duplicates), len(result.quarantined)
    if kept + dup + quar != processed:
        raise InvariantError(f"rows do not reconcile: {kept} + {dup} + {quar} != {processed}")
    # R-INV-02: every clean row must re-validate with zero errors and zero repairs
    seen: set[str] = set()
    for r in result.kept:
        row = r.clean_row()
        checks = [
            parse_txn_id(row["transaction_id"]),
            parse_date(row["date"], result.config.date_order),
            parse_amount(row["amount"], result.config.max_amount),
            normalize_store(row["store_id"]),
            normalize_category(row["category"], result.config.categories, result.config.category_aliases),
        ]
        if any(c.errors or c.repairs or c.missing for c in checks):
            raise InvariantError(f"post-condition failed for clean row {row}")
        if row["transaction_id"] in seen:
            raise InvariantError(f"duplicate transaction_id in clean output: {row['transaction_id']}")
        seen.add(row["transaction_id"])


# ------------------------------------------------------------------------------ driver
def run_pipeline(rows: list[RawRow], cfg: Config) -> PipelineResult:
    records = [validate_row(r, cfg) for r in rows]

    business_date, source = infer_business_date(records, cfg)
    apply_window(records, business_date, cfg)

    if cfg.missing_strategy == "quarantine":
        for r in records:
            if r.amount_missing:
                r.errors.append(C.MISSING_AMOUNT)

    for r in records:
        if r.errors:
            r.fate = C.QUARANTINED

    candidates = [r for r in records if r.fate is None]
    clusters = dedupe(candidates, cfg)
    survivors = [r for r in candidates if r.fate is None]
    impute(survivors, cfg)

    for r in survivors:
        if r.fate is None:
            if C.AMOUNT_IMPUTED in r.repairs:
                r.fate = C.KEPT_IMPUTED
            elif r.repairs:
                r.fate = C.KEPT_REPAIRED
            else:
                r.fate = C.KEPT_CLEAN
    flag_outliers([r for r in survivors if r.kept], cfg)

    result = PipelineResult(records, business_date, source, clusters, cfg)
    check_invariants(result, len(rows))
    return result

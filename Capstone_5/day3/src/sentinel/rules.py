"""Pure field-level parsers. String in -> FieldResult out. No I/O, no global state.

Each function implements one SPEC rule family so it can be table-tested in isolation.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from . import codes as C

CENT = Decimal("0.01")
MISSING_TOKENS = frozenset({"", "null", "none", "na", "n/a", "nan", "-"})
_CURRENCY = "$₹€£"


@dataclass
class FieldResult:
    value: Any = None
    errors: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- R-TXN-01
_ASCII_DIGITS = re.compile(r"[0-9]+")


def parse_txn_id(raw: str) -> FieldResult:
    s = (raw or "").strip()
    if not _ASCII_DIGITS.fullmatch(s) or int(s) <= 0:
        return FieldResult(errors=[C.BAD_TXN_ID], missing=(s == ""))
    value = str(int(s))
    res = FieldResult(value=value)
    if value != raw:
        res.repairs.append(C.TXN_ID_NORMALIZED)
    return res


# --------------------------------------------------------------------------- R-DATE-01..03
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_ISO_TS = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?")
_YMD_SEP = re.compile(r"(\d{4})([/.])(\d{1,2})\2(\d{1,2})")
_YMD_COMPACT = re.compile(r"(\d{4})(\d{2})(\d{2})")
_ABY = re.compile(r"(\d{1,2})([/-])(\d{1,2})\2(\d{4}|\d{2})")


def _mk(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def parse_date(raw: str, order: str = "MDY") -> FieldResult:
    s = (raw or "").strip()
    if not s:
        return FieldResult(errors=[C.BAD_DATE], missing=True)

    m = _ISO.fullmatch(s)
    if m:
        d = _mk(int(m[1]), int(m[2]), int(m[3]))
        if d is None:
            return FieldResult(errors=[C.BAD_DATE])
        res = FieldResult(value=d)
        if s != raw:  # surrounding whitespace was trimmed
            res.repairs.append(C.DATE_REFORMATTED)
        return res

    candidate: dt.date | None = None
    warnings: list[str] = []
    if m := _ISO_TS.fullmatch(s):
        candidate = _mk(int(m[1]), int(m[2]), int(m[3]))
    elif m := _YMD_SEP.fullmatch(s):
        candidate = _mk(int(m[1]), int(m[3]), int(m[4]))
    elif m := _YMD_COMPACT.fullmatch(s):
        candidate = _mk(int(m[1]), int(m[2]), int(m[3]))
    elif m := _ABY.fullmatch(s):
        a, b, ytxt = int(m[1]), int(m[3]), m[4]
        year = 2000 + int(ytxt) if len(ytxt) == 2 else int(ytxt)
        mdy, dmy = _mk(year, a, b), _mk(year, b, a)
        preferred, other = (mdy, dmy) if order == "MDY" else (dmy, mdy)
        if preferred is not None:
            candidate = preferred
            if other is not None and other != preferred:
                warnings.append(C.AMBIGUOUS_DATE)
        elif other is not None:
            candidate = other
            warnings.append(C.DATE_ORDER_INFERRED)

    if candidate is None:
        return FieldResult(errors=[C.BAD_DATE])
    return FieldResult(value=candidate, repairs=[C.DATE_REFORMATTED], warnings=warnings)


# --------------------------------------------------------------------------- R-AMT-01..07
_PLAIN_DECIMAL = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)")
_THOUSANDS = re.compile(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?")
_ACCOUNTING_NEG = re.compile(r"\((.+)\)")


def parse_amount(raw: str, max_amount: Decimal = Decimal("100000.00")) -> FieldResult:
    s = (raw or "").strip()
    if s.casefold() in MISSING_TOKENS:
        return FieldResult(missing=True)

    t = s
    negative_wrap = False
    if m := _ACCOUNTING_NEG.fullmatch(t):
        t, negative_wrap = m[1].strip(), True
    t = t.strip(_CURRENCY + " ").replace(" ", "")
    if t and t[0] in "+-" and len(t) > 1 and t[1] in _CURRENCY:   # "-$50.00"
        t = t[0] + t[1:].lstrip(_CURRENCY)
    if _THOUSANDS.fullmatch(t):
        t = t.replace(",", "")
    if not _PLAIN_DECIMAL.fullmatch(t):
        return FieldResult(errors=[C.BAD_AMOUNT])
    try:
        value = Decimal(t)
    except InvalidOperation:  # pragma: no cover - regex already guarantees validity
        return FieldResult(errors=[C.BAD_AMOUNT])
    if negative_wrap:
        value = -value

    res = FieldResult()
    if t != raw or negative_wrap:
        res.repairs.append(C.AMOUNT_NORMALIZED)
    q = value.quantize(CENT, rounding=ROUND_HALF_UP)
    if q != value:
        res.repairs.append(C.AMOUNT_ROUNDED)
    if q < 0:
        res.errors.append(C.NEGATIVE_AMOUNT)
    elif q == 0:
        res.errors.append(C.ZERO_AMOUNT)
    elif q > max_amount:
        res.errors.append(C.AMOUNT_ABOVE_CEILING)
    res.value = q
    return res


def format_amount(value: Decimal) -> str:
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"


# --------------------------------------------------------------------------- R-STORE-01
_STORE = re.compile(r"S[-_ ]?([0-9]{1,3})")


def normalize_store(raw: str) -> FieldResult:
    s = (raw or "").strip().upper()
    m = _STORE.fullmatch(s)
    if not m or int(m[1]) == 0:
        return FieldResult(errors=[C.BAD_STORE], missing=(s == ""))
    value = f"S{int(m[1]):03d}"
    res = FieldResult(value=value)
    if value != raw:
        res.repairs.append(C.STORE_NORMALIZED)
    return res


# --------------------------------------------------------------------------- R-CAT-01
def normalize_category(
    raw: str,
    allowed: Sequence[str] = ("Electronics", "Clothing", "Grocery"),
    aliases: Mapping[str, str] | None = None,
) -> FieldResult:
    key = " ".join((raw or "").split()).casefold()
    if not key:
        return FieldResult(errors=[C.BAD_CATEGORY], missing=True)
    lookup = {c.casefold(): c for c in allowed}
    for alias, target in (aliases or {}).items():
        lookup.setdefault(" ".join(alias.split()).casefold(), lookup.get(target.casefold(), target))
    value = lookup.get(key)
    if value is None:
        return FieldResult(errors=[C.BAD_CATEGORY])
    res = FieldResult(value=value)
    if value != raw:
        res.repairs.append(C.CATEGORY_NORMALIZED)
    return res

"""The single vocabulary of reason codes used in the ledger, quarantine and report."""
from __future__ import annotations

# Errors -> row is QUARANTINED
MALFORMED_ROW = "MALFORMED_ROW"
BAD_TXN_ID = "BAD_TXN_ID"
BAD_DATE = "BAD_DATE"
DATE_OUT_OF_WINDOW = "DATE_OUT_OF_WINDOW"
BAD_AMOUNT = "BAD_AMOUNT"
NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
ZERO_AMOUNT = "ZERO_AMOUNT"
AMOUNT_ABOVE_CEILING = "AMOUNT_ABOVE_CEILING"
MISSING_AMOUNT = "MISSING_AMOUNT"
BAD_STORE = "BAD_STORE"
BAD_CATEGORY = "BAD_CATEGORY"
ID_CONFLICT = "ID_CONFLICT"

# Duplicate codes -> REMOVED_DUPLICATE
DUPLICATE_EXACT = "DUPLICATE_EXACT"
DUPLICATE_CONTENT = "DUPLICATE_CONTENT"

# Repairs -> row kept, value changed
TXN_ID_NORMALIZED = "TXN_ID_NORMALIZED"
DATE_REFORMATTED = "DATE_REFORMATTED"
AMOUNT_NORMALIZED = "AMOUNT_NORMALIZED"
AMOUNT_ROUNDED = "AMOUNT_ROUNDED"
AMOUNT_IMPUTED = "AMOUNT_IMPUTED"
STORE_NORMALIZED = "STORE_NORMALIZED"
CATEGORY_NORMALIZED = "CATEGORY_NORMALIZED"

# Warnings -> row kept unchanged, review suggested
AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
DATE_ORDER_INFERRED = "DATE_ORDER_INFERRED"
OUTLIER_AMOUNT = "OUTLIER_AMOUNT"
IMPUTED_KEY_COLLISION = "IMPUTED_KEY_COLLISION"

DESCRIPTIONS: dict[str, str] = {
    MALFORMED_ROW: "field count differs from header",
    BAD_TXN_ID: "transaction_id missing or not a positive integer",
    BAD_DATE: "date missing, unparseable or impossible",
    DATE_OUT_OF_WINDOW: "date outside business-date plausibility window",
    BAD_AMOUNT: "amount is not a number",
    NEGATIVE_AMOUNT: "negative amount (refund/reversal, not a sale)",
    ZERO_AMOUNT: "zero amount (void/test scan)",
    AMOUNT_ABOVE_CEILING: "amount above configured ceiling",
    MISSING_AMOUNT: "amount missing and not imputable",
    BAD_STORE: "store_id missing or malformed",
    BAD_CATEGORY: "category missing or not allowed",
    ID_CONFLICT: "transaction_id reused with different content",
    DUPLICATE_EXACT: "exact repeat of an earlier row",
    DUPLICATE_CONTENT: "same date/amount/store/category as an earlier row",
    TXN_ID_NORMALIZED: "leading zeros removed from transaction_id",
    DATE_REFORMATTED: "date converted to ISO YYYY-MM-DD",
    AMOUNT_NORMALIZED: "currency symbol / separators removed",
    AMOUNT_ROUNDED: "amount rounded to 2 decimals (half-up)",
    AMOUNT_IMPUTED: "missing amount filled with group median",
    STORE_NORMALIZED: "store_id canonicalised to S###",
    CATEGORY_NORMALIZED: "category canonicalised (case/spacing/alias)",
    AMBIGUOUS_DATE: "date valid as both MM/DD and DD/MM; configured order used",
    DATE_ORDER_INFERRED: "date only valid in the non-configured order",
    OUTLIER_AMOUNT: "amount is a robust-z outlier within its category (kept)",
    IMPUTED_KEY_COLLISION: "imputed row matches an observed row's content key",
}

ERRORS = frozenset({
    MALFORMED_ROW, BAD_TXN_ID, BAD_DATE, DATE_OUT_OF_WINDOW, BAD_AMOUNT, NEGATIVE_AMOUNT,
    ZERO_AMOUNT, AMOUNT_ABOVE_CEILING, MISSING_AMOUNT, BAD_STORE, BAD_CATEGORY, ID_CONFLICT,
})
DUPLICATES = frozenset({DUPLICATE_EXACT, DUPLICATE_CONTENT})
REPAIRS = frozenset({
    TXN_ID_NORMALIZED, DATE_REFORMATTED, AMOUNT_NORMALIZED, AMOUNT_ROUNDED, AMOUNT_IMPUTED,
    STORE_NORMALIZED, CATEGORY_NORMALIZED,
})
WARNINGS = frozenset({AMBIGUOUS_DATE, DATE_ORDER_INFERRED, OUTLIER_AMOUNT, IMPUTED_KEY_COLLISION})

# Row fates (R-OUT-03)
KEPT_CLEAN = "KEPT_CLEAN"
KEPT_REPAIRED = "KEPT_REPAIRED"
KEPT_IMPUTED = "KEPT_IMPUTED"
REMOVED_DUPLICATE = "REMOVED_DUPLICATE"
QUARANTINED = "QUARANTINED"
KEPT_FATES = frozenset({KEPT_CLEAN, KEPT_REPAIRED, KEPT_IMPUTED})

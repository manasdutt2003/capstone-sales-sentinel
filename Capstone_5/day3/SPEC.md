# SPEC.md — Sales Sentinel: ledger-first sales data cleaning

> **This file is the contract.** Tests are written from it, code is written to
> satisfy it, and hooks enforce that every rule below is covered by a test.
> Every rule has a stable ID (`R-<AREA>-<NN>`). Tests cite rule IDs in their
> names or docstrings; `tools/spec_coverage.py` fails if any rule is uncovered.
> Only the human / orchestrator may change this file (see `CLAUDE.md`).

**Version:** 1.1.0  ·  **Status:** Approved  ·  **Owner:** Orchestrator (human-approved)

---

## 0. Problem in one paragraph

A retail chain receives a daily CSV of sales transactions from 50+ stores
(`transaction_id, date, amount, store_id, category`). It arrives with missing
values, duplicates, invalid amounts and mixed date formats; an analyst cleans
it by hand for 2 hours a day. We replace that with `python src/main.py`.

## 1. What makes this approach different ("ledger-first")

Most cleaning scripts are a chain of `dropna()` / `drop_duplicates()` calls:
rows vanish and nobody can say why. Sales Sentinel treats cleaning as an
**accounting problem**:

1. **Every input row gets a fate** — `KEPT_CLEAN`, `KEPT_REPAIRED`,
   `KEPT_IMPUTED`, `REMOVED_DUPLICATE` or `QUARANTINED` — with machine-readable
   reason codes, written to a **row ledger**. Nothing is silently dropped.
2. **Rows balance like a ledger**: `processed = kept + duplicates + quarantined`.
   If they don't, the run fails (exit 1). Money is reconciled the same way.
3. **Quarantine, don't delete**: bad rows go to `quarantine.csv` with their
   original raw values and *all* their problems (not just the first), so the
   store can be told exactly what to fix.
4. **Diagnose all, fix only the cosmetic**: we repair what is unambiguous
   (date format, `$1,200`, `s001`), never invent business meaning
   (no `abs()` on negatives, no guessing garbage text).
5. **Money is `Decimal`, never `float`** — `150.50` stays `150.50`.
6. **Policies are config, not code** — dedupe policy, imputation strategy,
   date order, allowed categories live in `config/pipeline.toml`.
7. **Self-checking output**: the clean file is re-validated after writing
   (post-condition) and the pipeline is a fixed point on its own output.
8. **Zero runtime dependencies** — Python ≥ 3.11 standard library only.

## 2. Inputs

| Column | Type | Rule family |
|---|---|---|
| transaction_id | positive integer | R-TXN |
| date | calendar date | R-DATE |
| amount | money, 2 dp | R-AMT, R-IMP |
| store_id | `S` + 3 digits | R-STORE |
| category | one of configured set | R-CAT |

## 3. Rules

### 3.1 Ingestion (R-ING)

- **R-ING-01 — Path resolution.** Input path precedence: CLI `--input` >
  env `SALES_SENTINEL_INPUT` > config `paths.input`. Same for output dir
  (`--output-dir` > `SALES_SENTINEL_OUTPUT_DIR` > `paths.output_dir`). Relative
  paths given on the CLI/env resolve against the CWD; relative paths inside a
  config file resolve against that config file's directory. No absolute path
  is hardcoded anywhere in `src/`.
- **R-ING-02 — Missing / unreadable input.** File missing, a directory, or
  unreadable → exit code **2**, one-line `ERROR:` message on stderr, no Python
  traceback, and **no output files are created**.
- **R-ING-03 — Encoding.** Decode as UTF-8 with BOM stripping (`utf-8-sig`);
  on failure fall back to `cp1252`, then `latin-1`. The encoding used is
  recorded in the report.
- **R-ING-04 — Header.** Header names are normalised (trim, lower-case). All 5
  required columns must exist, else exit 2 naming the missing columns.
  Duplicate column names → exit 2. Extra columns are ignored and listed in the
  report. Column order does not matter.
- **R-ING-05 — Empty input.** A zero-byte/whitespace-only file or a header with
  no data rows → exit 2 (`no data rows`). An empty daily file is an upstream
  failure, not a clean day.
- **R-ING-06 — Row shape.** Fully blank lines are skipped and counted
  (`blank_lines`), not treated as rows. A row whose field count differs from
  the header is quarantined with `MALFORMED_ROW`.

### 3.2 Field rules

A row is checked against **every** field rule; all failures are recorded
(diagnose-all, not first-fail).

**transaction_id (R-TXN)**
- **R-TXN-01** — Trimmed value must be ASCII digits only and > 0. Leading zeros
  are normalised (`007` → `7`, repair `TXN_ID_NORMALIZED`). Anything else
  (empty, `abc`, `1.0`, `-3`, `0`, non-ASCII digits like `١٢`) → `BAD_TXN_ID`.

**date (R-DATE)**
- **R-DATE-01 — Accepted formats**, output always ISO `YYYY-MM-DD`:
  `YYYY-MM-DD` (canonical), `YYYY/MM/DD`, `YYYY.MM.DD`, `YYYYMMDD`,
  `MM/DD/YY`, `MM/DD/YYYY`, `MM-DD-YYYY`, `MM-DD-YY`, and ISO timestamps
  `YYYY-MM-DD[T ]HH:MM[:SS…]` (time discarded). Two-digit years map to
  `2000 + YY`. Any non-canonical accepted form → repair `DATE_REFORMATTED`.
- **R-DATE-02 — Ambiguity.** For `a/b/y` forms the configured order
  (`dates.order`, default `MDY`) wins. If the other order is *also* a valid,
  different date (e.g. `03/04/26`) the row is kept with warning
  `AMBIGUOUS_DATE`. If only the other order is valid (e.g. `21/10/2026`), it is
  used with warning `DATE_ORDER_INFERRED`.
- **R-DATE-03 — Unparseable.** Empty, garbage (`invalid`) or impossible dates
  (`2025-02-29`, `13/45/26`) → `BAD_DATE`.
- **R-DATE-04 — Plausibility window.** Business date = config
  `dates.business_date` if set, else the most frequent valid date in the
  batch (ties → latest). Dates after `business_date + future_tolerance_days`
  (default 0) or before `business_date − max_age_days` (default 7) →
  `DATE_OUT_OF_WINDOW`.

**amount (R-AMT)**
- **R-AMT-01 — Missing.** Empty / whitespace / `null` / `none` / `na` / `n/a` /
  `nan` / `-` (case-insensitive) → missing; handled by R-IMP.
- **R-AMT-02 — Cosmetic repair.** Currency symbols (`$ ₹ € £`), internal
  spaces and correct thousands separators (`1,200.50`) are stripped → repair
  `AMOUNT_NORMALIZED`.
- **R-AMT-03 — Non-numeric.** After repair the value must match a plain
  decimal (`[+-]?digits[.digits]`). Anything else (`abc`, `xyz`, `inf`,
  `1e3`, `12.3.4`) → `BAD_AMOUNT`. Garbage is never coerced to a number.
- **R-AMT-04 — Negative.** `< 0` (incl. accounting form `(50.00)`) →
  `NEGATIVE_AMOUNT`. Negatives are refunds/reversals, not sales; we never
  `abs()` them.
- **R-AMT-05 — Zero.** `0` after rounding (incl. `0.004`, `-0.00`) →
  `ZERO_AMOUNT` (voids/test scans are not sales).
- **R-AMT-06 — Ceiling.** `> amounts.max_amount` (default 100000.00) →
  `AMOUNT_ABOVE_CEILING`.
- **R-AMT-07 — Precision.** Arithmetic in `Decimal`; quantised to 2 dp with
  `ROUND_HALF_UP`; if rounding changed the value → repair `AMOUNT_ROUNDED`.
  Output always has exactly 2 decimals (`45` → `45.00`; this is formatting, not
  a repair).
- **R-AMT-08 — Outliers are flagged, never removed.** Within each category,
  over kept rows with observed amounts (n ≥ 5, MAD > 0), robust
  z = 0.6745·(x − median)/MAD. `|z| > amounts.outlier_z` (default 3.5) →
  warning `OUTLIER_AMOUNT`; the row stays. (Statistical rule, not ML.)

**store_id (R-STORE)**
- **R-STORE-01** — Trim, upper-case, accept `S`, optional `-`/`_`/space, then
  1–3 digits (number ≥ 1); canonical form `S%03d` (`s1` → `S001`, repair
  `STORE_NORMALIZED`). Anything else, incl. empty → `BAD_STORE`.

**category (R-CAT)**
- **R-CAT-01** — Trim, collapse inner whitespace, case-fold; must match an
  allowed category or a configured alias (`apparel` → `Clothing`); output the
  canonical spelling (repair `CATEGORY_NORMALIZED` if changed). Else
  `BAD_CATEGORY`.

### 3.3 Duplicates (R-DUP)

Run on rows that passed every field rule, in file order.

- **R-DUP-01 — Exact duplicate.** Same transaction_id and identical
  normalised content as an earlier kept row → `REMOVED_DUPLICATE`,
  code `DUPLICATE_EXACT`, `duplicate_of=<id>`.
- **R-DUP-02 — ID conflict.** Same transaction_id, different content →
  later row `QUARANTINED` with `ID_CONFLICT` (we can't know which is true).
- **R-DUP-03 — Content duplicate** (policy `content`, default). Same
  `(date, amount, store_id, category)` as an earlier kept row but a different
  id → `REMOVED_DUPLICATE`, code `DUPLICATE_CONTENT`, `duplicate_of=<first id>`.
  Only rows with an **observed** amount take part — a missing/imputed amount
  is never evidence of duplication. Policy `id` disables this rule.
- **R-DUP-04 — Survivor.** The first occurrence in file order is kept.
- **R-DUP-05 — Burst report.** Content-duplicate clusters with size ≥
  `dedupe.burst_threshold` (default 5) are listed in the report as suspected
  POS replay bursts, with their size and revenue removed.

### 3.4 Imputation (R-IMP)

- **R-IMP-01 — Strategy.** `amounts.missing_strategy`:
  `group_median` (default) or `quarantine` (missing → `MISSING_AMOUNT`).
  `group_median` fills with the median of observed amounts for the same
  `(store_id, category)` if that group has ≥ `min_group_size` (default 3)
  values; else the category median (same threshold); else the global median.
  Value quantised to 2 dp; repair `AMOUNT_IMPUTED`; ledger note records the
  method and n (e.g. `store_category_median S001/Electronics n=9`).
- **R-IMP-02 — Only valid rows are imputed.** A row with a missing amount
  *and* another error is quarantined, not imputed.
- **R-IMP-03 — Order independence.** Medians are computed from kept rows
  **after** dedupe and **before** any imputation; imputed values never feed
  other imputations. If no observed amounts exist at all, missing rows are
  quarantined `MISSING_AMOUNT`.
- **R-IMP-04 — Collision guard.** If an imputed row's content key equals the
  key of any kept row — observed **or another imputed row** — **both** rows get
  warning `IMPUTED_KEY_COLLISION` and a note naming the partner id (on a re-run
  either one could be the row that is deduped). *(v1.1.0: widened after the
  R-INV-03 test found the observed partner was being removed on a second pass.)*

### 3.5 Outputs (R-OUT)

All written to the output dir, created if missing.

- **R-OUT-01 — `clean_sales.csv`.** Header exactly
  `transaction_id,date,amount,store_id,category`; only kept rows; input order;
  ISO dates; 2-dp amounts; canonical store/category.
- **R-OUT-02 — `quarantine.csv`.** `line_no, transaction_id, date, amount,
  store_id, category, reason_codes` with the **original raw values** and all
  reason codes `|`-separated.
- **R-OUT-03 — `row_ledger.csv`.** Exactly one line per processed input row:
  `line_no, transaction_id, fate, codes, duplicate_of, note`.
- **R-OUT-04 — `data_quality_report.txt`** contains these lines verbatim
  (numbers vary):
  ```
  Rows processed: X
  Rows removed: Y (duplicates)
  Nulls filled: Z
  Invalid entries fixed/skipped: W (fixed A, skipped B)
  Overall data quality score: S/100 (G)
  ```
  where Y = duplicate rows removed, Z = amounts imputed, A = kept rows with at
  least one non-imputation repair, B = quarantined rows, W = A + B. Followed by
  sections: reconciliation, score breakdown, issues by code, duplicate bursts,
  money reconciliation, warnings, output confidence, files.
- **R-OUT-05 — `run_manifest.json`.** Tool version, UTC timestamp, sha256 of
  input, config and each output, effective config, counts.
- **R-OUT-06 — Atomic writes.** Each file is written to a temp file in the
  same dir then `os.replace`d, so downstream jobs never read a half file.

### 3.6 Invariants (R-INV) — checked on every run

- **R-INV-01 — Row reconciliation.**
  `processed == kept + removed_duplicates + quarantined` and the ledger has
  `processed` lines. Violation → exit 1.
- **R-INV-02 — Post-condition.** Every row of `clean_sales.csv` re-validates
  with zero errors and zero repairs; transaction_ids are unique. Violation →
  exit 1.
- **R-INV-03 — Idempotence.** Running the pipeline on its own
  `clean_sales.csv` (same config, same business date) produces an identical
  clean file with 0 duplicates, 0 nulls filled and 0 quarantined
  (except rows carrying `IMPUTED_KEY_COLLISION`).
- **R-INV-04 — Determinism.** Same input + config ⇒ byte-identical
  `clean_sales.csv`, `quarantine.csv`, `row_ledger.csv`.

### 3.7 Data quality score (R-SCORE)

- **R-SCORE-01 — Raw input health, 0–100.** Weighted mean of four DAMA
  dimensions measured on the *input* (weights in config, must sum to 1):
  - completeness (0.30) = non-empty required cells / required cells
  - validity (0.30) = non-empty cells passing their field rule (incl. after
    cosmetic repair) / non-empty cells
  - consistency (0.15) = valid cells already in canonical form / valid cells
  - uniqueness (0.25) = 1 − duplicate rows / processed rows

  Grade: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, else F.
- **R-SCORE-02 — Output confidence.** Report yield (kept/processed) and the
  split of kept rows into untouched / repaired / imputed percentages.
- **R-SCORE-03 — Money reconciliation.** Raw total of all numerically
  parseable amounts = clean total − imputed total + duplicate total +
  quarantined-parseable total; printed and checked.

### 3.8 Operations (R-OPS)

- **R-OPS-01 — Exit codes.** 0 ok · 1 invariant failure · 2 input/config error
  · 3 quality gate failed (only with `--strict`: quarantine rate >
  `quality_gate.max_quarantine_rate` or score < `quality_gate.min_score`).
- **R-OPS-02 — Config.** `config/pipeline.toml`; invalid values (unknown
  policy, weights not summing to 1, bad business date) → exit 2. CLI flags
  `--dedupe-policy`, `--missing-strategy`, `--business-date` override config.
- **R-OPS-03 — No network, no secrets, no DB, no UI, no ML.** (Out of scope per
  the problem statement.)
- **R-OPS-04 — Console.** Logs to stderr; one summary line to stdout.

## 4. Acceptance on `data/sample_sales_data.csv` (golden numbers)

Derived by hand from the file before coding (tests assert these):

| Metric | Expected | Why |
|---|---|---|
| Rows processed | 200 | 200 data rows, all ids unique |
| Quarantined | 6 | ids 10 `abc`, 38 `xyz` (BAD_AMOUNT); 13 `-50.00` (NEGATIVE); 44 `0.00`, 68 `0` (ZERO); 21 `invalid` (BAD_DATE) |
| Duplicates removed | 70 | 5 content clusters: 150.50/S001/Electronics ×53, …/Clothing ×12, …/Grocery ×6, 45.00/S001/Clothing ×2, 280.50/S001/Electronics ×2 |
| Nulls filled | 32 | 32 empty amounts, all on otherwise-valid rows |
| Fixed | 5 | dates on ids 4, 16, 33, 55, 71 reformatted |
| Kept | 124 | 200 − 70 − 6 |
| Business date | 2026-10-21 | modal date; id 9 (2026-10-20) is inside the window |
| Outlier flagged, kept | id 3 (3500.00 Electronics) | robust z ≫ 3.5 |

## 5. Out of scope

Database integration, visualisation/Power BI export, ML anomaly detection,
API endpoints, web UI (problem statement "Don't build").

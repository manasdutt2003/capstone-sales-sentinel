# DECISIONS.md — key cleaning decisions and why

Each decision cites the SPEC rule it produced. Numbers are from `data/sample_sales_data.csv`
(200 rows) with the default config.

| # | Issue found | Decision | Alternatives rejected | Rule |
|---|---|---|---|---|
| D-01 | Bad rows are usually dropped silently | **Quarantine, don't delete.** Every rejected row goes to `quarantine.csv` with raw values + *all* reason codes; every input row gets a fate in `row_ledger.csv` | `dropna()` and move on: unauditable, the store never learns what to fix | R-OUT-02/03, R-INV-01 |
| D-02 | Money as float drifts (`0.1+0.2`) | `Decimal` end to end, `ROUND_HALF_UP` to 2 dp | float + `round()` (banker's rounding, binary error) | R-AMT-07 |
| D-03 | 6 date formats in one file (`2026-10-21`, `10/21/26`, `2026/10/21`, `10-21-2026`, `20261021`, `invalid`) | Explicit pattern list, ISO output; `MDY` because `10/21/26` proves month-first; ambiguous dates kept with a warning; garbage → quarantine | `dateutil.parser` (guesses silently, adds a dependency); dropping all non-ISO rows (loses 5 good sales) | R-DATE-01…03 |
| D-04 | **All 200 transaction_ids are unique, yet 70 rows (35 %) repeat another row's date+amount+store+category.** `150.50/S001/Electronics` appears 53 times, plus ×12 and ×6 for the same amount/store in other categories | Default `content` dedupe, first occurrence kept, `duplicate_of` recorded; clusters ≥ 5 reported as *suspected POS replay bursts* with the revenue removed (10,559.50) so the business can confirm. `--dedupe-policy id` switches it off | Dedupe on id only (would report 0 duplicates and pass 70 replays into revenue); dedupe on all columns incl. id (same result) | R-DUP-01…05 |
| D-05 | 32 empty amounts | Fill with **median** of `(store, category)` → `category` → global, min group 3; marked `KEPT_IMPUTED`; imputed revenue (10,175.76) shown separately. `--missing-strategy quarantine` available for finance use | Mean (one 3,500.00 sale skews it); fill with 0 (creates fake zero sales); drop (loses 16 % of transactions whose other fields are fine) | R-IMP-01 |
| D-06 | `abc`, `xyz` amounts | Quarantine `BAD_AMOUNT`; never coerce garbage to a number or impute over it (garbage means the row is corrupted; an empty cell only means a value wasn't captured) | Treat garbage as missing and impute | R-AMT-03 |
| D-07 | Stage order changes results | validate → window → quarantine → **dedupe → impute** → outliers. Dedupe first so (a) replayed values don't bias medians and (b) a guessed amount is never evidence of duplication | Impute first: the 53× replay would pull S001/Electronics' median to 150.50 | R-IMP-03, R-DUP-03 |
| D-08 | `-50.00` | Quarantine `NEGATIVE_AMOUNT` — it is a refund/reversal, a different business event | `abs()` (turns a refund into a sale) | R-AMT-04 |
| D-09 | `0.00` and `0` | Quarantine `ZERO_AMOUNT` (voids / test scans) | Keep (inflates transaction counts, deflates average basket) | R-AMT-05 |
| D-10 | `3500.00` Electronics (robust z ≈ 12.8) | **Flag, don't remove** (`OUTLIER_AMOUNT` warning; row kept). Robust z on median/MAD per category — a statistical rule, not ML (ML is out of scope) | Remove outliers (a real TV sale is not an error); IQR on mean/stddev (masked by the outlier itself) | R-AMT-08 |
| D-11 | Imputed rows often equal a real row (median of an odd group *is* a real value): 26 of 32 imputations collide | Flag **both** rows `IMPUTED_KEY_COLLISION` with the partner id; contract: dedupe the clean file by `transaction_id` only. Idempotence (R-INV-03) holds except for flagged rows, and exactly with `--dedupe-policy id` | Jitter imputed values to avoid collisions (fabricates precision); use mean (outlier-sensitive) | R-IMP-04, R-INV-03 |
| D-12 | One-off date `2026-10-20` in a 10-21 batch | Infer business date as the modal date; accept anything within 7 days back, nothing in the future (configurable) | Reject everything ≠ modal date (late-posted sales are normal) | R-DATE-04 |
| D-13 | Quality score definition | Four DAMA dimensions on the *raw* input (completeness .30, validity .30, consistency .15, uniqueness .25) → 90.0 (A) on the sample; plus output confidence (yield 62 %, 70 % of kept rows untouched) | One opaque "% rows kept" (hides *why*) | R-SCORE-01/02 |
| D-14 | Empty daily file | Exit 2, not "0 rows, all clean" — an empty feed from 50 stores is an upstream outage | Treat as a clean day | R-ING-05 |
| D-15 | Automation needs machine-readable failure | Exit codes 0/1/2/3; `--strict` quality gate (quarantine rate > 10 % or score < 60 → 3) so a scheduler can alert | Always exit 0 and rely on someone reading the report | R-OPS-01 |
| D-16 | Downstream may read a half-written file | Atomic writes (temp file + `os.replace`) and a manifest with sha256 of input, config and outputs | Write in place | R-OUT-05/06 |
| D-17 | Dependencies | Runtime is stdlib only (csv, decimal, tomllib); pandas would be convenient but adds 50 MB and float semantics for a 200-row job | pandas | R-OPS-03 |

## Open questions for the business

1. Are the 53 identical `150.50/S001/Electronics` sales a replay? If S001 genuinely sells one fixed-price
   item all day, switch to `--dedupe-policy id` (revenue impact +10,559.50).
2. Should refunds (negatives) be kept in a separate refunds feed instead of quarantined?
3. Is imputing missing amounts acceptable for revenue reporting, or should those rows go back to stores?

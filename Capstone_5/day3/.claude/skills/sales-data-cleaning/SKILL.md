---
name: sales-data-cleaning
description: Domain playbook for cleaning retail sales transaction CSVs the Sales Sentinel way — ledger-first fates, Decimal money, date-format resolution, duplicate policy, median imputation, quarantine codes and the edge-case checklist. Use whenever implementing, testing, reviewing or explaining any cleaning rule in this project, or when a new messy-data pattern shows up.
---

# Sales data cleaning — the Sales Sentinel playbook

This skill is *how we think* about messy sales data. `SPEC.md` is *what we must do* (rule IDs);
when they differ, **SPEC.md wins** and this skill should be updated by the orchestrator.

## 1. The five questions for every messy value

1. **Is it unambiguous?** → repair it, record a repair code, keep the row.
   (`2026/10/21` → `2026-10-21`, `$1,200.50` → `1200.50`, `s1` → `S001`, `apparel` → `Clothing`)
2. **Does fixing it need business judgement?** → quarantine with a reason code; never guess.
   (`abc`, `-50.00` refund, `0.00` void, `invalid` date, unknown category)
3. **Is it simply absent?** → policy decides (`group_median` impute, or quarantine). Mark it.
4. **Is it suspicious but plausible?** → keep and **warn** (outlier, ambiguous date). Humans review.
5. **Can I prove where every row went?** → ledger fate + reconciliation. If not, fail the run.

## 2. Row fates (exactly one per input row)

| Fate | Meaning | In clean file? |
|---|---|---|
| `KEPT_CLEAN` | valid as received | yes |
| `KEPT_REPAIRED` | valid after cosmetic repair | yes |
| `KEPT_IMPUTED` | amount was missing, filled by median | yes (flagged in ledger) |
| `REMOVED_DUPLICATE` | exact or content duplicate of an earlier kept row | no |
| `QUARANTINED` | ≥ 1 error; all errors listed | no → `quarantine.csv` |

`processed = kept + duplicates + quarantined` — always. Money balances the same way.

## 3. Field recipes

**Money.** `Decimal(str)`, never `float(str)`. Strip `$ ₹ € £`, spaces, *valid* thousands separators
(`1,234.50` yes, `1,20` no → BAD). Accounting negatives `(50.00)` are negative. Quantise
`ROUND_HALF_UP` to 0.01 (`10.005` → `10.01`; Python's default banker's rounding would give `10.00`).
Check zero *after* rounding (`0.004` is a zero sale). Scientific notation (`1e3`) is rejected:
POS systems don't emit it; spreadsheets corrupting the export do.

**Dates.** Fixed list of explicit patterns — no "smart" parser that guesses. For `a/b/yy[yy]`:
configured order wins (`MDY` here, because the sample contains `10/21/26`); if the other order is
also a valid *different* date, warn `AMBIGUOUS_DATE`; if only the other order is valid
(`21/10/2026`), use it and warn `DATE_ORDER_INFERRED`. Then a plausibility window around the
business date (modal date of the batch) catches typo years (`2016-10-21`).

**IDs.** ASCII digits only (`[0-9]`, not `\d` — `\d` matches Arabic-Indic `١٢`). Leading zeros
normalised. `0` and negatives are invalid.

**Store / category.** Canonicalise case, whitespace, separators (`S-12` → `S012`); categories via an
allow-list + aliases in config. Unknown → quarantine (a new category is a business event, not a typo).

## 4. Duplicates — the decision that matters most

On the sample, **every transaction_id is unique**, yet 70 rows (35 %) repeat another row's
`(date, amount, store, category)`; one key (`150.50 / S001 / Electronics`) appears 53 times.
That is the signature of a POS replay / double-submit, not 53 identical sales.

- Default policy `content`: first occurrence survives, later ones `REMOVED_DUPLICATE` with
  `duplicate_of`. Clusters ≥ 5 are reported as *suspected replay bursts* with revenue removed, so the
  business can confirm.
- Policy `id`: only exact `transaction_id` repeats are duplicates — use when the source guarantees
  unique sales and identical baskets are normal.
- **Missing amounts are never duplicate evidence.** Dedupe runs *before* imputation.
- Same id + different content = `ID_CONFLICT` (quarantine; we can't know which is true).

## 5. Imputation

Median of observed amounts, most specific group first: `(store, category)` → `category` → global,
each needing ≥ `min_group_size` values. Medians are frozen after dedupe and before any fill, so the
result does not depend on row order. Median, not mean: one 3500.00 sale must not inflate a fill.

**Known consequence:** a median of an odd-sized group *is* one of the observed values, so an imputed
row often has the same content key as a real row (26 of 32 on the sample). Both rows get
`IMPUTED_KEY_COLLISION`; downstream consumers must dedupe the clean file by `transaction_id`, never by
content. If imputed revenue is unacceptable, run `--missing-strategy quarantine`.

## 6. Data-quality score

Raw-input health on four DAMA dimensions (weights in config): completeness 0.30, validity 0.30,
consistency 0.15, uniqueness 0.25 → 0–100 + grade. It measures *what arrived*, so the trend over
days tells you which stores are degrading. Output confidence (yield, % untouched / repaired /
imputed) tells you how much to trust *what we produced*.

## 7. Edge-case checklist (tester: walk this for every rule)

| Category | Probes |
|---|---|
| Empty / null | `""`, whitespace, `NULL`, `NaN`, `-`, missing column, header-only file, zero-byte file |
| Boundaries | amount `0.00` / `0.01` / `max` / `max+0.01`; window `bd-7` / `bd-8` / `bd+1`; group size `k-1` / `k`; outlier z exactly on threshold |
| Invalid types | `"10"` vs `10.00`, `1e3`, `inf`, `12.3.4`, `1.0` as id |
| Large input | 100k-row file (performance), very long field |
| Special text | Unicode digits `١٢`, emoji, SQL quote `'; DROP TABLE`, BOM, cp1252 bytes |
| Time & dates | leap day `2024-02-29` ok / `2025-02-29` bad, 2-digit years, `03/04/26` ambiguity, ISO timestamps with TZ |
| Duplicates | exact repeat, normalised repeat (`10/21/26,10,s001`), id conflict, missing-amount pairs, invalid row before valid twin |
| Failures | missing file, directory as input, unreadable config, bad TOML, weights ≠ 1, output dir not writable |

## 8. Reason-code vocabulary

All codes live in `src/sentinel/codes.py` with descriptions; the report and the MCP `explain_row`
tool print them. Add a code there first, then to SPEC.md, then test, then implement.

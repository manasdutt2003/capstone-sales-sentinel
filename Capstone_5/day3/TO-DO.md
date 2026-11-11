# TO-DO.md — living task board

> Both agents read this first and update their own items. Rule IDs point into
> `SPEC.md`. Tick `[x]` only when the hook-verified exit criterion is met.

## Problem-statement must-haves

- [x] Runs without manual intervention: `python src/main.py`
- [x] Processes the sample CSV completely (200/200 rows reconciled — R-INV-01)
- [x] Outputs `clean_sales.csv` and `data_quality_report.txt` (R-OUT-01, R-OUT-04)
- [x] Handles all data-quality issues (missing, duplicates, invalid amounts, mixed dates)
- [x] 3–5 tests covering normal and edge cases → 5 test modules (see below)
- [x] No hardcoded file paths (config + CLI + env — R-ING-01)
- [x] No secrets committed (`.gitignore`, guard denies `.env*` reads)
- [x] Key decisions in `DECISIONS.md`
- [x] AI usage, mistakes caught & fixes in `REFLECTION.md`

## P0 Contract (orchestrator)
- [x] SPEC.md v1.0.0 with rule IDs and golden numbers
- [x] PLAN.md, TO-DO.md, DECISIONS.md
- [x] CLAUDE.md with embedded **coder** and **tester** agent definitions

## P1 Guardrails (orchestrator)
- [x] `.claude/agents/coder.md`, `.claude/agents/tester.md` (mirror CLAUDE.md)
- [x] `.claude/hooks/guard_boundaries.py` + `ownership.json` (PreToolUse)
- [x] `.claude/hooks/post_edit_feedback.py` (PostToolUse)
- [x] `.claude/hooks/subagent_gate.py` (SubagentStop: coder→tests green, tester→spec coverage)
- [x] `.claude/hooks/session_context.py` (SessionStart status injection)
- [x] `.claude/skills/sales-data-cleaning/SKILL.md`
- [x] `.mcp.json` + `tools/mcp_server/dq_server.py` (profile, run, explain_row, spec tools)

## P2 Red tests (tester) — one module per concern
- [x] `tests/test_ingest.py` — R-ING-01…06, R-OPS-01/02
- [x] `tests/test_field_rules.py` — R-TXN, R-DATE, R-AMT, R-STORE, R-CAT tables
- [x] `tests/test_pipeline.py` — R-DUP, R-IMP, R-AMT-08, R-DATE-04, R-INV-01/02
- [x] `tests/test_e2e_sample.py` — golden numbers (SPEC §4), R-OUT, R-INV-03/04, R-SCORE
- [x] `tests/test_properties.py` — Hypothesis fuzzing of invariants

## P3 Green code (coder)
- [x] config.py, ingest.py, codes.py, rules.py
- [x] pipeline.py (stage order per DECISIONS D-07)
- [x] scoring.py, report.py, cli.py, main.py

## P4 Evaluate
- [x] Full suite green
- [x] `spec_coverage --check` = 100 %
- [x] Coverage ≥ 90 % (95 % branch)
- [x] `mutation_smoke` ≥ 70 % killed (90.4 %)

## Backlog / ideas (not required)
- [ ] Per-store quarantine e-mail digest (needs SMTP → out of scope for POC)
- [ ] Multi-file batch mode (`--input data/*.csv`) with a combined ledger
- [ ] Make `burst_threshold` adaptive to store volume

## Hand-off log
<!-- tester appends "Failure report", coder appends "Fixed"/"Dispute". Newest last. -->
- 2026-10-22 bootstrap (single session, see REFLECTION.md): SPEC v1.0.0 golden numbers hand-derived; src + tests written; suite green except R-INV-03.
- 2026-10-22 tester → coder: test_R_INV_03_fixed_point_on_own_output | R-IMP-04 | expected only flagged rows to dedupe on re-run | got observed partners + imputed-vs-imputed rows removed.
- 2026-10-22 orchestrator: SPEC R-IMP-04 widened (both parties flagged, imputed-vs-imputed) → v1.1.0.
- 2026-10-22 coder: impute() now tracks key owners and flags both rows; suite green.
- 2026-10-22 orchestrator → tester: mutation 147/198 (74 %); survivors concentrated in scoring.py + boundaries (group size, outlier threshold, future tolerance, `"+"` amount).
- 2026-10-22 tester: added exact score dimensions, grade edges, weight sensitivity, min-group / outlier / tolerance boundaries, `"+"`/`"$"` amounts. No src change needed.
- 2026-10-22 tester: added config-validation and quality-gate boundary tests (R-OPS-01/02).
- 2026-10-22 orchestrator: live Claude Code acceptance test — coder Edit/sed on tests/ denied, tester Write on src/ denied, tester used MCP profile_csv; gates fired.
- NEXT: tester agent re-derives the suite from SPEC.md in a fresh context (independence check).

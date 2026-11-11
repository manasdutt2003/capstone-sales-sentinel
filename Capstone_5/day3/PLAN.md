# PLAN.md — how we build Sales Sentinel

> Read with `SPEC.md` (what) and `TO-DO.md` (status). This file is the *how*:
> architecture, phases, who does what, and how we know we're done.

## 1. Workflow (from the "AI Coding & Testing" deck)

```
                SPEC.md  (the contract, rule IDs)
               /                               \
     tester agent                          coder agent
  writes tests/ from SPEC only          writes src/ to pass tests
  never touches src/  (hook-enforced)   never touches tests/ (hook-enforced)
               \                               /
                   pytest  (the judge)  +  spec_coverage  +  mutation_smoke
```

Every feature goes through: **1 Spec → 2 Tests (red) → 3 Code (green) →
4 Evaluate (coverage, mutation, review) → 5 Fix** — and every bug found
becomes a permanent test (loop back to step 2).

## 2. Architecture

```
src/main.py                  thin entry point: `python src/main.py`
src/sentinel/
  config.py     load + validate config/pipeline.toml (tomllib), path precedence  R-ING-01, R-OPS-02
  ingest.py     bytes → decoded text → header checks → RawRow list              R-ING-*
  codes.py      every reason code + description (single vocabulary)
  rules.py      pure field parsers: txn_id, date, amount, store, category       R-TXN/DATE/AMT/STORE/CAT
  pipeline.py   validate → window → quarantine → dedupe → impute → outliers
                → fates → invariants                                           R-DUP, R-IMP, R-INV
  scoring.py    DAMA dimensions, grade, confidence, money reconciliation        R-SCORE-*
  report.py     render report, atomic writers, manifest                         R-OUT-*
  cli.py        argparse, exit codes, orchestration                             R-OPS-*
```

Design principles:
- **Pure functions in `rules.py`** (string in → `FieldResult` out) so the tester
  can table-test them in isolation (Given/When/Then rows).
- **One record object per input row** carries raw values, parsed values,
  errors, repairs, warnings and fate — the ledger is a by-product, not an
  afterthought.
- **Stage order is a correctness decision** (see DECISIONS.md D-07): dedupe
  before imputation, medians before any fill, window after date parsing.
- **Fail loud on broken accounting**: invariants raise `InvariantError` → exit 1.

## 3. Phases

| Phase | Owner | Output | Exit criterion |
|---|---|---|---|
| P0 Contract | Orchestrator + human | SPEC.md, PLAN.md, TO-DO.md, DECISIONS.md, CLAUDE.md | Human approves SPEC v1.0.0 |
| P1 Guardrails | Orchestrator | `.claude/` hooks, agents, skill, `.mcp.json`, MCP server | Guard hook denies a cross-boundary edit in a dry run |
| P2 Red tests | **tester** | `tests/*` citing rule IDs | `spec_coverage --check` passes; tests fail (no impl) |
| P3 Green code | **coder** | `src/sentinel/*` | Full suite green; coder's SubagentStop gate passes |
| P4 Evaluate | tester + orchestrator | coverage ≥ 90 %, mutation score ≥ 70 %, review notes | `tools/mutation_smoke.py` report |
| P5 Fix loop | tester → coder | new tests for every survivor/bug | All green again |
| P6 Docs | Orchestrator | DECISIONS.md, REFLECTION.md, README.md | Must-have checklist in TO-DO.md all ticked |

## 4. Agent hand-off protocol

1. Orchestrator picks the next open item in `TO-DO.md` and names the rule IDs.
2. **tester** writes/extends tests for those IDs only from SPEC.md, runs them,
   appends a *Failure report* (test id → rule id → expected vs actual) under
   `TO-DO.md › Hand-off log`.
3. **coder** reads the hand-off log + SPEC, implements in `src/`, runs the
   suite, and may not stop while it is red (SubagentStop hook).
4. If the coder believes a test contradicts SPEC, it writes a
   *Dispute* entry in the hand-off log — it never edits the test. The
   orchestrator rules on it (fix SPEC → tester updates test, or coder complies).
5. Orchestrator runs evaluation (coverage + `mutation_smoke`) and turns every
   surviving mutant into a tester task.

## 5. Evaluation scorecard (deck slide 6)

`pass rate + coverage + mutation score + review notes`

- pass rate: `pytest -q`
- coverage: `pytest --cov=src/sentinel --cov-report=term-missing` (target ≥ 90 %)
- mutation: `python tools/mutation_smoke.py` (AST mutants, target ≥ 70 % killed)
- spec traceability: `python tools/spec_coverage.py --check` (100 % rules)
- review: tester checks for assert-free tests, over-mocking, missing edge
  cases from the deck checklist (empty/null, boundaries, invalid types, large
  input, special text, dates, failures).

## 6. Risks

| Risk | Mitigation |
|---|---|
| Content-dedupe removes legitimate identical sales (35 % of sample) | Policy switch `--dedupe-policy id`; burst report shows clusters + revenue so business decides (D-04) |
| Imputation invents revenue | Configurable `quarantine` strategy; imputed total shown separately in money reconciliation; ledger marks every imputed row |
| MM/DD vs DD/MM ambiguity | Config order + `AMBIGUOUS_DATE` warning, never silent |
| Agent bypasses guard via Bash (`sed -i tests/…`) | Guard also inspects Bash commands for write verbs on forbidden paths |
| Agent edits its own guard | `.claude/**` is read-only for both subagents |

# Sales Sentinel & AI Agent Engineering

A three-day arc through AI-assisted engineering: structured LLM extraction, then a Claude Code
sandbox with custom instructions, hooks and an MCP server, then a real product — **Sales
Sentinel**, a ledger-first cleaning pipeline for daily retail sales CSVs, built and maintained
by **two AI agents that check each other**.

> Week 5 individual capstone · Perficient Global AI First Academy · Author: **Manas Dutt**

## Day 3 — Sales Sentinel

Replaces a two-hour manual job with one command.

```bash
cd Capstone_5/day3
python src/main.py
# OK processed=200 kept=124 duplicates=70 quarantined=6 nulls_filled=32 score=90.0(A) -> output/
```

| | |
|---|---|
| Tests | **180** across 5 modules · **95%** branch coverage |
| Spec traceability | **47/47** SPEC rules cited by tests |
| Mutation testing | **179/198** mutants killed (90.4%) |
| Agent boundary | **26/26** guard cases hold |

### What makes it different

| Typical script | Sales Sentinel |
|---|---|
| `dropna()` / `drop_duplicates()`; rows vanish | **Every input row gets one fate** in `row_ledger.csv`; rows *and money* must reconcile or the run fails |
| bad rows deleted | **Quarantined** with raw values and all reason codes, ready to send back to the store |
| `float` money | `Decimal`, half-up rounding |
| dedupe on id (finds 0 here) | **Content-replay detection** — 70 replays found, bursts reported with revenue impact |
| fill nulls with mean/0 | Hierarchical **median** imputation *after* dedupe, flagged, with collision detection |
| one opaque "quality %" | 4 DAMA dimensions + output confidence + money reconciliation |
| hardcoded paths | CLI > env > TOML config; exit codes 0/1/2/3 for schedulers |
| one AI writes code and tests | **Two agents, hook-enforced boundary**, spec traceability gate, mutation testing |

### The two-agent workflow

```
                SPEC.md  (the contract, rule IDs)
               /                               \
     tester agent                          coder agent
  writes tests/ from SPEC only          writes src/ to pass tests
  never touches src/  (hook-enforced)   never touches tests/ (hook-enforced)
               \                               /
                   pytest  +  spec_coverage  +  mutation_smoke
```

Every feature goes through **Spec → Tests (red) → Code (green) → Evaluate → Fix**, and every bug
found becomes a permanent test. Ask the coder to "just fix the failing test" and the guard
**denies it** and logs the attempt to `.claude/state/audit.jsonl`.

A local **MCP server** (`sales-dq`) gives both agents real data-quality tools, and a domain skill
loads automatically.

### Outputs

| File | Contents |
|---|---|
| `clean_sales.csv` | only valid, cleaned rows |
| `data_quality_report.txt` | summary, reconciliation, score breakdown, issues by code, duplicate bursts, money, quarantine, confidence |
| `quarantine.csv` | rejected rows: raw values + reason codes |
| `row_ledger.csv` | fate, codes, `duplicate_of` and note for **every** input row |
| `run_manifest.json` | sha256 of input/config/outputs, effective config, counts |

## Day 1 — structured LLM extraction

Hardening an invoice-extraction prompt until it returns **parse-safe JSON every run**. The first
attempt drifted — key names changed between runs, output came wrapped in fences with a preamble,
and dates and amounts varied in format. The final prompt pins all six keys, the date format and
the output contract so the reply goes straight to `json.loads()`.

## Day 2 — Claude Code sandbox

A deliberately tiny project used to practise the extension surface: `CLAUDE.md` project
instructions, **hook exit-code semantics** (code 1 is non-blocking and shown only to the user;
code 2 is blocking and fed back to the agent), and a FastMCP `text-tools` server over stdio.

## Verify it

```bash
cd Capstone_5/day3
pip install -r requirements-dev.txt
python -m pytest -q                      # 180 tests
python -m pytest --cov=src/sentinel      # 95% branch
python tools/spec_coverage.py            # 47/47 SPEC rules
python tools/mutation_smoke.py           # 179/198 mutants killed
python tools/hook_selftest.py            # 26/26 boundary cases
```

## Documents

`SPEC.md` (contract) · `PLAN.md` (architecture, phases) · `TO-DO.md` (board) · `CLAUDE.md`
(rules, both agent definitions, hooks, MCP) · `DECISIONS.md` · `REFLECTION.md` ·
`ARCHITECTURE.md`

## Out of scope

Not built, per the problem statement: database integration, visualisation / Power BI export,
ML anomaly detection, API endpoints, web UI.

> **Note:** sample retail data only. API keys were kept in `.env` files, which are git-ignored
> and are **not** included in this repository.

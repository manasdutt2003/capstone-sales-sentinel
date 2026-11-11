# Sales Sentinel

Ledger-first, automated cleaning for daily retail sales CSVs. It replaces a 2-hour manual job with
`python src/main.py`. It is built and maintained by two Claude Code agents, a **coder** and a
**tester**, that check each other. Hooks enforce the line between them, and an MCP server gives
them data-quality tools.

```bash
python src/main.py
# OK processed=200 kept=124 duplicates=70 quarantined=6 nulls_filled=32 score=90.0(A) -> output/
```

## What makes it different

| Typical script | Sales Sentinel |
|---|---|
| `dropna()` / `drop_duplicates()`; rows vanish | **Every input row gets one fate** in `row_ledger.csv`; rows *and money* must reconcile or the run fails |
| bad rows deleted | **Quarantined** with raw values and *all* their reason codes, ready to send back to the store |
| `float` money | `Decimal`, half-up rounding |
| dedupe on id (finds 0 here) | Content-replay detection: 70 replays found, bursts reported with revenue impact, policy switchable |
| fill nulls with mean/0 | Hierarchical **median** imputation *after* dedupe, flagged, with collision detection |
| one opaque "quality %" | 4 DAMA dimensions on the raw input + output confidence + money reconciliation |
| hardcoded paths | CLI > env > TOML config; exit codes 0/1/2/3 for schedulers; `--strict` quality gate |
| one AI writes code and tests | **Two agents, hook-enforced boundary**, spec traceability gate, mutation testing |

## Outputs (`output/`)

| File | Contents |
|---|---|
| `clean_sales.csv` | only valid, cleaned rows: `transaction_id,date,amount,store_id,category` |
| `data_quality_report.txt` | required summary (rows processed / removed / nulls filled / fixed-skipped / score) plus reconciliation, score breakdown, issues by code, duplicate bursts, money, warnings, quarantine, confidence |
| `quarantine.csv` | rejected rows: raw values + reason codes |
| `row_ledger.csv` | fate, codes, `duplicate_of` and note for **every** input row |
| `run_manifest.json` | sha256 of input/config/outputs, effective config, counts |

## Quick start

```bash
python --version                         # 3.11+
python src/main.py                       # uses config/pipeline.toml
python src/main.py --input other.csv --output-dir out/ --strict
pip install -r requirements-dev.txt      # pytest, hypothesis, coverage, mcp
python -m pytest -q                      # 180 tests in 5 modules
python -m pytest --cov=src/sentinel      # 95 % (branch)
python tools/spec_coverage.py            # 47/47 SPEC rules cited by tests
python tools/mutation_smoke.py           # 179/198 mutants killed (90.4 %)
python tools/hook_selftest.py            # 26/26 agent-boundary cases
```

## Working with the agents in Claude Code

1. Open the folder in Claude Code. `SessionStart` injects the status; `/agents` lists **coder** and **tester**.
2. Approve the project MCP server `sales-dq` when prompted (or `claude mcp list` to check).
3. Run a cycle: `/cycle R-DUP-03 R-IMP-04`. The orchestrator sends red tests to the tester, the
   fix to the coder, then evaluates.
4. Try to break the boundary: ask the coder to "just fix the failing test". The guard denies it and
   logs the attempt to `.claude/state/audit.jsonl`.

Hooks run through `.claude/hooks/run.sh` (python3 → python → py, fails closed if none is found).
On Windows, Claude Code runs hooks through Git Bash. The MCP server in `.mcp.json` is started with
`python`; if your machine only has `python3`, change that one word.

## Project documents

`SPEC.md` (contract, rule IDs) · `PLAN.md` (architecture, phases) · `TO-DO.md` (board + hand-off
log) · `CLAUDE.md` (rules + both agent definitions + hooks + MCP) ·
`.claude/skills/sales-data-cleaning/SKILL.md` (domain playbook; this location lets Claude Code load
it as a skill) · `DECISIONS.md` · `REFLECTION.md`.

## Scope

Not built, per the problem statement: database integration, visualisation / Power BI export, ML
anomaly detection, API endpoints, web UI.

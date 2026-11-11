# CLAUDE.md — Sales Sentinel (project memory for Claude Code)

> Automated, **ledger-first** cleaning of daily retail sales CSVs, built by **two Claude Code agents
> that check each other**: a **coder** that may only touch `src/` and a **tester** that may only touch
> `tests/`. Both agents are defined in full below (§4) and mirrored in `.claude/agents/` so `/agents`
> can run them. Boundaries are enforced by **hooks** (§5), not just by politeness. A project **MCP
> server** (§6) gives both agents data-profiling and ledger-inspection tools.

---

## 1. Source-of-truth files — read in this order, refer back constantly

| File | Role | Who may change it |
|---|---|---|
| `SPEC.md` | **The contract.** Every behaviour has a rule ID `R-XXX-NN`. Tests cite IDs; code implements IDs. | Orchestrator, with human approval (bump version) |
| `PLAN.md` | Architecture, phases, hand-off protocol, evaluation scorecard | Orchestrator |
| `TO-DO.md` | Live task board + **Hand-off log** between agents | Everyone (own items only) |
| `.claude/skills/sales-data-cleaning/SKILL.md` | Domain playbook: dates, money, dedupe, imputation, edge-case checklist | Orchestrator |
| `DECISIONS.md` | Why each cleaning choice was made (D-01 …) | Orchestrator, coder |
| `REFLECTION.md` | How AI was used, mistakes caught, fixes | Orchestrator / human |

**Rule zero:** if it isn't in SPEC.md it isn't a requirement. If SPEC.md is wrong or silent, stop and
raise it (TO-DO.md › Hand-off log, prefix `SPEC GAP:`) — never invent behaviour in code or tests.

## 2. Commands

```bash
python src/main.py                                   # clean data/sample_sales_data.csv -> output/
python src/main.py --input X.csv --output-dir out/   # any file; also $SALES_SENTINEL_INPUT / _OUTPUT_DIR
python src/main.py --dedupe-policy id --missing-strategy quarantine --strict
python -m pytest -q                                  # the judge
python -m pytest --cov=src/sentinel                  # coverage (target >= 90 %)
python tools/spec_coverage.py --check                # every SPEC rule cited by a test (100 %)
python tools/mutation_smoke.py                       # mutation score (target >= 70 %)
python tools/hook_selftest.py                        # prove the agent boundaries without Claude
```
Runtime: Python ≥ 3.11, **standard library only**. Dev: `pip install -r requirements-dev.txt`.

## 3. Layout & ownership

```
SPEC.md PLAN.md TO-DO.md DECISIONS.md REFLECTION.md README.md CLAUDE.md
config/pipeline.toml        policies (dedupe, imputation, dates, categories, score weights, gate)
data/sample_sales_data.csv  INPUT — immutable for everyone
src/main.py                 entry point  -> src/sentinel/{config,ingest,codes,rules,pipeline,scoring,report,cli}.py
tests/                      5 modules: ingest · field_rules · pipeline · e2e_sample · properties
tools/                      spec_coverage.py · mutation_smoke.py · hook_selftest.py · mcp_server/dq_server.py
output/                     generated — never hand-edited
.claude/agents/             coder.md · tester.md (mirrors of §4)
.claude/hooks/              run.sh · guard_boundaries.py · post_edit_feedback.py · subagent_gate.py · session_context.py · ownership.json
.claude/skills/sales-data-cleaning/SKILL.md
.claude/commands/cycle.md   /cycle <rule IDs> — one full spec→test→code→evaluate loop
.mcp.json                   registers the sales-dq MCP server
```

| Path | orchestrator (main session) | **coder** | **tester** |
|---|---|---|---|
| `src/**` | ✗ (delegate) | **RW** | R (run only — never read to decide "correct") |
| `tests/**` | ✗ (delegate) | R | **RW** |
| `config/**` | RW | RW | R |
| `SPEC.md` | RW (human-approved) | R | R |
| `PLAN.md`, `REFLECTION.md`, `README.md` | RW | R | R |
| `TO-DO.md` | RW | RW (own items, hand-off) | RW (own items, hand-off) |
| `DECISIONS.md` | RW | RW | R |
| `.claude/**`, `.mcp.json`, `tools/**` | RW | ✗ | ✗ |
| `data/**`, `output/**`, `.env*`, keys | ✗ | ✗ | ✗ |

The table is machine-enforced from `.claude/hooks/ownership.json`. A deliberate human edit to `src/`
or `tests/` from the main session: `SENTINEL_HUMAN_OVERRIDE=1`.

---

## 4. The two agents

The main session is the **orchestrator**: it plans, delegates, evaluates and owns the docs. It does
not write `src/` or `tests/` itself — it hands work to these two agents.

### Agent 1 — `coder`

```yaml
name: coder
description: Implements SPEC.md in src/ until the tester's suite is green. Use after the tester has
  written (red) tests for a TO-DO item, or to fix a failure report in TO-DO.md > Hand-off log.
  Never edits tests.
tools: Read, Grep, Glob, Edit, Write, Bash, mcp__sales-dq__run_pipeline, mcp__sales-dq__explain_row,
       mcp__sales-dq__quarantine_summary, mcp__sales-dq__spec_rules
hooks: PreToolUse -> guard_boundaries.py --role coder ; Stop(SubagentStop) -> subagent_gate.py --role coder
```

**Identity.** Senior Python data engineer. Implements the contract; does not negotiate with the judge.

**Reads first, every time:** SPEC.md → TO-DO.md (incl. Hand-off log) → PLAN.md §2 → SKILL.md → DECISIONS.md.

**May write:** `src/**`, `config/**`, `DECISIONS.md`, `TO-DO.md`.

**Must never:**
- touch `tests/` in any way (Edit/Write *or* Bash `sed -i`, `>`, `mv`, `git checkout`, `python -c open(...)`);
  never add `skip`/`xfail`; never special-case test inputs in production code;
- edit `SPEC.md`, `.claude/**`, `.mcp.json`, `tools/**`, `data/**`;
- add runtime dependencies, network, DB, UI or ML (R-OPS-03); use `float` for money (R-AMT-07).

**Loop:**
1. Take the TO-DO item + rule IDs. Read the failing tests for *expected behaviour*; implement what SPEC says.
2. Implement in the module PLAN.md assigns; keep `rules.py` pure.
3. `python -m pytest -q` (the PostToolUse hook also runs it after every edit and shows the tail).
4. `python src/main.py`; inspect with `mcp__sales-dq__run_pipeline` / `explain_row`.
5. Repeat until green — **the SubagentStop gate blocks finishing while the suite is red or the pipeline fails.**
6. Test contradicts SPEC? Don't touch it. Log `- <date> coder DISPUTE: <test> expects X, SPEC <rule> says Y.` and stop.
7. Record non-obvious choices in DECISIONS.md; tick TO-DO items.

**Reports:** files changed · rule IDs implemented · pytest summary line · disputes.

### Agent 2 — `tester`

```yaml
name: tester
description: QA engineer. Writes and runs pytest tests in tests/ from SPEC.md only (never from src/),
  hunts edge cases, reports failures to the coder via TO-DO.md. Use before coding (red phase) and after
  coding (evaluate, mutation survivors). Never edits src/.
tools: Read, Grep, Glob, Edit, Write, Bash, mcp__sales-dq__profile_csv, mcp__sales-dq__run_pipeline,
       mcp__sales-dq__explain_row, mcp__sales-dq__spec_rules, mcp__sales-dq__spec_coverage_report
hooks: PreToolUse -> guard_boundaries.py --role tester ; Stop(SubagentStop) -> subagent_gate.py --role tester
```

**Identity.** Senior QA engineer. The coder is biased toward tests that pass its code; the tester
exists to find what it missed.

**Reads first, every time:** SPEC.md (only source of expected behaviour) → TO-DO.md → SKILL.md §Edge-case checklist.

**May write:** `tests/**`, `TO-DO.md`.

**Must never:** edit `src/`, `config/`, `SPEC.md`, `DECISIONS.md`, `.claude/**`, `tools/**`, `data/**`;
weaken an assertion, `skip`/`xfail` a failure, mock the unit under test, or write a test without an assertion.

**How tests are written** (deck: *How to write a good test case*):
- One behaviour per test; name `test_<RULE_ID>_<behaviour>`; every SPEC rule cited by ≥ 1 test.
- Given/When/Then tables with `pytest.mark.parametrize` for field rules.
- Edge-case checklist for every rule: empty/null · boundaries (0, 1, max, max+1, −1) · invalid types ·
  large input · special text (Unicode digits, emoji, SQL quotes) · dates (leap day, 2-digit year,
  MM/DD vs DD/MM) · failures (missing file, bad config).
- `mcp__sales-dq__profile_csv` first, to discover the data's real edge cases.
- End-to-end through `python src/main.py` in a subprocess; Hypothesis properties for invariants.

**Loop:**
1. Write tests for the item's rule IDs → run → red is expected before the coder works.
2. Log each failure: `- <date> tester → coder: <test> | <rule> | expected <x> | got <y>`.
3. After green, evaluate: coverage ≥ 90 %, `tools/mutation_smoke.py` ≥ 70 %; every non-equivalent
   SURVIVED mutant becomes a new test.
4. **The SubagentStop gate blocks finishing** while a SPEC rule is uncovered, a test has no assertion,
   or tests fail to collect.

**Reports:** tests added (→ rule IDs) · pass/fail · coverage · mutation score · hand-offs.

### Orchestrator protocol (main session) — the 5-step loop from the deck

```
1 Spec ──> 2 Tests (tester, red) ──> 3 Code (coder, green) ──> 4 Evaluate ──> 5 Fix
   ^                                                                              |
   └──────────── every bug / surviving mutant becomes a permanent test ───────────┘
```
1. Confirm the rule IDs exist in SPEC.md (add/approve them with the human first).
2. Delegate to **tester** → expect red + hand-off entries.
3. Delegate to **coder** → expect green (gate-enforced).
4. Run coverage + `mutation_smoke` + `spec_coverage`; review tests for assert-free/over-mocked cases.
5. Survivors / review notes → new tester tasks in TO-DO.md. Repeat. Update DECISIONS/REFLECTION.

Shortcut: `/cycle R-DUP-03 R-IMP-04` runs this loop for the given rule IDs.

---

## 5. Hooks (`.claude/settings.json` + agent frontmatter)

| Event | Script | What it does |
|---|---|---|
| `SessionStart` | `session_context.py` | Injects SPEC version, open TO-DO items, spec-coverage %, guard-denial count |
| `PreToolUse` (Edit/Write/MultiEdit/NotebookEdit/Bash) | `guard_boundaries.py` | Enforces §3 table from `ownership.json`; role from `agent_type` (settings) **and** `--role` (frontmatter); inspects Bash for write verbs on forbidden paths; denials logged to `.claude/state/audit.jsonl` |
| `PostToolUse` (Edit/Write/MultiEdit) | `post_edit_feedback.py` | Blocks on Python syntax errors; runs the suite after edits to `src/`/`tests/` and feeds the result back |
| `SubagentStop` | `subagent_gate.py` | coder: suite green + pipeline exit 0. tester: 100 % spec coverage, no assert-free tests, collects cleanly. Max 5 blocks, then hands back to orchestrator |

Every hook runs through `.claude/hooks/run.sh`, which picks `python3` → `python` → `py` and exits 2
(blocking) if none exists, so the guard **fails closed**. The guard also denies agent writes if it
crashes. Verify offline with `python tools/hook_selftest.py`. Verified live with Claude Code 2.1: coder
Edit and `sed -i` on `tests/` were denied, and so was a tester Write into `src/`; both gates fired on SubagentStop.

## 6. MCP server `sales-dq` (`.mcp.json` → `tools/mcp_server/dq_server.py`)

| Tool | Used by | Purpose |
|---|---|---|
| `profile_csv(path)` | tester | nulls, value "shapes" (`9999-99-99` vs `99/99/99`), non-numeric/negative/zero amounts, duplicate clusters |
| `run_pipeline(...)` | both | runs `python src/main.py` into `output/mcp_run`, returns exit code + report |
| `explain_row(transaction_id \| line_no)` | both | fate + every reason code (with description) from the latest ledger |
| `quarantine_summary()` | coder | reason-code counts + examples |
| `spec_rules()` / `spec_coverage_report()` | both | rule IDs from SPEC.md; which are/aren't cited by tests |

Paths are confined to the project. Install: `pip install "mcp>=1.2"`.

## 7. Engineering rules (both agents)

- Money is `Decimal`, rounded `ROUND_HALF_UP` to 2 dp. Never `float`, never `abs()` a negative.
- Never silently drop a row: every input row gets exactly one fate in `row_ledger.csv` (R-INV-01).
- Diagnose-all: record every problem on a row, not just the first.
- Repair only the unambiguous (format, case, currency symbols). Anything requiring business judgement → quarantine.
- No hardcoded paths; no secrets; no network; deterministic output (R-INV-04).
- Small, pure functions; one rule family per function; docstrings cite rule IDs.

## 8. Definition of done

- [ ] `python src/main.py` exits 0 and prints the summary line; golden numbers in SPEC §4 hold
- [ ] `python -m pytest -q` green; coverage ≥ 90 %; mutation ≥ 70 %; `spec_coverage --check` passes
- [ ] `python tools/hook_selftest.py` 26/26
- [ ] TO-DO.md must-haves ticked; DECISIONS.md and REFLECTION.md updated

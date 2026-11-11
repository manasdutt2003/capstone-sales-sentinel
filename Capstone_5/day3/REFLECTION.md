# REFLECTION.md — how AI (Claude) was used, what went wrong, how it was fixed

## How Claude was used

| Phase | Claude's role | Human's role |
|---|---|---|
| Understanding | Read the problem statement and the *AI Coding & Testing* deck; profiled the CSV before writing any code | Supplied the problem, data and constraints (two agents, hooks, MCP, spec-first) |
| Contract | Drafted SPEC.md with rule IDs and **hand-computed golden numbers** (SPEC §4) before implementation | Reviews/approves SPEC; owns business questions in DECISIONS.md |
| Build | Wrote `src/`, `tests/`, hooks, MCP server, agent definitions | Reviews, runs, challenges |
| Evaluate | Coverage, mutation smoke test, spec traceability, hook self-test | Decides what "good enough" is |

**Honest caveat about independence.** The project was bootstrapped in a single Claude session that
wrote both code and tests (code first). That is exactly the bias the two-agent design exists to
remove, so the bootstrap leaned on checks that don't depend on the author: golden numbers derived
by hand from the raw file before coding, Hypothesis property tests, and mutation testing. The first
exercise to run in Claude Code is therefore: **delegate a fresh review to the `tester` agent**
(`/cycle R-DUP-03 R-IMP-01 R-AMT-08`), which works from SPEC.md only under the hook-enforced boundary.

## Mistakes caught and how they were fixed

Every entry below actually happened during this build.

1. **Wrong definition of "duplicate" (caught by profiling, before code).** The obvious reading is "same
   transaction_id". Profiling showed all 200 ids are unique, so that definition finds **0** duplicates
   while 70 rows replay another row's content (one key 53×). → Content-based dedupe as default, an `id`
   policy switch, and a burst report with revenue impact so the business can make the final call (D-04).

2. **Collision guard was too narrow (caught by the idempotence test R-INV-03).** First version of
   R-IMP-04 only warned when an imputed row matched an *observed* row, and only flagged the imputed
   side. Re-running the pipeline on its own output then removed rows nobody had flagged: the
   **observed partner** of a collision, and imputed rows that matched each other. → Both parties are
   now flagged with the partner id, imputed-vs-imputed collisions are detected, SPEC bumped to v1.1.0.

3. **Underestimated how often that happens.** I expected collisions to be rare. In fact 26 of 32
   imputations collide, because the median of an odd-sized group *is* an observed value. → Documented
   as a contract (dedupe clean output by `transaction_id` only) and offered `--missing-strategy quarantine` (D-11).

4. **"Green tests" that didn't test the score (caught by mutation testing).** First mutation run:
   147/198 killed (74 %), with most survivors in `scoring.py` — e.g. `*` → `/` in the weighted sum
   survived because tests only checked the report *format*, never the values. Further survivors on
   boundaries: group size `>=` vs `>`, outlier `>` vs `>=`, future-tolerance `+` vs `-`, and
   `len(t) > 1` (mutated to `>=` it raises `IndexError` on input `"+"`, an input no test used). → Added
   hand-computed exact dimension values (968/1000, 962/968, 957/962, 130/200), grade edges, weight
   sensitivity, and boundary tests, then config-validation and quality-gate boundaries. Mutation score
   74.2 % → 85.9 % → **90.4 %** (179/198). The 19 survivors are equivalent or display-only: `strerror or exc`
   message fallbacks, `missing=` flags already implied by an error, dataclass defaults, report layout.

5. **Coverage looked like 58 % (measurement bug, not a test gap).** End-to-end tests run
   `python src/main.py` in a subprocess, which coverage didn't follow. → `patch = ["subprocess"]` in
   `pyproject.toml`; real coverage is 94 %+.

6. **The guard hook had bypasses (caught by `tools/hook_selftest.py`).**
   - `python -c "open('tests/x.py','w')"` was allowed: the path sat inside one quoted shell token.
     → quoted paths are now extracted from the command.
   - `sed -i 's/assert/#/' tests/...` was denied, but for the wrong reason (the sed expression was
     treated as a path). → tokens that aren't real paths are ignored.
   - `git checkout -- tests/` matched no rule because `tests` (the directory) didn't match `tests/*`.
   - Found on review: `pytest > /dev/null` would have been blocked for agents (`/dev/null` is
     outside the project). → whitelisted.

7. **The gate fired twice per stop.** The gate is wired both in `settings.json` (role from `agent_type`)
   and in agent frontmatter (`--role`). Two invocations meant tests ran twice and the "max 5 blocks"
   counter moved by 2. → 30-second per-agent decision cache.

8. **Small consistency bugs.**
   - Business-date inference at first only looked at rows with no errors. A bad amount says nothing
     about the date, so it now uses every valid date.
   - Amount repairs compared against the stripped value, while ids compared against the raw value,
     so surrounding whitespace was a "repair" for one field but not another. → both compare to raw.
   - A test-table row was a `pytest.skip` placeholder. → removed (a skipped case is a hidden gap).

9. **Library drift.** The installed MCP Python SDK was 2.x, where `FastMCP` became `MCPServer`.
   → The server imports either, so it works with `mcp` 1.x and 2.x.

10. **The guard could fail open (caught on review before the live test).** Claude Code treats a hook that
    errors with a code other than 2 as non-blocking. A missing `python` on PATH, or a crash inside the
    guard, would have let every edit through without a word. → `run.sh` launcher exits 2 when no
    interpreter is found, and the guard denies agent writes if it throws.

11. **Live verification surprised me twice.** (a) Asked to edit a test, the coder agent *refused on its
    own* from the CLAUDE.md rules, so the hard guard was never exercised. A passing "nothing happened"
    test proves nothing about the hook, so the acceptance test now tells the agent to attempt the
    edit. (b) Edits whose `old_string` matched several places fail Claude Code's own validation
    *before* PreToolUse runs. Again the hook isn't exercised, so the test uses `Write`. Final live
    result: coder Edit + `sed -i` on `tests/` denied, tester Write into `src/` denied, files
    unchanged, all denials in `audit.jsonl`, SubagentStop gates passed.

## What I would do next

- Run the `tester` agent from a clean context against SPEC.md to get a truly independent test suite.
- Ask the business the three open questions in DECISIONS.md. D-04 alone moves revenue by about 10.5k.
- Track the raw-input score per store per day. A falling score is an early warning about a store's POS.

## Your notes (Manas)

<!-- Add your own experience: prompts that worked, places you overrode Claude, what you learned. -->
-

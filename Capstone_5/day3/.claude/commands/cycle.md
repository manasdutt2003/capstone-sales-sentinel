---
description: Run one spec → tests → code → evaluate → fix cycle for the given SPEC rule IDs
argument-hint: R-XXX-NN [R-YYY-NN ...]
---
Run one full Sales Sentinel cycle for rule IDs: **$ARGUMENTS**

Follow CLAUDE.md §4 "Orchestrator protocol" exactly:

1. Verify each ID exists in SPEC.md (`mcp__sales-dq__spec_rules`). If one is missing, stop and ask me to approve a SPEC change.
2. Delegate to the **tester** subagent: write/extend tests for $ARGUMENTS from SPEC.md only, run them, log failures in TO-DO.md › Hand-off log.
3. Delegate to the **coder** subagent: make the suite green for $ARGUMENTS without touching tests.
4. Evaluate: `python -m pytest --cov=src/sentinel -q`, `python tools/spec_coverage.py --check`, `python tools/mutation_smoke.py --module <affected module>`.
5. Turn every non-equivalent surviving mutant into a tester task in TO-DO.md and repeat from step 2 (max 2 extra rounds).
6. Summarise: rule IDs done, tests added, coverage %, mutation score, open hand-offs.

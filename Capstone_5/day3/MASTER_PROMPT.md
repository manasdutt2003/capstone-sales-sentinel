# Master Prompt: Two-Agent Build (Coder + Tester)

Hi! I'd like your help building a project properly, the way a senior AI engineer would: spec first,
tests that actually mean something, and two AI agents that keep each other honest. Here's the
full picture.

## Who I need you to be

Think of yourself as a **senior AI engineer** who also cares a lot about testing. You've seen
plenty of AI-written code that looks right, passes a demo and quietly breaks in production. So you
don't just make things work; you make them *provably* work, and you're upfront when something
is a judgement call rather than a fact.

## The project

- **What we're building:** ["a script that cleans our daily sales CSV automatically along with coder and tester agents"]
- **Problem statement:** attached the task file.
- **Sample data or other files:** [attached the data file]

Please read the problem statement carefully, all of it, including the "must-haves" and
"don't build" parts. Before you design anything, **look at the actual data** if there is any.
Profile it and tell me what's really in there. The most important problems are often not the
ones the brief mentions. (Last time, the brief said "remove duplicates", but every ID was unique and the real
duplicates were the same sale repeated under new IDs. Profiling caught that; guessing wouldn't have.)

## The core idea: two agents that check each other

I've attached a PPT from our *AI Coding & Testing* session; please use it as your reference. The
main lesson is that **the agent that writes the code is biased toward writing tests that pass it**.
So we split the work:

**The coding agent**

- Reads the spec and implements it in `src/`
- Runs the tests and keeps going until they pass
- **Can edit `src/` but must never touch `tests/`.** Not with an edit, and not with a shell trick
  like `sed -i` or `> file` either.
- If it thinks a test is wrong, it doesn't "fix" the test. It writes a note explaining why and leaves
  the decision to me.

**The testing agent**

- Reads the spec only, never the source code, to decide what "correct" means
- Writes tests in `tests/`, including the nasty edge cases
- Runs them and reports failures back to the coder
- **Can edit `tests/` but must never touch `src/`.**

Both agents need to be **defined in full inside `CLAUDE.md`**: role, what they read first, what
they may and may not edit, how they work, and what they report back. Then mirror them as
`.claude/agents/coder.md` and `.claude/agents/tester.md` so Claude Code can actually run them.

## The four files we live by

Please create these first, before any code, and **keep coming back to them** throughout the work.
They aren't paperwork. They're how both agents (and I) stay on the same page.

1. **`SPEC.md`**: the contract. Every behaviour gets a short rule ID (like `R-DUP-03`) so tests and
   code can point to it. If possible, include a few expected results worked out *by hand from the
   real data* before any code exists; those become your strongest tests. If something isn't in the
   spec, it isn't a requirement. If the spec is wrong or silent, flag it, don't invent behaviour.
2. **`PLAN.md`**: how we'll build it: architecture, modules, phases, how the agents hand work to each
   other, and how we'll judge quality.
3. **`TO-DO.md`**: a live checklist, plus a **hand-off log** where the agents leave each other short
   notes ("tester → coder: test X fails, expected A, got B"). Keep it honest; only tick what's
   genuinely done.
4. **`CLAUDE.md`**: the project memory Claude Code reads every session: rules, commands, folder
   layout, a who-can-edit-what table, and both agent definitions.

## How the work should flow

Follow the 5-step loop from the deck:

1. **Spec**: write down the behaviour and acceptance rules.
2. **Tests**: the tester writes them from the spec. They'll fail at first, and that's expected.
3. **Code**: the coder implements until the tests pass.
4. **Evaluate**: don't stop at "all green". Check coverage, and run mutation testing (break the code
   on purpose and see if the tests notice). Look for tests with no assertions or too much mocking.
5. **Fix**: every bug or weak spot becomes a new permanent test. Then loop back.

For edge cases, walk the deck's checklist every time: empty or missing values, boundaries
(0, 1, max, max+1, −1), wrong types, large inputs, odd text (Unicode, emoji, quotes), dates (leap
days, formats, time zones) and failures (missing file, bad config).

## Please make the rules real, not just polite

Instructions in a prompt are easy to ignore. I'd like the coder/tester boundary **enforced**, not
just requested:

- Use **Claude Code hooks** so that before any edit or shell command, a small script checks which
  agent is acting and blocks it if it's crossing the line. Keep the permission table in one file.
- Make the guard **fail closed**: if it crashes or Python can't be found, block rather than allow.
- Don't let agents edit `.claude/`, so they can't switch off their own guard.
- Add a check when an agent tries to finish: the coder can't stop while tests fail; the tester
  can't stop while a spec rule has no test.
- Log every block to a file so I can see what happened.
- Give me a small self-test script that proves the guard works without needing Claude at all.

If it helps the agents do better work, an **MCP server** with a few project tools (e.g. "profile
this data", "run the pipeline", "explain why this record was rejected") is a great addition.

## Quality bar

- Runs with **one command** and no manual steps
- **No hardcoded paths** (use config, arguments or environment variables) and **no secrets** committed
- Handles bad input gracefully: a clear one-line error, no scary tracebacks
- Tests cover normal cases *and* edge cases, and every spec rule is covered by at least one test
- Keep dependencies minimal; don't pull in a heavy library if the standard library does the job
- Respect anything the problem statement says **not** to build

## What I'd like back

1. A **zip file** of the whole project, ready to unzip and run, including the hidden `.claude/`
   folder and `.mcp.json`
2. The four core files (`SPEC.md`, `PLAN.md`, `TO-DO.md`, `CLAUDE.md`), plus `README.md` with
   setup and run steps
3. `DECISIONS.md`: the key choices you made and *why*, including alternatives you rejected
4. `REFLECTION.md`: how AI was used, the **real** mistakes caught along the way and how each was
   fixed. Please don't invent tidy-sounding ones; the honest list is more useful.
5. A short summary when you're done: what works, the key numbers (tests, coverage, mutation score),
   anything that still needs a human decision, and any limitations.

## A few working preferences

- **Actually run things.** Run the code, run the tests, try the guard. Don't tell me something works
  unless you've seen it work.
- **Be honest about independence.** If one session ended up writing both code and tests, say so,
  and add checks that don't depend on the author (hand-computed expected values, randomised
  property tests, mutation testing).
- **Ask me** when something is really a business decision (e.g. "are these duplicates or real repeat
  sales?"). Make the choice configurable, explain the trade-off, and pick a sensible default.
- **Keep it explainable.** I'll be presenting this, so clear names, short functions and readable docs
  matter as much as clever code.
- Aim for an approach that **stands out** from the usual run-of-the-mill solution, but stays practical.

Thanks! Start by reading the attachments and profiling the data, then show me what you found
before you start building.

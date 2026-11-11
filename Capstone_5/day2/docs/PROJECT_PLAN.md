# Project Plan & Spec — Hands-On POC: Extending Claude Code

Source brief: `day2_poc.md`. This file breaks the brief into every individual
requirement, maps each to a deliverable and a verification, records design
decisions and risks, and gives a step-by-step runbook for the checks that must be
watched live in Claude Code.

Legend: ✅ built and verified outside Claude Code · 👁 must be observed in Claude Code
(prompt given in the runbook) · ✍ written, reword in your own voice.

---

## 1. Objective and constraints

Build a sandbox repo and extend Claude Code in five ways: **instructions
(CLAUDE.md), hooks, a public MCP server, a custom MCP server, a skill**, then
explain the result in NOTES.md.

| Constraint (from brief) | How it is handled |
|---|---|
| ~2 hours, splittable (Parts 1–2, then 3–5) | Commits are one per part, so work can stop after any commit. |
| Only docs, training material and Claude Code | No third-party libraries beyond pytest, flake8, uv, mcp SDK. |
| "Prove it, don't assume it" | Every part has an automated or manual check (section 4) plus a live 👁 check. |
| Dummy values only (`dummy`) | Only `KEY=dummy` is used; no `.env` file and no realistic-looking key anywhere in the repo. |
| Hooks / MCP run code on your machine | All scripts are short and readable; read them before approving. |
| Sandbox only | Everything lives in `claude-poc-sandbox/`. |
| Nothing confidential to a public server | Rule in CLAUDE.md; MS Learn added at local scope only. |
| Explain every file | Each file has a header comment explaining what and why; NOTES.md covers the rest. |

---

## 2. Requirement traceability matrix

### Setup

| ID | Requirement | Deliverable | Verification | Status |
|---|---|---|---|---|
| S1 | Tools installed: claude, git, Python ≥3.9 (real), pytest, flake8, uv | your machine | `claude --version`, `git --version`, `python --version`, `uv --version` | 👁 on your machine |
| S2 | Create folders `tests tools/mcp .claude/hooks .claude/skills/add-util`, `git init` | repo | tree | ✅ |
| S3 | `utils.py` and `tests/test_utils.py` exactly as given | files | diff vs brief | ✅ |
| S4 | Baseline passes, then commit "chore: starter sandbox" | commit `chore: starter sandbox` | 2 passed, flake8 clean | ✅ |

### Part 1 — CLAUDE.md

| ID | Requirement | Deliverable | Verification | Status |
|---|---|---|---|---|
| P1.1 | Project overview | `CLAUDE.md` § Project overview | read | ✅ |
| P1.2 | Tech stack and conventions | § Tech stack and conventions | read | ✅ |
| P1.3 | ≥3 specific rules | § Rules for Claude (5 rules) | read | ✅ |
| P1.4 | ≥2 "Do NOT" rules | § Do NOT (5 rules) | read | ✅ |
| P1.5 | Copy-pasteable run commands | § Run commands | each command run in shell | ✅ |
| P1.6 | Self-critique: find one gap, close it, mark it at the bottom | § Self-critique (bare `pytest` fails → always `python -m pytest`; + duplicate-function rule) | reproduced the failure | ✅ |
| P1.7 | `/context` lists the file | — | runbook R1 | 👁 |
| P1.8 | Claude answers "where does a helper go" from the file | — | runbook R1 | 👁 |
| P1.9 | Claude follows the rules when adding a function | — | runbook R1 | 👁 |

### Part 2 — Hooks

| ID | Requirement | Deliverable | Verification | Status |
|---|---|---|---|---|
| P2.1 | Hooks defined in `.claude/settings.json`, scripts in `.claude/hooks/` | `settings.json`, `guard.py`, `lint.py` | JSON parses; commands run from another cwd | ✅ |
| P2.2 | Guard blocks `rm -rf` (all spellings) | `guard.py` `is_recursive_force_rm` | `tests/test_hooks.py` | ✅ |
| P2.3 | Guard blocks force push | `guard.py` `is_force_push` | tests | ✅ |
| P2.4 | Guard blocks creating/editing `.env`, `.env.*`, `*.pem`, `*.key`, `*.pfx` | `guard.py` file tools + Bash writes | tests | ✅ |
| P2.5 | `.env.example` still allowed | `ALLOWED_CREDENTIAL_LOOKALIKES` | tests | ✅ |
| P2.6 | Claude is told why | exit 2 + reason on stderr | tests assert stderr text | ✅ |
| P2.7 | Lint after Write/Edit of `.py`, flake8 max 88 | `lint.py`, PostToolUse `Write\|Edit\|MultiEdit` | tests | ✅ |
| P2.8 | Claude actually finds out about lint problems | exit 2 + flake8 output on stderr | tests | ✅ |
| P2.9 | Other file types left alone | early exit 0 for non-`.py` | test with Markdown | ✅ |
| P2.10 | Two sentences on exit 1 vs exit 2 | NOTES.md § Part 2 | read | ✍ |
| P2.11 | `/hooks` lists both | — | runbook R2 | 👁 |
| P2.12 | Try to break it (blocked, allowed, lint, Markdown) | — | runbook R2 | 👁 |
| P2.13 | If a hook does nothing, find out whether it ran | — | `claude --debug`, runbook R2 | 👁 |

### Part 3 — Public MCP server

| ID | Requirement | Deliverable | Verification | Status |
|---|---|---|---|---|
| P3.1 | Add Microsoft Learn (or Context7) using the documented command | `claude mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp` (local scope) | `claude mcp list` | 👁 (blocked from the build workspace, works on a normal network) |
| P3.2 | `/mcp` lists its tools | — | runbook R3 | 👁 |
| P3.3 | Docs question that needs it, with cited page | — | runbook R3 | 👁 |
| P3.4 | Same question without it; what the tool added | — | runbook R3 | 👁 |
| P3.5 | NOTES: what was sent, what you'd never send | NOTES.md § Part 3 | read | ✍ |

### Part 4 — Custom MCP server

| ID | Requirement | Deliverable | Verification | Status |
|---|---|---|---|---|
| P4.1 | `tools/mcp/server.py`, stdio, official SDK FastMCP | `server.py` | runs | ✅ |
| P4.2 | `word_stats(text)` → word count, char count, longest word | `word_stats` | MCP client call | ✅ |
| P4.3 | `slugify(text)`; `"Hello, World!"` → `"hello-world"` | `slugify` | MCP client call | ✅ |
| P4.4 | Registered for everyone who clones | `.mcp.json` (project scope) | MCP client launched the `.mcp.json` command | ✅ |
| P4.5 | Run with `uv run --with "mcp[cli]" python ...` | `uv run --with "mcp[cli]<2" python tools/mcp/server.py` (pin needed, see D5) | shell | ✅ |
| P4.6 | Pre-warm the first `uv run` | — | runbook R4 step 1 | 👁 |
| P4.7 | `claude mcp list` connected, `/mcp` shows both tools | — | runbook R4 | 👁 |
| P4.8 | Claude *calls* the tools | — | runbook R4 | 👁 |
| P4.9 | Break with a typo, read the error, fix, reconnect | error text recorded in NOTES | shell | ✅ + 👁 |

### Part 5 — Skill

| ID | Requirement | Deliverable | Verification | Status |
|---|---|---|---|---|
| P5.1 | `.claude/skills/add-util/SKILL.md`, invoked as `/add-util is_even "..."` | SKILL.md with `$ARGUMENTS` | YAML parses | ✅ |
| P5.2 | Step 1 read `utils.py`, match style | Step 1 | dry run | ✅ |
| P5.3 | Step 2 add function, type hints, one-line docstring | Step 2 | dry run | ✅ |
| P5.4 | Step 3 one normal + one edge test | Step 3 | dry run | ✅ |
| P5.5 | Step 4 run pytest and flake8 | Step 4 (`python -m pytest`) | dry run | ✅ |
| P5.6 | Step 5 fix and re-run until both pass | Step 5 | — | ✅ |
| P5.7 | Step 6 report signature and results | Step 6 | — | ✅ |
| P5.8 | NOTES: why each setting | NOTES.md § Part 5 table | read | ✍ |
| P5.9 | Listed in "What skills are available?" | — | runbook R5 | 👁 |
| P5.10 | Run it; args reached Claude; steps in order; both checks | — | runbook R5 | 👁 |
| P5.11 | Existing function → what happens | Step 1 duplicate check | runbook R5 | 👁 |
| P5.12 | Edit a step, rerun without restart | — | runbook R5 | 👁 |
| P5.13 | Plain-words request without slash command | — | runbook R5 | 👁 |

### Wrap-up and hand-in

| ID | Requirement | Deliverable | Status |
|---|---|---|---|
| W1–W6 | Six wrap-up answers | NOTES.md § Wrap-up | ✍ |
| H1 | Hand-in tree (CLAUDE.md, NOTES.md, .mcp.json, utils.py, tests, server.py, settings.json, hooks/, SKILL.md) | all present | ✅ |
| H2 | `utils.py` "plus whatever your skill added" | `is_even` added when **you** run R5 | 👁 |
| H3 | Everything committed | one commit per part; commit after R5 | ✅ + 👁 |
| H4 | Keep transcripts / screenshots | `docs/evidence/` (create) | 👁 |
| H5 | No secrets, even fake-looking ones | no `.env`; no realistic-looking key in the repo (`git grep -n "sk-"` is empty) | ✅ (re-check before sharing) |

---

## 3. Design decisions

| # | Decision | Why | Alternative |
|---|---|---|---|
| D1 | Hook scripts in **Python**, not bash | Works on Windows, macOS and Linux; Python is already required. | bash + `jq` (not on Windows by default). |
| D2 | Guard **parses** the command (shlex, segments on `;`, `&&`, `|`) instead of a plain substring match | Catches `-fr`, `-r -f`, `--recursive --force`, `sudo rm`, `ls && rm -rf`; avoids false positives like `rm -r build`. | Regex on `rm -rf` only (easy to bypass). |
| D3 | Guard also checks **Bash writes** to credential files | Otherwise `echo ... > .env` bypasses an Edit/Write-only guard. | Only file tools (what the brief literally lists). |
| D4 | Guard **fails closed**, lint **fails open** | A broken guard must be noticed; a broken linter must not stop work. | — |
| D5 | Pin **`mcp[cli]<2`** | SDK 2.x renamed FastMCP; the brief's unpinned starter now crashes. Pin keeps the API the brief specifies. | Port to `mcp.server.mcpserver.MCPServer`. |
| D6 | Public MCP at **local** scope; own server at **project** scope (`.mcp.json`) | Third-party data flow should be an individual opt-in; our server is safe to share. | Both in `.mcp.json`. |
| D7 | `word_stats` strips punctuation from words, keeps apostrophes/hyphens | `"World!"` should count as `World`; `don't` is one word. Also returns `characters_no_spaces`. | `text.split()`. |
| D8 | Skill is **model-invocable** (default) with precise `description` | Plain-words requests reuse the tested procedure. | `disable-model-invocation: true` for strictly manual use. |
| D9 | Skill `allowed-tools` lists only Read, Edit and the two exact check commands | Smooth run without prompts, but nothing else is pre-approved. | No `allowed-tools` (prompt for every command). |
| D10 | `tests/test_hooks.py` kept in the repo | Makes "test your scripts with sample input" repeatable and part of the normal test run. | One-off manual `echo ... \| python guard.py`. |

---

## 4. Risks and issues found

| Risk / issue | Impact | Mitigation |
|---|---|---|
| Bare `pytest` fails (`No module named 'utils'`) | Skill step 4 / Claude "fixes" a non-bug | CLAUDE.md + skill always use `python -m pytest` (found by testing). |
| MCP SDK 2.x breaks FastMCP starter | Part 4 server never connects | Pin `<2` (found by testing). |
| `python` not on PATH (macOS `python3` only, Windows Store shim) | Hooks fail with a non-blocking error → guard silently off | Check with the canary in R2; change `python` to `python3` (or full path) in `settings.json` if needed. |
| First `uv run` is slow | `/mcp` shows the server as failed/timed out | Run it once by hand first (R4 step 1). |
| Project `.mcp.json` needs approval | Server not loaded until approved | Approve when Claude Code asks; or check `/mcp`. |
| Bash guard is best-effort | A `python -c "open('.env','w')"` would get through | Layers: CLAUDE.md rule, `permissions.deny`, `.gitignore`, review. |
| MS Learn blocked on corporate network | Part 3 can't connect | Use Context7. |

---

## 5. Runbook — live checks in Claude Code (👁 items)

Do these in order in `claude-poc-sandbox/`. Screenshot each result into
`docs/evidence/` and fill the `TODO (observe)` lines in NOTES.md.

**R0. Setup** — `claude --version`, `git --version`, `python --version`,
`uv --version`, `python -m pip install pytest flake8`. If only `python3` exists,
replace `python` with `python3` in `.claude/settings.json` and the skill's
`allowed-tools`. Then `python -m pytest -q` (expect 38 passed).

**R1. CLAUDE.md** — start `claude`, run `/context` (CLAUDE.md listed). Ask:
"Where should a new helper function go in this project, and how do I run the
tests?" (expect `utils.py`, `python -m pytest`). Then: "Add a function `square(x)`
that returns x squared." Expect: added to `utils.py` with type hints and docstring,
two tests, both checks run. Then `git checkout utils.py tests/test_utils.py` to undo.

**R2. Hooks** — `/hooks` (PreToolUse and PostToolUse entries listed). Ask, one by one:
1. "Run `rm -rf build`." → blocked, Claude quotes the guard reason.
2. "Run `git push --force`." → blocked.
3. "Create a .env file with KEY=dummy." → blocked.
4. "Create .env.example with KEY=dummy." → allowed.
   Delete it afterwards.
5. "Create scratch.py containing `import os` and `x=1` exactly, don't fix it." →
   Claude receives flake8 F401/E225 and fixes them. Delete the file afterwards.
6. "Add a line to NOTES.md." → no lint message.
If nothing happens: run `claude --debug` and look for the hook execution lines;
run the command from `settings.json` by hand.

**R3. Public MCP** — in a terminal:
`claude mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp`,
then `claude mcp list` (connected). In Claude: `/mcp` (tools listed). Ask:
"Using the Microsoft Learn MCP server, how do I create an Azure storage account
with the Azure CLI? Cite the page URL." Then `/mcp` → disable it (or ask in a
session without it) and ask the same thing; compare. Fill NOTES § Part 3.

**R4. Custom MCP** —
1. Pre-warm: `uv run --with "mcp[cli]<2" python tools/mcp/server.py`, wait for it
   to sit idle (it's waiting on stdin), then Ctrl+C.
2. Start `claude`, approve the project server `text-tools`. `claude mcp list` and
   `/mcp` show both tools.
3. Ask: "Use the text-tools server to analyse: 'Claude Code hooks run
   deterministic checks, don't they?'" → expect a `word_stats` tool call
   (8 words, 55 chars, longest `deterministic`).
4. Ask: "Use slugify on 'Hands-On POC: Extending Claude Code'." → expect
   `hands-on-poc-extending-claude-code` from a tool call.
5. Break: change `@mcp.tool()` to `@mcp.tol()` on one tool, `/mcp` → reconnect,
   read the failure; run the server by hand to see `AttributeError ... Did you
   mean: 'tool'?`; fix with `git checkout tools/mcp/server.py`; reconnect.

**R5. Skill** —
1. "What skills are available?" → `add-util` listed.
2. `/add-util is_even "return True when an integer is even"` → steps 1–6 in
   order, both checks run, report with signature and results.
3. Commit: `git add utils.py tests/test_utils.py && git commit -m "feat: add is_even via /add-util skill"`.
4. `/add-util clamp "limit a value"` → stops at step 1, no edits.
5. Edit Step 6 of SKILL.md (e.g. also "list the files changed"), run
   `/add-util is_odd "return True when an integer is odd"` without restarting;
   note whether the new instruction is followed. Revert or keep and commit.
6. Plain words: "Add a helper called `is_positive` that returns True for numbers
   above zero." Note whether Claude loads the skill on its own (D8) or follows
   CLAUDE.md rules directly.

**R6. Finish** — reword NOTES.md, fill all TODOs, save evidence, `git status`
clean, check nothing secret-looking was added (`git grep -n "sk-"`), commit.

---

## 6. Deliverable tree

```text
claude-poc-sandbox/
├── CLAUDE.md                     # Part 1
├── NOTES.md                      # Parts 2-5 notes + wrap-up
├── .mcp.json                     # Part 4 registration (project scope)
├── .gitignore
├── utils.py                      # + is_even after you run R5
├── tests/
│   ├── test_utils.py
│   └── test_hooks.py             # hook sample-input tests (36 cases)
├── tools/mcp/server.py           # Part 4
├── docs/PROJECT_PLAN.md          # this file
└── .claude/
    ├── settings.json             # Part 2 hook registration
    ├── hooks/guard.py            # PreToolUse guard
    ├── hooks/lint.py             # PostToolUse flake8
    └── skills/add-util/SKILL.md  # Part 5
```

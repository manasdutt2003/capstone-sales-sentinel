# NOTES.md — claude-poc-sandbox

> Draft answers. Re-read each one and reword it in your own voice before you hand
> in: the facilitator will ask you to explain them. Fill in every `TODO (observe)`
> line from your own Claude Code session, and keep the transcripts/screenshots.

---

## Part 1: CLAUDE.md

- The gap I found and closed is written at the bottom of `CLAUDE.md`
  (bare `pytest` fails in this repo; only `python -m pytest` works).
- Checks:
  - `/context` lists `CLAUDE.md`: TODO (observe)
  - "Where does a new helper function belong?" answered `utils.py` without me
    repeating it: TODO (observe)
  - Asked for a small function; it added tests and ran both checks: TODO (observe)

---

## Part 2: Hooks

**Exit codes (the two sentences):**
When a hook exits with **code 1** (or any code other than 0 and 2) it is a
*non-blocking* error: Claude's pending action **still goes ahead**, and the stderr
text is only shown to the user, not to Claude. When it exits with **code 2** it is
a *blocking* error: for a `PreToolUse` hook the pending tool call is **cancelled**
and stderr is fed back to Claude so it knows why, while for a `PostToolUse` hook
the action has already happened, so stderr is fed to Claude as feedback to act on.

**Design:**
- `guard.py` (PreToolUse, matcher `Bash|Write|Edit|MultiEdit|NotebookEdit`)
  exits 2 with a reason for `rm` with recursive+force flags in any spelling
  (`-rf`, `-fr`, `-r -f`, `-Rf`, `--recursive --force`, after `sudo` or `&&`),
  for force pushes (`--force`, `-f`, `--force-with-lease`, `+branch`), and for
  writing `.env`, `.env.*`, `*.pem`, `*.key`, `*.pfx` through the file tools *or*
  through Bash (`>`, `cp`, `mv`, `touch`, `tee`...). `.env.example` is allowed.
  It **fails closed**: bad input means exit 2, not a silent pass.
- `lint.py` (PostToolUse, matcher `Write|Edit|MultiEdit`) runs
  `flake8 --max-line-length=88` only on `.py` files and exits **2** with the
  flake8 output, because exit 0 output is never shown to Claude, so Claude would
  not find out. Other file types exit 0 immediately.
- Scripts are Python, not bash, so they also work on Windows; the command uses
  `$CLAUDE_PROJECT_DIR` so they work from any working directory.

**Tested by hand before trusting:** `tests/test_hooks.py` pipes 36 sample payloads
into the scripts exactly as Claude Code does (blocked and allowed commands,
credential vs normal files, lint pass/fail/Markdown). All pass. I also ran the
exact command strings from `settings.json` from another directory.

**Checks in Claude Code:**
- `/hooks` lists both: TODO (observe)
- "Delete the build folder with rm -rf" was blocked and Claude explained why: TODO (observe)
- "Create .env with KEY=dummy" blocked; `.env.example` allowed: TODO (observe)
- Python file with an unused import: Claude saw the flake8 output and fixed it: TODO (observe)
- Edited a Markdown file: no lint ran: TODO (observe)

---

## Part 3: Public MCP server (Microsoft Learn)

Command (from the docs page *Connect Claude Code to tools via MCP*):

```bash
claude mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp
# if blocked on your network:
claude mcp add --transport http context7 https://mcp.context7.com/mcp
claude mcp list
```

I used the default **local** scope on purpose, not `.mcp.json`: it is a third-party
server, so each teammate should opt in to sending queries to it. `.mcp.json` only
holds our own server.

- Question asked (with the server): TODO (observe), e.g. "Using Microsoft Learn,
  how do I create an Azure Storage account with the Azure CLI? Cite the page."
- Cited page: TODO (observe)
- Same question without the server: TODO (observe). What the tool added:
  current official docs and a citable URL instead of an answer from memory that
  can be outdated or wrong.

**What I sent to a third party:** only the search question text I typed (and
whatever query Claude wrote from it), plus normal connection metadata such as my
IP address.
**What I would never send:** source code, file contents, secrets or keys (even
dummy ones), customer or personal data, internal hostnames, or anything
confidential, because it leaves my machine and I don't control what is logged.

---

## Part 4: Custom MCP server (`text-tools`)

- Registered in **`.mcp.json` (project scope)** so everyone who clones the repo
  gets it. Claude Code asks each person to approve project servers on first use.
- **Finding:** the brief's command `uv run --with "mcp[cli]"` now installs the
  MCP Python SDK **2.x**, where `FastMCP` was renamed (`mcp.server.fastmcp`
  no longer exists), so the starter crashes with `ModuleNotFoundError`.
  I pinned `mcp[cli]<2` (resolves to 1.30.0) to keep the FastMCP API the brief
  asks for. The alternative is to port to the 2.x `MCPServer` API.
- Tested outside Claude Code with a real MCP client launching the exact
  `.mcp.json` command: it lists `word_stats` and `slugify`;
  `slugify("Hello, World!")` returns `hello-world`.
- **Broke it on purpose** (`@mcp.tol()`): the server dies at start-up with
  `AttributeError: 'FastMCP' object has no attribute 'tol'. Did you mean: 'tool'?`
  In Claude Code it shows as failed in `claude mcp list` / `/mcp`. Fixed, then
  reconnected from `/mcp`.
- Checks in Claude Code: `/mcp` lists both tools: TODO (observe); Claude
  *called* `word_stats` / `slugify` (tool call visible in transcript) instead of
  counting itself: TODO (observe).

---

## Part 5: Skill settings and why

| Setting | Value | Why |
|---|---|---|
| `name` | `add-util` | Gives the `/add-util` command; matches the folder name. |
| `description` | what it does + "use when the user asks to add a helper" | Claude reads this to decide when to load the skill on its own, so it states both the job and the trigger. |
| `argument-hint` | `<function_name> "<description>"` | Shown in autocomplete so the user knows the argument format. |
| `allowed-tools` | `Read`, `Edit`, `python -m pytest/flake8` (and `python3` forms) | Pre-approves only what the procedure needs, so the run is not interrupted by prompts, while anything else (other shell commands, `Write` of new files) still asks. The hooks still apply. |
| `disable-model-invocation` | not set (default `false`) | I want a plain-words request ("add a helper that...") to follow the same tested procedure. If the team wanted it strictly manual, set it to `true`. |
| Body uses `$ARGUMENTS` | first word = name, rest = description | Shows exactly what reached Claude; the skill stops and asks if the name or description is missing. |

- **Existing function** (`/add-util clamp "..."`): Step 1 tells Claude to stop,
  edit nothing, and show the existing signature. Observed: TODO (observe)
- **Edited a step without restarting:** TODO (observe whether the change took effect)
- **Plain words, no slash command:** expected: Claude may load `add-util` itself
  because the description matches; if it doesn't, CLAUDE.md rules 1 to 3 still
  make it add tests and run both checks. Observed: TODO (observe)
- Dry run of the procedure on a copy (is_even + 2 tests): 40 passed, flake8 clean.

---

## Wrap-up

**1. What each one solves that the others don't**
- **CLAUDE.md:** standing project knowledge (where code goes, conventions, the
  right commands), loaded every session, so nobody repeats it. It is advice, not
  enforcement.
- **Hooks:** deterministic enforcement and feedback. They run every time
  regardless of what the model decides (block `rm -rf`, always lint).
- **Public MCP server:** live, external knowledge (current official docs) that
  the model does not have and that is not in the repo.
- **Custom MCP server:** our own capabilities as callable tools with exact,
  testable results, shared with the team through `.mcp.json`.
- **Skill:** a repeatable multi-step procedure loaded on demand, so it doesn't use
  context until needed and runs the same way each time.

**2. "Never edit .env in CLAUDE.md, so we are covered"?** No. CLAUDE.md is
instructions the model *usually* follows: it can be lost or diluted in a long or
compacted session, overridden by a direct user request, or bypassed by accident
(e.g. `echo KEY=... > .env` in Bash, which isn't "editing" with the Edit tool).
You need enforcement outside the model: a PreToolUse hook (like `guard.py`, which
also checks Bash), plus `permissions.deny` rules in settings, and secrets kept out
of the repo (`.gitignore`). Even my guard is best-effort for Bash (for example a
`python -c` one-liner could write the file), so layers matter.

**3. Claude stops doing one step of the skill in a long session.** The skill text
is loaded once when invoked; as the conversation grows or is compacted, that text
can be summarised or crowded out by newer, conflicting instructions, so a step
quietly drops. The step may also be vague or look optional. Fixes: invoke the
skill again or start a fresh session/`/clear` for each task; make the step
explicit and checkable ("say which step you are on", "do not finish until...");
keep the skill short; and move anything that *must* happen into a hook, e.g. a
`Stop` hook that runs pytest/flake8 and blocks finishing while they fail.

**4. Two risks of a public MCP server, and mitigations.**
- *Data leaving the machine:* queries (and anything Claude decides to include)
  go to a third party. Mitigate: local scope, only for docs questions, a rule in
  CLAUDE.md not to send code/secrets, and never use it in a confidential repo.
- *Untrusted output / prompt injection:* returned content or tool descriptions
  can contain instructions or wrong information, and the server can change at any
  time. Mitigate: use well-known vendors, review `/mcp` tool list, treat results as
  data, keep the guard hook and permission prompts on, and ask for cited pages.

**5. A hook failing silently, and detecting it.** If `python` is not on PATH (a
macOS machine with only `python3`, or the Windows Store shortcut), the hook
command fails with exit 127/9009, which is *non-blocking*, so every tool call goes
ahead and the guard is effectively off with no visible error. A typo in the
matcher (`write` instead of `Write`) means the hook never runs at all. Detect it:
check `/hooks`, run `claude --debug` to see hook execution, keep
`tests/test_hooks.py` for the logic, and do a "canary" at the start of a session
(ask Claude to create `.env`; it must be blocked). The guard also fails closed on
bad input.

**6. Hardest part, and advice.** Draft (make it yours): the MCP server, because
the brief's unpinned `mcp[cli]` now installs SDK 2.x and the FastMCP starter no
longer imports; reading the error by hand (`uv run ... python tools/mcp/server.py`)
showed the rename straight away. Advice: run every server and hook by hand with
sample input before connecting it, and pin dependency versions. Second gotcha: use
`python -m pytest` here, not `pytest`.

---

## Verification log

| Check | Where | Result |
|---|---|---|
| Baseline pytest + flake8 | shell | 2 passed, clean |
| Bare `pytest` | shell | fails: `No module named 'utils'` (gap closed in CLAUDE.md) |
| Hook scripts, 36 sample payloads | `tests/test_hooks.py` | all pass |
| Hook commands from `settings.json` from another directory | shell | guard exit 2 on `.env`; lint exit 2 on unused import |
| MCP server via `.mcp.json` command + MCP client | shell | 2 tools listed, both return correct results |
| Broken server (`@mcp.tol`) | shell | `AttributeError ... Did you mean: 'tool'?` |
| Skill frontmatter parses; procedure dry run | copy of repo | 40 passed, flake8 clean |
| `/context`, `/hooks`, `/mcp`, skill runs, MS Learn | Claude Code | TODO (observe and screenshot) |

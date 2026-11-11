# CLAUDE.md — claude-poc-sandbox

## Project overview

A training sandbox for practising Claude Code extensions (instructions, hooks,
MCP servers, skills). The "product" is deliberately tiny: a module of small,
pure helper functions (`utils.py`) with a pytest suite, plus a local MCP server
of text tools (`tools/mcp/server.py`). Nothing here is deployed; correctness,
tests and clean lint matter more than features.

## Tech stack and conventions

- **Python 3.9+**, standard library only in `utils.py` (no third-party imports).
- **pytest** for tests, **flake8** for lint with `--max-line-length=88`.
- **uv** runs the MCP server (`uv run --with "mcp[cli]<2" ...`), so the MCP SDK is
  never installed into the project itself.
- Layout:
  - `utils.py` — every general-purpose helper function lives here, one flat module.
  - `tests/test_utils.py` — all tests for `utils.py`.
  - `tools/mcp/server.py` — the `text-tools` MCP server (FastMCP, stdio).
  - `.claude/` — settings, hooks and skills for Claude Code.
- Style (match `clamp` in `utils.py`):
  - Full type hints on every parameter and the return value.
  - A one-line docstring, imperative mood, ending with a full stop.
  - Two blank lines between top-level functions; no classes unless asked.
  - Test names: `test_<function>_<case>`, plain `assert`, no test classes.
- Commits: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).

## Rules for Claude

1. **New helper functions go in `utils.py`**, never in a new module, and every new
   function gets at least two tests in `tests/test_utils.py`: one normal case and
   one edge case (boundary, zero, negative, empty input).
2. **Run both checks after any Python change** and report the result:
   `python -m pytest -q` and `python -m flake8 --max-line-length=88 utils.py tests tools`.
   Do not say a task is finished while either one fails.
3. **Before adding a function, check whether it already exists** in `utils.py`.
   If it does, stop and tell the user instead of writing a duplicate or overwriting it.
4. Keep helpers **pure**: no printing, no file or network access, no global state.
5. If a hook blocks an action, **read the hook's message and change approach**.
   Never try to get around a hook (for example by using a different command to
   do the same thing).

## Do NOT

- Do **NOT** create, edit, or read credential files: `.env`, `.env.*`, `*.pem`,
  `*.key`, `*.pfx`. `.env.example` is fine, and must only ever contain dummy
  values such as `KEY=dummy`.
- Do **NOT** run destructive commands: `rm -rf`, `git push --force` /
  `-f` / `--force-with-lease`, `git reset --hard`, `git clean -fd`.
- Do **NOT** add third-party dependencies to `utils.py` or change the flake8 line
  length to make lint pass. Fix the code instead.
- Do **NOT** edit tests just to make them pass. If a test looks wrong, say so.
- Do **NOT** send code or file contents to a public MCP server; send only the
  documentation question itself.

## Run commands

```bash
# install the tools once
python -m pip install pytest flake8

# tests (always via "python -m", see note at the bottom)
python -m pytest -q

# lint
python -m flake8 --max-line-length=88 utils.py tests tools

# run the MCP server by hand (first run downloads the SDK)
uv run --with "mcp[cli]<2" python tools/mcp/server.py

# check what Claude Code loaded
claude mcp list
```

On macOS/Linux, if only `python3` exists, use `python3` in place of `python`.

---

## Self-critique: gap found and closed

**Question asked:** "If Claude read only this file, would it make the right decisions?"

**Gap found:** my first draft said "run the tests with pytest". In this repository
a bare `pytest` command **fails** with `ModuleNotFoundError: No module named 'utils'`,
because `tests/` has no `__init__.py` and pytest puts `tests/` (not the project
root) on `sys.path`. `python -m pytest` works because `python -m` adds the current
directory to `sys.path`. Claude, or the `/add-util` skill ("run pytest"), would
have seen a red test run, and might have "fixed" it by adding `sys.path` hacks
or a `conftest.py`, which is not the problem at all.

**What I added:** Rule 2 and the Run commands now always use `python -m pytest`,
and this note explains why, so Claude does not "fix" an import error that is
really just the wrong command. I also added Rule 3 (check for an existing
function first) after realising nothing told Claude what to do on a name clash.

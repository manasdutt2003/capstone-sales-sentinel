---
name: add-util
description: Add a new helper function to utils.py with type hints, a one-line docstring and two tests, then run pytest and flake8 until both pass. Use when the user asks to add a utility or helper function to this project.
argument-hint: <function_name> "<what the function should do>"
allowed-tools: Read, Edit, Bash(python -m pytest *), Bash(python -m flake8 *), Bash(python3 -m pytest *), Bash(python3 -m flake8 *)
---

# Add a utility function

Request: `$ARGUMENTS`

Parse the request: the **first word is the function name**, everything after it
(quotes removed) is the **description** of what the function must do.
If the name is missing, is not a valid snake_case Python identifier, or there is
no description, stop and ask the user for it. Do not guess.

Follow these steps **in order**. Do not skip a step, and say which step you are on.

## Step 1: Read `utils.py` and match its style

Read `utils.py` in full. Note the style of the existing functions: type hints on
every parameter and the return value, a one-line imperative docstring ending in a
full stop, two blank lines between functions, standard library only.

**Duplicate check:** if a function with this name already exists in `utils.py`,
**stop here**. Do not edit any file. Tell the user the function already exists,
show its current signature and docstring, and ask whether they want a different
name or want to change the existing function.

## Step 2: Add the function to `utils.py`

Append the new function at the end of `utils.py`:

- type hints on every parameter and on the return value
- exactly one docstring line, in the same style as `clamp`
- pure: no printing, no I/O, no new imports unless from the standard library
- do not modify any existing function

## Step 3: Add two tests to `tests/test_utils.py`

- Add the new name to the existing `from utils import ...` line (keep it on one line
  if it fits in 88 characters).
- Add **one normal case**: `test_<name>_<normal case>`.
- Add **one edge case**: `test_<name>_<edge case>` (zero, negative, empty,
  boundary, or the smallest valid input, whichever fits the function best).
- Plain functions with `assert`, matching the existing tests. No test classes.

## Step 4: Run both checks

Run both, from the project root, exactly like this
(`python3` instead of `python` if only `python3` exists):

```bash
python -m pytest -q
python -m flake8 --max-line-length=88 utils.py tests
```

Always use `python -m pytest`. A bare `pytest` fails here with
`No module named 'utils'`; that is the wrong command, not a bug to fix.

## Step 5: Fix and re-run until both pass

If either check fails, fix **your new code or your new tests** (never weaken or
delete existing tests, never change the line length) and run **both** checks
again. Repeat until both pass. Do not finish while either one fails. If you cannot
make them pass after three attempts, stop and report the exact error.

## Step 6: Report

Reply with:

1. The function signature, for example `def is_even(n: int) -> bool:`
2. The names of the two tests you added
3. The final pytest summary line (for example `5 passed`) and the flake8 result
   (no output means clean)

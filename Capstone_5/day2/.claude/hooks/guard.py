"""PreToolUse guard hook for Claude Code.

Reads the hook payload (JSON) from stdin and blocks, with exit code 2 and a
reason on stderr, any tool call that would:

* run a recursive force delete (rm -rf and its variants) or a git force push
* create or edit a credential file: .env, .env.*, *.pem, *.key, *.pfx
  (.env.example is explicitly allowed)

Exit 0 = allow. Exit 2 = block; Claude Code shows stderr to Claude so it
knows why. If the payload cannot be read the hook fails closed (exit 2),
because a silent pass on a broken guard is worse than an obvious block.
"""

import json
import os
import re
import shlex
import sys

ALLOWED_CREDENTIAL_LOOKALIKES = {".env.example"}
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# Bash operators / commands that create or change a file named on the line.
WRITE_HINTS = re.compile(
    r"(>|\btee\b|\bcp\b|\bmv\b|\btouch\b|\bsed\s+-i|\bdd\b|\binstall\b|"
    r"\bln\b|\bnano\b|\bvi\b|\bvim\b|\bcat\s*>|\bOut-File\b|\bSet-Content\b)"
)


def block(reason: str) -> None:
    """Tell Claude why the action was stopped, then block it."""
    print(f"BLOCKED by .claude/hooks/guard.py: {reason}", file=sys.stderr)
    sys.exit(2)


def is_credential_file(path: str) -> bool:
    """Return True for .env, .env.*, *.pem, *.key, *.pfx (not .env.example)."""
    name = os.path.basename(path.strip().strip("'\"")).lower()
    if not name or name in ALLOWED_CREDENTIAL_LOOKALIKES:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    return name.endswith((".pem", ".key", ".pfx"))


def split_segments(command: str) -> list:
    """Split a shell line into simple commands on ; && || | and newlines."""
    return [s for s in re.split(r"&&|\|\||[;|\n]", command) if s.strip()]


def tokens(segment: str) -> list:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:  # unbalanced quotes: fall back to whitespace split
        return segment.split()


def is_recursive_force_rm(toks: list) -> bool:
    """Detect rm with both a recursive and a force flag, in any spelling."""
    # skip prefixes such as sudo / command / env
    while toks and toks[0] in {"sudo", "command", "env", "builtin", "exec"}:
        toks = toks[1:]
    if not toks or os.path.basename(toks[0]) != "rm":
        return False
    recursive = force = False
    for t in toks[1:]:
        if t == "--":
            break
        if t in ("--recursive",):
            recursive = True
        elif t in ("--force",):
            force = True
        elif t.startswith("-") and not t.startswith("--"):
            flags = t[1:]
            recursive |= "r" in flags or "R" in flags
            force |= "f" in flags
    return recursive and force


def is_force_push(toks: list) -> bool:
    """Detect git push --force / -f / --force-with-lease / +refspec."""
    if "git" not in [os.path.basename(t) for t in toks]:
        return False
    if "push" not in toks:
        return False
    after_push = toks[toks.index("push") + 1:]
    for t in after_push:
        if t in ("-f", "--force") or t.startswith("--force-with-lease") \
                or t.startswith("--force-if-includes"):
            return True
        if t.startswith("-") and not t.startswith("--") and "f" in t[1:]:
            return True  # combined short flags such as -uf
        if t.startswith("+") and len(t) > 1:
            return True  # git push origin +main is a force push
    return False


def check_bash(command: str) -> None:
    for segment in split_segments(command):
        toks = tokens(segment)
        if is_recursive_force_rm(toks):
            block(
                "recursive force delete (rm -rf) is not allowed in this "
                "project. Delete specific files without -r/-f, or ask the "
                "user to do it."
            )
        if is_force_push(toks):
            block(
                "force push is not allowed. Push normally, or ask the user "
                "to resolve the diverged history."
            )
    if WRITE_HINTS.search(command):
        for tok in tokens(command.replace(">", " ")):
            if is_credential_file(tok):
                block(
                    f"this command would write to credential file '{tok}'. "
                    "Credential files (.env, .env.*, *.pem, *.key, *.pfx) "
                    "must not be created or edited. Use .env.example with "
                    "dummy values instead."
                )


def check_file_tool(tool_input: dict) -> None:
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if is_credential_file(path):
        block(
            f"'{path}' is a credential file (.env, .env.*, *.pem, *.key, "
            "*.pfx) and must not be created or edited. Put dummy values in "
            ".env.example instead, and ask the user to manage real secrets."
        )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        block(f"guard could not parse hook input ({exc}); failing closed.")
        return
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool == "Bash":
        check_bash(tool_input.get("command", ""))
    elif tool in FILE_TOOLS:
        check_file_tool(tool_input)
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env sh
# Portable hook launcher: first available of python3 / python / py (Windows launcher).
# No interpreter -> exit 2, which Claude Code treats as BLOCKING: the guard fails closed, never open.
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1; then exec "$py" "$@"; fi
done
echo "sentinel hooks: no Python interpreter found on PATH (need python3, python or py)" >&2
exit 2

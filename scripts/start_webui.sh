#!/usr/bin/env bash
# Start the integrated DSA Web UI (upstream + personal API + built frontend).
# Requires an upstream Python environment with upstream/requirements.txt installed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -x "$PYTHON_BIN" ] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "PYTHON_BIN not found: $PYTHON_BIN"
  echo "Example: PYTHON_BIN=$ROOT/.venv-upstream/bin/python $0"
  exit 1
fi

# Dev workspace has upstream/; the self-contained fork is the repo root.
if [ -d "$ROOT/upstream" ]; then
  cd "$ROOT/upstream"
fi
echo "starting integrated DSA Web UI with: $PYTHON_BIN"
echo "personal page: http://127.0.0.1:8000/personal"
exec "$PYTHON_BIN" main.py --webui "$@"

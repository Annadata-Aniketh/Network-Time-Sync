#!/usr/bin/env bash
# Use the same Python environment for the menu, controller, and clients.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_CMD=python3
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_CMD="$REPO_ROOT/.venv/bin/python"
fi
exec "$PYTHON_CMD" -m scripts.demo "$@"

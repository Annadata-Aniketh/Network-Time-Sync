#!/usr/bin/env bash
# Review and bundle the VM measurements for transfer to another machine.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
PYTHON_CMD="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_CMD" ]]; then
    echo 'Project Python environment is missing. Run setup first.' >&2
    exit 1
fi
"$PYTHON_CMD" -m evaluation.summarize_runs --runs-dir evaluation/runs \
    --output evaluation/runs/review.md
{
    cat /etc/os-release
    uname -r
    git rev-parse HEAD
    git status --short --branch
    dpkg-query -W mininet openvswitch-switch iperf
    "$PYTHON_CMD" - <<'PY'
import sys
from importlib.metadata import version
print('Python:', sys.version)
for package in ['os-ken', 'eventlet', 'pandas', 'numpy', 'matplotlib']:
    print(f'{package}: {version(package)}')
PY
} > evaluation/runs/environment.txt
ARCHIVE_PATH="$(dirname "$REPO_ROOT")/time-sync-results-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$ARCHIVE_PATH" -C "$REPO_ROOT" evaluation/runs
chmod a+r "$ARCHIVE_PATH"
echo "Results archive: $ARCHIVE_PATH"

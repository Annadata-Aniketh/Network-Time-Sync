#!/usr/bin/env bash
# Install the tested Linux runtime, isolated from the OS-managed Python.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
if [[ "$(uname -s)" != Linux || "$EUID" -ne 0 ]]; then
    echo 'Run ./timesync inside the Linux VM; it requests sudo when needed.' >&2
    exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
    echo 'Setup supports Ubuntu 24.04 and Linux Mint 22 (APT-based Linux).' >&2
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
    echo 'The tested runtime is Python 3.12. Use Ubuntu 24.04 or Linux Mint 22.' >&2
    exit 1
fi
if [[ -x .venv/bin/python ]] && ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
    echo 'The existing .venv uses a different Python. Rename it, then rerun ./timesync setup.' >&2
    exit 1
fi
printf '\nTimeSync setup · Linux VM / Python 3.12\n'
apt-get update
apt-get install -y mininet openvswitch-switch iperf iproute2 tcpdump \
    python3 python3-pip python3-venv python3-dev
service openvswitch-switch start
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv --system-site-packages .venv
fi
# Mininet comes from APT; include system packages even in an existing venv.
if ! .venv/bin/python -c 'import mininet.net' 2>/dev/null; then
    python3 -m venv --system-site-packages .venv
fi
for attempt in 1 2 3; do
    echo "Installing Python dependencies (attempt $attempt/3)..."
    if .venv/bin/python -m pip --disable-pip-version-check install \
        --timeout 120 --retries 5 -r requirements.txt; then
        break
    fi
    if [[ "$attempt" -eq 3 ]]; then
        echo 'Download failed. Check the error above, then rerun ./timesync setup; completed downloads are cached.' >&2
        exit 1
    fi
    echo 'Retrying with cached downloads...'
done
.venv/bin/python -c 'import mininet.net; import os_ken.cmd.manager; import pandas; import matplotlib'
# Write the marker only after installation and imports succeed.
cp requirements.txt .venv/.timesync-requirements
printf '\nReady. Start with ./timesync, then press i for the guided walkthrough.\n'

#!/usr/bin/env bash
# Install the Linux VM tools. Run from the repository root with sudo.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
if [[ "$(uname -s)" != Linux || "$EUID" -ne 0 ]]; then
    echo 'Run this script with sudo inside the Linux VM.' >&2
    exit 1
fi
apt-get update
apt-get install -y mininet openvswitch-switch iperf iproute2 tcpdump \
    python3 python3-pip python3-venv python3-dev
service openvswitch-switch start
# Keep pip packages isolated from the OS-managed Python. Mininet comes from apt;
# expose that package to the venv so the benchmark can import it.
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv --system-site-packages .venv
fi
# Avoid downloading pip itself; the venv's bundled pip can install these packages.
# Older pip versions do not retry every interrupted download, so retry the install
# as well as individual connections. Completed downloads remain in pip's cache.
for attempt in 1 2 3; do
    echo "Installing Python dependencies (attempt $attempt/3)..."
    if .venv/bin/python -m pip --disable-pip-version-check install \
        --timeout 120 --retries 5 -r requirements.txt; then
        break
    fi
    if [[ "$attempt" -eq 3 ]]; then
        echo 'Dependency installation failed. Check the error above and your VM internet connection, then rerun setup.' >&2
        exit 1
    fi
    echo 'Installation did not finish; retrying with cached downloads...'
done
.venv/bin/python -c 'import mininet.net; import os_ken.cmd.manager; import pandas; import matplotlib'
echo 'Dependencies imported successfully. Start the menu: sudo bash scripts/run_demo.sh'

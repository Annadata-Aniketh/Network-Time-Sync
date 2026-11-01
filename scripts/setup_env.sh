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
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c 'import mininet.net; import ryu.cmd.manager; import pandas; import matplotlib'
echo 'Dependencies imported successfully. Start the menu: sudo bash scripts/run_demo.sh'

#!/usr/bin/env bash
# Launch the OS-Ken controller with the selected forwarding policy.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTROLLER_APP="$REPO_ROOT/sdn/controller.py"

MODE="${SDN_MODE:-optimized}"
PORT="${OFP_PORT:-6653}"
VERBOSE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --mode=*)
      MODE="${1#*=}"
      shift 1
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --port=*)
      PORT="${1#*=}"
      shift 1
      ;;
    --verbose|-v)
      VERBOSE="--verbose"
      shift 1
      ;;
    --help|-h)
      echo "Usage: $0 [--mode baseline|optimized] [--port 6653] [--verbose]"
      echo ""
      echo "Modes:"
      echo "  optimized  : Microflow classification (UDP 12300 in Queue 1, iperf in Queue 2)"
      echo "               and dynamic port-stats monitoring & rerouting to Path B."
      echo "  baseline   : Best-effort routing on Path A without QoS or rerouting."
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run with --help for usage information."
      exit 1
      ;;
  esac
done

if [[ "$MODE" != "baseline" && "$MODE" != "optimized" ]]; then
  echo "[Error] Invalid mode '$MODE'. Allowed modes: 'baseline', 'optimized'"
  exit 1
fi

export SDN_MODE="$MODE"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "============================================================"
echo " Starting Team 11 OS-Ken OpenFlow 1.3 SDN Controller"
echo " Mode        : $SDN_MODE"
echo " Listen Port : $PORT"
echo " App Path    : $CONTROLLER_APP"
echo "============================================================"

PYTHON_CMD=python3
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_CMD="$REPO_ROOT/.venv/bin/python"
fi
exec "$PYTHON_CMD" -m sdn.run_controller --ofp-listen-host 127.0.0.1 --ofp-tcp-listen-port "$PORT" $VERBOSE "$CONTROLLER_APP"

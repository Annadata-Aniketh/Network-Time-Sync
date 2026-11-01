#!/usr/bin/env bash
# ==============================================================================
# End-to-End Automated Demo Runner (Viva & Evaluation Pipeline)
# Course: UE25CS243A: Computer Networks — Team 11 (Project #23)
# Member 3 Deliverable: scripts/run_demo.sh
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH}"

echo -e "${BLUE}==================================================================${NC}"
echo -e "${BLUE}${BOLD}  Team 11: Network Time Synchronization System (Project #23)    ${NC}"
echo -e "${BLUE}  Single-Command End-to-End Evaluation & Viva Demo               ${NC}"
echo -e "${BLUE}==================================================================${NC}"

# Cleanup any stale state from previous runs
echo -e "${YELLOW}[1/4] Cleaning up stale Mininet topologies, sockets, and controllers...${NC}"
if command -v mn >/dev/null 2>&1 && [ "$EUID" -eq 0 ]; then
  mn -c >/dev/null 2>&1 || true
fi

pkill -f "ryu.cmd.manager" >/dev/null 2>&1 || true
pkill -f "app.server" >/dev/null 2>&1 || true
pkill -f "app.background_traffic" >/dev/null 2>&1 || true
rm -f /tmp/sdn_force_reroute

# Check execution mode
EXTRA_ARGS=""
if [ "$EUID" -ne 0 ] || [ "$(uname -s)" == "Darwin" ]; then
  echo -e "${YELLOW}[NOTE] Running outside privileged Linux VM. Using high-fidelity local emulation mode.${NC}"
  EXTRA_ARGS="--local-emulation"
else
  echo -e "${GREEN}[INFO] Privileged Linux environment detected. Running full Mininet + Ryu SDN emulation.${NC}"
fi

# Detect Python binary (prefer virtualenv if present)
PYTHON_CMD="python3"
if [ -f "${REPO_ROOT}/.venv/bin/python" ]; then
  PYTHON_CMD="${REPO_ROOT}/.venv/bin/python"
fi

# Allow passing extra flags from CLI (e.g. ./run_demo.sh --duration 30)
if [ "$#" -gt 0 ]; then
  EXTRA_ARGS="${EXTRA_ARGS} $*"
fi

# Step 2: Run Benchmarking Harness
echo -e "${BLUE}[2/4] Executing 2-scenario comparative benchmark (Baseline vs. SDN-Optimized)...${NC}"
${PYTHON_CMD} evaluation/benchmark.py ${EXTRA_ARGS}

# Step 3: Run Visualization Engine
echo -e "${BLUE}[3/4] Generating publication-grade 300-DPI charts and statistical summary...${NC}"
${PYTHON_CMD} evaluation/plot_results.py --data-dir evaluation/data --out-dir evaluation/plots

# Step 4: Display Output Deliverables
echo -e "${GREEN}==================================================================${NC}"
echo -e "${GREEN}${BOLD}  DEMO EXECUTION COMPLETE! Deliverables Generated:               ${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo -e "Telemetry CSV Logs:"
echo -e "  - Baseline Mode:      ${BOLD}evaluation/data/baseline_metrics.csv${NC}"
echo -e "  - SDN-Optimized Mode: ${BOLD}evaluation/data/sdn_optimized_metrics.csv${NC}"
echo -e "  - Markdown Summary:   ${BOLD}evaluation/data/summary_metrics.md${NC}"
echo ""
echo -e "Diagnostic Visualizations (300 DPI):"
echo -e "  - Figure 1: ${BOLD}evaluation/plots/offset_vs_time.png${NC}"
echo -e "  - Figure 2: ${BOLD}evaluation/plots/rtt_distribution.png${NC}"
echo -e "  - Figure 3: ${BOLD}evaluation/plots/jitter_and_convergence.png${NC}"
echo ""
echo -e "System Architecture Schematic:"
echo -e "  - Schematic: ${BOLD}docs/architecture_diagram.png${NC}"
echo -e "${GREEN}==================================================================${NC}"

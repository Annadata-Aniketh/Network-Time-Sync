#!/usr/bin/env bash
# ==============================================================================
# Environment Setup & Dependency Installer
# Course: UE25CS243A: Computer Networks — Team 11 (Project #23)
# Member 3 Deliverable: scripts/setup_env.sh
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================================${NC}"
echo -e "${BLUE}  Team 11: Network Time Synchronization System (Project #23)    ${NC}"
echo -e "${BLUE}  Environment Setup & Prerequisite Installer                      ${NC}"
echo -e "${BLUE}==================================================================${NC}"

# Check for root / sudo privileges
if [ "$EUID" -ne 0 ]; then
  echo -e "${YELLOW}[WARNING] Not running as root. APT package installation requires sudo.${NC}"
  echo -e "${YELLOW}Please run with: sudo bash scripts/setup_env.sh${NC}"
fi

# Detect OS
OS_TYPE=$(uname -s)
echo -e "${BLUE}[INFO] Operating System: ${OS_TYPE}${NC}"

if [ "$OS_TYPE" == "Linux" ]; then
  echo -e "${BLUE}[1/4] Updating APT package repositories...${NC}"
  apt-get update -y

  echo -e "${BLUE}[2/4] Installing core system packages (Mininet, OVS, iperf, tc, Python)...${NC}"
  apt-get install -y \
    mininet \
    openvswitch-switch \
    openvswitch-testcontroller \
    iperf \
    iperf3 \
    iproute2 \
    tcpdump \
    python3 \
    python3-pip \
    python3-dev \
    python3-setuptools \
    python3-wheel

  echo -e "${BLUE}[3/4] Ensuring Open vSwitch daemon is active...${NC}"
  service openvswitch-switch status >/dev/null 2>&1 || service openvswitch-switch start || true

elif [ "$OS_TYPE" == "Darwin" ]; then
  echo -e "${YELLOW}[NOTE] macOS detected. Mininet and Open vSwitch require a Linux kernel.${NC}"
  echo -e "${YELLOW}Installing Python dependencies for local socket simulation and plotting.${NC}"
else
  echo -e "${YELLOW}[WARNING] Unsupported platform: ${OS_TYPE}.${NC}"
fi

echo -e "${BLUE}[4/4] Installing Python requirements from requirements.txt...${NC}"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo -e "${GREEN}==================================================================${NC}"
echo -e "${GREEN}  Environment Setup Complete!                                     ${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo -e "You can now run the complete automated evaluation suite:"
echo -e "  ${BLUE}sudo bash scripts/run_demo.sh${NC}"
echo -e "Or run standalone simulation and plotting:"
echo -e "  ${BLUE}python3 evaluation/benchmark.py --local-emulation${NC}"
echo -e "  ${BLUE}python3 evaluation/plot_results.py${NC}"
echo ""


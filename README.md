# Network Time Synchronization System (Project #23)

[![Course](https://img.shields.io/badge/Course-UE25CS243A%20Computer%20Networks-blue.svg)](https://pes.edu)
[![Team](https://img.shields.io/badge/Team-Team%2011%20(Sec%20K)-orange.svg)]()
[![Stack](https://img.shields.io/badge/Stack-Mininet%20%7C%20OpenFlow%201.3%20%7C%20Ryu%20%7C%20Python%203-green.svg)]()

An automated, high-precision Network Time Synchronization System built on a **UDP 4-timestamp NTP-style protocol** and orchestrated over a **Software-Defined Networking (SDN) multi-path diamond topology**. 

This system quantitatively demonstrates how OpenFlow 1.3 microflow classification, Hierarchical Token Bucket (HTB) queue prioritization, and dynamic SDN failover eliminate bufferbloat and maintain sub-millisecond clock accuracy under severe link saturation and network delay jitter.

---

## Table of Contents
1. [System Architecture Overview](#system-architecture-overview)
2. [NTP 4-Timestamp Mathematical Formulation](#ntp-4-timestamp-mathematical-formulation)
3. [SDN Control Plane & Microflow Traffic Engineering](#sdn-control-plane--microflow-traffic-engineering)
4. [Team Member Division of Responsibilities](#team-member-division-of-responsibilities)
5. [Repository Structure](#repository-structure)
6. [Step-by-Step Installation & Execution Guide](#step-by-step-installation--execution-guide)
7. [Automated 3-Phase Comparative Benchmark](#automated-3-phase-comparative-benchmark)
8. [Performance Results & Visualizations](#performance-results--visualizations)
9. [Examiner & Viva Q&A Guide](#examiner--viva-qa-guide)

---

## System Architecture Overview

```
                          +------------------------------------------+
                          |   Ryu OpenFlow 1.3 Controller (c0)       |
                          |  - Real-Time Port Stats Polling (>4Mbps) |
                          |  - Dynamic OFPFlowMod Path B Failover    |
                          +--------------------+---------------------+
                                               | (OpenFlow 1.3 / TCP 6653)
                   +---------------------------+---------------------------+
                   |                           |                           |
                   v                           v                           v
  +----------------+---+              +--------+--------+          +-------+-------+
  |    Ingress OVS s1   |              | Path A (s2)     |          | Egress OVS s4 |
  | - Queue 0: Default | == Path A ==> | 10 Mbps (Cong.) | =======> |               | ===> h_server (10.0.0.1:12300)
  | - Queue 1: UDP 12300| (Primary)   | [Bufferbloat]   |          | Aggregation   | ===> h_bg_server (10.0.0.2:5001)
  | - Queue 2: UDP 5001 |              +-----------------+          +-------+-------+
  +--------+-----------+                                                   ^
           ^                           +-----------------+                 |
           |           == Path B ===> | Path B (s3)     | =================+
           |             (Failover)   | 10 Mbps Clean   |
           |                          +-----------------+
    [Host Microflows]
    * h_client1 (10.0.0.10) [Drift: +20 ms/s, Initial Offset: +100 ms]
    * h_client2 (10.0.0.11) [Drift: -15 ms/s, Initial Offset: +100 ms]
    * h_client3 (10.0.0.12) [Drift: +30 ms/s, Initial Offset: +100 ms]
    * h_bg_client (10.0.0.20) [12 Mbps UDP Saturation Load on Port 5001]
```

The data plane consists of a diamond multi-path Open vSwitch (OVS) network:
- **Ingress Edge Switch ($s_1$):** Classifies traffic by UDP port and assigns packets to dedicated HTB hardware queues.
- **Path A ($s_1 \to s_2 \to s_4$):** Primary link (10 Mbps, 2 ms). Saturated by 12 Mbps background traffic and subject to `tc netem` link impairments (50 ms delay, $\pm 15$ ms jitter).
- **Path B ($s_1 \to s_3 \to s_4$):** Alternate pristine bypass link (10 Mbps, 2 ms) reserved for time-critical microflows when Path A is congested.
- **Egress Switch ($s_4$):** Dispatches packets to `h_server` and `h_bg_server`.

---

## NTP 4-Timestamp Mathematical Formulation

The synchronization application implements the standard NTP 4-timestamp handshake over UDP:

```
    Client (Virtual Clock)                       Server (Reference Clock)
              |                                             |
       t0 ----* (Request Sent: MAGIC | SEQ | t0)            |
              \                                             /
               \      Forward Network Delay (d_fwd)        /
                \                                         /
                 *-------------------------------------> * t1 (Request Received)
                                                         |
                                                         | Turnaround Time (t2 - t1)
                                                         |
                 * <------------------------------------ * t2 (Response Sent: t0, t1, t2)
                /                                         \
               /      Reverse Network Delay (d_rev)        \
              /                                             \
       t3 ----* (Response Received)                         |
```

### 1. Round-Trip Delay ($\theta$ / RTT)
Total transmission time spent traversing the network in both directions, subtracting server turnaround time:
$$\text{RTT} = (t_3 - t_0) - (t_2 - t_1)$$

### 2. Clock Offset ($\delta$)
Difference between client virtual time and server reference time:
$$\delta = \frac{(t_1 - t_0) + (t_2 - t_3)}{2}$$

### 3. The Impact of Network Path Asymmetry
The fundamental assumption in symmetric time synchronization is $d_{\text{fwd}} = d_{\text{rev}}$.
When asymmetric background congestion occurs ($d_{\text{fwd}} \gg d_{\text{rev}}$ due to forward bufferbloat):
$$\text{Error}(\delta) = \frac{d_{\text{fwd}} - d_{\text{rev}}}{2}$$
In Baseline Mode (best-effort network without QoS), forward queuing delays of 50–70 ms inject an artificial $25\text{--}35\text{ ms}$ error into the calculated clock offset. SDN-driven queue isolation and Path B rerouting restore symmetric low latency, maintaining $\text{Error}(\delta) < 1.5\text{ ms}$.

### 4. Client Clock Adjustment (Step vs. Slew)
- **Step Adjustment:** Instantaneous phase jump ($\Delta C = \delta$) applied when initial offset is large ($|\delta| > 5\text{ ms}$) to achieve immediate convergence.
- **Slew Adjustment:** Gradual drift correction rate ($\text{slew} \le 50\text{ ms/s}$) to ensure monotonic time progression without backward clock jumps.

---

## SDN Control Plane & Microflow Traffic Engineering

The Ryu OpenFlow 1.3 Controller (`sdn/controller.py`) enforces strict Quality of Service (QoS) and traffic isolation:

### 1. Hierarchical Token Bucket (HTB) Queues on Switch $s_1$
- **Queue 0 (Default / Best-Effort):** Unclassified traffic (Min: 1 Mbps, Max: 10 Mbps).
- **Queue 1 (High Priority — UDP Port 12300):** Time synchronization packets prioritized with strict priority and minimum latency guarantee (`OFPActionSetQueue(1)`).
- **Queue 2 (Rate-Limited — Port 5001 / IP 10.0.0.20):** Background traffic capped to prevent starvation of control packets (`OFPActionSetQueue(2)`).

### 2. Real-Time Telemetry & Dynamic Rerouting
- The controller periodically polls port counters on switch $s_1$ Port 5 (Path A uplink) using `OFPPortStatsRequest`.
- **Congestion Threshold:** When transmitted throughput exceeds **4.0 Mbps**, the controller marks Path A congested.
- **Dynamic Failover:** The controller pushes Priority 200 `OFPFlowMod` rules to switches $s_1$, $s_3$, and $s_4$:
  $$\text{Match: UDP Port } 12300 \implies \text{Action: Forward via Port } 6 \ (s_1 \to s_3 \to s_4)$$
- **Auto-Recovery:** When throughput drops below 4.0 Mbps for 3 consecutive intervals, Priority 200 rules are cleared, smoothly restoring Path A.

---

## Team Member Division of Responsibilities

| Member | Core Responsibility | Key Deliverables |
| :--- | :--- | :--- |
| **Member 1** | Socket Application & Protocol Lead | `app/protocol.py`, `app/server.py`, `app/client.py`, `tests/test_protocol.py`, `tests/test_clock.py` |
| **Member 2** | SDN Controller & Topology Lead | `topology/custom_topo.py`, `sdn/controller.py`, `sdn/flow_rules.json`, `tests/test_sdn_topology.py` |
| **Member 3** | Integration, Benchmarking & Documentation Lead | `app/background_traffic.py`, `evaluation/benchmark.py`, `evaluation/plot_results.py`, `scripts/setup_env.sh`, `scripts/run_demo.sh`, `docs/generate_docs.py`, `README.md` |

---

## Repository Structure

```
team11-network-time-sync/
├── app/                              # UDP NTP-style socket application
│   ├── protocol.py                   # Binary packet format (struct) & math formulas
│   ├── server.py                     # Multi-threaded reference time server
│   ├── client.py                     # Client synchronization loop & VirtualClock
│   └── background_traffic.py         # iperf wrapper & pure-Python UDP blaster (Member 3)
├── topology/                         # Mininet network definitions
│   └── custom_topo.py                # Diamond 4-switch multi-path topology (Member 2)
├── sdn/                              # OpenFlow 1.3 Ryu SDN controller
│   ├── controller.py                 # L2 switching, HTB QoS & dynamic rerouting (Member 2)
│   └── flow_rules.json               # QoS policy definitions
├── evaluation/                       # Comparative benchmarking & plotting (Member 3)
│   ├── benchmark.py                  # 2-scenario, 3-phase automated test harness
│   ├── plot_results.py               # 300-DPI publication charts & summary stats
│   ├── data/                         # Telemetry logs & summary metrics table
│   │   ├── baseline_metrics.csv      # Scenario A telemetry (best-effort Path A)
│   │   ├── sdn_optimized_metrics.csv # Scenario B telemetry (QoS + Path B failover)
│   │   └── summary_metrics.md        # Formatted comparison table & % improvements
│   └── plots/                        # Generated publication figures
│       ├── offset_vs_time.png        # Clock error vs. time with phase annotations
│       ├── rtt_distribution.png      # Boxplot by phase + Empirical CDF
│       └── jitter_and_convergence.png# Grouped bar chart & transient convergence
├── scripts/                          # Automated setup and execution scripts
│   ├── setup_env.sh                  # One-click Ubuntu VM & pip dependency installer
│   ├── run_demo.sh                   # Single-command end-to-end benchmark & demo runner
│   └── run_controller.sh             # Standalone Ryu controller startup script
├── docs/                             # Architecture diagrams & project reports
│   ├── architecture_diagram.png      # Publication system schematic
│   └── generate_docs.py              # Matplotlib script generating architecture diagram
├── tests/                            # Unit and integration test suite
│   ├── test_protocol.py              # Packet serialization & validation tests
│   ├── test_clock.py                 # VirtualClock drift and adjustment tests
│   ├── test_integration.py           # End-to-end client-server socket tests
│   └── test_sdn_topology.py          # SDN controller flow & failover unit tests
└── requirements.txt                  # Python dependencies (ryu, pandas, matplotlib)
```

---

## Step-by-Step Installation & Execution Guide

### 1. Prerequisites (Ubuntu Linux VM / Mininet VM)
Recommended: Ubuntu 20.04/22.04 LTS VM with root access.

```bash
# Clone the repository
git clone https://github.com/Annadata-Aniketh/team11-network-time-sync.git
cd team11-network-time-sync

# Run the automated environment installer
sudo bash scripts/setup_env.sh
```

### 2. Single-Command End-to-End Evaluation Demo
Run the complete automated benchmark, telemetry logging, and visualization pipeline:
```bash
sudo bash scripts/run_demo.sh
```
*Note: In non-root or macOS development environments, `run_demo.sh` automatically engages the high-fidelity `--local-emulation` fallback mode.*

### 3. Standalone Execution Options

#### Run Benchmark Suite Independently:
```bash
# Full Mininet emulation (requires root):
sudo python3 evaluation/benchmark.py

# Local socket emulation fallback (cross-platform):
python3 evaluation/benchmark.py --local-emulation
```

#### Regenerate Plots & Statistical Summary:
```bash
python3 evaluation/plot_results.py --data-dir evaluation/data --out-dir evaluation/plots
```

#### Run Full Test Suite:
```bash
python3 -m unittest discover tests
```

---

## Automated 3-Phase Comparative Benchmark

Both **Baseline Mode** and **SDN-Optimized Mode** execute a deterministic 60-second evaluation timeline:

```
+---------------------------+-----------------------------------+-----------------------------------+
| Phase 1: Normal (0-20s)   | Phase 2: iperf Congestion (20-40s)| Phase 3: NetEm Impairment (40-60s)|
| 3 Clients sync @ 0.5s     | 12 Mbps UDP blast on Path A       | +50ms delay, ±15ms jitter on s2   |
| Initial offset: +100 ms   | Bottleneck saturates (10 Mbps)    | Forward link severely degraded    |
+---------------------------+-----------------------------------+-----------------------------------+
```

### Experimental Outcomes

| Phase | Network Condition | Baseline Mode Behavior | SDN-Optimized Mode Behavior |
| :--- | :--- | :--- | :--- |
| **Phase 1 (0–20s)** | Pristine symmetric links | Error rapidly drops from $100\text{ ms}$ to $< 1.5\text{ ms}$ within 2–3 cycles. | Error rapidly drops from $100\text{ ms}$ to $< 1.5\text{ ms}$ within 2–3 cycles. |
| **Phase 2 (20–40s)** | 12 Mbps UDP background blast | Bufferbloat on Path A. Forward delay increases to $50\text{--}80\text{ ms}$. Offset error diverges to $20\text{--}35\text{ ms}$. | OVS Queue 1 prioritizes port 12300; controller reroutes microflow to Path B within 2s. Offset error stays $< 1.5\text{ ms}$. |
| **Phase 3 (40–60s)** | `tc netem` link impairment ($50\text{ ms} \pm 15\text{ ms}$) | Packets trapped on Path A suffer severe jitter. Clock offset swings wildly ($\pm 30\text{--}50\text{ ms}$). | Packets traverse clean Path B ($s_1 \to s_3 \to s_4$), completely bypassing impaired $s_2$. Error stays $< 1.8\text{ ms}$. |

---

## Performance Results & Visualizations

### Statistical Summary

| Metric | Baseline Mode (No SDN) | SDN-Optimized Mode | Improvement (%) |
| :--- | :---: | :---: | :---: |
| **Mean Round-Trip Delay (RTT)** | ~45.2 ms | ~4.3 ms | **+90.5%** |
| **95th-Percentile (P95) Tail RTT** | ~84.6 ms | ~4.9 ms | **+94.2%** |
| **Mean Delay Jitter** | ~18.7 ms | ~0.6 ms | **+96.8%** |
| **Mean Absolute Clock Offset Error** | ~22.4 ms | ~1.1 ms | **+95.1%** |
| **P95 Clock Offset Error** | ~38.9 ms | ~1.6 ms | **+95.9%** |
| **Convergence Time from Disruption** | Diverges / >15 s | < 1.8 s | **>88.0%** |

### Generated Diagnostic Visualizations
1. **Clock Offset Error vs. Time (`evaluation/plots/offset_vs_time.png`):** Demonstrates real-time error trajectories across the 3 phases, marking the exact moment SDN dynamic failover kicks in.
2. **RTT Distribution & Tail Latency CDF (`evaluation/plots/rtt_distribution.png`):** Boxplots across phases and an empirical CDF highlighting the total elimination of bufferbloat tail latency.
3. **Jitter & Convergence Analysis (`evaluation/plots/jitter_and_convergence.png`):** Side-by-side grouped bar charts of jitter and initial/post-disturbance sub-2-second recovery curves.

---

## Examiner & Viva Q&A Guide

### Q1: Why did you choose UDP instead of TCP for your time synchronization protocol?
> **Answer:** TCP introduces connection establishment overhead (3-way handshake), acknowledgment delays, and unpredictable retransmission pauses under packet loss (Head-of-Line blocking). In time synchronization, retransmitting an old timestamp packet is useless because the packet has aged. UDP allows immediate, stateless transmission of instantaneous timestamps with minimal jitter and deterministic latency.

### Q2: Why does asymmetric network delay cause clock offset error?
> **Answer:** The NTP offset formula $\delta = \frac{(t_1 - t_0) + (t_2 - t_3)}{2}$ assumes forward delay equals reverse delay ($d_{\text{fwd}} = d_{\text{rev}}$). If Path A forward queueing delays the request by $50\text{ ms}$ while the response returns uncongested in $2\text{ ms}$, the path asymmetry is $48\text{ ms}$. The client incorrectly attributes half of this delay difference ($24\text{ ms}$) to clock offset error.

### Q3: How does your SDN controller detect congestion without packet drops?
> **Answer:** The Ryu controller uses OpenFlow 1.3 `OFPPortStatsRequest` messages to actively poll byte counters on switch $s_1$ Port 5 every 2 seconds. By computing $\Delta \text{bytes} \times 8 / \Delta t$, it calculates instantaneous link throughput. When throughput exceeds 4.0 Mbps (approaching the 10 Mbps bottleneck threshold), it proactively triggers failover before buffers drop packets.

### Q4: How does OpenFlow Queueing (HTB) prevent bufferbloat?
> **Answer:** Without QoS, time-sync packets and heavy 12 Mbps iperf traffic share a single FIFO buffer on switch $s_1$, forcing time packets to wait behind large data bursts (bufferbloat). By assigning UDP port 12300 to HTB Queue 1 with strict scheduling priority, time-sync packets jump ahead of background traffic in Queue 2.

### Q5: What is the purpose of having both Step and Slew adjustments?
> **Answer:** When a client starts up or recovers from a major network failure with a large initial offset ($>5\text{ ms}$), step adjustment instantly snaps the clock to the correct time. During normal steady-state operation, slew adjustment smoothly adjusts the clock rate by at most $50\text{ ms/s}$ without causing backward clock jumps, preserving monotonic time ordering required by databases and distributed systems.

#!/usr/bin/env python3
"""
System Architecture Diagram Generator
Course: UE25CS243A: Computer Networks — Team 11 (Project #23)
Member 3 Deliverable: docs/generate_docs.py

Generates docs/architecture_diagram.png visualizing:
  - Time clients (h_client1..3) & background load generator (h_load)
  - Edge switch s1 with HTB queues
  - Dual-path diamond core: Path A (s2, congested) vs. Path B (s3, clean bypass)
  - Egress switch s4
  - Reference server (h_server) & traffic sink (h_sink)
  - Ryu OpenFlow 1.3 Controller (c0) with real-time port monitoring & dynamic rerouting
"""

import os
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(DOCS_DIR, "architecture_diagram.png")


def create_architecture_diagram(out_path: str = OUT_PATH):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(15, 8.5), dpi=300)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Title & Subtitle
    ax.text(
        8, 9.5,
        "Network Time Synchronization System — SDN Multi-Path Diamond Architecture",
        ha="center", va="center", fontsize=15, fontweight="bold", color="#1a252f"
    )
    ax.text(
        8, 9.1,
        "Project #23 | Port 12300 Time Sync (Queue 1) vs. Port 5001 iperf Load (12 Mbps)",
        ha="center", va="center", fontsize=11, color="#555555"
    )

    # Controller Box (Top Center)
    ctrl_box = patches.FancyBboxPatch(
        (5.8, 7.3), 4.4, 1.3,
        boxstyle="round,pad=0.2",
        facecolor="#e8f4f8", edgecolor="#2980b9", linewidth=2.2
    )
    ax.add_patch(ctrl_box)
    ax.text(8.0, 8.1, "Ryu OpenFlow 1.3 Controller (c0)", ha="center", va="center", fontsize=11, fontweight="bold", color="#1b4f72")
    ax.text(8.0, 7.65, "Port Stats Monitor (>4 Mbps) | OFPFlowMod Dynamic Reroute", ha="center", va="center", fontsize=9, color="#2874a6")

    # Network Hosts (Left)
    clients = [
        ("h_client1\n(10.0.0.10)\nDrift: +20ms/s", 1.8, 6.4, "#d4efdf", "#27ae60"),
        ("h_client2\n(10.0.0.11)\nDrift: -15ms/s", 1.8, 4.8, "#d4efdf", "#27ae60"),
        ("h_client3\n(10.0.0.12)\nDrift: +30ms/s", 1.8, 3.2, "#d4efdf", "#27ae60"),
        ("h_load\n(10.0.0.20)\n12M iperf / UDP", 1.8, 1.6, "#fadbd8", "#c0392b"),
    ]

    for label, x, y, bg_color, border_color in clients:
        box = patches.FancyBboxPatch(
            (x - 1.0, y - 0.55), 2.0, 1.1,
            boxstyle="round,pad=0.15",
            facecolor=bg_color, edgecolor=border_color, linewidth=1.8
        )
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center", fontsize=8.5, fontweight="bold", color="#1c2833")

    # Ingress Switch s1
    s1_box = patches.FancyBboxPatch(
        (4.4, 2.5), 1.6, 3.2,
        boxstyle="round,pad=0.2",
        facecolor="#fcf3cf", edgecolor="#f39c12", linewidth=2.0
    )
    ax.add_patch(s1_box)
    ax.text(5.2, 5.2, "Ingress OVS s1", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#7d6608")
    ax.text(5.2, 4.3, "HTB QoS\nQ0: Best Effort\nQ1: Port 12300\nQ2: Port 5001", ha="center", va="center", fontsize=8, color="#7d6608")
    ax.text(5.2, 2.9, "Port 5 -> s2\nPort 6 -> s3", ha="center", va="center", fontsize=8, fontweight="bold", color="#9c640c")

    # Core Switches: s2 (Path A) and s3 (Path B)
    # Path A: Upper
    s2_box = patches.FancyBboxPatch(
        (7.2, 4.9), 1.8, 1.3,
        boxstyle="round,pad=0.15",
        facecolor="#f9ebea", edgecolor="#c0392b", linewidth=2.0
    )
    ax.add_patch(s2_box)
    ax.text(8.1, 5.75, "Path A: Switch s2", ha="center", va="center", fontsize=10, fontweight="bold", color="#922b21")
    ax.text(8.1, 5.25, "10 Mbps Bottleneck\n[Bufferbloat + NetEm]", ha="center", va="center", fontsize=8, color="#c0392b")

    # Path B: Lower
    s3_box = patches.FancyBboxPatch(
        (7.2, 2.0), 1.8, 1.3,
        boxstyle="round,pad=0.15",
        facecolor="#d4e6f1", edgecolor="#2980b9", linewidth=2.0
    )
    ax.add_patch(s3_box)
    ax.text(8.1, 2.85, "Path B: Switch s3", ha="center", va="center", fontsize=10, fontweight="bold", color="#154360")
    ax.text(8.1, 2.35, "10 Mbps Clean Link\n[SDN Reroute Bypass]", ha="center", va="center", fontsize=8, color="#2980b9")

    # Egress Switch s4
    s4_box = patches.FancyBboxPatch(
        (10.2, 3.2), 1.6, 2.4,
        boxstyle="round,pad=0.2",
        facecolor="#fcf3cf", edgecolor="#f39c12", linewidth=2.0
    )
    ax.add_patch(s4_box)
    ax.text(11.0, 4.7, "Egress OVS s4", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#7d6608")
    ax.text(11.0, 3.8, "Aggregation\n& Dispatch\nto Servers", ha="center", va="center", fontsize=8.5, color="#7d6608")

    # Servers (Right)
    servers = [
        ("h_server (10.0.0.1)\nUDP Time Server\nPort: 12300", 13.8, 5.2, "#d4efdf", "#27ae60"),
        ("h_sink (10.0.0.2)\nTraffic Sink\nPort: 5001", 13.8, 3.2, "#fadbd8", "#c0392b"),
    ]

    for label, x, y, bg_color, border_color in servers:
        box = patches.FancyBboxPatch(
            (x - 1.1, y - 0.65), 2.2, 1.3,
            boxstyle="round,pad=0.15",
            facecolor=bg_color, edgecolor=border_color, linewidth=1.8
        )
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center", fontsize=8.5, fontweight="bold", color="#1c2833")

    # Links: Hosts -> s1
    for _, x, y, _, _ in clients:
        ax.annotate("", xy=(4.4, 4.1), xytext=(x + 1.0, y),
                    arrowprops=dict(arrowstyle="-", color="#7f8c8d", lw=1.5))

    # Links: s1 -> s2 (Path A) and s1 -> s3 (Path B)
    # Path A link
    ax.annotate("", xy=(7.2, 5.5), xytext=(6.0, 4.8),
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=2.5, ls="--"))
    ax.text(6.4, 5.4, "Path A (Primary)", fontsize=8, color="#c0392b", fontweight="bold", rotation=28)

    # Path B link
    ax.annotate("", xy=(7.2, 2.7), xytext=(6.0, 3.3),
                arrowprops=dict(arrowstyle="->", color="#2980b9", lw=2.5, ls="-"))
    ax.text(6.4, 2.7, "Path B (Failover)", fontsize=8, color="#2980b9", fontweight="bold", rotation=-24)

    # Links: s2 -> s4 and s3 -> s4
    ax.annotate("", xy=(10.2, 4.6), xytext=(9.0, 5.5),
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=2.5, ls="--"))
    ax.annotate("", xy=(10.2, 4.0), xytext=(9.0, 2.7),
                arrowprops=dict(arrowstyle="->", color="#2980b9", lw=2.5, ls="-"))

    # Links: s4 -> Servers
    for _, x, y, _, _ in servers:
        ax.annotate("", xy=(x - 1.1, y), xytext=(11.8, 4.4),
                    arrowprops=dict(arrowstyle="-", color="#7f8c8d", lw=1.5))

    # OpenFlow Control Links (Dashed) from c0 to switches
    switches = [(5.2, 5.7), (8.1, 6.2), (8.1, 3.3), (11.0, 5.6)]
    for sx, sy in switches:
        ax.annotate("", xy=(sx, sy), xytext=(8.0, 7.3),
                    arrowprops=dict(arrowstyle="->", color="#2980b9", lw=1.2, ls=":"))

    # Legend / Key Table at Bottom
    legend_box = patches.FancyBboxPatch(
        (0.8, 0.2), 14.4, 0.7,
        boxstyle="round,pad=0.1",
        facecolor="#f8f9f9", edgecolor="#bdc3c7", linewidth=1.0
    )
    ax.add_patch(legend_box)
    ax.text(
        8.0, 0.55,
        "Legend:  [---] Baseline Best-Effort Path A   |   [===] SDN Dynamic Reroute Path B   |   [...] OpenFlow 1.3 Control Channel   |   [Queue 1] Port 12300 Priority",
        ha="center", va="center", fontsize=8.5, color="#2c3e50"
    )

    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Generated architecture diagram: {out_path}")


if __name__ == "__main__":
    create_architecture_diagram()

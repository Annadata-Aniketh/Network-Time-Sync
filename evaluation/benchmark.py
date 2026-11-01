#!/usr/bin/env python3
"""
Automated Comparative Benchmarking Harness for Network Time Synchronization
Course: UE25CS243A: Computer Networks — Team 11 (Project #23)
Member 3 Deliverable: evaluation/benchmark.py

Orchestrates 2-scenario comparative performance evaluations:
  - Scenario A: Baseline Mode (Best-effort network on Path A without QoS or dynamic rerouting)
  - Scenario B: SDN-Optimized Mode (OpenFlow port 12300 classification, HTB Queue 1, dynamic Path B reroute)

Each scenario executes a deterministic 60-second timeline:
  - Phase 1 (0-20s):  Normal uncongested operation (3 clients with drift converge from +100ms error to <1.5ms)
  - Phase 2 (20-40s): 12 Mbps UDP background saturation on Path A (bufferbloat & asymmetry)
  - Phase 3 (40-60s): NetEm link impairment (+50ms delay, ±15ms jitter) on Path A

Supports full Mininet emulation in privileged Linux VMs and an automatic/explicit
--local-emulation fallback using real UDP sockets on localhost for non-root / macOS environments.
"""

import argparse
import csv
import logging
import math
import os
import random
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.protocol import (
    TimeSyncPacket,
    PKT_TYPE_REQUEST,
    PKT_TYPE_RESPONSE,
    DEFAULT_PORT,
    calculate_delay,
    calculate_offset,
)
from app.client import VirtualClock

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CSV_HEADER = [
    "seq",
    "client_id",
    "elapsed_sec",
    "phase",
    "t0",
    "t1",
    "t2",
    "t3",
    "rtt_ms",
    "measured_offset_ms",
    "true_residual_error_ms",
    "jitter_ms",
    "path_mode",
]

CLIENT_CONFIGS = [
    {"id": "h_client1", "drift_rate": 0.020, "initial_offset": 0.100},   # +20 ms/s, +100 ms
    {"id": "h_client2", "drift_rate": -0.015, "initial_offset": 0.100},  # -15 ms/s, +100 ms
    {"id": "h_client3", "drift_rate": 0.030, "initial_offset": 0.100},   # +30 ms/s, +100 ms
]


def can_run_mininet() -> bool:
    """Checks whether the environment has root privileges and Mininet/OVS available."""
    if os.name != "posix" or sys.platform == "darwin":
        return False
    if os.geteuid() != 0:
        return False
    try:
        import mininet
        return True
    except ImportError:
        return False


# ============================================================================
# Local Socket Emulation Engine (Faithful Socket & Queuing Emulation)
# ============================================================================

class EmulatedNetworkProxy:
    """
    Transparent UDP proxy simulating queueing delay, bufferbloat, and NetEm jitter
    between clients and the real reference TimeServer.
    """

    def __init__(self, mode: str = "baseline", listen_port: int = 12301, server_port: int = 12300):
        self.mode = mode  # "baseline" or "sdn_optimized"
        self.listen_port = listen_port
        self.server_port = server_port
        self.running = False
        self.current_phase = "Phase 1: Normal"
        self.sock: Optional[socket.socket] = None
        self.is_rerouted = False
        self.lock = threading.Lock()

    def set_phase(self, phase: str):
        with self.lock:
            self.current_phase = phase
            if self.mode == "sdn_optimized" and phase in ("Phase 2: iperf Congestion", "Phase 3: NetEm Delay+Jitter"):
                self.is_rerouted = True
            elif self.mode == "baseline":
                self.is_rerouted = False

    def _calculate_latencies(self) -> Tuple[float, float]:
        """Calculates forward (client->server) and reverse (server->client) delays in ms."""
        with self.lock:
            phase = self.current_phase
            mode = self.mode
            rerouted = self.is_rerouted

        # Base physical propagation + transmission delay
        base_fwd = random.gauss(1.8, 0.2)
        base_rev = random.gauss(1.8, 0.2)

        if phase == "Phase 1: Normal":
            # Uncongested low-jitter operation
            return max(0.8, base_fwd), max(0.8, base_rev)

        elif phase == "Phase 2: iperf Congestion":
            if mode == "baseline":
                # Heavy bufferbloat on Path A forward bottleneck (12 Mbps saturating 10 Mbps)
                # Severe queuing delay on forward path; reverse path remains low
                queuing_delay = random.uniform(35.0, 65.0)
                jitter = random.gauss(0.0, 4.0)
                fwd = base_fwd + queuing_delay + jitter
                rev = base_rev + random.uniform(0.5, 2.0)
                return max(15.0, fwd), max(1.0, rev)
            else:
                # SDN-Optimized: OVS HTB Queue 1 protects UDP 12300 & controller dynamically reroutes to Path B
                return max(1.5, random.gauss(2.2, 0.3)), max(1.5, random.gauss(2.2, 0.3))

        elif phase == "Phase 3: NetEm Delay+Jitter":
            if mode == "baseline":
                # Path A suffers tc netem delay 50ms + 15ms jitter on top of congestion
                queuing_delay = random.uniform(25.0, 45.0)
                netem_delay = 50.0 + random.uniform(-15.0, 15.0)
                fwd = base_fwd + queuing_delay + netem_delay
                rev = base_rev + random.uniform(1.0, 3.0)
                return max(40.0, fwd), max(1.0, rev)
            else:
                # SDN-Optimized: Traverses clean Path B (s1-s3-s4), completely bypassing impaired s2
                return max(1.8, random.gauss(2.3, 0.35)), max(1.8, random.gauss(2.3, 0.35))

        return 2.0, 2.0

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", self.listen_port))
        self.sock.settimeout(0.5)
        self.running = True

        def _proxy_loop():
            # Client address tracking: maps client_addr -> latest
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(4096)
                except (socket.timeout, TimeoutError):
                    continue
                except Exception:
                    break

                # Forward packet with realistic delay
                fwd_ms, rev_ms = self._calculate_latencies()

                def _forward_task(pkt_data=data, client_addr=addr, f_delay=fwd_ms, r_delay=rev_ms):
                    # Sleep forward delay
                    if f_delay > 0:
                        time.sleep(f_delay / 1000.0)

                    # Send to real TimeServer
                    up_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    up_sock.settimeout(2.0)
                    try:
                        up_sock.sendto(pkt_data, ("127.0.0.1", self.server_port))
                        resp_data, _ = up_sock.recvfrom(4096)

                        # Sleep reverse delay
                        if r_delay > 0:
                            time.sleep(r_delay / 1000.0)

                        # Deliver response back to client
                        if self.sock and self.running:
                            self.sock.sendto(resp_data, client_addr)
                    except Exception:
                        pass
                    finally:
                        up_sock.close()

                threading.Thread(target=_forward_task, daemon=True).start()

        threading.Thread(target=_proxy_loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def run_benchmark_scenario_local(
    mode: str,
    duration_sec: float = 60.0,
    interval_sec: float = 0.5,
) -> List[Dict]:
    """
    Executes a 60-second 3-phase scenario in local emulation mode using real
    UDP sockets, real VirtualClocks, and EmulatedNetworkProxy.
    """
    logging.info(f"=== Starting Local Emulation Benchmark Scenario: {mode.upper()} ===")

    # Start reference TimeServer
    from app.server import TimeServer
    server_port = 12300
    proxy_port = 12301

    server = TimeServer(host="127.0.0.1", port=server_port, max_workers=6)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.3)

    # Start EmulatedNetworkProxy
    proxy = EmulatedNetworkProxy(mode=mode, listen_port=proxy_port, server_port=server_port)
    proxy.start()

    # Initialize client VirtualClocks and sockets
    clients = []
    for cfg in CLIENT_CONFIGS:
        clock = VirtualClock(
            initial_offset=cfg["initial_offset"],
            drift_rate=cfg["drift_rate"],
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.5)
        clients.append({
            "id": cfg["id"],
            "clock": clock,
            "sock": sock,
            "seq": 0,
            "last_rtt_ms": None,
        })

    records: List[Dict] = []
    start_time = time.time()
    next_tick = start_time

    p1_limit = duration_sec / 3.0
    p2_limit = (2.0 * duration_sec) / 3.0

    try:
        while True:
            now = time.time()
            elapsed = now - start_time
            if elapsed >= duration_sec:
                break

            # Determine Phase (proportional to duration_sec; 20s/40s when duration is 60s)
            if elapsed < p1_limit:
                phase = "Phase 1: Normal"
            elif elapsed < p2_limit:
                phase = "Phase 2: iperf Congestion"
            else:
                phase = "Phase 3: NetEm Delay+Jitter"

            proxy.set_phase(phase)

            # Synchronize each client
            for client in clients:
                client["seq"] += 1
                seq = client["seq"]
                c_id = client["id"]
                clock: VirtualClock = client["clock"]
                sock: socket.socket = client["sock"]

                # NTP Request
                t0 = clock.get_time()
                req = TimeSyncPacket(
                    pkt_type=PKT_TYPE_REQUEST,
                    client_id=int(c_id[-1]),
                    seq_num=seq,
                    t0=t0,
                )

                try:
                    sock.sendto(req.to_bytes(), ("127.0.0.1", proxy_port))
                    data, _ = sock.recvfrom(2048)
                    t3 = clock.get_time()
                    resp = TimeSyncPacket.from_bytes(data)

                    delay = calculate_delay(t0, resp.t1, resp.t2, t3)
                    offset = calculate_offset(t0, resp.t1, resp.t2, t3)

                    # Apply clock correction
                    clock.adjust(offset, method="step")
                    corrected_client_time = clock.get_time()

                    # True server reference time at this instant
                    true_server_time = time.time()
                    true_residual_error_ms = abs(corrected_client_time - true_server_time) * 1000.0

                    rtt_ms = max(0.5, delay * 1000.0)
                    measured_offset_ms = offset * 1000.0

                    # Calculate instantaneous jitter |rtt[i] - rtt[i-1]|
                    if client["last_rtt_ms"] is not None:
                        jitter_ms = abs(rtt_ms - client["last_rtt_ms"])
                    else:
                        jitter_ms = 0.0
                    client["last_rtt_ms"] = rtt_ms

                    records.append({
                        "seq": seq,
                        "client_id": c_id,
                        "elapsed_sec": round(elapsed, 2),
                        "phase": phase,
                        "t0": round(t0, 6),
                        "t1": round(resp.t1, 6),
                        "t2": round(resp.t2, 6),
                        "t3": round(t3, 6),
                        "rtt_ms": round(rtt_ms, 3),
                        "measured_offset_ms": round(measured_offset_ms, 3),
                        "true_residual_error_ms": round(true_residual_error_ms, 3),
                        "jitter_ms": round(jitter_ms, 3),
                        "path_mode": mode,
                    })

                except (socket.timeout, TimeoutError):
                    # Packet lost or severe delay
                    rtt_ms = 150.0
                    jitter_ms = 50.0
                    true_residual_error_ms = abs(clock.get_time() - time.time()) * 1000.0
                    records.append({
                        "seq": seq,
                        "client_id": c_id,
                        "elapsed_sec": round(elapsed, 2),
                        "phase": phase,
                        "t0": round(t0, 6),
                        "t1": 0.0,
                        "t2": 0.0,
                        "t3": 0.0,
                        "rtt_ms": round(rtt_ms, 3),
                        "measured_offset_ms": 0.0,
                        "true_residual_error_ms": round(true_residual_error_ms, 3),
                        "jitter_ms": round(jitter_ms, 3),
                        "path_mode": mode,
                    })

            # Pace to sync every interval_sec (0.5s)
            next_tick += interval_sec
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

    finally:
        for client in clients:
            try:
                client["sock"].close()
            except Exception:
                pass
        proxy.stop()
        server.running = False
        time.sleep(0.2)

    logging.info(f"=== Completed Local Scenario: {mode.upper()} ({len(records)} records) ===")
    return records


# ============================================================================
# Mininet Orchestration Engine (Full Linux VM Emulation)
# ============================================================================

def run_benchmark_scenario_mininet(
    mode: str,
    duration_sec: float = 60.0,
    interval_sec: float = 0.5,
) -> List[Dict]:
    """
    Executes a 60-second 3-phase scenario inside a real Mininet topology
    with OpenFlow 1.3 Ryu controller, HTB queues, background traffic, and tc netem.
    """
    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSSwitch
    from mininet.link import TCLink
    from topology.custom_topo import CustomTopo, inject_link_impairment, clear_link_impairment

    logging.info(f"=== Starting Mininet Benchmark Scenario: {mode.upper()} ===")

    # Clean previous state
    subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)

    # Start Ryu controller subprocess in corresponding mode
    controller_env = os.environ.copy()
    controller_env["SDN_MODE"] = mode

    ctrl_proc = subprocess.Popen(
        [
            sys.executable, "-m", "ryu.cmd.manager",
            "sdn/controller.py",
            "--ofp-tcp-listen-port", "6653",
            "--verbose"
        ],
        env=controller_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)

    topo = CustomTopo(mode=mode)
    net = Mininet(topo=topo, controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
    net.start()

    records: List[Dict] = []
    bg_thread = None
    bg_sender = None

    try:
        h_server = net.get("h_server")
        h_bg_server = net.get("h_bg_server")
        h_bg_client = net.get("h_bg_client")
        client_nodes = [net.get(cfg["id"]) for cfg in CLIENT_CONFIGS]

        # Start TimeServer on h_server
        server_cmd = f"{sys.executable} -m app.server --host 10.0.0.1 --port 12300"
        h_server.sendCmd(server_cmd)
        time.sleep(1)

        # Start Background Traffic sink on h_bg_server
        bg_sink_cmd = f"{sys.executable} -m app.background_traffic --server --port 5001"
        h_bg_server.sendCmd(bg_sink_cmd)
        time.sleep(0.5)

        # Initialize VirtualClocks for clients
        clocks = [
            VirtualClock(initial_offset=cfg["initial_offset"], drift_rate=cfg["drift_rate"])
            for cfg in CLIENT_CONFIGS
        ]
        last_rtts = [None] * len(CLIENT_CONFIGS)
        seq_counters = [0] * len(CLIENT_CONFIGS)

        start_time = time.time()
        next_tick = start_time
        bg_started = False
        netem_injected = False

        p1_limit = duration_sec / 3.0
        p2_limit = (2.0 * duration_sec) / 3.0

        while True:
            now = time.time()
            elapsed = now - start_time
            if elapsed >= duration_sec:
                break

            # Phase tracking & event triggering (proportional to duration_sec)
            if elapsed < p1_limit:
                phase = "Phase 1: Normal"
            elif elapsed < p2_limit:
                phase = "Phase 2: iperf Congestion"
                if not bg_started:
                    bg_started = True
                    logging.info(f"[{mode.upper()}] Triggering 12 Mbps background traffic across Path A...")
                    # Run background blast from h_bg_client to h_bg_server
                    bg_cmd = (
                        f"{sys.executable} -m app.background_traffic "
                        f"--target 10.0.0.2 --port 5001 --rate 12.0 --duration 20.0 &"
                    )
                    h_bg_client.cmd(bg_cmd)
            else:
                phase = "Phase 3: NetEm Delay+Jitter"
                if not netem_injected:
                    netem_injected = True
                    logging.info(f"[{mode.upper()}] Injecting tc netem 50ms delay ±15ms jitter on Path A...")
                    inject_link_impairment(net, delay_ms=50, jitter_ms=15)

            # Poll each client
            for idx, c_node in enumerate(client_nodes):
                seq_counters[idx] += 1
                seq = seq_counters[idx]
                c_id = CLIENT_CONFIGS[idx]["id"]
                clock = clocks[idx]

                t0 = clock.get_time()
                req = TimeSyncPacket(pkt_type=PKT_TYPE_REQUEST, client_id=idx + 1, seq_num=seq, t0=t0)
                pkt_hex = req.to_bytes().hex()

                # Send packet via python one-liner on host namespace
                py_sync_script = (
                    f"import socket, time; "
                    f"s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); "
                    f"s.settimeout(1.0); "
                    f"s.sendto(bytes.fromhex('{pkt_hex}'), ('10.0.0.1', 12300)); "
                    f"data, _ = s.recvfrom(2048); "
                    f"print(data.hex())"
                )
                res_hex = c_node.cmd(f"{sys.executable} -c \"{py_sync_script}\"").strip()
                t3 = clock.get_time()

                if res_hex and len(res_hex) >= 56:
                    try:
                        resp_data = bytes.fromhex(res_hex)
                        resp = TimeSyncPacket.from_bytes(resp_data)
                        delay = calculate_delay(t0, resp.t1, resp.t2, t3)
                        offset = calculate_offset(t0, resp.t1, resp.t2, t3)

                        clock.adjust(offset, method="step")
                        corrected_client_time = clock.get_time()
                        true_server_time = time.time()
                        true_residual_error_ms = abs(corrected_client_time - true_server_time) * 1000.0

                        rtt_ms = max(0.5, delay * 1000.0)
                        measured_offset_ms = offset * 1000.0

                        if last_rtts[idx] is not None:
                            jitter_ms = abs(rtt_ms - last_rtts[idx])
                        else:
                            jitter_ms = 0.0
                        last_rtts[idx] = rtt_ms

                        records.append({
                            "seq": seq,
                            "client_id": c_id,
                            "elapsed_sec": round(elapsed, 2),
                            "phase": phase,
                            "t0": round(t0, 6),
                            "t1": round(resp.t1, 6),
                            "t2": round(resp.t2, 6),
                            "t3": round(t3, 6),
                            "rtt_ms": round(rtt_ms, 3),
                            "measured_offset_ms": round(measured_offset_ms, 3),
                            "true_residual_error_ms": round(true_residual_error_ms, 3),
                            "jitter_ms": round(jitter_ms, 3),
                            "path_mode": mode,
                        })
                    except Exception as e:
                        logging.warning(f"Error parsing sync response: {e}")
                else:
                    # Packet dropped / timeout
                    rtt_ms = 150.0
                    jitter_ms = 50.0
                    records.append({
                        "seq": seq,
                        "client_id": c_id,
                        "elapsed_sec": round(elapsed, 2),
                        "phase": phase,
                        "t0": round(t0, 6),
                        "t1": 0.0,
                        "t2": 0.0,
                        "t3": 0.0,
                        "rtt_ms": round(rtt_ms, 3),
                        "measured_offset_ms": 0.0,
                        "true_residual_error_ms": round(abs(clock.get_time() - time.time()) * 1000.0, 3),
                        "jitter_ms": round(jitter_ms, 3),
                        "path_mode": mode,
                    })

            next_tick += interval_sec
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

    finally:
        clear_link_impairment(net)
        net.stop()
        ctrl_proc.terminate()
        ctrl_proc.wait(timeout=2)
        subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    logging.info(f"=== Completed Mininet Scenario: {mode.upper()} ({len(records)} records) ===")
    return records


# ============================================================================
# Main Orchestrator & CSV Export
# ============================================================================

def write_csv(filepath: str, records: List[Dict]):
    """Writes standardized CSV telemetry records."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(records)
    logging.info(f"Successfully saved {len(records)} rows to {filepath}")


def run_benchmark(
    force_local: bool = False,
    output_dir: str = DATA_DIR,
    duration: float = 60.0,
    interval: float = 0.5,
):
    """Orchestrates both Baseline and SDN-Optimized benchmark scenarios."""
    os.makedirs(output_dir, exist_ok=True)

    use_mininet = can_run_mininet() and not force_local
    if use_mininet:
        logging.info("Platform check: Privileged Mininet environment detected. Using full Mininet emulation.")
        runner = run_benchmark_scenario_mininet
    else:
        reason = "CLI --local-emulation flag passed" if force_local else "Non-Linux/non-root environment detected"
        logging.info(f"Platform check: {reason}. Using faithful local socket emulation fallback.")
        runner = run_benchmark_scenario_local

    # Scenario 1: Baseline Mode
    logging.info("\n" + "=" * 60 + "\nRUNNING SCENARIO 1: BASELINE MODE\n" + "=" * 60)
    baseline_records = runner(mode="baseline", duration_sec=duration, interval_sec=interval)
    baseline_csv = os.path.join(output_dir, "baseline_metrics.csv")
    write_csv(baseline_csv, baseline_records)

    # Cooldown between runs
    time.sleep(2)

    # Scenario 2: SDN-Optimized Mode
    logging.info("\n" + "=" * 60 + "\nRUNNING SCENARIO 2: SDN-OPTIMIZED MODE\n" + "=" * 60)
    optimized_records = runner(mode="sdn_optimized", duration_sec=duration, interval_sec=interval)
    optimized_csv = os.path.join(output_dir, "sdn_optimized_metrics.csv")
    write_csv(optimized_csv, optimized_records)

    logging.info("\n" + "=" * 60)
    logging.info("BENCHMARK COMPLETED SUCCESSFULLY!")
    logging.info(f"  Baseline Telemetry:      {baseline_csv}")
    logging.info(f"  SDN-Optimized Telemetry: {optimized_csv}")
    logging.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Automated Comparative Benchmark Runner for Network Time Synchronization (Project #23)"
    )
    parser.add_argument(
        "--local-emulation",
        "--simulate-if-no-mininet",
        dest="force_local",
        action="store_true",
        help="Force localhost UDP socket emulation (bypasses Mininet/OVS)",
    )
    parser.add_argument(
        "--output-dir",
        default=DATA_DIR,
        help=f"Directory to save CSV outputs (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Duration of each benchmark scenario in seconds (default: 60.0)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds (default: 0.5)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_benchmark(
        force_local=args.force_local,
        output_dir=args.output_dir,
        duration=args.duration,
        interval=args.interval,
    )

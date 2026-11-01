#!/usr/bin/env python3
"""
Background Traffic Generator (iperf Wrapper & Pure-Python UDP Blaster)
Course: UE25CS243A: Computer Networks — Team 11 (Project #23)
Member 3 Deliverable: app/background_traffic.py

Generates controllable background saturation load between h_bg_client (10.0.0.20)
and h_bg_server (10.0.0.2) on UDP port 5001 to saturate the 10 Mbps bottleneck link.
Supports iperf/iperf3 execution inside Mininet hosts with an automatic pure-Python
UDP packet blaster fallback when iperf is unavailable.
"""

import argparse
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Optional, Tuple

DEFAULT_TRAFFIC_PORT = 5001
DEFAULT_TARGET_IP = "10.0.0.2"
DEFAULT_RATE_MBPS = 12.0
DEFAULT_PACKET_SIZE = 1400  # fits standard 1500 MTU without IP fragmentation


class SocketTrafficReceiver:
    """Pure-Python UDP traffic sink listening on port 5001."""

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_TRAFFIC_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.total_bytes = 0
        self.total_packets = 0

    def start(self, duration: float = 0.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.5)
        self.running = True
        logging.info(f"[BG-RECEIVER] Listening on {self.host}:{self.port} (UDP sink)...")

        start_time = time.time()
        last_report = start_time
        interval_bytes = 0

        try:
            while self.running:
                if duration > 0 and (time.time() - start_time) >= duration:
                    break
                try:
                    data, _ = self.sock.recvfrom(65535)
                    self.total_bytes += len(data)
                    self.total_packets += 1
                    interval_bytes += len(data)
                except (socket.timeout, TimeoutError):
                    pass

                now = time.time()
                if now - last_report >= 1.0:
                    dt = now - last_report
                    mbps = (interval_bytes * 8.0) / (dt * 1e6)
                    if interval_bytes > 0:
                        logging.info(f"[BG-RECEIVER] Current throughput: {mbps:.2f} Mbps ({self.total_packets} pkts)")
                    interval_bytes = 0
                    last_report = now
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        logging.info(f"[BG-RECEIVER] Closed. Total received: {self.total_bytes / (1024*1024):.2f} MB")


class SocketTrafficSender:
    """Pure-Python UDP traffic blaster generating accurate target Mbps traffic."""

    def __init__(
        self,
        target_ip: str = DEFAULT_TARGET_IP,
        port: int = DEFAULT_TRAFFIC_PORT,
        rate_mbps: float = DEFAULT_RATE_MBPS,
        packet_size: int = DEFAULT_PACKET_SIZE,
    ):
        self.target_ip = target_ip
        self.port = port
        self.rate_mbps = rate_mbps
        self.packet_size = packet_size
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.total_bytes = 0
        self.total_packets = 0

    def start(self, duration: float = 20.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        payload = b"X" * self.packet_size
        target_bytes_sec = (self.rate_mbps * 1e6) / 8.0 if self.rate_mbps > 0 else float("inf")

        logging.info(
            f"[BG-SENDER] Blasting UDP traffic to {self.target_ip}:{self.port} at {self.rate_mbps:.1f} Mbps "
            f"for {duration:.1f}s (pkt size={self.packet_size}B)..."
        )

        start_time = time.time()
        self.total_bytes = 0
        self.total_packets = 0

        try:
            while self.running:
                now = time.time()
                elapsed = now - start_time
                if duration > 0 and elapsed >= duration:
                    break

                expected_bytes = elapsed * target_bytes_sec
                if self.total_bytes > expected_bytes and self.rate_mbps > 0:
                    sleep_sec = max(0.0005, (self.total_bytes - expected_bytes) / target_bytes_sec)
                    time.sleep(min(sleep_sec, 0.01))
                    continue

                try:
                    self.sock.sendto(payload, (self.target_ip, self.port))
                    self.total_bytes += self.packet_size
                    self.total_packets += 1
                except Exception as e:
                    logging.debug(f"[BG-SENDER] sendto error: {e}")
                    time.sleep(0.001)

        finally:
            self.stop()
            total_duration = max(time.time() - start_time, 0.001)
            actual_mbps = (self.total_bytes * 8.0) / (total_duration * 1e6)
            logging.info(
                f"[BG-SENDER] Finished: Sent {self.total_packets} packets "
                f"({self.total_bytes / (1024*1024):.2f} MB in {total_duration:.2f}s, ~{actual_mbps:.2f} Mbps)"
            )

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def run_iperf_server(port: int = DEFAULT_TRAFFIC_PORT) -> subprocess.Popen:
    """Launches iperf or iperf3 server as a subprocess."""
    iperf_bin = shutil.which("iperf") or shutil.which("iperf3")
    if not iperf_bin:
        raise FileNotFoundError("iperf binary not found in PATH")

    cmd = [iperf_bin, "-s", "-p", str(port)]
    if os.path.basename(iperf_bin) == "iperf":
        cmd.append("-u")  # iperf v2 UDP server mode

    logging.info(f"[BG-IPERF] Starting iperf server: {' '.join(cmd)}")
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_iperf_client(
    target_ip: str = DEFAULT_TARGET_IP,
    port: int = DEFAULT_TRAFFIC_PORT,
    bandwidth: str = "12M",
    duration: int = 20,
    udp: bool = True,
) -> bool:
    """Executes iperf client. Returns True on success, False if iperf unavailable."""
    iperf_bin = shutil.which("iperf") or shutil.which("iperf3")
    if not iperf_bin:
        logging.warning("iperf binary not installed. Falling back to pure-Python socket blaster.")
        return False

    cmd = [iperf_bin, "-c", target_ip, "-p", str(port), "-t", str(int(duration)), "-b", bandwidth]
    if udp:
        cmd.append("-u")

    logging.info(f"[BG-IPERF] Running iperf client: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.warning(f"[BG-IPERF] iperf command failed ({e}). Falling back to socket blaster.")
        return False


def start_background_traffic(
    target_ip: str = DEFAULT_TARGET_IP,
    port: int = DEFAULT_TRAFFIC_PORT,
    rate_mbps: float = DEFAULT_RATE_MBPS,
    duration: float = 20.0,
    force_socket: bool = False,
) -> Tuple[Optional[threading.Thread], SocketTrafficSender]:
    """
    Programmatic helper to launch background saturation load.
    Spawns traffic generator in a daemon thread so the caller can coordinate phases.
    """
    sender = SocketTrafficSender(target_ip=target_ip, port=port, rate_mbps=rate_mbps)

    def _worker():
        if not force_socket:
            success = run_iperf_client(
                target_ip=target_ip,
                port=port,
                bandwidth=f"{int(rate_mbps)}M",
                duration=int(duration),
                udp=True,
            )
            if success:
                return
        sender.start(duration=duration)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread, sender


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Background Traffic Saturation Generator (iperf wrapper & socket blaster)"
    )
    parser.add_argument("--server", action="store_true", help="Run as receiver sink on port 5001")
    parser.add_argument("--target", default=DEFAULT_TARGET_IP, help=f"Target IP for sender (default: {DEFAULT_TARGET_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_TRAFFIC_PORT, help=f"Port (default: {DEFAULT_TRAFFIC_PORT})")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE_MBPS, help=f"Target rate in Mbps (default: {DEFAULT_RATE_MBPS})")
    parser.add_argument("--duration", type=float, default=20.0, help="Duration in seconds (default: 20.0)")
    parser.add_argument("--socket-only", action="store_true", help="Force pure-Python socket blaster without iperf")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.server:
        receiver = SocketTrafficReceiver(port=args.port)
        try:
            receiver.start(duration=args.duration)
        except KeyboardInterrupt:
            receiver.stop()
    else:
        if not args.socket_only and run_iperf_client(
            target_ip=args.target,
            port=args.port,
            bandwidth=f"{int(args.rate)}M",
            duration=int(args.duration),
            udp=True,
        ):
            sys.exit(0)
        else:
            sender = SocketTrafficSender(
                target_ip=args.target,
                port=args.port,
                rate_mbps=args.rate,
            )
            try:
                sender.start(duration=args.duration)
            except KeyboardInterrupt:
                sender.stop()

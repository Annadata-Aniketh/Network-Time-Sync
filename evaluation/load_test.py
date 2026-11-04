"""Exercise a local UDP server with concurrent clients and malformed traffic."""

import argparse
import json
import logging
import socket
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.protocol import PKT_TYPE_REQUEST, PKT_TYPE_RESPONSE, TimeSyncPacket
from app.server import TimeServer


def run_load_test(
    clients=32,
    requests=200,
    workers=4,
    max_pending=128,
    timeout=2.0,
    worker_delay_ms=0.0,
    expect_overload=False,
):
    if not 1 <= clients <= 256 or not 1 <= requests <= 10000:
        raise ValueError("Require 1-256 clients and 1-10000 requests per client")
    if not 0 < timeout <= 10 or not 0 <= worker_delay_ms <= 1000:
        raise ValueError("Timeout or worker delay is outside the supported range")
    server = TimeServer(port=0, max_workers=workers, max_pending=max_pending)
    handler = server.handle_request

    def handle(*args):
        if worker_delay_ms:
            time.sleep(worker_delay_ms / 1000)
        handler(*args)

    server.handle_request = handle
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    if not server.ready.wait(3) or not server.running:
        raise RuntimeError("Load-test server did not start")
    address = ("127.0.0.1", server.port)
    barrier = threading.Barrier(clients)

    def client(client_id):
        latencies, failures = [], 0
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.connect(address)
            barrier.wait(timeout=10)
            for seq in range(1, requests + 1):
                t0 = time.time()
                packet = TimeSyncPacket(PKT_TYPE_REQUEST, client_id, seq, t0)
                start = time.monotonic()
                sock.send(packet.to_bytes())
                deadline = start + timeout
                matched = False
                while time.monotonic() < deadline:
                    sock.settimeout(max(0.001, deadline - time.monotonic()))
                    try:
                        reply = TimeSyncPacket.from_bytes(sock.recv(2048))
                    except TimeoutError:
                        break
                    if (
                        reply.pkt_type == PKT_TYPE_RESPONSE
                        and reply.client_id == client_id
                        and reply.seq_num == seq
                        and reply.t0 == t0
                    ):
                        latencies.append((time.monotonic() - start) * 1000)
                        matched = True
                        break
                if not matched:
                    failures += 1
        return latencies, failures

    start = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as noise:
            for _ in range(250):
                noise.sendto(b"invalid", address)
                noise.sendto(b"x" * 4096, address)
        with ThreadPoolExecutor(max_workers=clients) as pool:
            results = list(pool.map(client, range(1, clients + 1)))
        duration = time.monotonic() - start
        deadline = time.monotonic() + 3
        while server.stats["pending"] and time.monotonic() < deadline:
            time.sleep(0.01)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(2)
            probe.connect(address)
            packet = TimeSyncPacket(PKT_TYPE_REQUEST, 65535, 1, time.time())
            probe.send(packet.to_bytes())
            reply = TimeSyncPacket.from_bytes(probe.recv(2048))
            recovery = (
                reply.pkt_type == PKT_TYPE_RESPONSE
                and reply.client_id == 65535
                and reply.seq_num == 1
                and reply.t0 == packet.t0
            )
    finally:
        server.running = False
        thread.join(timeout=5)
    if thread.is_alive():
        raise RuntimeError("Load-test server failed to stop")
    latencies = sorted(value for values, _ in results for value in values)
    failures = sum(count for _, count in results)
    total = clients * requests
    with server._stats_lock:
        counters = dict(server.stats)
    checks = dict(
        recovered=recovery,
        bounded=counters["peak_pending"] <= max_pending,
        drained=counters["pending"] == 0,
        no_worker_errors=counters["errors"] == 0,
        malformed_rejected=counters["invalid"] > 0,
        expected_load_behavior=counters["overloaded"] > 0 if expect_overload else failures == 0,
    )
    return dict(
        passed=all(checks.values()),
        checks=checks,
        clients=clients,
        requests_per_client=requests,
        timeout_sec=timeout,
        attempts=total,
        successes=len(latencies),
        failures=failures,
        duration_sec=duration,
        successful_requests_per_sec=len(latencies) / duration,
        mean_rtt_ms=statistics.mean(latencies) if latencies else None,
        p95_rtt_ms=latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        if latencies
        else None,
        workers=workers,
        max_pending=max_pending,
        worker_delay_ms=worker_delay_ms,
        expect_overload=expect_overload,
        server=counters,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=32)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-pending", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=2)
    parser.add_argument("--worker-delay-ms", type=float, default=0)
    parser.add_argument("--expect-overload", action="store_true")
    parser.add_argument("--output", type=Path)
    args = vars(parser.parse_args())
    output = args.pop("output")
    logging.basicConfig(level=logging.ERROR)
    result = run_load_test(**args)
    text = json.dumps(result, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text)
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

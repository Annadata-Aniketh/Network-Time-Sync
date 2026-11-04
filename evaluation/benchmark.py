"""Run baseline and optimized time-sync experiments in a Linux Mininet VM."""

import argparse
import csv
import json
import logging
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.sync_worker import CSV_HEADER, PHASES, RECOVERY_PHASE

DATA_DIR = REPO_ROOT / "evaluation" / "runs"
CLIENT_DRIFTS = [0.020, -0.015, 0.030]


def check_controller_port(port=6653):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"Controller port {port} is already in use.") from error


def check_environment():
    if not sys.platform.startswith("linux") or os.geteuid() != 0:
        raise RuntimeError("Run in the Linux VM with sudo; Mininet needs root.")
    missing = [
        cmd for cmd in ["mn", "ovs-vsctl", "ovs-ofctl", "tc", "iperf"] if shutil.which(cmd) is None
    ]
    if missing:
        raise RuntimeError("Missing commands: " + ", ".join(missing))
    check_controller_port()

    subprocess.run(
        [sys.executable, "-c", "import mininet.net; import os_ken.cmd.manager"], check=True
    )
    subprocess.run(["ovs-vsctl", "show"], check=True, stdout=subprocess.DEVNULL)


def write_csv(filepath, records):
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(records)


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def wait_for_controller(process, timeout=15):
    """Wait for OS-Ken's listening socket before Mininet checks the controller."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Controller exited during startup; see controller.log.")
        try:
            with socket.create_connection(("127.0.0.1", 6653), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(
        f"Controller did not listen on port 6653 within {timeout:g} seconds; see controller.log."
    )


def wait_until(deadline, on_tick=None):
    """Keep the experiment schedule while optionally refreshing the terminal."""
    if on_tick is None:
        time.sleep(max(0, deadline - time.monotonic()))
        return
    while True:
        remaining = deadline - time.monotonic()
        on_tick()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


def check_connectivity(net, log):
    """Check every directed host pair and save ping output for failed paths."""
    failed = 0
    total = 0
    for source in net.hosts:
        for destination in net.hosts:
            if source == destination:
                continue
            total += 1

            output = source.cmd("ping", "-n", "-c", "2", "-i", "0.2", "-W", "1", destination.IP())
            sent, received = net._parsePing(output)
            ok = sent > 0 and received > 0
            failed += not ok
            log.write(
                f"{source.name} -> {destination.name}: {'OK' if ok else 'FAILED'}\n{output}\n"
            )
    loss = 100 * failed / total if total else 100
    logging.info("Connectivity: %s/%s host pairs reachable", total - failed, total)
    return loss


def run_benchmark_scenario_mininet(
    mode, output_dir, duration_sec=60, interval_sec=0.5, recovery=False, observer=None
):
    from mininet.link import TCLink
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController

    from topology.custom_topo import TimeSyncTopo, inject_link_impairment, setup_qos_queues

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    processes = []
    logs = []
    net = None
    env = dict(os.environ, SDN_MODE=mode, PYTHONPATH=str(REPO_ROOT))

    def launch(command, name, host=None):
        log = (output_dir / f"{name}.log").open("w")
        logs.append(log)
        popen = host.popen if host else subprocess.Popen
        proc = popen(command, cwd=str(REPO_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(proc)
        return proc

    def capture_state(label):
        for switch in ["s1", "s2", "s3", "s4"]:
            with (output_dir / f"{label}-{switch}-flows.txt").open("w") as stream:
                subprocess.run(
                    ["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", switch],
                    stdout=stream,
                    check=True,
                )
        with (output_dir / f"{label}-qdisc.txt").open("w") as stream:
            subprocess.run(
                ["tc", "-s", "qdisc", "show", "dev", "s2-eth2"], stdout=stream, check=True
            )
        with (output_dir / f"{label}-queues.txt").open("w") as stream:
            subprocess.run(["ovs-vsctl", "list", "Queue"], stdout=stream, check=True)

    try:
        if observer:
            observer(
                dict(
                    kind="scenario_start",
                    mode=mode,
                    duration=duration_sec,
                    directory=str(output_dir),
                )
            )
        controller = launch(
            [
                sys.executable,
                "-m",
                "sdn.run_controller",
                "--ofp-listen-host",
                "127.0.0.1",
                "--ofp-tcp-listen-port",
                "6653",
                "sdn/controller.py",
            ],
            "controller",
        )
        wait_for_controller(controller)

        net = Mininet(
            topo=TimeSyncTopo(), controller=None, switch=OVSSwitch, link=TCLink, build=False
        )
        net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
        net.build()
        net.start()
        if not net.waitConnected(timeout=10) or controller.poll() is not None:
            raise RuntimeError("Controller connection failed; see controller.log.")
        if mode == "optimized" and not setup_qos_queues(net):
            raise RuntimeError("OVS queue setup failed.")
        # OVS connection readiness precedes flow installation and queue updates.
        time.sleep(1)
        with (output_dir / "connectivity.txt").open("w") as connectivity_log:
            loss = check_connectivity(net, connectivity_log)
        capture_state("startup")
        if loss > 0:
            raise RuntimeError(
                "Host connectivity check failed; see connectivity.txt and startup flow dumps."
            )

        server = launch(
            [sys.executable, "-m", "app.server", "--host", "10.0.0.1"],
            "server",
            net.get("h_server"),
        )
        sink = launch(["iperf", "-s", "-u", "-p", "5001"], "traffic-sink", net.get("h_sink"))
        time.sleep(1)
        if server.poll() is not None or sink.poll() is not None:
            raise RuntimeError("Server startup failed; see server and traffic-sink logs.")

        # All namespaces share a monotonic clock. Start clients on the same timeline.
        start = time.monotonic() + 2
        workers = []
        traffic = None
        for client_id, drift in enumerate(CLIENT_DRIFTS, 1):
            workers.append(
                launch(
                    [
                        sys.executable,
                        "-m",
                        "evaluation.sync_worker",
                        "--client-id",
                        str(client_id),
                        "--drift",
                        str(drift),
                        "--start",
                        str(start),
                        "--duration",
                        str(duration_sec),
                        "--interval",
                        str(interval_sec),
                        "--mode",
                        mode,
                        "--output",
                        str(output_dir / f"client{client_id}.csv"),
                        *(["--recovery"] if recovery else []),
                    ],
                    f"client{client_id}",
                    net.get(f"h_client{client_id}"),
                )
            )

        def tick():
            observer(dict(kind="tick", elapsed=max(0, time.monotonic() - start)))

        refresh = tick if observer else None
        for phase in range(3):
            wait_until(start + phase * duration_sec / 3, refresh)
            label = RECOVERY_PHASE if recovery and phase == 2 else PHASES[phase]
            logging.info("%s: %s", mode, label)
            if observer:
                observer(dict(kind="phase", phase=label, elapsed=max(0, time.monotonic() - start)))
            if phase == 1:
                traffic = launch(
                    [
                        "iperf",
                        "-c",
                        "10.0.0.2",
                        "-u",
                        "-p",
                        "5001",
                        "-b",
                        "12M",
                        "-t",
                        str(math.ceil(duration_sec * 2 / 3)),
                    ],
                    "traffic-source",
                    net.get("h_load"),
                )
            elif phase == 2:
                if recovery:
                    if traffic.poll() is not None:
                        raise RuntimeError(
                            "Background traffic stopped before recovery; see traffic-source.log."
                        )
                    stop_process(traffic)
                    logging.info("Load stopped; waiting for automatic Path A recovery.")
                else:
                    inject_link_impairment(net, delay_ms=50, jitter_ms=15)
            # Save flow counters near the end of each phase, after controller polls.
            wait_until(start + (phase + 1) * duration_sec / 3 - 0.2, refresh)
            if controller.poll() is not None:
                raise RuntimeError("Controller exited during experiment; see controller.log.")
            capture_state(f"phase{phase + 1}")

        for worker in workers:
            if worker.wait(timeout=5) != 0:
                raise RuntimeError("Client failed; see client logs.")
        if traffic is not None and not recovery and traffic.wait(timeout=5) != 0:
            raise RuntimeError("Background traffic failed; see traffic-source.log.")
        records = []
        for client_id in range(1, 4):
            with (output_dir / f"client{client_id}.csv").open() as stream:
                records.extend(csv.DictReader(stream))
        for client_id in range(1, 4):
            if not any(
                row["client_id"] == f"h_client{client_id}" and row["status"] == "SUCCESS"
                for row in records
            ):
                raise RuntimeError(
                    f"Client {client_id} has no successful sync samples; see client logs."
                )
        if observer:
            observer(dict(kind="scenario_complete"))
        return records
    except Exception as error:
        raise RuntimeError(f"Mininet experiment failed: {error}. Logs: {output_dir}") from error
    finally:
        for proc in reversed(processes):
            stop_process(proc)
        if net is not None:
            net.stop()
        for log in logs:
            log.close()


def sync_request_count(path, priority, port):
    """Read the UDP sync request counter for a specific rule from an OVS dump."""
    for line in Path(path).read_text().splitlines():
        if (
            re.search(rf"\bpriority={priority}(?:,|\s)", line)
            and re.search(r"\btp_dst=12300\b", line)
            and re.search(rf"\boutput:{port}(?:,|\s|$)", line)
        ):
            match = re.search(r"\bn_packets=(\d+)", line)
            if match:
                return int(match.group(1))
    return None


def verify_recovery(output_dir, records, quiet=False):
    """Require packet evidence for both the reroute and the return to Path A."""
    output_dir = Path(output_dir)
    logs = output_dir / "optimized"
    path_b = sync_request_count(logs / "phase2-s1-flows.txt", 200, 6)
    before = sync_request_count(logs / "phase2-s1-flows.txt", 100, 5)
    after = sync_request_count(logs / "phase3-s1-flows.txt", 100, 5)
    checks = {
        "Sync requests used Path B under load": path_b is not None and path_b > 0,
        "Reroute rules removed from s1, s3, and s4": all(
            not re.search(
                r"\bpriority=200(?:,|\s)", (logs / f"phase3-{switch}-flows.txt").read_text()
            )
            for switch in ["s1", "s3", "s4"]
        ),
        "Sync request counter increased on Path A after load stopped": before is not None
        and after is not None
        and after > before,
        "All three clients received replies during recovery": all(
            any(
                row["client_id"] == f"h_client{client}"
                and row["phase"] == RECOVERY_PHASE
                and row["status"] == "SUCCESS"
                for row in records
            )
            for client in range(1, 4)
        ),
    }
    passed = all(checks.values())
    result = dict(
        passed=passed,
        checks=checks,
        path_b_packets=path_b,
        path_a_packets_before=before,
        path_a_packets_after=after,
    )
    (output_dir / "recovery_check.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# Automatic recovery: " + ("PASS" if passed else "FAIL"), ""]
    lines += [f"- {'PASS' if ok else 'FAIL'}: {label}" for label, ok in checks.items()]
    summary = "\n".join(lines) + "\n"
    (output_dir / "summary_metrics.md").write_text(summary)
    if not quiet:
        print(summary)
    if not passed:
        raise RuntimeError(
            f"Recovery was not verified; inspect {output_dir / 'recovery_check.json'}"
        )
    return result


def run_benchmark(output_dir=None, duration=60, interval=0.5, scenario="both", observer=None):
    if not math.isfinite(duration) or duration < 9:
        raise ValueError("Duration must be at least 9 seconds (three controller polling phases).")
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("Interval must be positive and finite.")
    if scenario not in ["baseline", "optimized", "both", "recovery"]:
        raise ValueError("Unknown scenario")
    if scenario == "recovery" and duration < 60:
        raise ValueError("Use at least 60 seconds for the recovery test.")
    check_environment()
    output_dir = Path(output_dir or DATA_DIR / time.strftime("%Y%m%d-%H%M%S")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # Do not mix a new scenario with results left over from a previous experiment.
    if any(output_dir.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_dir}")
    metadata = dict(
        backend="mininet",
        duration=duration,
        interval=interval,
        scenario=scenario,
        python=sys.version,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        status="running",
    )
    metadata_path = output_dir / "run.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    if scenario == "both":
        modes = ["baseline", "optimized"]
    else:
        modes = ["optimized" if scenario == "recovery" else scenario]
    logging.info("Saving logs and evidence to %s", output_dir)
    try:
        for mode in modes:
            records = run_benchmark_scenario_mininet(
                mode,
                output_dir / mode,
                duration,
                interval,
                recovery=scenario == "recovery",
                observer=observer,
            )
            name = "baseline_metrics.csv" if mode == "baseline" else "sdn_optimized_metrics.csv"
            write_csv(output_dir / name, records)
            if scenario == "recovery":
                verify_recovery(output_dir, records, quiet=observer is not None)
        metadata["status"] = "complete"
    except BaseException:
        metadata["status"] = "incomplete"
        raise
    finally:
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    if observer is None:
        print(f"Results: {output_dir}")
    return output_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument(
        "--scenario", choices=["baseline", "optimized", "both", "recovery"], default="both"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        run_benchmark(**vars(args))
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")

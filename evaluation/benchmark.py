"""Run baseline and optimized time-sync experiments in a Linux Mininet VM."""

import argparse
import csv
import json
import logging
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.sync_worker import CSV_HEADER, PHASES

DATA_DIR = REPO_ROOT / 'evaluation' / 'runs'
CLIENT_DRIFTS = [0.020, -0.015, 0.030]


def check_environment():
    if not sys.platform.startswith('linux') or os.geteuid() != 0:
        raise RuntimeError('Run in the Linux VM with sudo; Mininet needs root.')
    missing = [cmd for cmd in ['mn', 'ovs-vsctl', 'ovs-ofctl', 'tc', 'iperf']
               if shutil.which(cmd) is None]
    if missing:
        raise RuntimeError('Missing commands: ' + ', '.join(missing))
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 6653))
        except OSError as error:
            raise RuntimeError('Controller port 6653 is already in use.') from error
    # Check the same interpreter that will run the controller and clients.
    subprocess.run([sys.executable, '-c', 'import mininet.net; import os_ken.cmd.manager'], check=True)
    subprocess.run(['ovs-vsctl', 'show'], check=True, stdout=subprocess.DEVNULL)


def write_csv(filepath, records):
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open('w', newline='') as stream:
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


def run_benchmark_scenario_mininet(mode, output_dir, duration_sec=60, interval_sec=0.5):
    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSSwitch
    from mininet.link import TCLink
    from topology.custom_topo import TimeSyncTopo, setup_qos_queues, inject_link_impairment

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    processes = []
    logs = []
    net = None
    env = dict(os.environ, SDN_MODE=mode, PYTHONPATH=str(REPO_ROOT))

    def launch(command, name, host=None):
        log = (output_dir / f'{name}.log').open('w')
        logs.append(log)
        popen = host.popen if host else subprocess.Popen
        proc = popen(command, cwd=str(REPO_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(proc)
        return proc

    def capture_state(label):
        for switch in ['s1', 's2', 's3', 's4']:
            with (output_dir / f'{label}-{switch}-flows.txt').open('w') as stream:
                subprocess.run(['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', switch],
                               stdout=stream, check=True)
        with (output_dir / f'{label}-qdisc.txt').open('w') as stream:
            subprocess.run(['tc', '-s', 'qdisc', 'show', 'dev', 's2-eth2'], stdout=stream, check=True)
        with (output_dir / f'{label}-queues.txt').open('w') as stream:
            subprocess.run(['ovs-vsctl', 'list', 'Queue'], stdout=stream, check=True)

    try:
        controller = launch([sys.executable, '-m', 'sdn.run_controller',
                             '--ofp-tcp-listen-port', '6653', 'sdn/controller.py'], 'controller')
        # Assign the network before building so a partial build can be stopped.
        net = Mininet(topo=TimeSyncTopo(), controller=None, switch=OVSSwitch, link=TCLink, build=False)
        net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
        net.build()
        net.start()
        if not net.waitConnected(timeout=10) or controller.poll() is not None:
            raise RuntimeError('Controller connection failed; see controller.log.')
        if mode == 'optimized' and not setup_qos_queues(net):
            raise RuntimeError('OVS queue setup failed.')
        if net.pingAll(timeout='2') > 0:
            raise RuntimeError('Host connectivity check failed.')

        server = launch([sys.executable, '-m', 'app.server'], 'server', net.get('h_server'))
        sink = launch(['iperf', '-s', '-u', '-p', '5001'], 'traffic-sink', net.get('h_sink'))
        time.sleep(1)
        if server.poll() is not None or sink.poll() is not None:
            raise RuntimeError('Server startup failed; see server and traffic-sink logs.')

        # All namespaces share a monotonic clock. Start clients on the same timeline.
        start = time.monotonic() + 2
        workers = []
        traffic = None
        for client_id, drift in enumerate(CLIENT_DRIFTS, 1):
            workers.append(launch([
                sys.executable, '-m', 'evaluation.sync_worker', '--client-id', str(client_id),
                '--drift', str(drift), '--start', str(start), '--duration', str(duration_sec),
                '--interval', str(interval_sec), '--mode', mode,
                '--output', str(output_dir / f'client{client_id}.csv'),
            ], f'client{client_id}', net.get(f'h_client{client_id}')))

        for phase in range(3):
            time.sleep(max(0, start + phase * duration_sec / 3 - time.monotonic()))
            logging.info('%s: %s', mode, PHASES[phase])
            if phase == 1:
                traffic = launch(['iperf', '-c', '10.0.0.2', '-u', '-p', '5001', '-b', '12M',
                        '-t', str(math.ceil(duration_sec * 2 / 3))],
                       'traffic-source', net.get('h_load'))
            elif phase == 2:
                inject_link_impairment(net, delay_ms=50, jitter_ms=15)
            # Save flow counters near the end of each phase, after controller polls.
            time.sleep(max(0, start + (phase + 1) * duration_sec / 3 - 0.2 - time.monotonic()))
            if controller.poll() is not None:
                raise RuntimeError('Controller exited during experiment; see controller.log.')
            capture_state(f'phase{phase + 1}')

        for worker in workers:
            if worker.wait(timeout=5) != 0:
                raise RuntimeError('Client failed; see client logs.')
        if traffic is not None and traffic.wait(timeout=5) != 0:
            raise RuntimeError('Background traffic failed; see traffic-source.log.')
        records = []
        for client_id in range(1, 4):
            with (output_dir / f'client{client_id}.csv').open() as stream:
                records.extend(csv.DictReader(stream))
        for client_id in range(1, 4):
            if not any(row['client_id'] == f'h_client{client_id}' and row['status'] == 'SUCCESS' for row in records):
                raise RuntimeError(f'Client {client_id} has no successful sync samples; see client logs.')
        return records
    except Exception as error:
        raise RuntimeError(f'Mininet experiment failed: {error}. Logs: {output_dir}') from error
    finally:
        for proc in reversed(processes):
            stop_process(proc)
        if net is not None:
            net.stop()
        for log in logs:
            log.close()


def run_benchmark(output_dir=None, duration=60, interval=0.5, scenario='both'):
    if not math.isfinite(duration) or duration < 9:
        raise ValueError('Duration must be at least 9 seconds (three controller polling phases).')
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('Interval must be positive and finite.')
    check_environment()
    output_dir = Path(output_dir or DATA_DIR / time.strftime('%Y%m%d-%H%M%S')).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # Do not mix a new scenario with results left over from a previous experiment.
    if any(output_dir.iterdir()):
        raise ValueError(f'Output directory is not empty: {output_dir}')
    metadata = dict(backend='mininet', duration=duration, interval=interval, scenario=scenario,
                    python=sys.version, started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                    status='running')
    metadata_path = output_dir / 'run.json'
    metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
    modes = ['baseline', 'optimized'] if scenario == 'both' else [scenario]
    logging.info('Saving logs and evidence to %s', output_dir)
    try:
        for mode in modes:
            records = run_benchmark_scenario_mininet(mode, output_dir / mode, duration, interval)
            name = 'baseline_metrics.csv' if mode == 'baseline' else 'sdn_optimized_metrics.csv'
            write_csv(output_dir / name, records)
        metadata['status'] = 'complete'
    except BaseException:
        metadata['status'] = 'incomplete'
        raise
    finally:
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Results: {output_dir}')
    return output_dir


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir')
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--scenario', choices=['baseline', 'optimized', 'both'], default='both')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        run_benchmark(**vars(args))
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')

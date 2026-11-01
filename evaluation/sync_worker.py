"""Persistent UDP client used inside each Mininet host during a benchmark."""

import argparse
import csv
import logging
import socket
import time

from app.client import VirtualClock
from app.protocol import (
    DEFAULT_PORT, PKT_TYPE_REQUEST, PKT_TYPE_RESPONSE, TimeSyncPacket,
    calculate_delay, calculate_offset,
)

CSV_HEADER = [
    'seq', 'client_id', 'elapsed_sec', 'phase', 't0', 't1', 't2', 't3',
    'rtt_ms', 'measured_offset_ms', 'true_residual_error_ms', 'jitter_ms',
    'path_mode', 'status',
]
PHASES = ['Phase 1: Normal', 'Phase 2: iperf Congestion', 'Phase 3: NetEm Delay+Jitter']


def phase_at(elapsed, duration):
    return PHASES[min(int(elapsed / (duration / 3)), 2)]


def sample(sock, clock, client_id, seq):
    """Timestamp at the socket, then correct only a valid matching response."""
    t0 = clock.get_time()
    request = TimeSyncPacket(PKT_TYPE_REQUEST, client_id, seq, t0=t0)
    row = dict.fromkeys(CSV_HEADER, '')
    row.update(seq=seq, t0=t0, status='TIMEOUT')
    try:
        sock.send(request.to_bytes())
        data = sock.recv(2048)
        t3 = clock.get_time()
        response = TimeSyncPacket.from_bytes(data)
        if (response.pkt_type != PKT_TYPE_RESPONSE or response.seq_num != seq
                or response.client_id != client_id or response.t0 != t0):
            raise ValueError('Response does not match request')
        rtt = calculate_delay(t0, response.t1, response.t2, t3) * 1000
        offset = calculate_offset(t0, response.t1, response.t2, t3)
        clock.adjust(offset)
        row.update(t1=response.t1, t2=response.t2, t3=t3, rtt_ms=rtt,
                   measured_offset_ms=offset * 1000, status='SUCCESS')
    except (socket.timeout, ConnectionRefusedError):
        pass
    except ValueError:
        row['status'] = 'INVALID'
    # Mininet namespaces share the VM clock, so reference error is observable.
    row['true_residual_error_ms'] = abs(clock.get_time() - time.time()) * 1000
    return row


def run_client(server, client_id, drift, start, duration, interval, mode, output):
    clock = VirtualClock(initial_offset=0.100, drift_rate=drift)
    last_rtt = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, open(output, 'w', newline='') as stream:
        sock.settimeout(1.0)
        sock.connect((server, DEFAULT_PORT))
        writer = csv.DictWriter(stream, fieldnames=CSV_HEADER)
        writer.writeheader()
        time.sleep(max(0, start - time.monotonic()))
        seq = 0
        next_tick = start
        while time.monotonic() - start < duration:
            elapsed = time.monotonic() - start
            seq += 1
            row = sample(sock, clock, client_id, seq)
            row.update(client_id=f'h_client{client_id}', elapsed_sec=elapsed,
                       phase=phase_at(elapsed, duration), path_mode=mode)
            if row['status'] == 'SUCCESS':
                row['jitter_ms'] = abs(row['rtt_ms'] - last_rtt) if last_rtt is not None else ''
                last_rtt = row['rtt_ms']
            else:
                last_rtt = None
            writer.writerow(row)
            stream.flush()
            logging.info('Client %s #%s: %s RTT=%s ms error=%.3f ms',
                         client_id, seq, row['status'], row['rtt_ms'], row['true_residual_error_ms'])
            next_tick += interval
            time.sleep(max(0, next_tick - time.monotonic()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', default='10.0.0.1')
    parser.add_argument('--client-id', type=int, required=True)
    parser.add_argument('--drift', type=float, required=True)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--interval', type=float, required=True)
    parser.add_argument('--mode', choices=['baseline', 'optimized'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    run_client(**vars(args))

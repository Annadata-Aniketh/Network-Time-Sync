"""UDP Time Client for Network Time Synchronization System."""
import socket
import time
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import PORT, BUFFER_SIZE, create_request, parse_packet

def sync_time(server_ip, server_port=PORT, client_id="h3", count=3):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    print(f"--- Synchronizing with {server_ip}:{server_port} ---", flush=True)

    for i in range(1, count + 1):
        req = create_request(client_id=client_id)
        t0 = time.time()
        sock.sendto(req, (server_ip, server_port))
        try:
            raw_data, _ = sock.recvfrom(BUFFER_SIZE)
            t3 = time.time()
            res = parse_packet(raw_data)
            t1, t2 = res["t1"], res["t2"]

            rtt = (t3 - t0) - (t2 - t1)
            offset = ((t1 - t0) + (t2 - t3)) / 2.0
            print(f"Sample {i}: RTT = {rtt * 1000.0:.3f} ms | Offset = {offset * 1000.0:+.3f} ms | Sync Time = {t3 + offset:.6f} s", flush=True)
        except socket.timeout:
            print(f"Sample {i}: Request timed out.", flush=True)
        time.sleep(1)

    sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="10.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--client-id", default="h3")
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    sync_time(args.server, args.port, args.client_id, args.count)

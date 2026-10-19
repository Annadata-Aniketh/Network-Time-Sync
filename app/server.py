"""UDP Time Server for Network Time Synchronization System."""
import socket
import time
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import PORT, BUFFER_SIZE, create_response, parse_packet

def run_server(host="0.0.0.0", port=PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"[TimeServer] Listening on UDP {host}:{port}...", flush=True)

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            rx_time = time.time()
            pkt = parse_packet(data)
            if pkt.get("type") == "SYNC_REQUEST":
                resp = create_response(pkt, rx_time)
                sock.sendto(resp, addr)
                print(f"[TimeServer] Request handled for {addr[0]}:{addr[1]} at t={rx_time:.6f}", flush=True)
        except Exception as e:
            print(f"[TimeServer] Error: {e}", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    run_server(args.host, args.port)

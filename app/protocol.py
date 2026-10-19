"""Protocol definitions for Network Time Synchronization System."""
import json
import time

PORT = 12300
BUFFER_SIZE = 1024

def create_request(client_id="client"):
    return json.dumps({
        "type": "SYNC_REQUEST",
        "client_id": client_id,
        "t0": time.time()
    }).encode('utf-8')

def create_response(req_data, server_rx_time):
    return json.dumps({
        "type": "SYNC_RESPONSE",
        "client_id": req_data.get("client_id"),
        "t0": req_data.get("t0"),
        "t1": server_rx_time,
        "t2": time.time()
    }).encode('utf-8')

def parse_packet(raw_bytes):
    return json.loads(raw_bytes.decode('utf-8'))

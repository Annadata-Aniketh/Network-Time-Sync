import time
import socket
import csv
import os
import argparse
import logging
from app.protocol import (
    TimeSyncPacket, PKT_TYPE_REQUEST, PKT_TYPE_RESPONSE, DEFAULT_PORT, calculate_delay, calculate_offset
)
class VirtualClock:
    def __init__(self, initial_offset: float = 0.0, drift_rate: float = 0.020, max_slew_rate: float = 0.050):
        self.start_real_time = time.time()
        self.initial_offset = initial_offset
        self.drift_rate = drift_rate
        self.last_check_time = self.start_real_time
        self.max_slew_rate = max_slew_rate
        self.correction = 0.0
        self.remaining_slew = 0.0

    def get_time(self) -> float:
        # virtual time = real_time + initial_offset + (elapsed_real * drift_rate) + correction
        now = time.time()
        dt = now - self.last_check_time
        self.last_check_time = now

        if self.remaining_slew != 0.0 and dt > 0:
            max_adjust = self.max_slew_rate * dt
            if self.remaining_slew > 0:
                slew_slice = min(self.remaining_slew, max_adjust)
            else:
                slew_slice = max(self.remaining_slew, -max_adjust)
            self.correction += slew_slice
            self.remaining_slew -= slew_slice

        elapsed_real = now - self.start_real_time
        drift = elapsed_real * self.drift_rate
        return now + self.initial_offset + drift + self.correction

    def adjust(self, offset: float, method: str = "step"):
        if method == "step":
            self.correction += offset
        elif method == "slew":
            self.remaining_slew += offset

class TimeSyncClient:
    def __init__(self, server_ip: str = "127.0.0.1", server_port: int = DEFAULT_PORT, client_id: int = 1, interval: float = 1.0, clock: VirtualClock = None, csv_path: str = None, timeout: float = 2.0, method: str = "step"):
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_id = client_id
        self.interval = interval
        self.clock = clock or VirtualClock()
        self.timeout = timeout
        self.seq_num = 0
        self.running = False
        self.csv_path = csv_path or f"data/client_{client_id}_sync.csv"
        os.makedirs(os.path.dirname(self.csv_path), exist_ok = True)
        self._init_csv()
        self.method = method

    def _init_csv(self): # initialize csv file
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "client_id", "seq_num", "t0", "t1", "t2", "t3", "rtt", "offset", "status"])
    def _log_to_csv(self, row:list): # add logs into csv file
        with open(self.csv_path, "a", newline = "") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def sync_once(self, sock:socket.socket):
        self.seq_num += 1
        t0 = self.clock.get_time()
        req_pkt = TimeSyncPacket(pkt_type=PKT_TYPE_REQUEST, client_id=self.client_id, seq_num=self.seq_num, t0=t0)
        sock.sendto(req_pkt.to_bytes(), (self.server_ip, self.server_port))

        try: # analysing response pkt and also check ing for timeouts if any
            data, _ = sock.recvfrom(2048) # 2048 is the buffer size of reciever window 
            t3 = self.clock.get_time()
            resp_pkt = TimeSyncPacket.from_bytes(data)
            
            if resp_pkt.pkt_type != PKT_TYPE_RESPONSE or resp_pkt.seq_num != self.seq_num: # checking pkt for validation(same pkt or different pkt)
                logging.warning(f"Ignored mismatched response (seq {resp_pkt.seq_num}, expected {self.seq_num})")
                return
            
            delay = calculate_delay(t0, resp_pkt.t1, resp_pkt.t2, t3)
            offset = calculate_offset(t0, resp_pkt.t1, resp_pkt.t2, t3)

            self.clock.adjust(offset, method = self.method) # adjusting virtual clock
            rtt_ms = delay * 1000
            offset_ms = offset * 1000

            logging.info(
                f"Sync #{self.seq_num} | Delay: {rtt_ms:.3f} ms | Offset: {offset_ms:.3f} ms | Virtual time: {self.clock.get_time():.6f}"
            )

            self._log_to_csv([time.time(), self.client_id, self.seq_num, t0, resp_pkt.t1, resp_pkt.t2, t3, rtt_ms, offset_ms, "SUCCESS"]) # log data to csv
        
        except(socket.timeout, TimeoutError): # timeout case
            logging.warning(f"Sync #{self.seq_num} timed out (packet dropped or server unreachable)")
            self._log_to_csv([time.time(), self.client_id, self.seq_num, t0, 0.0, 0.0, 0.0, 0.0, 0.0, "TIMEOUT"]) # log data to csv
            
    def start(self, count: int = 0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        self.running = True
        logging.info(f"Client {self.client_id} started. Syncing with {self.server_ip}:{self.server_port} every {self.interval}s (Initial Offset: {self.clock.initial_offset}s, Drift: {self.clock.drift_rate}s/s)")

        sync_count = 0

        try:
            while self.running:
                self.sync_once(sock)
                sync_count += 1
                if count>0 and sync_count>= count:
                    logging.info(f"Completed requested {count} sync cycles" )
                    break
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logging.info("Client stopping...")
        finally:
            self.running = False
            sock.close()
            logging.info("Client socket closed.")
    
if __name__ == "__main__": # CLI arguments
    parser = argparse.ArgumentParser(description="UDP Time Synchronization Client")
    parser.add_argument("--server-ip", default="127.0.0.1", help="Server IP address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server UDP port (default: {DEFAULT_PORT})")
    parser.add_argument("--client-id", type=int, default=1, help="Client ID integer (default: 1)")
    parser.add_argument("--drift-rate", type=float, default=0.020, help="Artificial drift rate in s/s (default: 0.020)")
    parser.add_argument("--initial-offset", type=float, default=2.0, help="Initial clock offset in seconds (default: 2.0)")
    parser.add_argument("--interval", type=float, default=1.0, help="Sync interval in seconds (default: 1.0)")
    parser.add_argument("--count", type=int, default=0, help="Sync count limit (0 = run indefinitely)")
    parser.add_argument("--csv", type=str, default=None, help="Custom CSV output path")
    parser.add_argument("--method", choices=["step", "slew"], default="step", help="Adjustment method: step or slew")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    clock = VirtualClock(initial_offset=args.initial_offset, drift_rate=args.drift_rate)
    client = TimeSyncClient(
        server_ip=args.server_ip,
        server_port=args.port,
        client_id=args.client_id,
        interval=args.interval,
        clock=clock,
        csv_path=args.csv,
        method = args.method
    )
    client.start(count=args.count)


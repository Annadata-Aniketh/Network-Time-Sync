import socket
import time
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
# Since we use UDP (connectionless) all the pkts arrive at port 12300, so we use threads for concurrency
from app.protocol import (
    TimeSyncPacket, PKT_TYPE_REQUEST, PKT_TYPE_RESPONSE,
    DEFAULT_PORT, PACKET_SIZE
)

class TimeServer:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT, max_workers: int = 4):
        self.host = host
        self.port = port
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running = False
        
    def handle_request(self, sock: socket.socket, data: bytes, client_addr: tuple, t1: float):
        try:
            request_pkt = TimeSyncPacket.from_bytes(data)
            if request_pkt.pkt_type != PKT_TYPE_REQUEST:
                logging.warning(f"Ignored packet as its not a request from {client_addr}")
                return
            
            t2 = time.time() # Noting server time
            response_pkt = TimeSyncPacket(
                pkt_type=PKT_TYPE_RESPONSE,
                client_id=request_pkt.client_id,
                seq_num=request_pkt.seq_num,
                t0=request_pkt.t0,
                t1=t1,
                t2=t2
            )

            sock.sendto(response_pkt.to_bytes(), client_addr)
            turnaround_time = (t2-t1)*1000 # in milliseconds
            logging.info(
                f"Handled sync from {client_addr[0]}:{client_addr[1]} | Client ID: {request_pkt.client_id} | Seq: {request_pkt.seq_num} | Turnaround: {turnaround_time:.3f}ms"
            )
        except ValueError as error:
            logging.warning(f"Malformed packet from {client_addr}: {error}")

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        self.running = True
        logging.info(f"UDP Time Server listening on {self.host}:{self.port} with {self.max_workers} worker threads")

        sock.settimeout(1.0)  # Allows loop to wake up periodically and check self.running / handle Ctrl+C
        try:
            while self.running:
                try:
                    data, client_addr = sock.recvfrom(2048)
                except (socket.timeout, TimeoutError):
                    continue  # No packet arrived in 1s; check self.running and loop again
                
                t1 = time.time()  # Record arrival time immediately
                self.executor.submit(self.handle_request, sock, data, client_addr, t1)
        except KeyboardInterrupt:
            logging.info("Server shutting down...")
        finally:
            self.running = False
            self.executor.shutdown(wait=True)
            sock.close()
            logging.info("Server closed successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP Reference Time Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"UDP port (default: {DEFAULT_PORT})")
    parser.add_argument("--workers", type=int, default=4, help="Thread pool worker count (default: 4)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    server = TimeServer(host=args.host, port=args.port, max_workers=args.workers)
    server.start()
        
import argparse
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.protocol import (
    DEFAULT_PORT,
    PACKET_SIZE,
    PKT_TYPE_REQUEST,
    PKT_TYPE_RESPONSE,
    TimeSyncPacket,
)


class TimeServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        max_workers: int = 4,
        max_pending: int = 128,
    ):
        if max_workers < 1 or max_pending < max_workers:
            raise ValueError("Require 1 <= max_workers <= max_pending")
        self.host = host
        self.port = port
        self.max_workers = max_workers
        self.max_pending = max_pending
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._slots = threading.BoundedSemaphore(max_pending)
        self._stats_lock = threading.Lock()
        self.stats = dict(accepted=0, invalid=0, overloaded=0, pending=0, peak_pending=0, errors=0)
        self.running = False
        self.ready = threading.Event()

    def _completed(self, future):
        with self._stats_lock:
            self.stats["pending"] -= 1
            if future.exception() is not None:
                self.stats["errors"] += 1
        self._slots.release()

    def submit_request(self, sock, data, client_addr, t1):
        """Validate datagrams before admitting work to the bounded worker queue."""
        try:
            request = TimeSyncPacket.from_bytes(data)
            if request.pkt_type != PKT_TYPE_REQUEST:
                raise ValueError("Expected a request")
        except ValueError:
            with self._stats_lock:
                self.stats["invalid"] += 1
            return False
        if not self._slots.acquire(blocking=False):
            with self._stats_lock:
                self.stats["overloaded"] += 1
            return False
        with self._stats_lock:
            self.stats["accepted"] += 1
            self.stats["pending"] += 1
            self.stats["peak_pending"] = max(self.stats["peak_pending"], self.stats["pending"])
        try:
            future = self.executor.submit(self.handle_request, sock, data, client_addr, t1)
        except RuntimeError:
            with self._stats_lock:
                self.stats["pending"] -= 1
            self._slots.release()
            raise
        future.add_done_callback(self._completed)
        return True

    def handle_request(self, sock: socket.socket, data: bytes, client_addr: tuple, t1: float):
        try:
            request_pkt = TimeSyncPacket.from_bytes(data)
            if request_pkt.pkt_type != PKT_TYPE_REQUEST:
                logging.warning(f"Ignored packet as its not a request from {client_addr}")
                return

            t2 = time.time()
            response_pkt = TimeSyncPacket(
                pkt_type=PKT_TYPE_RESPONSE,
                client_id=request_pkt.client_id,
                seq_num=request_pkt.seq_num,
                t0=request_pkt.t0,
                t1=t1,
                t2=t2,
            )

            sock.sendto(response_pkt.to_bytes(), client_addr)
            turnaround_time = (t2 - t1) * 1000
            logging.info(
                f"Handled sync from {client_addr[0]}:{client_addr[1]} | Client ID: {request_pkt.client_id} | Seq: {request_pkt.seq_num} | Turnaround: {turnaround_time:.3f}ms"
            )
        except ValueError as error:
            logging.warning(f"Malformed packet from {client_addr}: {error}")

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
            self.port = sock.getsockname()[1]
            self.running = True
            self.ready.set()
            logging.info(
                f"UDP Time Server listening on {self.host}:{self.port} with {self.max_workers} worker threads"
            )
            sock.settimeout(1.0)
            while self.running:
                try:
                    data, client_addr = sock.recvfrom(PACKET_SIZE + 1)
                except TimeoutError:
                    continue

                t1 = time.time()
                self.submit_request(sock, data, client_addr, t1)
        except KeyboardInterrupt:
            logging.info("Server shutting down...")
        finally:
            self.running = False
            self.ready.set()
            self.executor.shutdown(wait=True)
            sock.close()
            logging.info("Server closed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP Reference Time Server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: loopback; set the reference host IP for remote clients)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"UDP port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Thread pool worker count (default: 4)"
    )
    parser.add_argument(
        "--max-pending",
        type=int,
        default=128,
        help="Maximum active and queued requests (default: 128)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    server = TimeServer(
        host=args.host, port=args.port, max_workers=args.workers, max_pending=args.max_pending
    )
    server.start()

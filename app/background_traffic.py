import socket
import time
import argparse
import logging
import shutil
import subprocess

DEFAULT_TRAFFIC_PORT = 5001

def run_iperf_client(target_ip: str, port: int = DEFAULT_TRAFFIC_PORT, bandwidth: str = "20M", duration:  int = 10, udp: bool = True):
    iperf_cmd = shutil.which("iperf3") or shutil.which("iperf") # check if iperf exists
    if not iperf_cmd:
        logging.warning("iperf was not installed. Falling back to socket generator.")
        run_socket_sender(target_ip=target_ip, port=port,duration=float(duration))
        return
    
    cmd = [iperf_cmd,"-c",target_ip,"-p",str(port),"-t",str(duration),"-b",bandwidth]
    if udp:
        cmd.append("-u")
    logging.info(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd)
def run_socket_sender(target_ip: str, port: int = DEFAULT_TRAFFIC_PORT, rate_mbps: float = 20.0, duration: float = 10.0, packet_size: int = 1400): # 1400 becuase the ethernet max allowed size is 1500
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b"X" * packet_size
    target_bytes_sec = (rate_mbps * 1000000)/8.0 if rate_mbps>0 else float("inf")
    
    start_time = time.time()
    bytes_sent = 0
    packets_sent = 0
    try:
        while True:
            now = time.time()
            elapsed = now - start_time
            if duration>0 and elapsed>=duration:
                break
            
            expected_bytes = elapsed * target_bytes_sec # if we sent more packets by mistake than what was expected, we are pacing by sleeping
            if bytes_sent>expected_bytes and rate_mbps>0:
                time.sleep(0.001)
                continue

            sock.sendto(payload, (target_ip, port))
            bytes_sent += packet_size
            packets_sent += 1
    except KeyboardInterrupt:
        logging.info("Traffic generation stopped manually by user.")
    finally:
        sock.close()
        total_time = max(time.time()-start_time, 0.001)
        mbps = (bytes_sent*8.0)/(total_time*1000000)
        logging.info(f"Summary: Sent {packets_sent} packets ({bytes_sent/1024/1024:.2f} MB) in {total_time:.2f}s (~{mbps:.2f} Mbps)")
def run_socket_receiver(port: int = DEFAULT_TRAFFIC_PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # receiver dump port
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(1.0)
    logging.info(f"Background traffic sink listening on 0.0.0.0:{port}...")

    bytes_received = 0
    last_report_time = time.time()

    try:
        while True:
            try:
                data, _ = sock.recvfrom(65535)
                bytes_received += len(data)
            except (socket.timeout, TimeoutError):
                pass  # timeout passed without packet, looping to check timer

            now = time.time()
            if now - last_report_time >= 1.0:
                mbps = (bytes_received * 8.0) / ((now - last_report_time) * 1_000_000) # caluclating Mbps every second
                if bytes_received > 0:
                    logging.info(f"Receiving background load: {mbps:.2f} Mbps")
                bytes_received = 0
                last_report_time = now

    except KeyboardInterrupt:
        logging.info("Traffic sink stopped manually by user.")
    finally:
        sock.close()

if __name__ == "__main__": # CLI arguments
    parser = argparse.ArgumentParser(description="Background Traffic Generator (iperf wrapper & socket blaster)")
    parser.add_argument("--server", action="store_true", help="Run as receiver sink on port 5001")
    parser.add_argument("--target", default="127.0.0.1", help="Target IP for sender (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_TRAFFIC_PORT, help=f"Port (default: {DEFAULT_TRAFFIC_PORT})")
    parser.add_argument("--rate", type=float, default=20.0, help="Target rate in Mbps (default: 20.0)")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration in seconds (default: 10.0)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.server:
        run_socket_receiver(port=args.port)
    else:
        run_iperf_client(target_ip=args.target, port=args.port, bandwidth=f"{int(args.rate)}M", duration=int(args.duration))

    
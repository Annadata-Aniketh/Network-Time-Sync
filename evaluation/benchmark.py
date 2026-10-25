
import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime


def run_benchmark(args):
    os.makedirs(args.output_dir, exist_ok=True)

    results_file = os.path.join(
        args.output_dir, "benchmark_results.csv"
    )

    fieldnames = [
        "timestamp",
        "mode",
        "client_id",
        "seq_num",
        "rtt",
        "offset",
        "status",
    ]

    server_process = None

    try:
        if args.start_server:
            print("Starting local time server...")
            server_process = subprocess.Popen([
                sys.executable, "-m", "app.server",
                "--host", args.server_ip,
                "--port", str(args.port),
            ])
            time.sleep(1)

        with open(results_file, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for client_id in range(1, args.clients + 1):
                client_file = os.path.join(
                    args.output_dir,
                    f"client_{client_id}.csv",
                )

                command = [
                    sys.executable, "-m", "app.client",
                    "--server-ip", args.server_ip,
                    "--port", str(args.port),
                    "--client-id", str(client_id),
                    "--interval", str(args.interval),
                    "--count", str(args.samples),
                    "--csv", client_file,
                ]

                print(f"Running client {client_id}/{args.clients}...")
                result = subprocess.run(command, check=False)

                if result.returncode != 0:
                    print(f"Warning: client {client_id} returned an error.")

                if not os.path.exists(client_file):
                    print(f"No output created for client {client_id}.")
                    continue

                with open(client_file, newline="") as rawfile:
                    reader = csv.DictReader(rawfile)

                    for row in reader:
                        writer.writerow({
                            "timestamp": datetime.now().isoformat(),
                            "mode": args.mode,
                            "client_id": row.get("client_id", client_id),
                            "seq_num": row.get("seq_num", ""),
                            "rtt": row.get("rtt", ""),
                            "offset": row.get("offset", ""),
                            "status": row.get("status", ""),
                        })

        print(f"\nBenchmark results saved to: {results_file}")

    finally:
        if server_process is not None:
            server_process.terminate()
            server_process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(
        description="Network time synchronization benchmark"
    )
    parser.add_argument("--mode", choices=["baseline", "sdn"], default="baseline")
    parser.add_argument("--server-ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12300)
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output-dir", default="evaluation/data")
    parser.add_argument("--start-server", action="store_true")

    args = parser.parse_args()
    run_benchmark(args)


if __name__ == "__main__":
    main()

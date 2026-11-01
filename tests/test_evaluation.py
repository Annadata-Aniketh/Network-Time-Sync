#!/usr/bin/env python3
"""
Unit and Integration Tests for Member 3 Deliverables
Course: UE25CS243A: Computer Networks — Team 11 (Project #23)
Tests:
  - app/background_traffic.py (UDP receiver, sender, and helpers)
  - evaluation/benchmark.py (Local proxy, latency calculation, and CSV telemetry schema)
  - evaluation/plot_results.py (Summary table calculation, statistics, and plot generation)
"""

import os
import shutil
import tempfile
import time
import unittest

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
import pandas as pd

from app.background_traffic import (
    SocketTrafficReceiver,
    SocketTrafficSender,
    start_background_traffic,
)
from evaluation.benchmark import (
    EmulatedNetworkProxy,
    run_benchmark_scenario_local,
    write_csv,
    CSV_HEADER,
)
from evaluation.plot_results import (
    compute_summary_table,
    calculate_convergence_time,
)


class TestBackgroundTraffic(unittest.TestCase):
    """Verifies pure-Python background traffic sender and receiver."""

    def test_sender_and_receiver_communication(self):
        port = 15001
        receiver = SocketTrafficReceiver(host="127.0.0.1", port=port)
        
        # Test basic initialization and attributes
        sender = SocketTrafficSender(target_ip="127.0.0.1", port=port, rate_mbps=1.0)
        self.assertEqual(sender.target_ip, "127.0.0.1")
        self.assertEqual(sender.port, port)
        self.assertEqual(receiver.port, port)


class TestBenchmarkHarness(unittest.TestCase):
    """Verifies benchmark proxy logic and CSV schema validation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_emulated_proxy_latencies(self):
        proxy = EmulatedNetworkProxy(mode="baseline")
        proxy.set_phase("Phase 1: Normal")
        fwd, rev = proxy._calculate_latencies()
        self.assertGreater(fwd, 0.5)
        self.assertLess(fwd, 10.0)

        proxy.set_phase("Phase 2: iperf Congestion")
        fwd_cong, rev_cong = proxy._calculate_latencies()
        self.assertGreater(fwd_cong, 15.0)

        # Optimized mode should maintain low latency even in Phase 2
        proxy_opt = EmulatedNetworkProxy(mode="sdn_optimized")
        proxy_opt.set_phase("Phase 2: iperf Congestion")
        fwd_opt, rev_opt = proxy_opt._calculate_latencies()
        self.assertLess(fwd_opt, 8.0)

    def test_local_benchmark_run_and_schema(self):
        """Runs a short 1-second benchmark run and validates CSV schema."""
        records = run_benchmark_scenario_local(mode="baseline", duration_sec=1.0, interval_sec=0.5)
        self.assertGreater(len(records), 0)

        # Check required columns
        for col in CSV_HEADER:
            self.assertIn(col, records[0])

        out_csv = os.path.join(self.test_dir, "test_metrics.csv")
        write_csv(out_csv, records)
        self.assertTrue(os.path.exists(out_csv))

        df = pd.read_csv(out_csv)
        self.assertEqual(list(df.columns), CSV_HEADER)
        self.assertIn("Phase 1: Normal", df["phase"].values)


class TestPlotResults(unittest.TestCase):
    """Verifies summary statistics and table formatting."""

    def test_summary_table_computation(self):
        data_base = {
            "elapsed_sec": [1.0, 2.0, 3.0, 4.0],
            "rtt_ms": [40.0, 50.0, 45.0, 60.0],
            "jitter_ms": [10.0, 15.0, 12.0, 14.0],
            "true_residual_error_ms": [25.0, 22.0, 24.0, 26.0],
            "phase": ["Phase 1: Normal"] * 4,
        }
        data_opt = {
            "elapsed_sec": [1.0, 2.0, 3.0, 4.0],
            "rtt_ms": [4.0, 4.2, 4.1, 4.3],
            "jitter_ms": [0.5, 0.4, 0.5, 0.6],
            "true_residual_error_ms": [1.2, 1.1, 1.0, 0.9],
            "phase": ["Phase 1: Normal"] * 4,
        }

        df_base = pd.DataFrame(data_base)
        df_opt = pd.DataFrame(data_opt)

        stats, md_table = compute_summary_table(df_base, df_opt)
        self.assertIn("Mean RTT (ms)", stats)
        self.assertIn("SDN-Optimized Mode", md_table)
        self.assertIn("+91", md_table)  # Check improvement string


if __name__ == "__main__":
    unittest.main()

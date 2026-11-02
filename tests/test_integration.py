import unittest
import threading
import os
import socket
import tempfile
from evaluation.sync_worker import sample
from app.server import TimeServer
from app.client import TimeSyncClient, VirtualClock


class TestTimeSyncIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = TimeServer(host="127.0.0.1", port=0, max_workers=2)
        cls.server_thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.server_thread.start()
        if not cls.server.ready.wait(timeout=3) or not cls.server.running:
            raise RuntimeError('Test server did not start')
        cls.test_port = cls.server.port

    @classmethod
    def tearDownClass(cls):
        cls.server.running = False
        cls.server_thread.join(timeout=3)
        if cls.server_thread.is_alive():
            raise RuntimeError('Test server did not stop')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.test_csv_dir = self.directory.name

    def tearDown(self):
        self.directory.cleanup()

    def test_benchmark_sample_with_real_server(self):
        clock = VirtualClock(initial_offset=.1, drift_rate=0)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            sock.connect(('127.0.0.1', self.test_port))
            row = sample(sock, clock, client_id=1, seq=1)
        self.assertEqual(row['status'], 'SUCCESS')
        self.assertGreaterEqual(row['rtt_ms'], 0)
        self.assertLess(row['true_residual_error_ms'], 30)

    def test_client_server_step_sync(self):
        """Verify client connects to server and converges using step adjustment."""
        csv_file = os.path.join(self.test_csv_dir, "client_step.csv")
        clock = VirtualClock(initial_offset=1.5, drift_rate=0.010)
        client = TimeSyncClient(
            server_ip="127.0.0.1",
            server_port=self.test_port,
            client_id=1,
            interval=0.2,
            clock=clock,
            csv_path=csv_file,
            method="step",
        )

        # Run 3 sync cycles
        client.start(count=3)

        self.assertTrue(os.path.exists(csv_file))
        with open(csv_file) as f:
            lines = f.readlines()
            # 1 header + 3 sync rows
            self.assertEqual(len(lines), 4)
            # Verify status in rows is SUCCESS
            for row in lines[1:]:
                self.assertIn("SUCCESS", row)

    def test_client_server_slew_sync(self):
        """Verify client connects to server and runs slew adjustment without crashing."""
        csv_file = os.path.join(self.test_csv_dir, "client_slew.csv")
        clock = VirtualClock(initial_offset=0.05, drift_rate=0.005)
        client = TimeSyncClient(
            server_ip="127.0.0.1",
            server_port=self.test_port,
            client_id=2,
            interval=0.2,
            clock=clock,
            csv_path=csv_file,
            method="slew",
        )

        client.start(count=3)

        self.assertTrue(os.path.exists(csv_file))
        with open(csv_file) as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 4)


if __name__ == "__main__":
    unittest.main()

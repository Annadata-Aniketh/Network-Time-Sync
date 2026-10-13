import unittest
import threading
import time
import os
import shutil
from app.server import TimeServer
from app.client import TimeSyncClient, VirtualClock


class TestTimeSyncIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_port = 12850
        cls.server = TimeServer(host="127.0.0.1", port=cls.test_port, max_workers=2)
        cls.server_thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.server_thread.start()
        time.sleep(0.2)  # Give server time to bind

    @classmethod
    def tearDownClass(cls):
        cls.server.running = False
        time.sleep(0.1)

    def setUp(self):
        self.test_csv_dir = "data/test_integration"
        os.makedirs(self.test_csv_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_csv_dir):
            shutil.rmtree(self.test_csv_dir, ignore_errors=True)

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

import unittest
import time
from app.client import VirtualClock


class TestVirtualClock(unittest.TestCase):
    def test_initial_offset(self):
        """Verify initial offset shifts the returned time."""
        clock = VirtualClock(initial_offset=5.0, drift_rate=0.0)
        vtime = clock.get_time()
        rtime = time.time()
        # Should be approximately 5 seconds ahead
        self.assertAlmostEqual(vtime - rtime, 5.0, delta=0.05)

    def test_drift_rate_accumulation(self):
        """Verify clock drifts faster than real time when drift_rate > 0."""
        # High drift rate to easily measure in short sleep
        clock = VirtualClock(initial_offset=0.0, drift_rate=0.50)  # +50% faster
        t_start = clock.get_time()
        time.sleep(0.1)
        t_end = clock.get_time()

        elapsed_virtual = t_end - t_start
        # Virtual elapsed should be roughly 0.1 * 1.50 = 0.15s
        self.assertGreater(elapsed_virtual, 0.11)

    def test_step_adjustment(self):
        """Verify step adjustment instantly shifts virtual time."""
        clock = VirtualClock(initial_offset=2.0, drift_rate=0.0)
        clock.adjust(-2.0, method="step")
        vtime = clock.get_time()
        rtime = time.time()
        # After subtracting 2.0s, difference from real time should be near 0
        self.assertAlmostEqual(vtime - rtime, 0.0, delta=0.05)

    def test_slew_adjustment_gradual(self):
        """Verify slew adjustment does not jump instantly, but adjusts over time."""
        # Set max slew rate = 0.10s per second
        clock = VirtualClock(initial_offset=0.0, drift_rate=0.0, max_slew_rate=0.10)
        clock.adjust(0.50, method="slew")  # request +500ms slew

        # Immediately after adjust(), remaining_slew should be 0.50
        self.assertAlmostEqual(clock.remaining_slew, 0.50, places=3)

        # After a short sleep, a small slice should be absorbed
        time.sleep(0.1)
        _ = clock.get_time()
        self.assertLess(clock.remaining_slew, 0.50)
        self.assertGreater(clock.remaining_slew, 0.0)


if __name__ == "__main__":
    unittest.main()

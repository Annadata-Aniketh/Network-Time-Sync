import time
import unittest

from app.client import VirtualClock


class TestVirtualClock(unittest.TestCase):
    def test_initial_offset(self):
        """Verify initial offset shifts the returned time."""
        clock = VirtualClock(initial_offset=5.0, drift_rate=0.0)
        vtime = clock.get_time()
        rtime = time.time()

        self.assertAlmostEqual(vtime - rtime, 5.0, delta=0.05)

    def test_drift_rate_accumulation(self):
        """Verify clock drifts faster than real time when drift_rate > 0."""

        clock = VirtualClock(initial_offset=0.0, drift_rate=0.50)
        t_start = clock.get_time()
        time.sleep(0.1)
        t_end = clock.get_time()

        elapsed_virtual = t_end - t_start

        self.assertGreater(elapsed_virtual, 0.11)

    def test_step_adjustment(self):
        """Verify step adjustment instantly shifts virtual time."""
        clock = VirtualClock(initial_offset=2.0, drift_rate=0.0)
        clock.adjust(-2.0, method="step")
        vtime = clock.get_time()
        rtime = time.time()

        self.assertAlmostEqual(vtime - rtime, 0.0, delta=0.05)

    def test_slew_adjustment_gradual(self):
        """Verify slew adjustment does not jump instantly, but adjusts over time."""

        clock = VirtualClock(initial_offset=0.0, drift_rate=0.0, max_slew_rate=0.10)
        clock.adjust(0.50, method="slew")

        self.assertAlmostEqual(clock.remaining_slew, 0.50, places=3)

        time.sleep(0.1)
        _ = clock.get_time()
        self.assertLess(clock.remaining_slew, 0.50)
        self.assertGreater(clock.remaining_slew, 0.0)


if __name__ == "__main__":
    unittest.main()

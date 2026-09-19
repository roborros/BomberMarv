import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timing_abstraction import (
    Clock,
    GameClock,
    PerfCounterTimingBackend,
    TimeManager,
    get_ticks,
)


class TimingTests(unittest.TestCase):
    def test_get_ticks_is_non_negative_int(self):
        value = get_ticks()
        self.assertIsInstance(value, int)
        self.assertGreaterEqual(value, 0)

    def test_get_ticks_advances(self):
        first = get_ticks()
        time.sleep(0.02)
        second = get_ticks()
        self.assertGreaterEqual(second, first)

    def test_clock_first_tick_dt_is_zero(self):
        clock = Clock()
        self.assertEqual(clock.tick(0), 0)

    def test_perf_backend_monotonic(self):
        backend = PerfCounterTimingBackend()
        a = backend.get_ticks()
        time.sleep(0.01)
        b = backend.get_ticks()
        self.assertGreaterEqual(b, a)

    def test_time_manager_uses_custom_backend(self):
        class FixedBackend(PerfCounterTimingBackend):
            def get_ticks(self):
                return 1234

        manager = TimeManager(FixedBackend())
        self.assertEqual(manager.get_ticks(), 1234)
        clock = manager.get_clock()
        self.assertIsInstance(clock, GameClock)
        self.assertIs(manager.get_clock(), clock)

    def test_fps_counter_after_ticks(self):
        clock = GameClock(PerfCounterTimingBackend())
        clock.tick(0)
        clock.tick(0)
        self.assertGreaterEqual(clock.get_fps(), 0.0)
        self.assertGreaterEqual(clock.get_time(), 0)


if __name__ == "__main__":
    unittest.main()

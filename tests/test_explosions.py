"""Tests for explosion helpers, including the big-blast sound window."""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from explosions import (
    compute_explosion_active_cells,
    count_unique_explosion_tiles,
    crossed_big_explosion_threshold,
    prune_explosion_events,
)
from bm_params import BIG_EXPLOSION_TILE_THRESHOLD, BIG_EXPLOSION_WINDOW_MS


class TestBigExplosionWindow(unittest.TestCase):
    def test_defaults_are_forty_tiles_in_500ms(self):
        self.assertEqual(BIG_EXPLOSION_TILE_THRESHOLD, 40)
        self.assertEqual(BIG_EXPLOSION_WINDOW_MS, 500)
    def test_single_large_explosion_crosses_threshold(self):
        over = BIG_EXPLOSION_TILE_THRESHOLD + 1
        cells = [(i, 0) for i in range(over)]
        events = [(1000, cells)]
        self.assertEqual(count_unique_explosion_tiles(events, 1000, 1000), over)
        self.assertTrue(crossed_big_explosion_threshold(False, over, BIG_EXPLOSION_TILE_THRESHOLD))

    def test_exactly_threshold_does_not_trigger(self):
        cells = [(i, 0) for i in range(BIG_EXPLOSION_TILE_THRESHOLD)]
        events = [(1000, cells)]
        self.assertEqual(count_unique_explosion_tiles(events, 1000, 1000), BIG_EXPLOSION_TILE_THRESHOLD)
        self.assertFalse(crossed_big_explosion_threshold(False, BIG_EXPLOSION_TILE_THRESHOLD, BIG_EXPLOSION_TILE_THRESHOLD))

    def test_tiles_outside_window_are_ignored(self):
        events = [
            (0, [(x, 0) for x in range(BIG_EXPLOSION_TILE_THRESHOLD + 1)]),
            (1500, [(0, 1)]),
        ]
        self.assertEqual(count_unique_explosion_tiles(events, 1500, 1000), 1)

    def test_overlapping_tiles_count_once(self):
        events = [
            (1000, [(0, 0), (1, 0), (2, 0)]),
            (1100, [(2, 0), (3, 0)]),
        ]
        self.assertEqual(count_unique_explosion_tiles(events, 1100, 1000), 4)

    def test_chain_in_window_crosses_threshold(self):
        first = [(i, 0) for i in range(BIG_EXPLOSION_TILE_THRESHOLD)]
        second = [(i, 1) for i in range(BIG_EXPLOSION_TILE_THRESHOLD)]
        events = [(1000, first), (1400, second)]
        count = count_unique_explosion_tiles(events, 1400, 1000)
        self.assertEqual(count, BIG_EXPLOSION_TILE_THRESHOLD * 2)
        self.assertTrue(crossed_big_explosion_threshold(False, count, BIG_EXPLOSION_TILE_THRESHOLD))

    def test_does_not_retrigger_while_still_over(self):
        self.assertFalse(crossed_big_explosion_threshold(True, BIG_EXPLOSION_TILE_THRESHOLD + 10, BIG_EXPLOSION_TILE_THRESHOLD))

    def test_retriggers_after_window_drops_below(self):
        old = [(0, [(x, 0) for x in range(BIG_EXPLOSION_TILE_THRESHOLD + 1)])]
        pruned = prune_explosion_events(old, 2000, 1000)
        self.assertEqual(pruned, [])
        aged = count_unique_explosion_tiles(pruned, 2000, 1000)
        self.assertEqual(aged, 0)
        was_over = aged > BIG_EXPLOSION_TILE_THRESHOLD
        fresh = [(2000, [(x, 1) for x in range(BIG_EXPLOSION_TILE_THRESHOLD + 1)])]
        count = count_unique_explosion_tiles(fresh, 2000, 1000)
        self.assertTrue(crossed_big_explosion_threshold(was_over, count, BIG_EXPLOSION_TILE_THRESHOLD))

    def test_empty_events_count_zero(self):
        self.assertEqual(count_unique_explosion_tiles([], 1000, 1000), 0)

    def test_active_cells_grow_then_shrink(self):
        class FakeExplosion:
            def __init__(self):
                self.start_time = 0
                self.cells = [(2, 2), (2, 1), (2, 0), (2, 3), (1, 2), (3, 2)]

        early = compute_explosion_active_cells(FakeExplosion(), 1, 400)
        self.assertEqual(early, [(2, 2)])
        mid = compute_explosion_active_cells(FakeExplosion(), 200, 400)
        self.assertGreater(len(mid), len(early))
        self.assertIn((2, 2), mid)
        done = compute_explosion_active_cells(FakeExplosion(), 400, 400)
        self.assertEqual(done, [])

    def test_prune_keeps_recent_only(self):
        events = [(0, [(0, 0)]), (900, [(1, 1)])]
        pruned = prune_explosion_events(events, 1000, 200)
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0][0], 900)


if __name__ == "__main__":
    unittest.main()

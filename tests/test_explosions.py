"""Tests for explosion helpers, including the big-blast sound window."""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from explosions import (
    compute_explosion_active_cells,
    count_unique_explosion_tiles,
    crossed_big_explosion_threshold,
    explosion_cell_rect,
    explosion_player_radius,
    is_player_in_planned_blast,
    planned_blast_cells,
    prune_explosion_events,
)
from bm_params import (
    BIG_EXPLOSION_TILE_THRESHOLD,
    BIG_EXPLOSION_VOLUME,
    BIG_EXPLOSION_WINDOW_MS,
    CELL_SIZE,
    DESTRUCTIBLE,
    EMPTY,
    EXPLOSION_COLLISION_SCALE,
    EXPLOSION_PLAYER_HIT_SCALE,
    INDESTRUCTIBLE,
    SCARED_BLAST_MAX_CELLS,
)


class TestBigExplosionWindow(unittest.TestCase):
    def test_defaults_are_50_tiles_in_700ms(self):
        self.assertEqual(BIG_EXPLOSION_TILE_THRESHOLD, 100)
        self.assertEqual(BIG_EXPLOSION_WINDOW_MS, 700)
        self.assertEqual(BIG_EXPLOSION_VOLUME, 1.0)

    def test_single_large_explosion_crosses_threshold(self):
        cells = [(i, 0) for i in range(BIG_EXPLOSION_TILE_THRESHOLD)]
        events = [(1000, cells)]
        self.assertEqual(count_unique_explosion_tiles(events, 1000, 1000), BIG_EXPLOSION_TILE_THRESHOLD)
        self.assertTrue(crossed_big_explosion_threshold(False, BIG_EXPLOSION_TILE_THRESHOLD, BIG_EXPLOSION_TILE_THRESHOLD))
        self.assertFalse(crossed_big_explosion_threshold(False, BIG_EXPLOSION_TILE_THRESHOLD - 1, BIG_EXPLOSION_TILE_THRESHOLD))

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
        was_over = aged >= BIG_EXPLOSION_TILE_THRESHOLD
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


class PlannedBlastAndHitboxTests(unittest.TestCase):
    def _open_board(self, size=9):
        board = [[EMPTY for _ in range(size)] for _ in range(size)]
        for y in range(size):
            for x in range(size):
                if x == 0 or y == 0 or x == size - 1 or y == size - 1:
                    board[y][x] = INDESTRUCTIBLE
        return board

    def test_planned_blast_stops_at_wall_and_includes_soft_block(self):
        board = self._open_board()
        board[3][5] = INDESTRUCTIBLE
        board[5][3] = DESTRUCTIBLE
        cells = planned_blast_cells(3, 3, 4, board, 9, 9)
        self.assertIn((3, 3), cells)
        self.assertIn((4, 3), cells)
        self.assertNotIn((5, 3), cells)
        self.assertIn((3, 5), cells)
        self.assertNotIn((3, 6), cells)

    def test_scared_range_is_capped_at_five(self):
        board = self._open_board(13)
        cells = planned_blast_cells(1, 1, 10, board, 13, 13, max_range=SCARED_BLAST_MAX_CELLS)
        self.assertIn((6, 1), cells)
        self.assertNotIn((7, 1), cells)

    def test_diagonal_cell_is_not_in_planned_blast(self):
        board = self._open_board()

        class Bomb:
            x, y, fire_power = 3, 3, 2

        self.assertTrue(is_player_in_planned_blast(3, 3, [Bomb()], board, 9, 9))
        self.assertTrue(is_player_in_planned_blast(5, 3, [Bomb()], board, 9, 9))
        self.assertFalse(is_player_in_planned_blast(4, 4, [Bomb()], board, 9, 9))

    def test_explosion_hitbox_is_inner_70_percent(self):
        x, y, w, h = explosion_cell_rect(3, 2, CELL_SIZE, EXPLOSION_COLLISION_SCALE)
        self.assertEqual(EXPLOSION_COLLISION_SCALE, 0.7)
        self.assertAlmostEqual(w, 70)
        self.assertAlmostEqual(h, 70)
        self.assertAlmostEqual(x, 315)
        self.assertAlmostEqual(y, 215)
        self.assertAlmostEqual(explosion_player_radius(CELL_SIZE, EXPLOSION_PLAYER_HIT_SCALE), 15.0)

    def test_flame_arm_stops_at_last_cell_center(self):
        from explosions import explosion_arm_pixel_length
        reach = 3
        flame = explosion_arm_pixel_length(1.0, reach, CELL_SIZE)
        self.assertAlmostEqual(flame, reach * CELL_SIZE)
        self.assertEqual(explosion_arm_pixel_length(1.0, 0, CELL_SIZE), 0.0)

    def test_last_cell_kill_box_stops_at_center(self):
        from explosions import explosion_cell_rect, explosion_tip_clip
        cells = [(3, 3), (4, 3), (5, 3)]
        clip = explosion_tip_clip(3, 3, 5, 3, cells)
        self.assertEqual(clip, "right")
        x, y, w, h = explosion_cell_rect(5, 3, CELL_SIZE, EXPLOSION_COLLISION_SCALE, clip_outward=clip)
        self.assertAlmostEqual(x + w, 5 * CELL_SIZE + CELL_SIZE / 2.0)
        cx, cy, cw, ch = explosion_cell_rect(3, 3, CELL_SIZE, EXPLOSION_COLLISION_SCALE)
        self.assertAlmostEqual(cw, 70)

    def test_blast_arm_cache_is_bounded(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame
        pygame.init()
        from bm_drawing import _BLAST_ARM_CACHE, _BLAST_ARM_CACHE_MAX, _get_blast_arm_surface

        _BLAST_ARM_CACHE.clear()
        image = pygame.Surface((16, 8), pygame.SRCALPHA)
        image.fill((255, 80, 0, 255))
        for direction in ("left", "right", "up", "down"):
            for length in range(1, 500, 3):
                _get_blast_arm_surface(image, length, 40, direction)
        self.assertGreater(len(_BLAST_ARM_CACHE), 0)
        self.assertLessEqual(len(_BLAST_ARM_CACHE), _BLAST_ARM_CACHE_MAX)


if __name__ == "__main__":
    unittest.main()

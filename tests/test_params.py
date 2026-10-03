import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import (
    BOSS_CRUSHING_WALLS_DELAY,
    BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS,
    CRUSHING_WALLS_2P_DELAY,
    CRUSHING_WALLS_DELAY,
    CRUSHING_WALLS_GROWTH_INTERVAL_MS,
    CRUSHING_WALLS_MIN_START_S,
    CRUSHING_WALLS_CROWDED_TIME_MULTIPLIER,
    CRUSHING_WALLS_STALE_TIME_MULTIPLIER,
    CRUSHING_WALLS_STALE_WALL_FRACTION,
    GRID_SIZE_1_2,
    GRID_SIZE_2_PLAYERS,
    GRID_SIZE_3_4,
    GRID_SIZE_5_6,
    GRID_SIZE_7_8,
    GRID_SIZE_BOSS,
    GRID_SIZE_DEFAULT,
    GRID_SIZE_OFFSETS,
    QUAD_DAMAGE_DELAY,
    QUAD_DAMAGE_PROBABILITY,
    clamp_odd_grid,
    default_grid_size,
    get_grid_size,
    grid_size_choices,
)
import bm_constants


class GridSizeTests(unittest.TestCase):
    def test_default_and_variants(self):
        self.assertEqual(get_grid_size(), GRID_SIZE_DEFAULT)
        self.assertEqual(GRID_SIZE_DEFAULT, 15)
        self.assertEqual(get_grid_size(1), GRID_SIZE_1_2)
        self.assertEqual(get_grid_size(2), GRID_SIZE_2_PLAYERS)
        self.assertEqual(GRID_SIZE_2_PLAYERS, 15)
        self.assertEqual(get_grid_size(3), GRID_SIZE_3_4)
        self.assertEqual(get_grid_size(4), GRID_SIZE_3_4)
        self.assertEqual(GRID_SIZE_3_4, 17)
        self.assertEqual(get_grid_size(5), GRID_SIZE_5_6)
        self.assertEqual(get_grid_size(6), GRID_SIZE_5_6)
        self.assertEqual(GRID_SIZE_5_6, 19)
        self.assertEqual(get_grid_size(7), GRID_SIZE_7_8)
        self.assertEqual(get_grid_size(8), GRID_SIZE_7_8)
        self.assertEqual(GRID_SIZE_7_8, 21)
        self.assertGreater(GRID_SIZE_3_4, GRID_SIZE_1_2)
        self.assertGreater(GRID_SIZE_5_6, GRID_SIZE_3_4)
        self.assertGreater(GRID_SIZE_7_8, GRID_SIZE_5_6)
        self.assertEqual(get_grid_size(1, is_boss_fight=True), GRID_SIZE_BOSS)
        self.assertEqual(get_grid_size(8, is_boss_fight=True), GRID_SIZE_BOSS)
        self.assertEqual(GRID_SIZE_BOSS, 15)
        self.assertEqual(GRID_SIZE_BOSS, GRID_SIZE_2_PLAYERS)

    def test_lobby_offset_shifts_default_by_even_steps(self):
        self.assertEqual(GRID_SIZE_OFFSETS, (-6, -4, -2, 0, 2, 4, 6))
        self.assertEqual(get_grid_size(3, offset=0), 17)
        self.assertEqual(get_grid_size(3, offset=2), 19)
        self.assertEqual(get_grid_size(3, offset=-2), 15)
        self.assertEqual(get_grid_size(3, offset=6), 23)
        self.assertEqual(get_grid_size(2, offset=-6), 9)
        self.assertEqual(grid_size_choices(4), [11, 13, 15, 17, 19, 21, 23])
        self.assertEqual(get_grid_size(8, is_boss_fight=True, offset=6), GRID_SIZE_BOSS)
        self.assertEqual(clamp_odd_grid(16), 17)
        self.assertEqual(default_grid_size(9), GRID_SIZE_7_8)

    def test_trophy_threshold_default_is_three(self):
        from bm_params import TROPHY_WIN_THRESHOLD
        self.assertEqual(TROPHY_WIN_THRESHOLD, 3)

    def test_odd_sizes(self):
        for count in (None, 1, 2, 3, 4, 5, 6, 7, 8):
            self.assertEqual(get_grid_size(count) % 2, 1)
            for offset in GRID_SIZE_OFFSETS:
                self.assertEqual(get_grid_size(count, offset=offset) % 2, 1)

    def test_constants_shim_reexports_params(self):
        self.assertEqual(bm_constants.EMPTY, 0)
        self.assertEqual(bm_constants.INDESTRUCTIBLE, 1)
        self.assertEqual(bm_constants.DESTRUCTIBLE, 2)
        self.assertEqual(bm_constants.get_grid_size(2), GRID_SIZE_2_PLAYERS)

    def test_crushing_walls_timing(self):
        self.assertEqual(CRUSHING_WALLS_GROWTH_INTERVAL_MS, 800)
        self.assertEqual(CRUSHING_WALLS_2P_DELAY, 120)
        self.assertEqual(CRUSHING_WALLS_DELAY, 120)
        self.assertEqual(CRUSHING_WALLS_MIN_START_S, 120)
        self.assertGreaterEqual(CRUSHING_WALLS_DELAY, CRUSHING_WALLS_MIN_START_S)
        self.assertGreaterEqual(CRUSHING_WALLS_2P_DELAY, CRUSHING_WALLS_MIN_START_S)
        self.assertEqual(BOSS_CRUSHING_WALLS_DELAY, 120)
        self.assertGreaterEqual(BOSS_CRUSHING_WALLS_DELAY, CRUSHING_WALLS_MIN_START_S)
        self.assertEqual(BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS, 1200)
        self.assertEqual(CRUSHING_WALLS_STALE_WALL_FRACTION, 0.15)
        self.assertEqual(CRUSHING_WALLS_CROWDED_TIME_MULTIPLIER, 1.5)
        self.assertEqual(CRUSHING_WALLS_STALE_TIME_MULTIPLIER, 2)

    def test_quad_damage_delay_is_sixty_seconds(self):
        self.assertEqual(QUAD_DAMAGE_DELAY, 60)
        self.assertEqual(QUAD_DAMAGE_PROBABILITY, 0.000675)

    def test_explosion_hitbox_and_scared_range(self):
        from bm_params import (
            EXPLOSION_COLLISION_SCALE,
            EXPLOSION_PLAYER_HIT_SCALE,
            SCARED_BLAST_MAX_CELLS,
        )
        self.assertEqual(EXPLOSION_COLLISION_SCALE, 0.7)
        self.assertEqual(EXPLOSION_PLAYER_HIT_SCALE, 0.30)
        self.assertEqual(SCARED_BLAST_MAX_CELLS, 5)

    def test_match_clock_counts_whole_seconds(self):
        from bm_params import format_crushing_wall_start, format_match_clock
        self.assertEqual(format_match_clock(0), "0")
        self.assertEqual(format_match_clock(65000), "65")
        self.assertEqual(format_match_clock(-500), "0")
        self.assertEqual(format_crushing_wall_start(180, 360), "(cw start: 180s/360s)")


if __name__ == "__main__":
    unittest.main()

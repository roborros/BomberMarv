import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import (
    CRUSHING_WALLS_2P_DELAY,
    CRUSHING_WALLS_DELAY,
    CRUSHING_WALLS_GROWTH_INTERVAL_MS,
    GRID_SIZE_2_PLAYERS,
    GRID_SIZE_5_6,
    GRID_SIZE_7_8,
    GRID_SIZE_BOSS,
    GRID_SIZE_DEFAULT,
    get_grid_size,
)
import bm_constants


class GridSizeTests(unittest.TestCase):
    def test_default_and_variants(self):
        self.assertEqual(get_grid_size(), GRID_SIZE_DEFAULT)
        self.assertEqual(GRID_SIZE_DEFAULT, 19)
        self.assertEqual(get_grid_size(2), GRID_SIZE_2_PLAYERS)
        self.assertEqual(GRID_SIZE_2_PLAYERS, 17)
        self.assertEqual(get_grid_size(3), GRID_SIZE_DEFAULT)
        self.assertEqual(get_grid_size(4), GRID_SIZE_DEFAULT)
        self.assertEqual(get_grid_size(5), GRID_SIZE_5_6)
        self.assertEqual(get_grid_size(6), GRID_SIZE_5_6)
        self.assertEqual(GRID_SIZE_5_6, 21)
        self.assertEqual(get_grid_size(7), GRID_SIZE_7_8)
        self.assertEqual(get_grid_size(8), GRID_SIZE_7_8)
        self.assertEqual(GRID_SIZE_7_8, 23)
        self.assertGreater(GRID_SIZE_5_6, GRID_SIZE_DEFAULT)
        self.assertGreater(GRID_SIZE_7_8, GRID_SIZE_5_6)
        self.assertEqual(get_grid_size(1, is_boss_fight=True), GRID_SIZE_BOSS)
        self.assertEqual(get_grid_size(8, is_boss_fight=True), GRID_SIZE_BOSS)
        self.assertEqual(GRID_SIZE_BOSS, 17)
        self.assertEqual(GRID_SIZE_BOSS, GRID_SIZE_2_PLAYERS)

    def test_trophy_threshold_default_is_three(self):
        from bm_params import TROPHY_WIN_THRESHOLD
        self.assertEqual(TROPHY_WIN_THRESHOLD, 3)

    def test_odd_sizes(self):
        for count in (None, 1, 2, 3, 4, 5, 6, 7, 8):
            self.assertEqual(get_grid_size(count) % 2, 1)

    def test_constants_shim_reexports_params(self):
        self.assertEqual(bm_constants.EMPTY, 0)
        self.assertEqual(bm_constants.INDESTRUCTIBLE, 1)
        self.assertEqual(bm_constants.DESTRUCTIBLE, 2)
        self.assertEqual(bm_constants.get_grid_size(2), GRID_SIZE_2_PLAYERS)

    def test_crushing_walls_timing(self):
        self.assertEqual(CRUSHING_WALLS_GROWTH_INTERVAL_MS, 600)
        self.assertEqual(CRUSHING_WALLS_2P_DELAY, 180)
        self.assertEqual(CRUSHING_WALLS_DELAY, 3)

    def test_explosion_hitbox_and_scared_range(self):
        from bm_params import (
            EXPLOSION_COLLISION_SCALE,
            EXPLOSION_PLAYER_HIT_SCALE,
            SCARED_BLAST_MAX_CELLS,
        )
        self.assertEqual(EXPLOSION_COLLISION_SCALE, 0.5)
        self.assertEqual(EXPLOSION_PLAYER_HIT_SCALE, 0.30)
        self.assertEqual(SCARED_BLAST_MAX_CELLS, 5)


if __name__ == "__main__":
    unittest.main()

import os
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import DESTRUCTIBLE, EMPTY, INDESTRUCTIBLE
from lib_grid import clear_safe_zone, generate_maze, get_random_L_pattern, spawn_slots


class GridTests(unittest.TestCase):
    def test_generate_maze_has_indestructible_border(self):
        board = generate_maze(9, 9)
        self.assertEqual(len(board), 9)
        self.assertEqual(len(board[0]), 9)
        for x in range(9):
            self.assertEqual(board[0][x], INDESTRUCTIBLE)
            self.assertEqual(board[8][x], INDESTRUCTIBLE)
        for y in range(9):
            self.assertEqual(board[y][0], INDESTRUCTIBLE)
            self.assertEqual(board[y][8], INDESTRUCTIBLE)

    def test_even_even_interior_is_pillar(self):
        board = generate_maze(9, 9)
        self.assertEqual(board[2][2], INDESTRUCTIBLE)
        self.assertEqual(board[4][4], INDESTRUCTIBLE)

    def test_clear_safe_zone_clears_destructible_only(self):
        board = [
            [INDESTRUCTIBLE, INDESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, DESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, INDESTRUCTIBLE, INDESTRUCTIBLE],
        ]
        clear_safe_zone(board, 1, 1, [(0, 0)])
        self.assertEqual(board[1][1], EMPTY)
        self.assertEqual(board[0][0], INDESTRUCTIBLE)

    def test_clear_safe_zone_ignores_out_of_bounds(self):
        board = [[DESTRUCTIBLE]]
        clear_safe_zone(board, 0, 0, [(-1, 0), (1, 0), (0, 0)])
        self.assertEqual(board[0][0], EMPTY)

    def test_l_pattern_has_three_cells(self):
        with patch("lib_grid.random.choice", side_effect=lambda seq: seq[0]):
            pattern = get_random_L_pattern()
        self.assertEqual(len(pattern), 3)
        self.assertIn((0, 0), pattern)

    def test_maze_respects_requested_size(self):
        random.seed(1)
        board = generate_maze(7, 11)
        self.assertEqual(len(board), 11)
        self.assertEqual(len(board[0]), 7)

    def test_spawn_slots_eight_unique_walkable(self):
        for size in (9, 15, 17, 19, 21, 23, 27):
            slots = spawn_slots(size, size, 8)
            self.assertEqual(len(slots), 8)
            cells = [(x, y) for x, y, _ in slots]
            self.assertEqual(len(set(cells)), 8)
            for x, y, offsets in slots:
                self.assertFalse(x % 2 == 0 and y % 2 == 0)
                self.assertGreaterEqual(x, 1)
                self.assertLessEqual(x, size - 2)
                self.assertIn((0, 0), offsets)

    def test_extra_players_use_interior_mids(self):
        slots = spawn_slots(21, 21, 8)
        fifth = (slots[4][0], slots[4][1])
        sixth = (slots[5][0], slots[5][1])
        seventh = (slots[6][0], slots[6][1])
        eighth = (slots[7][0], slots[7][1])
        self.assertEqual(fifth, (5, 10))
        self.assertEqual(sixth, (15, 10))
        self.assertEqual(seventh, (10, 5))
        self.assertEqual(eighth, (10, 15))
        for x, y in (fifth, sixth, seventh, eighth):
            self.assertNotEqual(x, 1)
            self.assertNotEqual(x, 19)
            self.assertNotEqual(y, 1)
            self.assertNotEqual(y, 19)


if __name__ == "__main__":
    unittest.main()

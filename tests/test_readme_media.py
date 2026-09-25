"""README GIF placements must stay on open floor, not visually on walls."""
from __future__ import annotations

import importlib.util
import os
import unittest

from helpers import cell_center, silence_sounds
from bm_params import CELL_SIZE, DESTRUCTIBLE, EMPTY, INDESTRUCTIBLE


def _load_capture():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "tools", "capture_readme_gifs.py")
    spec = importlib.util.spec_from_file_location("capture_readme_gifs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReadmeMediaPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        silence_sounds()
        cls.cap = _load_capture()

    def test_open_neighborhood_rejects_bomb_against_a_wall(self):
        board = self.cap.empty_arena(9, extra_destructible=((4, 3),))
        with self.assertRaises(RuntimeError):
            self.cap.require_open_neighborhood(board, [(5, 3)], "bomb")

    def test_open_neighborhood_allows_interior_floor(self):
        board = self.cap.empty_arena(9, extra_pillars=self.cap.classic_pillars(9))
        self.cap.require_open_neighborhood(board, [(3, 3), (5, 5)], "bomb")

    def test_classic_pillars_are_even_cells(self):
        pillars = self.cap.classic_pillars(9)
        self.assertIn((2, 2), pillars)
        self.assertNotIn((3, 3), pillars)
        for x, y in pillars:
            self.assertEqual(x % 2, 0)
            self.assertEqual(y % 2, 0)

    def test_centered_corner_player_does_not_cover_border(self):
        game = self.cap._playing_game(self.cap.empty_arena(9))
        player = self.cap._local_player(1, 1, "Marv", (100, 150, 200))
        game.players = [player]
        self.cap.assert_sprites_clear_of_walls(game, "corner")

    def test_player_hugging_a_pillar_is_rejected(self):
        game = self.cap._playing_game(self.cap.empty_arena(9, extra_pillars=((4, 4),)))
        player = self.cap._local_player(3, 4, "Marv", (100, 150, 200))
        player.pos[0] = 4 * CELL_SIZE - 8
        player.pos[1] = 4 * CELL_SIZE + CELL_SIZE / 2
        game.players = [player]
        with self.assertRaises(RuntimeError):
            self.cap.assert_sprites_clear_of_walls(game, "hug")

    def test_gameplay_demo_bombs_are_not_against_walls(self):
        board = self.cap.empty_arena(
            9,
            extra_destructible=((3, 5), (5, 3)),
            extra_pillars=self.cap.classic_pillars(9),
        )
        self.assertEqual(board[3][3], EMPTY)
        self.assertEqual(board[2][2], INDESTRUCTIBLE)
        self.assertEqual(board[5][3], DESTRUCTIBLE)
        self.cap.require_open_neighborhood(board, [(3, 3), (5, 5)], "gameplay")
        cx, cy = cell_center(3, 3)
        self.assertEqual(cx, 3 * CELL_SIZE + CELL_SIZE // 2)
        self.assertEqual(cy, 3 * CELL_SIZE + CELL_SIZE // 2)


if __name__ == "__main__":
    unittest.main()

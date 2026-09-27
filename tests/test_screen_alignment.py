"""Alignment checks read pixels from saved screenshots, not from layout math."""

import os
import sys
import unittest

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_classes import Game
from bm_drawing import draw_boss_result_screen, draw_champion_screen
from helpers import silence_sounds

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "layout_preview")
NAME = (255, 0, 220)
WIN_GREEN = (88, 220, 120)
WIN_GOLD = (255, 214, 90)


def _shot(surface, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    pygame.image.save(surface, path)
    loaded = pygame.image.load(path)
    return pygame.surfarray.array3d(loaded)


def _near(arr, color, tol):
    diff = np.abs(arr.astype(np.int16) - np.array(color, dtype=np.int16)).sum(axis=2)
    return diff <= tol


def _bbox(mask):
    xs, ys = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _human(game, name):
    human = next(p for p in game.players if not getattr(p, "is_ai", False))
    human.name = name
    human.color = NAME
    for i, player in enumerate(game.players):
        if player is human:
            continue
        player.color = (40, 90, 210) if i % 2 == 0 else (210, 120, 40)
    return human


class ScreenshotAlignmentTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        pygame.font.init()

    def _champion(self, size, name, filename):
        game = Game()
        human = _human(game, name)
        surface = pygame.Surface(size)
        draw_champion_screen(surface, human, game.players, game)
        return _shot(surface, filename)

    def _assert_name_clears_card(self, arr, label, heading_is_name=True):
        width = arr.shape[0]
        name_ink = (arr[:, :, 0] > 170) & (arr[:, :, 2] > 150) & (arr[:, :, 1] < 80)
        height = arr.shape[1]
        border = _near(arr, (196, 209, 228), 22)
        border[:, int(height * 0.42):] = False
        border[: int(width * 0.60), :] = False
        box = _bbox(border)
        fill = _near(arr, (24, 28, 38), 8)
        self.assertIsNotNone(box, f"{label}: boss card is missing from the screenshot")
        x0, y0, x1, y1 = box
        self.assertGreater(x0, width * 0.5, label)
        self.assertLess(y0, 48, label)
        self.assertGreater(int(name_ink.sum()), 40, f"{label}: champion name was not drawn")
        interior = np.zeros_like(fill)
        interior[x0 + 3:x1 - 2, y0 + 3:y1 - 2] = True
        self.assertFalse(bool(np.any(name_ink & interior)), f"{label}: name pixels sit on the card")
        in_column = name_ink[x0:x1 + 1, :]
        ys = np.where(in_column)[1]
        if len(ys):
            self.assertGreaterEqual(int(ys.min()), y1 + 8, f"{label}: name runs under the card")
        if heading_is_name:
            heading = name_ink.copy()
            heading[:, int(arr.shape[1] * 0.55):] = False
            self.assertGreater(int(heading.sum()), 20, f"{label}: heading is missing above the table")
            heading_top = int(np.where(heading)[1].min())
            self.assertLessEqual(y1 + 8, heading_top, f"{label}: card bottom {y1} meets the name at {heading_top}")
        inset = interior.copy()
        inset[:x0 + 8, :] = False
        inset[x1 - 8:, :] = False
        inset[:, :y0 + 8] = False
        inset[:, y1 - 8:] = False
        light = (arr[:, :, 0] > 180) & (arr[:, :, 1] > 180) & (arr[:, :, 2] > 185)
        self.assertGreater(int((light & inset).sum()), 30, f"{label}: card text is missing or clipped to the edge")

    def test_champion_card_stays_off_the_name(self):
        arr = self._champion((1280, 800), "Nova", "champion.png")
        self._assert_name_clears_card(arr, "champion")

    def test_long_champion_name_stays_clear_on_a_short_screen(self):
        arr = self._champion((1280, 720), "VeryLongChampionName", "champion_long.png")
        self._assert_name_clears_card(arr, "long name")

    def test_bombertom_card_stays_off_the_win_line(self):
        game = Game()
        human = _human(game, "Nova")
        game.boss_advance = "brabi"
        game.boss_fight_winner = human
        game.game_state = "boss_result"
        surface = pygame.Surface((1280, 800))
        draw_boss_result_screen(surface, human, game.players, game)
        arr = _shot(surface, "bombertom.png")
        self._assert_name_clears_card(arr, "BomberTom invite", heading_is_name=False)
        green = _near(arr, WIN_GREEN, 55)
        border = _near(arr, (196, 209, 228), 22)
        border[:, int(arr.shape[1] * 0.42):] = False
        border[: int(arr.shape[0] * 0.60), :] = False
        _x0, _y0, _x1, y1 = _bbox(border)
        below = green.copy()
        below[:, : y1 + 8] = False
        self.assertGreater(int(below.sum()), 20, "You win is covered or missing under the BomberTom card")

    def test_marv_killer_banner_stays_off_the_win_line(self):
        game = Game()
        human = _human(game, "Nova")
        game.boss_stage = "brabi"
        game.boss_advance = "lobby"
        game.boss_fight_winner = human
        game.game_state = "boss_result"
        surface = pygame.Surface((1280, 800))
        draw_boss_result_screen(surface, human, game.players, game)
        arr = _shot(surface, "marv_killer.png")
        banner = _near(arr, (28, 20, 8), 12)
        banner[:, int(arr.shape[1] * 0.42):] = False
        box = _bbox(banner)
        self.assertIsNotNone(box, "MarvKiller banner is missing from the screenshot")
        x0, y0, x1, y1 = box
        self.assertLess(y0, 48)
        self.assertGreater(x1 - x0, 300)
        name_ink = (arr[:, :, 0] > 170) & (arr[:, :, 2] > 150) & (arr[:, :, 1] < 80)
        self.assertFalse(bool(np.any(name_ink & banner)), "player name sits on the MarvKiller banner")
        gold = _near(arr, WIN_GOLD, 50)
        below = gold.copy()
        below[:, : y1 + 8] = False
        self.assertGreater(int(below.sum()), 15, "You win is covered or missing under the MarvKiller banner")
        self.assertLess(x0, arr.shape[0] * 0.5)
        self.assertGreater(x1, arr.shape[0] * 0.5)


if __name__ == "__main__":
    unittest.main()

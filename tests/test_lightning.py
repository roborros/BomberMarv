import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_classes import Explosion
from lightning import bolt_polyline, is_boss_lightning_owner
import random


class LightningTests(unittest.TestCase):
    def test_boss_blast_is_lightning_and_a_normal_blast_is_not(self):
        boss = types.SimpleNamespace(ai_role="boss", global_id=9)
        uber = types.SimpleNamespace(ai_role="uber", global_id=8)
        human = types.SimpleNamespace(ai_role="", global_id=1)
        self.assertTrue(is_boss_lightning_owner(boss))
        boss_exp = Explosion([(3, 3), (3, 2), (4, 3)], 10, owner=boss)
        uber_exp = Explosion([(1, 1)], 10, owner=uber)
        human_exp = Explosion([(1, 1)], 10, owner=human)
        plain = Explosion([(1, 1)], 10)
        self.assertTrue(boss_exp.lightning)
        self.assertTrue(uber_exp.lightning)
        self.assertFalse(human_exp.lightning)
        self.assertFalse(plain.lightning)
        self.assertTrue(boss_exp.to_dict()["lightning"])
        self.assertFalse(human_exp.to_dict()["lightning"])
        self.assertEqual(boss_exp.lightning_style, "marv")
        self.assertEqual(uber_exp.lightning_style, "tom")
        self.assertEqual(human_exp.lightning_style, "")
        self.assertEqual(boss_exp.to_dict()["lightning_style"], "marv")
        self.assertEqual(uber_exp.to_dict()["lightning_style"], "tom")

    def test_bolt_stays_inside_the_corridor(self):
        rng = random.Random(4)
        amplitude = 16
        lane = 20
        points = bolt_polyline((0, 0), (400, 0), rng, 4, amplitude, lane)
        self.assertGreaterEqual(len(points), 4)
        for x, y in points:
            self.assertGreaterEqual(x, -30)
            self.assertLessEqual(x, 430)
            self.assertLess(abs(y), amplitude * 3 + abs(lane) + 8)

    def test_marv_bolts_read_blue_and_tom_bolts_read_green(self):
        import pygame
        from lightning import draw_lightning_cross
        pygame.init()
        arms = ((0, -1, 180), (0, 1, 140), (-1, 0, 140), (1, 0, 220))

        def tint(style):
            surf = pygame.Surface((420, 420))
            surf.fill((12, 14, 18))
            draw_lightning_cross(surf, (210, 210), arms, 80, 180, seed=17, alpha_scale=1, style=style)
            arr = pygame.surfarray.array3d(surf).astype("int16")
            spread = arr.max(axis=2) - arr.min(axis=2)
            ink = spread > 28
            self.assertGreater(int(ink.sum()), 200)
            return arr[ink].mean(axis=0)

        marv = tint("marv")
        tom = tint("tom")
        self.assertGreater(marv[2], marv[0] + 8)
        self.assertGreater(marv[2], marv[1] + 4)
        self.assertGreater(tom[1], tom[0] + 8)
        self.assertGreater(tom[1], tom[2] + 4)

    def test_replay_keeps_the_bolt_tint(self):
        from replay import hydrate_replay_snapshot
        frame = hydrate_replay_snapshot({
            "explosions": [{"cells": [[2, 2], [3, 2]], "start": 40, "qd": False, "bolt": True, "tint": "tom"}],
        })
        bolt = frame["explosions"][0]
        self.assertTrue(bolt.lightning)
        self.assertEqual(bolt.lightning_style, "tom")


if __name__ == "__main__":
    unittest.main()

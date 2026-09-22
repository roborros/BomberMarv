"""Contract tests for the CPU decision rules.

Covers the danger map, plant gates, personality goals, and a short movement
sim that a bot standing on its own bomb actually leaves before the fuse.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import open_board, silence_sounds

from ai_controller import (
    AI_PERSONALITIES,
    BOMB_COOLDOWN_MS,
    BOSS_BOMB_COOLDOWN_MS,
    BOSS_POWERUP_HUNT_LIMIT,
    BOSS_SAFETY_MARGIN_MS,
    CAUTIOUS_BOMB_COOLDOWN_MS,
    CAUTIOUS_POWERUP_HUNT_LIMIT,
    CAUTIOUS_SAFETY_MARGIN_MS,
    CRAZY_BOMB_COOLDOWN_MS,
    CRAZY_POWERUP_HUNT_LIMIT,
    CRAZY_SAFETY_MARGIN_MS,
    CPU_SAFETY_MARGIN_MS,
    POWERUP_HUNT_LIMIT,
    _bomb_cooldown_ms,
    _danger_times,
    _max_live_bombs,
    _must_flee,
    _powerup_limit,
    _safe_to_stay,
    _safety_margin_ms,
    ai_personality,
    reset_ai_memory,
    think_ai,
)
from bm_classes import Bomb, Player
from bm_params import BOMB_TIMER, DESTRUCTIBLE, EMPTY, EXPLOSION_DURATION, INDESTRUCTIBLE

silence_sounds()


def _bot(x, y, personality="normal", fire_power=1, bomb_capacity=1, active_bombs=0):
    player = Player(x, y, (220, 80, 40), None, personality)
    player.is_ai = True
    player.is_local = False
    player.fire_power = fire_power
    player.bomb_capacity = bomb_capacity
    player.active_bombs = active_bombs
    if personality == "boss":
        player.ai_role = "boss"
        player.ai_personality = "boss"
    else:
        player.ai_role = "cpu"
        player.ai_personality = personality
    reset_ai_memory(player)
    return player


def _arena(board, players, bombs=None, explosions=None, powerups=None, now=0):
    class Arena:
        pass

    game = Arena()
    game.board = board
    game.bombs = list(bombs or [])
    game.explosions = list(explosions or [])
    game.players = list(players)
    game.powerups = list(powerups or [])
    game.current_time = now
    game.grid_width = len(board[0])
    game.grid_height = len(board)
    return game


def _farm_board():
    """One high-value brick cross at (5, 3); a weaker brick beside the spawn."""
    board = open_board(9, 7)
    board[2][2] = DESTRUCTIBLE
    board[2][5] = DESTRUCTIBLE
    board[4][5] = DESTRUCTIBLE
    return board


def _brick_row():
    board = open_board(7, 5)
    board[1][3] = DESTRUCTIBLE
    return board


class DangerMapTests(unittest.TestCase):
    def test_overlapping_blasts_keep_the_earlier_fuse(self):
        board = open_board(7, 5)
        late = Bomb(2, 1, 0, 2, None)
        early = Bomb(2, 2, 400 - BOMB_TIMER, 1, None)
        game = _arena(board, [], bombs=[late, early], now=0)
        times = _danger_times(game)
        self.assertEqual(times[(2, 1)], 400)
        self.assertLess(times[(1, 1)], BOMB_TIMER)

    def test_chain_of_three_uses_the_first_fuse(self):
        board = open_board(9, 5)
        first = Bomb(6, 1, 100 - BOMB_TIMER, 1, None)
        middle = Bomb(5, 1, 0, 1, None)
        last = Bomb(4, 1, 0, 1, None)
        game = _arena(board, [], bombs=[last, middle, first], now=0)
        times = _danger_times(game)
        self.assertEqual(times[(4, 1)], 100)
        self.assertEqual(times[(3, 1)], 100)

    def test_expired_explosion_is_not_danger(self):
        board = open_board(5, 5)
        explosion = type("Exp", (), {})()
        explosion.cells = [(2, 2)]
        explosion.start_time = 0
        explosion.is_active = lambda t: t < EXPLOSION_DURATION
        live = _arena(board, [], explosions=[explosion], now=50)
        done = _arena(board, [], explosions=[explosion], now=EXPLOSION_DURATION + 10)
        self.assertEqual(_danger_times(live)[(2, 2)], 0)
        self.assertNotIn((2, 2), _danger_times(done))


class PersonalityKnobTests(unittest.TestCase):
    def test_each_style_has_its_own_limits(self):
        expected = {
            "cautious": (CAUTIOUS_SAFETY_MARGIN_MS, CAUTIOUS_BOMB_COOLDOWN_MS, 1, CAUTIOUS_POWERUP_HUNT_LIMIT),
            "normal": (CPU_SAFETY_MARGIN_MS, BOMB_COOLDOWN_MS, 3, POWERUP_HUNT_LIMIT),
            "crazy": (CRAZY_SAFETY_MARGIN_MS, CRAZY_BOMB_COOLDOWN_MS, 3, CRAZY_POWERUP_HUNT_LIMIT),
            "boss": (BOSS_SAFETY_MARGIN_MS, BOSS_BOMB_COOLDOWN_MS, 3, BOSS_POWERUP_HUNT_LIMIT),
        }
        for name, (margin, cooldown, live, pickup) in expected.items():
            with self.subTest(personality=name):
                bot = _bot(1, 1, name, bomb_capacity=3)
                self.assertEqual(ai_personality(bot), name)
                self.assertEqual(_safety_margin_ms(bot), margin)
                self.assertEqual(_bomb_cooldown_ms(bot), cooldown)
                self.assertEqual(_max_live_bombs(bot), live)
                quad = name == "crazy"
                self.assertEqual(_powerup_limit(bot, quad=quad), pickup)


class PlantGateTests(unittest.TestCase):
    def test_refuses_a_bomb_with_no_exit(self):
        board = [
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
        ]
        for name in (*AI_PERSONALITIES, "boss"):
            with self.subTest(personality=name):
                bot = _bot(1, 1, name, fire_power=2, bomb_capacity=3)
                _, place = think_ai(bot, _arena(board, [bot]))
                self.assertFalse(place)

    def test_refuses_while_off_center_or_on_cooldown_or_at_capacity(self):
        board = _brick_row()
        far = _bot(5, 3, "normal")
        for name in AI_PERSONALITIES:
            with self.subTest(personality=name):
                ready = _bot(2, 1, name)
                _, place = think_ai(ready, _arena(board, [ready, far]))
                self.assertTrue(place)

                offset = _bot(2, 1, name)
                offset.pos[0] += 30
                _, place = think_ai(offset, _arena(board, [offset, far]))
                self.assertFalse(place)

                cooling = _bot(2, 1, name)
                cooling._ai_last_bomb_ms = 0
                _, place = think_ai(cooling, _arena(board, [cooling, far], now=50))
                self.assertFalse(place)

                full = _bot(2, 1, name, bomb_capacity=2, active_bombs=2)
                _, place = think_ai(full, _arena(board, [full, far]))
                self.assertFalse(place)

    def test_cautious_will_not_plant_beside_a_nearby_player(self):
        board = _brick_row()
        bot = _bot(2, 1, "cautious")
        hunter = _bot(2, 3, "normal")
        _, place = think_ai(bot, _arena(board, [bot, hunter]))
        self.assertFalse(place)
        self.assertEqual(bot._ai_goal_kind, "retreat")


class GoalTests(unittest.TestCase):
    def test_far_opponent_farms_for_cautious_and_normal_and_hunts_for_the_rest(self):
        board = _farm_board()
        far = _bot(7, 5, "normal")
        for name, kind, cell in (
            ("cautious", "farm", (5, 3)),
            ("normal", "farm", (5, 3)),
            ("crazy", "hunt", None),
            ("boss", "hunt", None),
        ):
            with self.subTest(personality=name):
                bot = _bot(1, 1, name)
                think_ai(bot, _arena(board, [bot, far]))
                self.assertEqual(bot._ai_goal_kind, kind)
                if cell is not None:
                    self.assertEqual(bot._ai_goal_cell, cell)

    def test_crazy_walks_to_quad_damage_before_a_closer_brick(self):
        board = _farm_board()
        bot = _bot(1, 1, "crazy")
        qd = type("PU", (), {"x": 7, "y": 1, "type": "quad_damage"})()
        think_ai(bot, _arena(board, [bot], powerups=[qd]))
        self.assertEqual(bot._ai_goal_kind, "powerup")
        self.assertEqual(bot._ai_goal_cell, (7, 1))

    def test_a_lit_cell_drops_a_sticky_hunt(self):
        board = open_board(9, 5)
        bot = _bot(2, 2, "normal")
        bot._ai_goal_kind = "hunt"
        bot._ai_goal_cell = (6, 2)
        bot._ai_goal_until = 10_000
        bomb = Bomb(2, 2, 0, 1, bot)
        game = _arena(board, [bot], bombs=[bomb], now=400)
        step, place = think_ai(bot, game)
        self.assertFalse(place)
        self.assertNotEqual(step, (0, 0))
        self.assertIn(bot._ai_goal_kind, ("wait", "flee"))
        self.assertTrue(_must_flee(bot, game, _danger_times(game), set(), set(), 1, 1))


class FleeTests(unittest.TestCase):
    def test_every_style_steps_off_its_own_bomb_with_time_left(self):
        board = open_board(9, 9)
        for name in (*AI_PERSONALITIES, "boss"):
            with self.subTest(personality=name):
                bot = _bot(4, 4, name)
                bomb = Bomb(4, 4, 0, 1, bot)
                game = _arena(board, [bot], bombs=[bomb], now=BOMB_TIMER - 2200)
                step, place = think_ai(bot, game)
                self.assertFalse(place)
                self.assertNotEqual(step, (0, 0))
                nxt = (4 + step[0], 4 + step[1])
                self.assertNotEqual(nxt, (4, 4))

    def test_movement_clears_the_blast_before_the_fuse(self):
        board = open_board(9, 9)
        blast = {(4, 4), (5, 4), (3, 4), (4, 5), (4, 3)}
        for name in (*AI_PERSONALITIES, "boss"):
            with self.subTest(personality=name):
                bot = _bot(4, 4, name)
                bomb = Bomb(4, 4, 0, 1, bot)
                game = _arena(board, [bot], bombs=[bomb])
                cleared_at = None
                for t in range(0, 1600, 16):
                    game.current_time = t
                    bot.update(16, board, game.bombs, t, game=game)
                    cell = bot.get_grid_pos()
                    self.assertTrue(bot.alive)
                    if cell not in blast:
                        cleared_at = t
                        break
                self.assertIsNotNone(cleared_at, "%s was still in the blast" % name)
                self.assertLess(cleared_at, BOMB_TIMER - 800)
                self.assertTrue(
                    _safe_to_stay(bot.get_grid_pos(), cleared_at, _danger_times(game), EXPLOSION_DURATION)
                )


if __name__ == "__main__":
    unittest.main()

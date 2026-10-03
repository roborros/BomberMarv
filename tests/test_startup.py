import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from event_abstraction import EventType, GameCommand, GameCommandHandler, GameEvent
from helpers import silence_sounds
from startup_load import (
    STARTUP_CLIMB_MS,
    STARTUP_HOLD_98_MS,
    STARTUP_TOTAL_MS,
    build_startup_load_jumps,
    startup_load_percent,
)


class StartupLoadTests(unittest.TestCase):
    def test_jumps_climb_to_98_inside_four_seconds(self):
        for seed in range(30):
            jumps = build_startup_load_jumps(__import__("random").Random(seed))
            self.assertGreaterEqual(len(jumps), 2)
            self.assertEqual(jumps[-1], (STARTUP_CLIMB_MS, 98))
            previous_t = -1
            previous_p = 0
            for moment, percent in jumps:
                self.assertGreater(moment, previous_t)
                self.assertGreater(percent, previous_p)
                self.assertLessEqual(percent, 98)
                previous_t = moment
                previous_p = percent

    def test_hold_then_full_then_done_under_seven_seconds(self):
        jumps = build_startup_load_jumps(__import__("random").Random(1))
        self.assertLessEqual(startup_load_percent(0, jumps), 98)
        self.assertEqual(startup_load_percent(STARTUP_CLIMB_MS, jumps), 98)
        self.assertEqual(startup_load_percent(STARTUP_CLIMB_MS + STARTUP_HOLD_98_MS - 1, jumps), 98)
        self.assertEqual(startup_load_percent(STARTUP_CLIMB_MS + STARTUP_HOLD_98_MS, jumps), 100)
        self.assertEqual(STARTUP_TOTAL_MS, 7000)
        self.assertLessEqual(STARTUP_TOTAL_MS, 7000)

    def test_percent_only_moves_forward_during_the_climb(self):
        jumps = build_startup_load_jumps(__import__("random").Random(4))
        seen = 0
        for elapsed in range(0, STARTUP_CLIMB_MS + 1, 16):
            percent = startup_load_percent(elapsed, jumps)
            self.assertGreaterEqual(percent, seen)
            self.assertLessEqual(percent, 98)
            seen = percent
        self.assertEqual(seen, 98)


class StartupSkipTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        from bm_classes import Game
        self.game = Game()

    def test_enter_and_escape_leave_the_splash_for_the_lobby(self):
        handler = GameCommandHandler(self.game)
        self.assertEqual(self.game.game_state, "startup")
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.CANCEL_EDIT))
        self.assertEqual(self.game.game_state, "game_prep")

        self.game.game_state = "startup"
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.START_GAME))
        self.assertEqual(self.game.game_state, "game_prep")

    def test_splash_ends_in_the_lobby_at_seven_seconds(self):
        start = self.game.startup_start_time
        self.game.simulate(16, now_ms=start + STARTUP_TOTAL_MS - 1)
        self.assertEqual(self.game.game_state, "startup")
        self.game.simulate(16, now_ms=start + STARTUP_TOTAL_MS)
        self.assertEqual(self.game.game_state, "game_prep")

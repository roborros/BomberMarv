import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_game_logic import BackendGameLogic
from event_abstraction import GameCommand
from input_abstraction import Keys


class FakeGame:
    def __init__(self, state="startup"):
        self.game_state = state
        self.prep_screen_completed = False
        self.startup_start_time = 0
        self.current_time = 10
        self.game_start_time = 5
        self.prep_num_players = 2
        self.prep_player_names = ["A", "B"]
        self.prep_player_colors = [0, 1]
        self.prep_controls = []
        self.players = []
        self.frontend = None
        self.screen = None
        self.is_fullscreen = False
        self.init_calls = 0
        self.create_calls = 0
        self.trophy_resets = 0
        self.prep_events = []
        self.boss_starts = 0

    def get_ticks(self):
        return 99

    def init_game(self):
        self.init_calls += 1

    def create_players(self):
        self.create_calls += 1

    def reset_trophies(self):
        self.trophy_resets += 1

    def continue_from_champion(self):
        self.boss_starts += 1
        self.game_state = "boss_fight"
        return True

    def reset_series_and_start(self):
        self.trophy_resets += 1
        self.init_calls += 1
        self.game_state = "get_ready"
        return True

    def continue_from_intermission(self):
        if self.game_state == "champion":
            return self.continue_from_champion()
        if self.game_state in ("win", "boss_result"):
            if self.game_state == "boss_result":
                self.trophy_resets += 1
            self.init_game()
            self.game_state = "get_ready"
            return True
        return False

    def handle_prep_key_event(self, event):
        self.prep_events.append(event.key)


class BackendLogicTests(unittest.TestCase):
    def test_startup_start_game_enters_prep(self):
        game = FakeGame("startup")
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.START_GAME))
        self.assertEqual(game.game_state, "game_prep")

    def test_startup_start_game_blocked_after_prep(self):
        game = FakeGame("startup")
        game.prep_screen_completed = True
        logic = BackendGameLogic(game)
        self.assertFalse(logic.handle_game_state_transition(GameCommand.START_GAME))
        self.assertEqual(game.game_state, "startup")

    def test_enter_prep_from_startup(self):
        game = FakeGame("startup")
        game.prep_screen_completed = True
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.ENTER_PREP_SCREEN))
        self.assertEqual(game.game_state, "game_prep")

    def test_prep_enter_sends_enter_key(self):
        game = FakeGame("game_prep")
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.START_GAME))
        self.assertEqual(game.prep_events, [Keys.ENTER])

    def test_quick_start_creates_players_and_ready(self):
        game = FakeGame("game_prep")
        game.prep_num_players = 0
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.QUICK_START_GAME, {"command": GameCommand.QUICK_START_GAME}))
        self.assertEqual(game.prep_num_players, 1)
        self.assertEqual(game.create_calls, 1)
        self.assertEqual(game.init_calls, 1)
        self.assertTrue(game.prep_screen_completed)
        self.assertEqual(game.game_state, "get_ready")

    def test_prep_exit_returns_to_startup(self):
        game = FakeGame("game_prep")
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.EXIT_PREP_SCREEN))
        self.assertEqual(game.game_state, "startup")
        self.assertEqual(game.startup_start_time, 99)

    def test_ready_to_playing_waits_for_start_time(self):
        game = FakeGame("get_ready")
        game.current_time = 1
        game.game_start_time = 10
        logic = BackendGameLogic(game)
        self.assertFalse(logic.handle_game_state_transition(GameCommand.START_GAME))
        game.current_time = 11
        self.assertTrue(logic.handle_game_state_transition(GameCommand.START_GAME))
        self.assertEqual(game.game_state, "playing")

    def test_playing_restart(self):
        game = FakeGame("playing")
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.RESTART_GAME))
        self.assertEqual(game.init_calls, 1)
        self.assertEqual(game.game_state, "get_ready")

    def test_champion_enter_starts_boss(self):
        game = FakeGame("champion")
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_game_state_transition(GameCommand.RESTART_GAME))
        self.assertEqual(game.boss_starts, 1)
        self.assertEqual(game.trophy_resets, 0)
        self.assertEqual(game.game_state, "boss_fight")

    def test_champion_and_boss_reset_series(self):
        for state in ("champion", "boss_result"):
            game = FakeGame(state)
            logic = BackendGameLogic(game)
            self.assertTrue(logic.handle_game_state_transition(GameCommand.RESET_SERIES))
            self.assertEqual(game.trophy_resets, 1)
            self.assertEqual(game.game_state, "get_ready")

    def test_unknown_state_is_false(self):
        game = FakeGame("nope")
        logic = BackendGameLogic(game)
        self.assertFalse(logic.handle_game_state_transition(GameCommand.START_GAME))

    def test_prep_navigation_delegates(self):
        game = FakeGame("game_prep")
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_prep_screen_logic(GameCommand.NAVIGATE_UP, {}))
        self.assertEqual(game.prep_events, [Keys.UP])
        self.assertFalse(logic.handle_prep_screen_logic(GameCommand.START_GAME, {}))

    def test_prep_navigation_ignored_outside_prep(self):
        game = FakeGame("playing")
        logic = BackendGameLogic(game)
        self.assertFalse(logic.handle_prep_screen_logic(GameCommand.NAVIGATE_DOWN, {}))

    def test_window_toggle_fallback(self):
        game = FakeGame()
        logic = BackendGameLogic(game)
        self.assertTrue(logic.handle_window_management(GameCommand.TOGGLE_FULLSCREEN, {}))
        self.assertTrue(game.is_fullscreen)

    def test_unknown_window_command(self):
        game = FakeGame()
        logic = BackendGameLogic(game)
        self.assertFalse(logic.handle_window_management(GameCommand.START_GAME, {}))


if __name__ == "__main__":
    unittest.main()

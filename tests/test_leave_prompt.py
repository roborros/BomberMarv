"""Leave-game overlay, roster order, and explosion peek tests."""
import os
import sys
import unittest
from unittest.mock import patch

from helpers import cell_center, open_board, silence_sounds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import (
    AI_NAME_LEFT,
    AI_NAME_RIGHT,
    CELL_SIZE,
)
from bm_classes import Bomb, Explosion, Game
from event_abstraction import EventType, GameCommand, GameCommandHandler, GameEvent


class LeavePromptTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        self.game = Game()
        self.game.game_state = "playing"
        self.game.current_time = 5000
        self.game.bombs = []
        self.game.explosions = []

    def test_open_defaults_to_no(self):
        self.assertTrue(self.game.open_leave_prompt())
        self.assertTrue(self.game.leave_prompt_open)
        self.assertEqual(self.game.leave_prompt_choice, "no")
        self.assertEqual(self.game.leave_prompt_title(), "Do you want to cancel the game session?")
        payload = self.game.to_dict()["leave_prompt"]
        self.assertTrue(payload["open"])
        self.assertEqual(payload["choice"], "no")

    def test_stat_screen_uses_leave_game_title(self):
        self.game.game_state = "win"
        self.game.open_leave_prompt()
        self.assertEqual(self.game.leave_prompt_title(), "Leave game?")
        self.assertIn("Esc", self.game.result_prompt())

    def test_simulate_freezes_clock_while_open(self):
        self.game.open_leave_prompt()
        frozen = self.game.current_time
        self.assertIsNone(self.game.simulate(16, now_ms=frozen + 2000))
        self.assertEqual(self.game.current_time, frozen)

    def test_resume_shifts_bomb_timers(self):
        owner = self.game.players[0]
        bomb = Bomb(3, 3, 5000, 1, owner)
        self.game.bombs = [bomb]
        self.game.current_time = 5000
        self.game.open_leave_prompt()
        with patch("bm_classes.get_ticks", return_value=8000):
            self.game.close_leave_prompt()
        self.assertFalse(self.game.leave_prompt_open)
        self.assertEqual(bomb.start_time, 8000)
        self.assertEqual(self.game.current_time, 8000)

    def test_yes_returns_to_lobby_with_same_players(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 2
        self.game.create_players()
        before = [(p["type"], p["name"]) for p in self.game.get_all_players_info()]
        ai_names = [name for kind, name in before if kind == "ai"]
        self.assertEqual(len(ai_names), 2)
        for p in self.game.players:
            p.trophies = 2
        self.game.game_state = "win"
        self.game.open_leave_prompt()
        self.game.leave_prompt_choice = "yes"
        self.assertTrue(self.game.confirm_leave_prompt())
        self.assertEqual(self.game.game_state, "game_prep")
        after = [(p["type"], p["name"]) for p in self.game.get_all_players_info()]
        self.assertEqual(after, before)
        self.assertTrue(all(p.trophies == 0 for p in self.game.players))
        self.assertTrue(all(kind != "ai" or name.split()[0] in AI_NAME_LEFT for kind, name in after))

    def test_does_not_open_from_lobby(self):
        self.game.game_state = "game_prep"
        self.assertFalse(self.game.open_leave_prompt())


class AiNameTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        self.game = Game()

    def test_ais_are_last_and_use_random_names(self):
        self.game.prep_num_players = 2
        self.game.prep_ai_count = 2
        self.game._cached_status = None
        info = self.game.get_all_players_info()
        types = [p["type"] for p in info]
        self.assertEqual(types[-2:], ["ai", "ai"])
        self.assertNotIn("ai", types[:-2])
        for player in info:
            if player["type"] != "ai":
                continue
            left, right = player["name"].split(" ")
            self.assertIn(left, AI_NAME_LEFT)
            self.assertIn(right, AI_NAME_RIGHT)
            self.assertFalse(player["name"].endswith(" AI"))
        again = self.game.get_all_players_info()
        self.assertEqual(
            [p["name"] for p in info if p["type"] == "ai"],
            [p["name"] for p in again if p["type"] == "ai"],
        )


class ExplosionPeekTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        self.game = Game()
        self.game.board = open_board(9, 9)
        self.game.grid_width = 9
        self.game.grid_height = 9
        self.game.players[0].pos[0] = cell_center(3, 3)[0]
        self.game.players[0].pos[1] = cell_center(3, 3)[1]
        self.game.current_time = 1000
        self.game.explosions = []

    def test_slight_peek_into_flame_is_safe(self):
        player = self.game.players[0]
        player.pos[0] = 3 * CELL_SIZE + CELL_SIZE - 5
        player.pos[1] = 3 * CELL_SIZE + CELL_SIZE // 2
        self.game.explosions = [Explosion([(3, 3)], self.game.current_time - 80)]
        self.game.handle_explosions()
        self.assertTrue(player.alive)

    def test_center_of_flame_still_kills(self):
        player = self.game.players[0]
        player.pos[0] = cell_center(3, 3)[0]
        player.pos[1] = cell_center(3, 3)[1]
        self.game.explosions = [Explosion([(3, 3)], self.game.current_time - 80)]
        self.game.handle_explosions()
        self.assertFalse(player.alive)


class LeavePromptCommandTests(unittest.TestCase):
    def test_handler_opens_from_stats_screen(self):
        silence_sounds()
        game = Game()
        game.game_state = "champion"
        handler = GameCommandHandler(game)
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.CANCEL_EDIT))
        self.assertTrue(game.leave_prompt_open)
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.NAVIGATE_LEFT))
        self.assertEqual(game.leave_prompt_choice, "yes")
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.START_GAME))
        self.assertEqual(game.game_state, "game_prep")


if __name__ == "__main__":
    unittest.main()

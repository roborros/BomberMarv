import unittest

from helpers import silence_sounds

silence_sounds()

from bm_classes import Game
from bm_drawing import READY_KEY_LINES, control_guide_rows, get_ready_banner_rect
from event_abstraction import EventType, GameCommand, GameCommandHandler, GameEvent
from input_abstraction import Keys


def _event(key, text=""):
    return type("E", (), {"key": key, "unicode": text})()


class ControlGuideTests(unittest.TestCase):
    def test_ready_lines_name_the_main_keys(self):
        self.assertEqual(
            READY_KEY_LINES,
            (
                "Local   W A S D move   ·   Space bomb",
                "Browser   Arrow keys move   ·   Space bomb",
            ),
        )

    def test_guide_lists_every_local_seat(self):
        rows = control_guide_rows()
        self.assertEqual(rows[0], ("Player 1", "W A S D", "Space"))
        self.assertEqual(rows[1], ("Player 2", "I J K L", "Left Ctrl"))
        self.assertEqual(rows[2], ("Player 3", "F C V B", "H"))
        self.assertEqual(rows[5][0], "Player 6")
        self.assertIn(("Browser", "Arrow keys or W A S D", "Space or Enter"), rows)

    def test_ready_banner_stays_off_corner_spawns(self):
        banner = get_ready_banner_rect(1900, 1900)
        self.assertGreater(banner.y, 200)
        self.assertLess(banner.bottom, 1700)
        self.assertGreaterEqual(banner.height, 108)


class LobbyKeysAndQuitTests(unittest.TestCase):
    def test_k_opens_the_keys_screen(self):
        game = Game()
        game.game_state = "game_prep"
        game.handle_prep_key_event(_event(Keys.K, "k"))
        self.assertEqual(game.prep_section, "controls")
        game.handle_prep_key_event(_event(Keys.ESCAPE))
        self.assertEqual(game.prep_section, "local_players")
        self.assertFalse(game.quit_prompt_open)
        self.assertEqual(game.game_state, "game_prep")

    def test_keys_button_opens_the_keys_screen(self):
        game = Game()
        game.prep_section = "keys_button"
        game.handle_prep_key_event(_event(Keys.ENTER))
        self.assertEqual(game.prep_section, "controls")

    def test_escape_on_the_lobby_asks_before_quitting(self):
        game = Game()
        game.game_state = "game_prep"
        frontend = type("F", (), {"should_quit": False})()
        game.frontend = frontend
        game.handle_prep_key_event(_event(Keys.ESCAPE))
        self.assertTrue(game.quit_prompt_open)
        self.assertEqual(game.quit_prompt_choice, "no")
        self.assertEqual(game.game_state, "game_prep")
        game.handle_prep_key_event(_event(Keys.ENTER))
        self.assertFalse(game.quit_prompt_open)
        self.assertFalse(frontend.should_quit)
        self.assertFalse(game.quit_requested)

    def test_yes_exits_the_app(self):
        game = Game()
        game.game_state = "game_prep"
        game.prep_section = "start_game"
        frontend = type("F", (), {"should_quit": False})()
        game.frontend = frontend
        game.handle_prep_key_event(_event(Keys.ESCAPE))
        game.handle_prep_key_event(_event(Keys.RIGHT))
        self.assertEqual(game.quit_prompt_choice, "yes")
        game.handle_prep_key_event(_event(Keys.ENTER))
        self.assertTrue(game.quit_requested)
        self.assertTrue(frontend.should_quit)
        self.assertEqual(game.game_state, "game_prep")

    def test_escape_closes_the_quit_prompt(self):
        game = Game()
        game.game_state = "game_prep"
        game.handle_prep_key_event(_event(Keys.ESCAPE))
        game.handle_prep_key_event(_event(Keys.ESCAPE))
        self.assertFalse(game.quit_prompt_open)
        self.assertEqual(game.game_state, "game_prep")

    def test_quit_prompt_blocks_quick_start(self):
        game = Game()
        game.game_state = "game_prep"
        game.open_quit_prompt()
        handler = GameCommandHandler(game)
        handled = handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.QUICK_START_GAME))
        self.assertTrue(handled)
        self.assertTrue(game.quit_prompt_open)
        self.assertEqual(game.game_state, "game_prep")

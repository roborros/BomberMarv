import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
from event_abstraction import EventProcessor, EventType, GameCommand, GameCommandHandler, GameEvent
from input_abstraction import Keys


class EventProcessorTests(unittest.TestCase):
    def test_quit_maps_to_close_window(self):
        event = types.SimpleNamespace(type=pygame.QUIT)
        game_event = EventProcessor.process_pygame_event(event)
        self.assertIsNotNone(game_event)
        self.assertEqual(game_event.command, GameCommand.CLOSE_WINDOW)
        self.assertEqual(game_event.event_type, EventType.WINDOW_CLOSE)

    def test_resize_includes_size(self):
        event = types.SimpleNamespace(type=pygame.VIDEORESIZE, size=(800, 600))
        game_event = EventProcessor.process_pygame_event(event)
        self.assertEqual(game_event.command, GameCommand.RESIZE_WINDOW)
        self.assertEqual(game_event.data["size"], (800, 600))

    def test_enter_is_start_game(self):
        event = types.SimpleNamespace(type=pygame.KEYDOWN, key=Keys.ENTER, unicode="")
        game_event = EventProcessor.process_pygame_event(event)
        self.assertEqual(game_event.command, GameCommand.START_GAME)

    def test_space_is_quick_start(self):
        event = types.SimpleNamespace(type=pygame.KEYDOWN, key=Keys.SPACE, unicode="")
        game_event = EventProcessor.process_pygame_event(event)
        self.assertEqual(game_event.command, GameCommand.QUICK_START_GAME)

    def test_f11_toggles_fullscreen(self):
        event = types.SimpleNamespace(type=pygame.KEYDOWN, key=Keys.F11, unicode="")
        game_event = EventProcessor.process_pygame_event(event)
        self.assertEqual(game_event.command, GameCommand.TOGGLE_FULLSCREEN)

    def test_arrows_and_tab(self):
        mapping = {
            Keys.UP: GameCommand.NAVIGATE_UP,
            Keys.DOWN: GameCommand.NAVIGATE_DOWN,
            Keys.LEFT: GameCommand.NAVIGATE_LEFT,
            Keys.RIGHT: GameCommand.NAVIGATE_RIGHT,
            Keys.TAB: GameCommand.SWITCH_SECTION,
            Keys.ESCAPE: GameCommand.CANCEL_EDIT,
            Keys.BACKSPACE: GameCommand.REMOVE_CHARACTER,
        }
        for key, command in mapping.items():
            event = types.SimpleNamespace(type=pygame.KEYDOWN, key=key, unicode="")
            game_event = EventProcessor.process_pygame_event(event)
            self.assertEqual(game_event.command, command, msg=command)

    def test_printable_unicode_adds_character(self):
        event = types.SimpleNamespace(type=pygame.KEYDOWN, key=Keys.A, unicode="a")
        game_event = EventProcessor.process_pygame_event(event)
        self.assertEqual(game_event.command, GameCommand.ADD_CHARACTER)
        self.assertEqual(game_event.data["character"], "a")

    def test_keyup_is_ignored(self):
        event = types.SimpleNamespace(type=pygame.KEYUP, key=Keys.A, unicode="")
        self.assertIsNone(EventProcessor.process_pygame_event(event))

    def test_unknown_event_returns_none(self):
        event = types.SimpleNamespace(type=pygame.MOUSEMOTION)
        self.assertIsNone(EventProcessor.process_pygame_event(event))


class GameCommandHandlerTests(unittest.TestCase):
    def test_start_from_startup_goes_to_prep(self):
        game = types.SimpleNamespace(
            game_state="startup",
            prep_screen_completed=False,
            frontend=None,
            screen=None,
        )
        handler = GameCommandHandler(game)
        handled = handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.START_GAME))
        self.assertTrue(handled)
        self.assertEqual(game.game_state, "game_prep")

    def test_start_from_startup_skips_prep_when_completed(self):
        calls = []
        game = types.SimpleNamespace(
            game_state="startup",
            prep_screen_completed=True,
            init_game=lambda: calls.append("init"),
            frontend=None,
            screen=None,
        )
        handler = GameCommandHandler(game)
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.START_GAME))
        self.assertEqual(calls, ["init"])
        self.assertEqual(game.game_state, "get_ready")

    def test_champion_enter_faces_boss(self):
        calls = []
        game = types.SimpleNamespace(
            game_state="champion",
            continue_from_intermission=lambda: calls.append("boss") or True,
            frontend=None,
            screen=None,
        )
        handler = GameCommandHandler(game)
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.START_GAME))
        self.assertEqual(calls, ["boss"])

    def test_champion_r_resets_series(self):
        calls = []
        game = types.SimpleNamespace(
            game_state="champion",
            reset_series_and_start=lambda: calls.append("reset") or True,
            frontend=None,
            screen=None,
        )
        handler = GameCommandHandler(game)
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.RESET_SERIES))
        self.assertEqual(calls, ["reset"])

    def test_r_maps_to_reset_series(self):
        event = types.SimpleNamespace(type=pygame.KEYDOWN, key=Keys.R, unicode="r")
        game_event = EventProcessor.process_pygame_event(event)
        self.assertEqual(game_event.command, GameCommand.RESET_SERIES)

    def test_close_window_sets_should_quit(self):
        frontend = types.SimpleNamespace(should_quit=False)
        game = types.SimpleNamespace(frontend=frontend, screen=None)
        handler = GameCommandHandler(game)
        handler.handle_command(GameEvent(EventType.WINDOW_CLOSE, GameCommand.CLOSE_WINDOW))
        self.assertTrue(frontend.should_quit)

    def test_quick_start_ignored_outside_prep(self):
        game = types.SimpleNamespace(game_state="playing", frontend=None, screen=None)
        handler = GameCommandHandler(game)
        self.assertFalse(handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.QUICK_START_GAME)))

    def test_escape_opens_leave_prompt_while_playing(self):
        calls = []
        game = types.SimpleNamespace(
            game_state="playing",
            leave_prompt_open=False,
            frontend=None,
            screen=None,
            leave_prompt_states=lambda: {"playing", "win"},
            open_leave_prompt=lambda: calls.append("open") or True,
        )
        handler = GameCommandHandler(game)
        handled = handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.CANCEL_EDIT))
        self.assertTrue(handled)
        self.assertEqual(calls, ["open"])

    def test_leave_prompt_arrows_and_enter(self):
        calls = []
        game = types.SimpleNamespace(
            game_state="win",
            leave_prompt_open=True,
            frontend=None,
            screen=None,
            toggle_leave_prompt_choice=lambda: calls.append("toggle") or True,
            confirm_leave_prompt=lambda: calls.append("confirm") or True,
            close_leave_prompt=lambda: calls.append("close") or True,
        )
        handler = GameCommandHandler(game)
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.NAVIGATE_RIGHT))
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.START_GAME))
        handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.CANCEL_EDIT))
        self.assertEqual(calls, ["toggle", "confirm", "close"])

    def test_escape_on_prep_does_not_open_leave_prompt(self):
        calls = []
        game = types.SimpleNamespace(
            game_state="game_prep",
            leave_prompt_open=False,
            frontend=None,
            screen=None,
            leave_prompt_states=lambda: {"playing"},
            open_leave_prompt=lambda: calls.append("open") or True,
            handle_prep_key_event=lambda event: calls.append("prep"),
        )
        handler = GameCommandHandler(game)
        handled = handler.handle_command(GameEvent(EventType.KEY_PRESS, GameCommand.CANCEL_EDIT))
        self.assertTrue(handled)
        self.assertEqual(calls, ["prep"])


if __name__ == "__main__":
    unittest.main()

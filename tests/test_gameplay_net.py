import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

from helpers import cell_center, open_board, silence_sounds
from bm_classes import Game, Player
from bm_params import CELL_SIZE, INDESTRUCTIBLE, PLAYER_SPEED
from latency_metrics import queue_delay_ms, wall_clock_ms
from net_protocol import should_buffer_remote_input

silence_sounds()


def _remote_player(grid_x=1, grid_y=1, client_id=7, player_id=1, name="Remote"):
    player = Player(grid_x, grid_y, (100, 150, 200), None, name)
    player.is_local = False
    player.client_id = client_id
    player.client_player_id = player_id
    player.global_id = player_id
    return player


def _playing_game(player):
    game = Game()
    game.board = open_board(9, 9)
    game.grid_width = 9
    game.grid_height = 9
    game.game_state = "playing"
    game.current_time = 1000
    game.dt = 200
    game.players = [player]
    game.bombs = []
    game.explosions = []
    game.powerups = []
    return game


class GameplayNetTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        keys_patch = patch("bm_classes.get_pressed_keys", return_value={})
        keys_patch.start()
        self.addCleanup(keys_patch.stop)

    def test_remote_input_moves_and_places_bomb_in_one_step(self):
        player = _remote_player()
        start_x = float(player.pos[0])
        game = _playing_game(player)
        received_at = wall_clock_ms() - 12
        event = {
            "type": "set_input_state",
            "client_id": 7,
            "player_id": 1,
            "keys": {"up": 0, "down": 0, "left": 0, "right": 1, "bomb": 1},
            "ws_received_timestamp": received_at,
        }
        delay = queue_delay_ms(event["ws_received_timestamp"], wall_clock_ms())
        self.assertGreaterEqual(delay, 11)
        self.assertLess(delay, 250)
        game.handle_web_key_event(event)
        game.update()
        snapshot = game.to_dict()
        self.assertGreater(player.pos[0], start_x)
        self.assertGreater(snapshot["players"][0]["x"], start_x)
        self.assertEqual(len(game.bombs), 1)
        self.assertEqual(len(snapshot["bombs"]), 1)
        expected = PLAYER_SPEED * (game.dt / 1000.0)
        self.assertAlmostEqual(player.pos[0] - start_x, expected, delta=1.5)

    def test_holding_bomb_does_not_drop_a_second_bomb(self):
        player = _remote_player()
        player.bomb_capacity = 2
        game = _playing_game(player)
        event = {
            "type": "set_input_state",
            "client_id": 7,
            "player_id": 1,
            "keys": {"up": 0, "down": 0, "left": 0, "right": 0, "bomb": 1},
        }
        game.handle_web_key_event(event)
        game.update()
        game.current_time += 200
        game.update()
        self.assertEqual(len(game.bombs), 1)

    def test_holding_bomb_while_moving_plants_on_empty_cells(self):
        player = _remote_player()
        player.bomb_capacity = 3
        game = _playing_game(player)
        game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 7,
                "player_id": 1,
                "keys": {"up": 0, "down": 0, "left": 0, "right": 1, "bomb": 1},
            }
        )
        for _ in range(8):
            game.current_time += game.dt
            game.update()
        cells = {(b.x, b.y) for b in game.bombs}
        self.assertGreaterEqual(len(game.bombs), 2)
        self.assertIn((1, 1), cells)
        self.assertIn((2, 1), cells)

    def test_wall_blocks_remote_movement(self):
        player = _remote_player()
        game = _playing_game(player)
        game.board[1][2] = INDESTRUCTIBLE
        start = player.pos.copy()
        game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 7,
                "player_id": 1,
                "keys": {"up": 0, "down": 0, "left": 0, "right": 1, "bomb": 0},
            }
        )
        game.dt = 400
        game.update()
        self.assertLess(abs(player.pos[0] - start[0]), 1.0)

    def test_unknown_client_and_dead_player_are_ignored(self):
        player = _remote_player()
        game = _playing_game(player)
        start = player.pos.copy()
        game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 99,
                "player_id": 1,
                "keys": {"right": 1, "bomb": 1},
            }
        )
        game.update()
        self.assertEqual(list(player.pos), list(start))
        self.assertEqual(len(game.bombs), 0)

        player.alive = False
        game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 7,
                "player_id": 1,
                "keys": {"right": 1, "bomb": 1},
            }
        )
        game.update()
        self.assertEqual(list(player.pos), list(start))
        self.assertEqual(len(game.bombs), 0)

    def test_releasing_keys_stops_on_next_step(self):
        player = _remote_player()
        game = _playing_game(player)
        game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 7,
                "player_id": 1,
                "keys": {"right": 1},
            }
        )
        game.update()
        after_move = float(player.pos[0])
        game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 7,
                "player_id": 1,
                "keys": {"up": 0, "down": 0, "left": 0, "right": 0, "bomb": 0},
            }
        )
        game.current_time += 200
        game.update()
        self.assertAlmostEqual(float(player.pos[0]), after_move, delta=0.01)

    def test_future_input_is_buffered_then_applied(self):
        self.assertTrue(should_buffer_remote_input(12, 10))
        self.assertFalse(should_buffer_remote_input(10, 10))
        player = _remote_player()
        game = _playing_game(player)
        start_x = float(player.pos[0])
        pending = {
            "type": "set_input_state",
            "client_id": 7,
            "player_id": 1,
            "keys": {"right": 1},
            "apply_tick_id": 12,
        }
        if not should_buffer_remote_input(pending["apply_tick_id"], 10):
            game.handle_web_key_event(pending)
        self.assertEqual(float(player.pos[0]), start_x)
        game.handle_web_key_event(pending)
        game.update()
        self.assertGreater(float(player.pos[0]), start_x)

    def test_spawn_center_matches_wire_snapshot(self):
        player = _remote_player(2, 3)
        game = _playing_game(player)
        expected = cell_center(2, 3)
        snapshot = game.to_dict()
        self.assertEqual(snapshot["state"], "playing")
        self.assertAlmostEqual(snapshot["players"][0]["x"], expected[0], delta=0.01)
        self.assertAlmostEqual(snapshot["players"][0]["y"], expected[1], delta=0.01)
        self.assertEqual(snapshot["players"][0]["owner_client_id"], 7)
        self.assertGreater(CELL_SIZE, 0)


if __name__ == "__main__":
    unittest.main()

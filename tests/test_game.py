import os
import sys
import types
import unittest
from unittest.mock import patch

from helpers import cell_center, open_board, silence_sounds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import (
    BOMB_TIMER,
    BOSS_COLOR,
    BOSS_EXTRA_LIVES,
    BOSS_NAME,
    CELL_SIZE,
    DESTRUCTIBLE,
    EMPTY,
    EXPLOSION_DURATION,
    INDESTRUCTIBLE,
    MAX_PLAYERS,
    PREP_ROW_PLAYERS,
    PLAYER_DRAW_SCALE,
    PLAYER_SPEED,
    UBER_BOSS_DRAW_SCALE,
    UBER_BOSS_EXTRA_LIVES,
    MARV_KILLER_TITLE,
    UBER_BOSS_NAME,
    UBER_BOSS_SPEED_MULTIPLIER,
    UBER_BOSS_START_BOMB_CAPACITY,
    UBER_BOSS_START_FIRE_POWER,
    QUAD_DAMAGE_POWER,
    QUAD_DAMAGE_TIME,
    REPLAY_LOG_INTERVAL_MS,
    REPLAY_KILLCAM_POST_MS,
    get_grid_size,
)
from bm_classes import Bomb, Explosion, Game, Player, PowerUp, browser_key_to_pygame
from input_abstraction import Keys
from replay import build_replay_snapshot

silence_sounds()


def _player(x=1, y=1, name="Marv", controls=None):
    controls = controls or {"up": Keys.W, "down": Keys.S, "left": Keys.A, "right": Keys.D, "bomb": Keys.SPACE}
    p = Player(x, y, (100, 150, 200), controls, name)
    p.is_local = True
    p.global_id = 1
    return p


class BrowserKeyMapTests(unittest.TestCase):
    def test_arrows_and_space(self):
        self.assertEqual(browser_key_to_pygame("ArrowUp"), "up")
        self.assertEqual(browser_key_to_pygame("ArrowDown"), "down")
        self.assertEqual(browser_key_to_pygame("ArrowLeft"), "left")
        self.assertEqual(browser_key_to_pygame("ArrowRight"), "right")
        self.assertEqual(browser_key_to_pygame(" "), "space")
        self.assertEqual(browser_key_to_pygame("Space"), "space")
        self.assertEqual(browser_key_to_pygame("Enter"), "return")

    def test_letters_pass_through(self):
        self.assertEqual(browser_key_to_pygame("w"), "w")
        self.assertEqual(browser_key_to_pygame("5"), "5")

    def test_unknown_returns_none(self):
        self.assertIsNone(browser_key_to_pygame("F13"))
        self.assertIsNone(browser_key_to_pygame("ControlLeftX"))

    def test_modifiers(self):
        self.assertEqual(browser_key_to_pygame("Control"), "left ctrl")
        self.assertEqual(browser_key_to_pygame("ControlRight"), "right ctrl")
        self.assertEqual(browser_key_to_pygame("Numpad0"), "kp0")


class PlayerBombTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        self.board = open_board()
        self.player = _player()

    def test_drop_bomb_adds_bomb_and_capacity(self):
        bombs = []
        self.player.drop_bomb(bombs, 100)
        self.assertEqual(len(bombs), 1)
        self.assertEqual(self.player.active_bombs, 1)
        self.assertEqual((bombs[0].x, bombs[0].y), self.player.get_grid_pos())

    def test_cannot_stack_two_bombs_in_same_cell(self):
        bombs = []
        self.player.bomb_capacity = 2
        self.player.drop_bomb(bombs, 100)
        self.player.drop_bomb(bombs, 200)
        self.assertEqual(len(bombs), 1)

    def test_capacity_blocks_extra_bombs(self):
        bombs = []
        self.player.drop_bomb(bombs, 100)
        self.player.pos = __import__("numpy").array(cell_center(2, 1), dtype="float64")
        self.player.drop_bomb(bombs, 200)
        self.assertEqual(len(bombs), 1)

    def test_dead_player_cannot_bomb(self):
        self.player.alive = False
        bombs = []
        self.player.drop_bomb(bombs, 100)
        self.assertEqual(bombs, [])

    def test_cannot_bomb_on_powerup(self):
        bombs = []
        game = types.SimpleNamespace(powerups=[PowerUp(1, 1, "fire")])
        self.player.drop_bomb(bombs, 100, game=game)
        self.assertEqual(bombs, [])

    def test_quad_damage_marks_bomb(self):
        self.player.quad_damage = True
        bombs = []
        self.player.drop_bomb(bombs, 100)
        self.assertTrue(bombs[0].quad_damage)

    def test_bomb_expires_after_timer(self):
        bomb = Bomb(1, 1, 0, 1, self.player)
        self.assertFalse(bomb.update(BOMB_TIMER - 1))
        self.assertTrue(bomb.update(BOMB_TIMER))
        self.assertTrue(bomb.exploded)

    def test_hold_does_not_stack_in_same_cell(self):
        bombs = []
        self.player.bomb_capacity = 3
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.SPACE), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.player.update(16, self.board, bombs, 0)
            self.player.update(16, self.board, bombs, 16)
            self.player.update(16, self.board, bombs, 32)
        self.assertEqual(len(bombs), 1)

    def test_hold_plants_trail_on_empty_cells_while_moving(self):
        bombs = []
        self.player.bomb_capacity = 4
        held = {Keys.SPACE, Keys.D}
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k in held), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            for t in range(0, 500, 16):
                self.player.update(16, self.board, bombs, t)
        cells = {(b.x, b.y) for b in bombs}
        self.assertGreaterEqual(len(bombs), 2)
        self.assertIn((1, 1), cells)
        self.assertIn((2, 1), cells)

    def test_web_space_places_bomb_for_client_player(self):
        self.player.controls = None
        bombs = []
        with patch("bm_classes.is_key_pressed", return_value=False), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.player.update(16, self.board, bombs, 0, web_keys={"space"})
        self.assertEqual(len(bombs), 1)

    def test_cardinal_walk_increments_animation(self):
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.D), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.player.update(16, self.board, [], 0)
        self.assertGreater(self.player.animation_time, 0)
        self.assertGreater(self.player.direction[0], 0)

    def test_web_arrow_moves_client_player(self):
        self.player.controls = None
        start_x = self.player.pos[0]
        with patch("bm_classes.is_key_pressed", return_value=False), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.player.update(50, self.board, [], 0, web_keys={"arrowright"})
        self.assertGreater(self.player.pos[0], start_x)

    def test_wall_blocks_movement(self):
        self.board[1][2] = INDESTRUCTIBLE
        start = self.player.pos.copy()
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.D), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.player.update(400, self.board, [], 0)
        self.assertLess(self.player.pos[0], start[0] + 80)

    def test_players_block_with_the_wall_collision_circle(self):
        board = open_board()
        a = _player(2, 2, name="A")
        b = _player(4, 2, name="B")
        game = types.SimpleNamespace(players=[a, b], flame_blocked_cells=set(), powerups=[])
        a.pos[0], a.pos[1] = b.pos[0], b.pos[1]
        self.assertTrue(a.collides_with_players(game.players))
        b.alive = False
        self.assertFalse(a.collides_with_players(game.players))
        b.alive = True
        a.pos[0], a.pos[1] = cell_center(2, 2)
        b.pos[0], b.pos[1] = cell_center(4, 2)
        reach = a.collision_radius + b.collision_radius
        for _ in range(80):
            with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.D), patch(
                "bm_classes.get_pressed_keys", return_value={}
            ):
                a.update(16, board, [], 0, game=game)
            with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.A), patch(
                "bm_classes.get_pressed_keys", return_value={}
            ):
                b.update(16, board, [], 0, game=game)
        dist = ((float(a.pos[0] - b.pos[0])) ** 2 + (float(a.pos[1] - b.pos[1])) ** 2) ** 0.5
        self.assertGreaterEqual(dist, reach - 1.0)
        self.assertLess(dist, CELL_SIZE * PLAYER_DRAW_SCALE)

    def test_players_pass_through_when_blocking_is_off(self):
        board = open_board()
        a = _player(2, 2, name="A")
        b = _player(3, 2, name="B")
        game = types.SimpleNamespace(players=[a, b], flame_blocked_cells=set(), powerups=[], players_block=False)
        start = float(a.pos[0])
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.D), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            a.update(80, board, [], 0, game=game)
        self.assertGreater(a.pos[0], start + 20)

    def test_quad_damage_expires(self):
        self.player.quad_damage = True
        self.player.quad_damage_start_time = 0
        self.player.bomb_capacity = 1 + QUAD_DAMAGE_POWER
        self.player.fire_power = 1 + QUAD_DAMAGE_POWER
        with patch("bm_classes.is_key_pressed", return_value=False), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.player.update(16, self.board, [], QUAD_DAMAGE_TIME * 1000 + 1)
        self.assertFalse(self.player.quad_damage)
        self.assertEqual(self.player.bomb_capacity, 1)
        self.assertEqual(self.player.fire_power, 1)

    def test_ai_slides_around_corner(self):
        import numpy as np
        self.board[2][2] = INDESTRUCTIBLE
        ai = _player()
        ai.is_ai = True
        ai.pos[0] += 25
        start = ai.pos.copy()
        game = types.SimpleNamespace(
            board=self.board,
            bombs=[],
            explosions=[],
            players=[ai],
            powerups=[],
            current_time=0,
            grid_width=len(self.board[0]),
            grid_height=len(self.board),
        )
        down = np.array([0.0, 1.0], dtype=np.float64)
        with patch("ai_controller.compute_ai_input", return_value=(down, False)):
            for _ in range(30):
                ai.update(16, self.board, [], 0, game=game)
        self.assertGreater(ai.pos[1], start[1] + 8)
        self.assertLess(ai.pos[0], start[0])

    def test_reset_clears_stats_and_position(self):
        self.player.trophies = 3
        self.player.alive = False
        self.player.bomb_capacity = 4
        self.player.pos = __import__("numpy").array(cell_center(4, 4), dtype="float64")
        self.player.reset()
        self.assertTrue(self.player.alive)
        self.assertEqual(self.player.bomb_capacity, 1)
        self.assertEqual(self.player.get_grid_pos(), (1, 1))
        self.assertIsNone(self.player._ai_intent_dir)
        self.assertIsNone(self.player._ai_goal_kind)

    def test_to_dict_has_identity_fields(self):
        self.player.client_id = 7
        self.player.client_player_id = 2
        self.player.is_local = False
        data = self.player.to_dict()
        self.assertEqual(data["name"], "Marv")
        self.assertEqual(data["owner_client_id"], 7)
        self.assertEqual(data["owner_client_player_id"], 2)
        self.assertFalse(data["is_ai"])
        self.assertEqual(data["shield_until"], 0)
        self.player.pickup_message = "+2 FLAMES"
        self.player.pickup_message_end_time = 5000
        labeled = self.player.to_dict()
        self.assertEqual(labeled["pickup_message"], "+2 FLAMES")
        self.assertEqual(labeled["pickup_message_until"], 5000)


class ExplosionLogicTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        self.game = Game()
        self.game.board = open_board(9, 9)
        self.game.grid_width = 9
        self.game.grid_height = 9
        self.game.bombs = []
        self.game.explosions = []
        self.game.powerups = []
        self.game.players = [_player(3, 3)]
        self.game.current_time = 1000
        self.game.round_start_time = 0

    def test_blast_stops_at_indestructible(self):
        self.game.board[3][5] = INDESTRUCTIBLE
        bomb = Bomb(3, 3, 0, 4, self.game.players[0])
        cells = self.game.get_explosion_cells(bomb)
        self.assertIn((3, 3), cells)
        self.assertIn((4, 3), cells)
        self.assertNotIn((5, 3), cells)
        self.assertNotIn((6, 3), cells)

    def test_blast_includes_destructible_then_stops(self):
        self.game.board[3][5] = DESTRUCTIBLE
        bomb = Bomb(3, 3, 0, 4, self.game.players[0])
        cells = self.game.get_explosion_cells(bomb)
        self.assertIn((5, 3), cells)
        self.assertNotIn((6, 3), cells)

    def test_chain_detonates_adjacent_bomb(self):
        owner = self.game.players[0]
        owner.active_bombs = 2
        a = Bomb(3, 3, 0, 2, owner)
        b = Bomb(4, 3, 0, 1, owner)
        self.game.bombs = [a, b]
        triggered = self.game._explode_with_chain([a])
        self.assertGreaterEqual(len(triggered), 2)
        self.assertEqual(self.game.bombs, [])

    def test_handle_explosions_kills_player_on_center(self):
        player = self.game.players[0]
        exp = Explosion([(3, 3)], self.game.current_time - 80, owner=None)
        self.game.explosions = [exp]
        self.game.handle_explosions()
        self.assertFalse(player.alive)
        self.assertEqual(player.death_animation_time, 1000)

    def test_death_detonates_bomb_in_cell(self):
        player = self.game.players[0]
        owner = _player(5, 5, name="Other")
        owner.global_id = 2
        owner.active_bombs = 1
        self.game.players.append(owner)
        bomb = Bomb(3, 3, 0, 1, owner)
        self.game.bombs = [bomb]
        exp = Explosion([(3, 3)], self.game.current_time - 80, owner=None)
        self.game.explosions = [exp]
        self.game.handle_explosions()
        self.assertFalse(player.alive)
        self.assertEqual(self.game.bombs, [])

    def test_soft_wall_cleared_when_arm_covers_it(self):
        self.game.board[3][4] = DESTRUCTIBLE
        exp = Explosion([(3, 3), (4, 3)], self.game.current_time - 80)
        self.game.explosions = [exp]
        self.game.handle_explosions()
        self.assertEqual(self.game.board[3][4], EMPTY)

    def test_opened_wall_stays_solid_until_the_flame_is_gone(self):
        player = self.game.players[0]
        player.pos[0], player.pos[1] = cell_center(5, 3)
        self.game.board[3][4] = DESTRUCTIBLE
        start = 1000
        self.game.current_time = start + 120
        self.game.explosions = [Explosion([(3, 3), (4, 3)], start)]
        self.game.handle_explosions()
        self.assertEqual(self.game.board[3][4], EMPTY)
        self.assertIn((4, 3), self.game.flame_blocked_cells)
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.A), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            for _ in range(40):
                player.update(16, self.game.board, [], self.game.current_time, game=self.game)
                self.game.handle_explosions()
        self.assertTrue(player.alive)
        self.assertEqual(player.get_grid_pos(), (5, 3))
        self.game.current_time = start + EXPLOSION_DURATION + 5
        self.game.handle_explosions()
        self.assertNotIn((4, 3), self.game.flame_blocked_cells)
        with patch("bm_classes.is_key_pressed", side_effect=lambda k: k == Keys.A), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            for _ in range(50):
                player.update(16, self.game.board, [], self.game.current_time, game=self.game)
        self.assertTrue(player.alive)
        self.assertLessEqual(player.get_grid_pos()[0], 4)

    def test_boss_extra_life_stays_in_place(self):
        boss = _player(3, 3, name=BOSS_NAME)
        boss.is_ai = True
        boss.boss_lives_remaining = BOSS_EXTRA_LIVES
        pos_before = [float(boss.pos[0]), float(boss.pos[1])]
        self.game.players = [boss]
        self.game.explosions = [Explosion([(3, 3)], self.game.current_time - 80)]
        self.game.handle_explosions()
        self.assertTrue(boss.alive)
        self.assertEqual(boss.boss_lives_remaining, BOSS_EXTRA_LIVES - 1)
        self.assertEqual([float(boss.pos[0]), float(boss.pos[1])], pos_before)
        self.assertGreater(boss.boss_shield_until, self.game.current_time)
        self.game.handle_explosions()
        self.assertTrue(boss.alive)
        self.game.current_time = boss.boss_shield_until + 1
        self.game.explosions = [Explosion([(3, 3)], self.game.current_time - 80)]
        self.game.handle_explosions()
        self.assertFalse(boss.alive)

    def test_friendly_fire_off_skips_teammate(self):
        owner = _player(2, 3, name="A")
        owner.team = 0
        victim = _player(3, 3, name="B")
        victim.team = 0
        self.game.players = [owner, victim]
        self.game.team_mode_enabled = True
        self.game.friendly_fire = False
        self.game.explosions = [Explosion([(3, 3)], self.game.current_time - 80, owner=owner)]
        self.game.handle_explosions()
        self.assertTrue(victim.alive)

    def test_powerup_pickup_increases_stats(self):
        player = self.game.players[0]
        self.game.powerups = [PowerUp(3, 3, "fire"), PowerUp(4, 3, "bomb")]
        self.game.dt = 0
        with patch("bm_classes.is_key_pressed", return_value=False), patch(
            "bm_classes.get_pressed_keys", return_value={}
        ):
            self.game.update()
        self.assertEqual(player.fire_power, 2)
        # second powerup is adjacent, not on the player cell
        self.assertEqual(player.bomb_capacity, 1)
        self.assertEqual(player.powerups_collected, 1)


class GameStateTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        self.game = Game()

    def test_starts_in_prep(self):
        self.assertEqual(self.game.game_state, "game_prep")
        self.assertGreaterEqual(len(self.game.players), 1)

    def test_to_dict_has_protocol_fields(self):
        payload = self.game.to_dict()
        for key in ("time", "state", "board", "players", "bombs", "explosions", "powerups", "crushing_walls", "local_player_count", "blast_ms"):
            self.assertIn(key, payload)
        self.assertEqual(payload["state"], "game_prep")
        self.assertGreater(payload["blast_ms"], 0)

    def test_create_players_includes_registered_web_client(self):
        self.game.prep_num_players = 1
        self.game._cached_status = {
            "clients": {
                "4": {"registered": True, "players": [2], "display_name": "Webby", "slot": 2}
            },
            "players": {},
        }
        self.game.create_players()
        names = [p.name for p in self.game.players]
        self.assertIn("Webby", names)
        web = next(p for p in self.game.players if p.name == "Webby")
        self.assertFalse(web.is_local)
        self.assertEqual(int(web.client_id), 4)

    def test_enter_on_player_count_does_not_start(self):
        self.game.game_state = "game_prep"
        self.game.prep_section = "local_players"
        self.game.prep_cursor_row = 0
        self.game.prep_cursor_col = 1
        event = types.SimpleNamespace(key=Keys.ENTER, unicode="")
        self.game.handle_prep_key_event(event)
        self.assertEqual(self.game.game_state, "game_prep")
        self.assertEqual(self.game.prep_num_players, 2)

    def test_enter_on_start_section_starts_round(self):
        self.game.game_state = "game_prep"
        self.game.prep_section = "start_game"
        event = types.SimpleNamespace(key=Keys.ENTER, unicode="")
        self.game.handle_prep_key_event(event)
        self.assertEqual(self.game.game_state, "get_ready")
        self.assertTrue(self.game.prep_screen_completed)

    def _prep_key(self, key, unicode=""):
        return types.SimpleNamespace(key=key, unicode=unicode)

    def test_local_name_edit_commits_and_clears_caret(self):
        self.game.prep_num_players = 2
        self.game.prep_ai_count = 0
        self.game.game_state = "game_prep"
        self.game.prep_section = "local_players"
        self.game.prep_cursor_row = PREP_ROW_PLAYERS
        original = self.game.prep_player_names[0]
        self.game.handle_prep_key_event(self._prep_key(Keys.ENTER, "\r"))
        self.assertTrue(self.game.prep_editing_name)
        self.game.handle_prep_key_event(self._prep_key(Keys.BACKSPACE))
        self.game.handle_prep_key_event(self._prep_key(0, "t"))
        self.game.handle_prep_key_event(self._prep_key(Keys.ENTER, "\r"))
        self.assertFalse(self.game.prep_editing_name)
        self.assertFalse(self.game.team_mode_enabled)
        renamed = self.game.get_all_players_info()[0]["name"]
        self.assertEqual(renamed, original[:-1] + "t")
        self.assertFalse(renamed.endswith("_"))
        self.assertNotIn("\r", renamed)
        self.game.handle_prep_key_event(self._prep_key(Keys.DOWN))
        self.assertFalse(self.game.prep_editing_name)
        self.assertNotEqual(self.game.prep_cursor_row, PREP_ROW_PLAYERS)
        self.assertEqual(self.game.get_all_players_info()[0]["name"], renamed)

    def test_web_name_edit_commits_and_clears_caret(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 0
        self.game._cached_status = {
            "clients": {
                "4": {"registered": True, "players": [2], "display_name": "Webby", "slot": 2}
            },
            "players": {},
        }
        self.game.game_state = "game_prep"
        self.game.prep_section = "local_players"
        infos = self.game.get_all_players_info()
        web_index = next(i for i, info in enumerate(infos) if info["type"] == "client")
        self.game.prep_cursor_row = PREP_ROW_PLAYERS + web_index
        self.game.handle_prep_key_event(self._prep_key(Keys.ENTER, "\r"))
        self.assertTrue(self.game.prep_editing_name)
        self.assertEqual(self.game.prep_name_edit_index, web_index)
        self.game.handle_prep_key_event(self._prep_key(0, "X"))
        self.game.handle_prep_key_event(self._prep_key(Keys.ENTER, "\r"))
        self.assertFalse(self.game.prep_editing_name)
        renamed = self.game.get_all_players_info()[web_index]["name"]
        self.assertEqual(renamed, "WebbyX")
        self.assertFalse(renamed.endswith("_"))
        self.game.handle_prep_key_event(self._prep_key(Keys.UP))
        self.assertFalse(self.game.prep_editing_name)
        self.assertEqual(self.game.get_all_players_info()[web_index]["name"], "WebbyX")

    def test_two_living_players_do_not_end_the_round(self):
        players = self.game.players[:2]
        self.assertGreaterEqual(len(players), 2)
        for player in self.game.players:
            player.alive = player in players
            player.team = 0
        self.game.team_mode_enabled = True
        self.game.game_state = "playing"
        self.game.current_time = 8000
        self.game.game_start_time = 0
        self.game.endgame_hold_until = None
        self.game.post_win_target_state = None
        trophies = [player.trophies for player in self.game.players]
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertIsNone(self.game.endgame_hold_until)
        self.assertIsNone(self.game.post_win_target_state)
        self.assertEqual(self.game.game_state, "playing")
        self.assertTrue(all(player.alive for player in players))
        self.assertEqual([player.trophies for player in self.game.players], trophies)

    def test_one_survivor_wins_and_all_dead_is_a_draw(self):
        survivor, other = self.game.players[0], self.game.players[1]
        for player in self.game.players:
            player.alive = player is survivor
            player.trophies = 0
        self.game.team_mode_enabled = True
        survivor.team = 0
        other.team = 0
        self.game.game_state = "playing"
        self.game.current_time = 4000
        self.game.endgame_hold_until = 0
        self.game.post_win_target_state = None
        self.game.death_events = [1000]
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(survivor.trophies, 1)
        self.assertEqual(other.trophies, 0)
        self.assertEqual(self.game.post_win_target_state, "win")

        for player in self.game.players:
            player.alive = False
            player.trophies = 0
        self.game.post_win_target_state = None
        self.game.post_win_transition_time = None
        self.game.endgame_hold_until = 0
        self.game.game_state = "playing"
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertTrue(all(player.trophies == 0 for player in self.game.players))
        self.assertEqual(self.game.post_win_target_state, "win")

    def test_tab_switches_prep_section(self):
        self.game.prep_section = "local_players"
        self.game.handle_prep_key_event(types.SimpleNamespace(key=Keys.TAB, unicode=""))
        self.assertEqual(self.game.prep_section, "start_game")

    def test_reset_trophies_clears_totals(self):
        p = self.game.players[0]
        p.trophies = 4
        p.total_cells_walked = 12
        p.cells_walked = 3
        self.game.reset_trophies()
        self.assertEqual(p.trophies, 0)
        self.assertEqual(p.total_cells_walked, 0)
        self.assertEqual(p.cells_walked, 0)

    def test_get_ticks_matches_clock(self):
        self.assertIsInstance(self.game.get_ticks(), int)

    def test_log_replay_if_due_records_snapshot(self):
        self.game.game_state = "playing"
        self.game.current_time = REPLAY_LOG_INTERVAL_MS + 5
        self.game.last_replay_log_time = 0
        self.game.log_replay_if_due()
        self.assertEqual(len(self.game.replay_buffer), 1)
        self.game.log_replay_if_due()
        self.assertEqual(len(self.game.replay_buffer), 1)

    def test_replay_snapshot_shape(self):
        snap = build_replay_snapshot(self.game)
        self.assertIn("players", snap)
        self.assertIn("bombs", snap)
        self.assertIn("t", snap)
        self.assertIn("board", snap)
        self.assertIn("direction", snap["players"][0])

    def test_kill_cams_are_frozen_in_death_order(self):
        first = _player(1, 1, name="First")
        second = _player(3, 3, name="Second")
        self.game.players = [first, second]
        self.game.game_state = "playing"
        self.game.replay_buffer = []
        self.game.kill_cam_clips = []
        self.game._pending_kill_cams = []
        for t in range(0, 4000, REPLAY_LOG_INTERVAL_MS):
            self.game.current_time = t
            self.game.last_replay_log_time = t - REPLAY_LOG_INTERVAL_MS
            self.game.log_replay_if_due()
        first.alive = False
        first.death_time_ms = 1200
        self.game.current_time = 1200
        self.game._queue_kill_cam(first)
        second.alive = False
        second.death_time_ms = 2800
        self.game.current_time = 2800
        self.game._queue_kill_cam(second)
        self.game.current_time = 2800 + REPLAY_KILLCAM_POST_MS
        self.game._flush_kill_cams(force=True)
        names = [clip["name"] for clip in self.game.kill_cam_clips]
        self.assertEqual(names, ["First", "Second"])
        self.assertGreaterEqual(self.game.kill_cam_clips[0]["end"] - 1200, REPLAY_KILLCAM_POST_MS)
        self.assertGreaterEqual(self.game.kill_cam_clips[1]["end"] - 2800, REPLAY_KILLCAM_POST_MS)

    def test_count_cells(self):
        self.game.board = open_board(5, 5)
        self.game.grid_width = 5
        self.game.grid_height = 5
        self.game.board[2][2] = DESTRUCTIBLE
        self.assertEqual(self.game.count_destroyable_cells(), 1)
        self.assertGreater(self.game.count_empty_cells(), 0)

    def test_boss_winner_only_in_boss_result(self):
        self.game.game_state = "playing"
        self.game.boss_fight_winner = self.game.players[0]
        self.assertIsNone(self.game._serialize_boss_winner())
        self.game.game_state = "boss_result"
        winner = self.game._serialize_boss_winner()
        self.assertEqual(winner["name"], self.game.players[0].name)

    def test_init_boss_fight_adds_ai(self):
        champion = self.game.players[0]
        champion.walls_destroyed = 7
        champion.total_walls_destroyed = 3
        champion.players_killed = 2
        self.game.init_boss_fight(champion)
        self.assertEqual(len(self.game.players), 2)
        boss = next(p for p in self.game.players if getattr(p, "is_ai", False))
        self.assertEqual(boss.name, BOSS_NAME)
        self.assertEqual(tuple(boss.color), tuple(BOSS_COLOR))
        self.assertEqual(boss.boss_lives_remaining, BOSS_EXTRA_LIVES)
        self.assertEqual(self.game.grid_width, get_grid_size(is_boss_fight=True))
        self.assertEqual(self.game.grid_width, 15)
        self.assertEqual(len(self.game.board), 15)
        self.assertEqual(len(self.game.board[0]), 15)
        champ = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        self.assertEqual(champ.total_walls_destroyed, 10)
        self.assertEqual(champ.walls_destroyed, 0)
        self.assertEqual(champ.total_players_killed, 2)
        self.assertEqual(boss.sprite, "cleaver")

    def test_beating_bombermarv_starts_brabi(self):
        champion = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        self.game.init_boss_fight(champion)
        self.game.game_state = "boss_fight"
        boss = next(p for p in self.game.players if getattr(p, "is_ai", False))
        champ = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        boss.alive = False
        champ.alive = True
        self.game.current_time = self.game.game_start_time + 5000
        self.game.endgame_hold_until = self.game.current_time - 1
        self.game.post_win_target_state = None
        self.game.post_win_transition_time = None
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(self.game.boss_stage, "bombermarv")
        self.assertEqual(self.game.boss_advance, "brabi")
        self.assertEqual(self.game.post_win_target_state, "boss_result")
        self.game.current_time = self.game.post_win_transition_time
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(self.game.game_state, "boss_result")
        self.assertIn(UBER_BOSS_NAME, self.game.result_prompt())
        self.game.continue_from_intermission()
        brabi = next(p for p in self.game.players if getattr(p, "is_ai", False))
        self.assertEqual(self.game.game_state, "boss_fight")
        self.assertEqual(brabi.name, UBER_BOSS_NAME)
        self.assertEqual(brabi.sprite, "brabi")
        self.assertEqual(brabi.fire_power, UBER_BOSS_START_FIRE_POWER)
        self.assertEqual(brabi.bomb_capacity, UBER_BOSS_START_BOMB_CAPACITY)
        self.assertEqual(brabi.boss_lives_remaining, UBER_BOSS_EXTRA_LIVES)
        self.assertEqual(brabi.speed, int(PLAYER_SPEED * UBER_BOSS_SPEED_MULTIPLIER))
        self.assertEqual(brabi.draw_scale, UBER_BOSS_DRAW_SCALE)
        base_radius = int(CELL_SIZE * PLAYER_DRAW_SCALE / 2)
        self.assertEqual(brabi.draw_radius, int(base_radius * UBER_BOSS_DRAW_SCALE))
        self.assertGreater(brabi.draw_radius, champ.draw_radius)

    def test_boss_loss_returns_to_the_lobby(self):
        champion = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        self.game.init_boss_fight(champion)
        self.game.game_state = "boss_fight"
        champ = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        champ.alive = False
        self.game.current_time = self.game.game_start_time + 5000
        self.game.endgame_hold_until = self.game.current_time - 1
        self.game.post_win_target_state = None
        self.game.post_win_transition_time = None
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(self.game.boss_advance, "lobby")
        self.assertEqual(self.game.post_win_target_state, "boss_result")
        self.game.game_state = "boss_result"
        self.assertIn("lobby", self.game.result_prompt())
        self.assertTrue(self.game.continue_from_intermission())
        self.assertEqual(self.game.game_state, "game_prep")

    def test_solo_start_opens_the_boss_fight(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 0
        self.game._cached_status = None
        self.game.game_state = "game_prep"
        self.assertTrue(self.game.start_match_from_lobby())
        self.assertEqual(self.game.game_state, "boss_fight")
        names = [p.name for p in self.game.players]
        self.assertIn(BOSS_NAME, names)
        self.assertEqual(sum(1 for p in self.game.players if getattr(p, "is_ai", False)), 1)

    def test_alt_k_l_kills_opponents(self):
        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        human.is_local = True
        for p in self.game.players:
            p.alive = True
        self.game.game_state = "playing"
        self.game.current_time = 1000
        self.game.round_start_time = 0
        held = {Keys.LALT, Keys.K, Keys.L}

        def _down(code):
            return code in held

        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", side_effect=_down
        ):
            self.game.update()
        self.assertTrue(human.alive)
        self.assertTrue(all(not p.alive for p in self.game.players if p is not human))
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", side_effect=_down
        ):
            self.game.update()
        self.assertTrue(human.alive)

    def test_alt_k_l_from_key_events_when_pressed_state_misses_alt(self):
        import pygame
        from input_abstraction import clear_noted_keys, note_key_event

        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        human.is_local = True
        for p in self.game.players:
            p.alive = True
        self.game.game_state = "playing"
        self.game.current_time = 1000
        self.game.round_start_time = 0
        try:
            note_key_event(types.SimpleNamespace(type=pygame.KEYDOWN, key=int(Keys.LALT), mod=0))
            note_key_event(types.SimpleNamespace(type=pygame.KEYDOWN, key=int(Keys.K), mod=pygame.KMOD_ALT))
            note_key_event(types.SimpleNamespace(type=pygame.KEYDOWN, key=int(Keys.L), mod=pygame.KMOD_ALT))
            with patch("bm_classes.get_pressed_keys", return_value={}), patch(
                "bm_classes.is_key_pressed", return_value=False
            ), patch("pygame.key.get_mods", return_value=0):
                self.game.update()
            self.assertTrue(human.alive)
            self.assertTrue(all(not p.alive for p in self.game.players if p is not human))
        finally:
            clear_noted_keys()

    def test_web_set_input_state_maps_keys(self):
        player = _player()
        player.is_local = False
        player.client_id = 3
        player.client_player_id = 1
        self.game.players = [player]
        self.game.handle_web_key_event(
            {
                "type": "set_input_state",
                "client_id": 3,
                "player_id": 1,
                "keys": {"up": 1, "down": 0, "left": 0, "right": 1, "bomb": 1},
            }
        )
        keys = self.game.web_keys_by_player[player]
        self.assertEqual(keys, {"arrowup", "arrowright", "space"})

    def test_web_enter_from_prep_starts_round(self):
        player = _player()
        player.is_local = False
        player.client_id = 1
        player.client_player_id = 1
        self.game.players = [player]
        self.game.game_state = "game_prep"
        self.game.handle_web_key_event(
            {"type": "keydown", "key": "Enter", "client_id": 1, "player_id": 1}
        )
        self.assertEqual(self.game.game_state, "get_ready")

    def test_crushing_walls_place_indestructible(self):
        self.game.board = open_board(7, 7)
        self.game.grid_width = 7
        self.game.grid_height = 7
        self.game.players = [_player(3, 3)]
        self.game.starting_player_count = 3
        self.game.game_state = "playing"
        self.game.game_start_time = 0
        self.game.current_time = 120_000
        self.game.handle_crushing_walls()
        self.assertTrue(self.game.crushing_walls_active)
        self.game.crushing_walls_last_time = 0
        self.game.handle_crushing_walls()
        self.assertGreater(self.game.crushing_walls_index, 0)

    def test_crushing_walls_two_player_start_waits_180s(self):
        self.game.board = open_board(7, 7)
        self.game.grid_width = 7
        self.game.grid_height = 7
        other = _player(5, 5, name="Sobi")
        other.global_id = 2
        self.game.players = [_player(3, 3), other]
        self.game.starting_player_count = 2
        self.game.game_state = "playing"
        self.game.game_start_time = 0
        self.game.current_time = 179_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        self.game.current_time = 180_000
        self.game.handle_crushing_walls()
        self.assertTrue(self.game.crushing_walls_active)

    def test_crushing_walls_not_before_120s(self):
        self.game.board = open_board(7, 7)
        self.game.grid_width = 7
        self.game.grid_height = 7
        other = _player(5, 5, name="Sobi")
        other.global_id = 2
        self.game.players = [_player(3, 3), other]
        self.game.starting_player_count = 3
        self.game.game_state = "playing"
        self.game.game_start_time = 0
        self.game.current_time = 119_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        self.game.current_time = 120_000
        self.game.handle_crushing_walls()
        self.assertTrue(self.game.crushing_walls_active)

    def test_boss_crushing_walls_wait_180s(self):
        self.game.board = open_board(7, 7)
        self.game.grid_width = 7
        self.game.grid_height = 7
        other = _player(5, 5, name="BomberMarv")
        other.global_id = 2
        self.game.players = [_player(3, 3), other]
        self.game.starting_player_count = 2
        self.game.destructible_at_round_start = 0
        self.game.game_state = "boss_fight"
        self.game.game_start_time = 0
        self.game.current_time = 120_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        self.game.current_time = 179_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        self.game.current_time = 180_000
        self.game.handle_crushing_walls()
        self.assertTrue(self.game.crushing_walls_active)

    def test_stale_map_starts_walls_after_double_timer(self):
        board = open_board(9, 9)
        for y in range(2, 6):
            for x in range(2, 6):
                board[y][x] = DESTRUCTIBLE
        self.game.board = board
        self.game.grid_width = 9
        self.game.grid_height = 9
        players = []
        for i, (x, y) in enumerate(((1, 1), (7, 1), (1, 7), (7, 7))):
            player = _player(x, y, name=f"P{i}")
            player.global_id = i + 1
            players.append(player)
        self.game.players = players
        self.game.starting_player_count = 4
        self.game.destructible_at_round_start = 100
        self.game.game_state = "playing"
        self.game.game_start_time = 0
        self.game.crushing_walls_active = False
        self.game.current_time = 120_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        # 16 of 100 is not under 15%, so 1.5x (180s) still waits.
        self.game.current_time = 180_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        board[2][2] = EMPTY
        board[2][3] = EMPTY
        self.game.current_time = 179_000
        self.game.handle_crushing_walls()
        self.assertFalse(self.game.crushing_walls_active)
        self.game.current_time = 180_000
        self.game.handle_crushing_walls()
        self.assertTrue(self.game.crushing_walls_active)
        board[2][2] = DESTRUCTIBLE
        board[2][3] = DESTRUCTIBLE
        self.game.crushing_walls_active = False
        self.game.current_time = 240_000
        self.game.handle_crushing_walls()
        self.assertTrue(self.game.crushing_walls_active)

    def test_init_game_uses_two_player_grid(self):
        self.game.prep_num_players = 2
        self.game.prep_ai_count = 0
        self.game._cached_status = None
        self.game.init_game()
        self.assertEqual(self.game.grid_width, get_grid_size(2))

    def test_solo_default_includes_ai(self):
        self.assertGreaterEqual(self.game.prep_ai_count, 1)
        ais = [p for p in self.game.players if getattr(p, "is_ai", False)]
        humans = [p for p in self.game.players if not getattr(p, "is_ai", False)]
        self.assertEqual(len(humans), 1)
        self.assertGreaterEqual(len(ais), 1)

    def test_three_trophies_schedules_champion_not_boss(self):
        from bm_params import TROPHY_WIN_THRESHOLD
        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        for p in self.game.players:
            p.alive = p is human
        human.trophies = TROPHY_WIN_THRESHOLD - 1
        self.game.game_state = "playing"
        self.game.current_time = 2000
        self.game.endgame_hold_until = 0
        self.game.post_win_target_state = None
        self.game.death_events = [1000]
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(human.trophies, TROPHY_WIN_THRESHOLD)
        self.assertEqual(self.game.post_win_target_state, "champion")

    def test_ai_trophy_goal_schedules_champion(self):
        ai = next(p for p in self.game.players if getattr(p, "is_ai", False))
        for p in self.game.players:
            p.alive = p is ai
        ai.trophies = self.game.trophy_threshold() - 1
        self.game.game_state = "playing"
        self.game.current_time = 2000
        self.game.endgame_hold_until = 0
        self.game.post_win_target_state = None
        self.game.death_events = [1000]
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(ai.trophies, self.game.trophy_threshold())
        self.assertEqual(self.game.post_win_target_state, "champion")
        self.assertIs(self.game.champion_player(), ai)

    def test_champion_continue_starts_boss_fight(self):
        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        for p in self.game.players:
            p.alive = p is human
        self.game.game_state = "champion"
        self.game.continue_from_champion()
        self.assertEqual(self.game.game_state, "boss_fight")
        self.assertEqual(len(self.game.players), 2)
        boss = next(p for p in self.game.players if getattr(p, "is_ai", False))
        self.assertEqual(getattr(boss, "ai_role", ""), "boss")

    def test_ai_champion_starts_boss_fight(self):
        ai = next(p for p in self.game.players if getattr(p, "is_ai", False))
        for p in self.game.players:
            p.alive = p is ai
            p.trophies = 0
        ai.trophies = 3
        self.game.game_state = "champion"
        self.assertIs(self.game.champion_player(), ai)
        self.game.continue_from_champion()
        self.assertEqual(self.game.game_state, "boss_fight")
        self.assertEqual(len(self.game.players), 2)
        champion = next(p for p in self.game.players if p.name == ai.name)
        self.assertTrue(getattr(champion, "is_ai", False))
        self.assertNotEqual(getattr(champion, "ai_role", ""), "boss")
        boss = next(p for p in self.game.players if getattr(p, "ai_role", "") == "boss")
        self.assertEqual(boss.name, BOSS_NAME)
        self.assertIsNot(champion, boss)

    def test_lobby_arena_offset_overrides_default_size(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 2
        self.game._cached_status = None
        self.game.game_state = "game_prep"
        self.game.prep_section = "local_players"
        self.game.prep_cursor_row = 3
        self.game.prep_cursor_col = 5
        self.game.handle_prep_key_event(types.SimpleNamespace(key=Keys.ENTER, unicode=""))
        self.assertEqual(self.game.grid_offset(), 4)
        self.game.init_game()
        self.assertEqual(len(self.game.players), 3)
        self.assertEqual(self.game.grid_width, 21)
        self.assertEqual(self.game.grid_height, 21)

    def test_reset_series_clears_trophies_and_restarts(self):
        for p in self.game.players:
            p.trophies = 3
            p.total_cells_walked = 9
        self.game.game_state = "champion"
        self.game.reset_series_and_start()
        self.assertEqual(self.game.game_state, "get_ready")
        self.assertTrue(all(p.trophies == 0 for p in self.game.players))
        self.assertTrue(all(p.total_cells_walked == 0 for p in self.game.players))

    def test_ai_trophies_persist_across_rounds(self):
        ai = next(p for p in self.game.players if getattr(p, "is_ai", False))
        ai.trophies = 2
        ai.ai_personality = "cautious"
        self.game.init_game()
        restored = next(p for p in self.game.players if getattr(p, "is_ai", False))
        self.assertEqual(restored.trophies, 2)
        self.assertEqual(restored.ai_personality, "cautious")

    def test_adding_an_ai_rolls_only_the_new_personality(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 1
        self.game.prep_ai_names = ["Steady CPU"]
        self.game.prep_ai_personalities = ["normal"]
        with patch("ai_controller.roll_cpu_personality", return_value="crazy"):
            self.game.prep_ai_count = 2
            infos = [p for p in self.game.get_all_players_info() if p["type"] == "ai"]
        self.assertEqual([p["personality"] for p in infos], ["normal", "crazy"])
        self.game.prep_ai_count = 1
        kept = [p for p in self.game.get_all_players_info() if p["type"] == "ai"]
        self.assertEqual(kept[0]["personality"], "normal")
        self.game.create_players()
        cpu = next(p for p in self.game.players if getattr(p, "is_ai", False))
        self.assertEqual(cpu.ai_personality, "normal")

    def test_result_prompt_offers_reset(self):
        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        for p in self.game.players:
            p.alive = p is human
        self.game.game_state = "champion"
        prompt = self.game.result_prompt()
        self.assertIn(BOSS_NAME, prompt)
        self.assertIn("reset", prompt.lower())
        payload = self.game.to_dict()
        self.assertEqual(payload["trophy_win_threshold"], 3)
        self.assertEqual(payload["result_prompt"], prompt)

    def test_lobby_trophy_threshold_is_selectable(self):
        self.game.game_state = "game_prep"
        self.game.prep_section = "local_players"
        self.game.prep_cursor_row = 2
        self.game.prep_cursor_col = 0
        self.game.handle_prep_key_event(types.SimpleNamespace(key=Keys.ENTER, unicode=""))
        self.assertEqual(self.game.trophy_threshold(), 1)
        self.game.prep_cursor_col = 4
        self.game.handle_prep_key_event(types.SimpleNamespace(key=Keys.ENTER, unicode=""))
        self.assertEqual(self.game.trophy_threshold(), 5)
        self.assertEqual(self.game.to_dict()["trophy_win_threshold"], 5)
        self.assertEqual(self.game.game_state, "game_prep")

    def test_eight_players_use_large_grid_and_unique_spawns(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 7
        self.game._cached_status = None
        self.game.init_game()
        self.assertEqual(len(self.game.players), 8)
        self.assertEqual(self.game.grid_width, get_grid_size(8))
        self.assertEqual(self.game.grid_width, 21)
        cells = [(p.start_grid_x, p.start_grid_y) for p in self.game.players]
        self.assertEqual(len(set(cells)), 8)

    def test_five_and_four_player_grid_sizes(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 4
        self.game._cached_status = None
        self.game.init_game()
        self.assertEqual(len(self.game.players), 5)
        self.assertEqual(self.game.grid_width, 19)
        self.game.prep_ai_count = 3
        self.game.init_game()
        self.assertEqual(len(self.game.players), 4)
        self.assertEqual(self.game.grid_width, 17)

    def test_boss_fight_uses_small_grid_after_large_ffa(self):
        self.game.prep_num_players = 1
        self.game.prep_ai_count = 7
        self.game._cached_status = None
        self.game.init_game()
        self.assertEqual(self.game.grid_width, 21)
        champion = self.game.players[0]
        self.game.init_boss_fight(champion)
        self.assertEqual(self.game.grid_width, 15)
        self.assertEqual(self.game.grid_height, 15)
        self.assertEqual(len(self.game.board), 15)
        self.assertEqual(len(self.game.board[0]), 15)
        self.assertEqual(len(self.game.players), 2)

    def test_local_eight_clamps_ai_to_zero(self):
        self.game.prep_section = "local_players"
        self.game.prep_cursor_row = 0
        self.game.prep_cursor_col = MAX_PLAYERS - 1
        self.game.prep_ai_count = 3
        self.game.handle_prep_key_event(types.SimpleNamespace(key=Keys.ENTER, unicode=""))
        self.assertEqual(self.game.prep_num_players, 8)
        self.assertEqual(self.game.prep_ai_count, 0)
        self.assertEqual(len(self.game.players), 8)

    def test_custom_trophy_goal_schedules_champion(self):
        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        for p in self.game.players:
            p.alive = p is human
        human.trophies = 0
        self.game.prep_trophy_threshold = 1
        self.game.game_state = "playing"
        self.game.current_time = 2000
        self.game.endgame_hold_until = 0
        self.game.post_win_target_state = None
        self.game.death_events = [1000]
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(human.trophies, 1)
        self.assertEqual(self.game.post_win_target_state, "champion")

    def test_champion_screen_renders(self):
        import pygame
        from bm_drawing import draw_champion_screen
        pygame.font.init()
        surface = pygame.Surface((1280, 800))
        champ = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        draw_champion_screen(surface, champ, self.game.players, self.game)
        self.assertNotEqual(surface.get_at((20, 20))[:3], (0, 0, 0))

    def test_champion_screen_draws_stats_and_replays(self):
        import pygame
        from unittest.mock import patch
        pygame.font.init()
        surface = pygame.Surface((1280, 800))
        champ = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        with patch("bm_drawing.draw_stat_screen") as mock_stats:
            from bm_drawing import draw_champion_screen
            draw_champion_screen(surface, champ, self.game.players, self.game)
        mock_stats.assert_called_once()
        args, kwargs = mock_stats.call_args
        self.assertIs(args[1], champ)
        self.assertEqual(list(args[2]), list(self.game.players))
        self.assertIn("Champion", kwargs.get("heading") or "")

    def test_champion_boss_card_is_top_right(self):
        from bm_drawing import champion_boss_card_rect
        rect = champion_boss_card_rect(1280, 720)
        self.assertLess(rect.y, 40)
        self.assertLess(rect.bottom, int(720 * 0.34))
        self.assertGreater(rect.width, 450)
        self.assertLess(rect.width, 560)
        self.assertGreater(rect.height, 180)
        self.assertGreater(rect.x, 1280 * 0.5)
        self.assertLessEqual(rect.right, 1280)

    def test_brabi_win_draws_an_invite_card(self):
        import pygame
        from bm_drawing import champion_boss_card_rect, draw_boss_result_screen
        pygame.font.init()
        surface = pygame.Surface((1280, 800))
        surface.fill((12, 14, 18))
        human = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        self.game.boss_advance = "brabi"
        self.game.boss_fight_winner = human
        self.game.game_state = "boss_result"
        draw_boss_result_screen(surface, human, self.game.players, self.game)
        card = champion_boss_card_rect(1280, 800)
        fill = surface.get_at((card.x + 24, card.y + 24))
        self.assertEqual(fill[:3], (24, 28, 38))
        green = False
        for y in range(card.y + 4, card.y + card.height // 2):
            pixel = surface.get_at((card.centerx, y))
            if pixel[1] > 150 and pixel[1] > pixel[0] + 40:
                green = True
                break
        self.assertTrue(green)
        self.game.boss_advance = "lobby"
        surface.fill((12, 14, 18))
        draw_boss_result_screen(surface, human, self.game.players, self.game)
        plain = surface.get_at((card.x + 24, card.y + 24))
        self.assertNotEqual(plain[:3], (24, 28, 38))

    def test_beating_bombertom_grants_marv_killer(self):
        import pygame
        from bm_drawing import draw_boss_result_screen, marv_killer_banner_rect
        champion = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        self.game.init_boss_fight(champion, uber=True)
        self.game.game_state = "boss_fight"
        boss = next(p for p in self.game.players if getattr(p, "is_ai", False))
        champ = next(p for p in self.game.players if not getattr(p, "is_ai", False))
        boss.alive = False
        boss.boss_lives_remaining = 0
        champ.alive = True
        self.game.current_time = self.game.game_start_time + 5000
        self.game.endgame_hold_until = self.game.current_time - 1
        self.game.post_win_target_state = None
        self.game.post_win_transition_time = None
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.game.current_time = self.game.post_win_transition_time
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            self.game.update()
        self.assertEqual(self.game.game_state, "boss_result")
        self.assertTrue(self.game.marv_killer_result())
        heading, detail, _color, prompt = self.game.boss_result_copy()
        self.assertEqual(heading, "You win")
        self.assertIn(MARV_KILLER_TITLE, detail)
        self.assertIn(champ.name, detail)
        self.assertIn("lobby", prompt)
        self.assertIn(champ.name, self.game.marv_killer_names)
        self.assertEqual(champ.title, MARV_KILLER_TITLE)
        pygame.font.init()
        surface = pygame.Surface((1280, 800))
        draw_boss_result_screen(surface, champ, self.game.players, self.game)
        banner = marv_killer_banner_rect(1280, 800)
        gold = surface.get_at((banner.centerx, banner.y + 2))
        self.assertGreater(gold[0], 180)
        self.assertGreater(gold[1], 140)
        self.assertTrue(self.game.continue_from_intermission())
        self.assertEqual(self.game.game_state, "game_prep")
        titled = next(p for p in self.game.get_all_players_info() if p["name"] == champ.name)
        self.assertEqual(titled["title"], MARV_KILLER_TITLE)

    def test_get_ready_banner_stays_off_corner_spawns(self):
        from bm_drawing import get_ready_banner_rect
        banner = get_ready_banner_rect(1900, 1900)
        self.assertGreater(banner.y, 200)
        self.assertLess(banner.bottom, 1700)
        self.assertEqual(banner.width, 1900)

    def test_player_name_font_stays_smaller_than_a_cell(self):
        from bm_drawing import player_label_font_size
        size = player_label_font_size(42)
        self.assertGreaterEqual(size, 13)
        self.assertLessEqual(size, 26)


class GameSimulateTests(unittest.TestCase):
    def setUp(self):
        silence_sounds()
        keys_patch = patch("bm_classes.get_pressed_keys", return_value={})
        keys_patch.start()
        self.addCleanup(keys_patch.stop)
        self.game = Game()

    def test_get_ready_becomes_playing_without_sleeping(self):
        self.game.game_state = "get_ready"
        self.game.game_start_time = 1000
        second = self.game.simulate(16, now_ms=1000)
        self.assertEqual(self.game.game_state, "playing")
        self.assertEqual(self.game.dt, 16)
        self.assertEqual(self.game.current_time, 1000)
        self.assertEqual(second, 0)

    def test_get_ready_reports_countdown_before_start(self):
        self.game.game_state = "get_ready"
        self.game.game_start_time = 3000
        second = self.game.simulate(16, now_ms=1000)
        self.assertEqual(self.game.game_state, "get_ready")
        self.assertEqual(second, 2)

    def test_tick_wrapper_uses_simulate_not_clock_sleep(self):
        self.game.game_state = "game_prep"
        with patch.object(self.game.clock, "tick", side_effect=AssertionError("host owns the clock")):
            self.game.tick(16, now_ms=50)
        self.assertEqual(self.game.current_time, 50)
        self.assertEqual(self.game.dt, 16)

    def test_playing_simulate_moves_web_player(self):
        player = _player()
        player.is_local = False
        player.client_id = 4
        player.client_player_id = 1
        player.controls = None
        start_x = float(player.pos[0])
        self.game.board = open_board(9, 9)
        self.game.grid_width = 9
        self.game.grid_height = 9
        self.game.players = [player]
        self.game.game_state = "playing"
        self.game.bombs = []
        self.game.explosions = []
        self.game.powerups = []
        self.game.handle_web_key_event(
            {"type": "set_input_state", "client_id": 4, "player_id": 1, "keys": {"right": 1}}
        )
        self.game.simulate(200, now_ms=1000)
        self.assertGreater(float(player.pos[0]), start_x)


class ExplosionEntityTests(unittest.TestCase):
    def test_is_active_window(self):
        exp = Explosion([(1, 1)], 100)
        self.assertTrue(exp.is_active(100 + EXPLOSION_DURATION - 1))
        self.assertFalse(exp.is_active(100 + EXPLOSION_DURATION))

    def test_to_dict_includes_owner(self):
        owner = _player()
        owner.global_id = 8
        exp = Explosion([(1, 1)], 0, owner=owner)
        self.assertEqual(exp.to_dict()["owner_player_id"], 8)


if __name__ == "__main__":
    unittest.main()

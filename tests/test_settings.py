import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from helpers import open_board, silence_sounds

silence_sounds()

import bm_settings
from bm_classes import Bomb, Explosion, Game, PowerUp
from bm_params import DESTRUCTIBLE, EMPTY
from input_abstraction import Keys


class MatchSettingsTests(unittest.TestCase):
    def tearDown(self):
        bm_settings.reset_defaults()

    def test_players_block_defaults_on_and_toggles(self):
        game = Game()
        self.assertTrue(game.players_block)
        self.assertFalse(game.friendly_fire)
        game.prep_section = "settings"
        game.settings_cursor = 0
        game.handle_prep_key_event(type("E", (), {"key": Keys.ENTER, "unicode": ""})())
        self.assertFalse(game.players_block)
        self.assertFalse(bm_settings.get("players_block"))

    def test_s_opens_settings_from_the_lobby(self):
        game = Game()
        game.prep_section = "local_players"
        game.handle_prep_key_event(type("E", (), {"key": Keys.S, "unicode": "s"})())
        self.assertEqual(game.prep_section, "settings")
        game.handle_prep_key_event(type("E", (), {"key": Keys.ESCAPE, "unicode": ""})())
        self.assertEqual(game.prep_section, "local_players")

    def test_speed_step_is_saved_and_reloaded(self):
        handle = tempfile.NamedTemporaryFile(prefix="bm-settings-", suffix=".json", delete=False)
        handle.close()
        try:
            with patch.dict(os.environ, {"BOMBERMARV_SETTINGS": handle.name}), patch(
                "bm_settings._disk_enabled", return_value=True
            ):
                bm_settings.reset_defaults()
                bm_settings.set_value("speed_multiplier", 1.4)
                bm_settings.set_value("players_block", False)
                self.assertTrue(bm_settings.save())
                bm_settings.reset_defaults()
                bm_settings.load()
                self.assertEqual(bm_settings.get("speed_multiplier"), 1.4)
                self.assertFalse(bm_settings.get("players_block"))
        finally:
            try:
                os.remove(handle.name)
            except OSError:
                pass
            bm_settings.reset_defaults()


def _event(key, text=""):
    return type("E", (), {"key": key, "unicode": text})()


class EverySettingTests(unittest.TestCase):
    def tearDown(self):
        bm_settings.reset_defaults()

    def test_each_row_changes_from_the_lobby_and_resets(self):
        game = Game()
        game.prep_section = "settings"
        for index, (key, _label, _kind, default, *_rest) in enumerate(bm_settings.RULES):
            with self.subTest(key=key):
                bm_settings.reset_defaults()
                game.apply_match_rules()
                game.settings_cursor = index
                before = bm_settings.get(key)
                game.handle_prep_key_event(_event(Keys.RIGHT))
                if bm_settings.get(key) == before:
                    game.handle_prep_key_event(_event(Keys.LEFT))
                self.assertNotEqual(bm_settings.get(key), before)
                game.handle_prep_key_event(_event(Keys.R, "r"))
                self.assertEqual(bm_settings.get(key), default)

    def test_each_numeric_rule_clamps(self):
        for key, _label, kind, default, low, high, step in bm_settings.RULES:
            if kind == "bool":
                continue
            with self.subTest(key=key):
                bm_settings.reset_defaults()
                self.assertEqual(bm_settings.get(key), default)
                topped = high if kind == "int" else float(high)
                floored = low if kind == "int" else float(low)
                self.assertEqual(bm_settings.set_value(key, high), topped)
                bm_settings.step_value(key, 1)
                self.assertEqual(bm_settings.get(key), topped)
                self.assertEqual(bm_settings.set_value(key, low), floored)
                bm_settings.step_value(key, -1)
                self.assertEqual(bm_settings.get(key), floored)

    def _arena(self):
        game = Game()
        game.board = open_board(7, 7)
        game.grid_width = 7
        game.grid_height = 7
        game.players = game.players[:1]
        game.bombs = []
        game.powerups = []
        game.explosions = []
        game.game_state = "playing"
        game.game_start_time = 0
        return game

    def test_players_block_and_friendly_fire_apply_to_the_match(self):
        game = self._arena()
        bm_settings.set_value("players_block", False)
        bm_settings.set_value("friendly_fire", True)
        game.apply_match_rules()
        self.assertFalse(game.players_block)
        self.assertTrue(game.friendly_fire)

    def test_speed_and_starting_loadout_apply_to_players(self):
        game = self._arena()
        player = game.players[0]
        bm_settings.set_value("speed_multiplier", 1.4)
        bm_settings.set_value("start_bombs", 3)
        bm_settings.set_value("start_fire", 4)
        game.apply_match_rules()
        self.assertEqual(player.speed, bm_settings.player_speed())
        self.assertEqual(player.bomb_capacity, 3)
        self.assertEqual(player.fire_power, 4)
        player.bomb_capacity = 9
        player.reset()
        self.assertEqual(player.bomb_capacity, 3)
        self.assertEqual(player.fire_power, 4)

    def test_bomb_fuse_changes_when_the_bomb_explodes(self):
        bm_settings.set_value("bomb_fuse_s", 5)
        bomb = Bomb(1, 1, 0, 1, None)
        self.assertFalse(bomb.update(4999))
        self.assertTrue(bomb.update(5000))
        from ai_controller import _bomb_timer
        self.assertEqual(_bomb_timer(), 5000)

    def test_blast_duration_changes_how_long_flames_stay(self):
        blast = Explosion([(1, 1)], 0)
        bm_settings.set_value("blast_ms", 200)
        self.assertTrue(blast.is_active(199))
        self.assertFalse(blast.is_active(200))
        from ai_controller import _explosion_duration
        self.assertEqual(_explosion_duration(), 200)

    def test_powerup_chance_gates_drops(self):
        game = self._arena()
        game.board[2][2] = DESTRUCTIBLE
        blast = Explosion([(2, 2)], 0)
        bm_settings.set_value("powerup_chance", 0)
        game._open_soft_wall(2, 2, blast)
        self.assertEqual(game.powerups, [])
        self.assertEqual(game.board[2][2], EMPTY)
        game.board[3][2] = DESTRUCTIBLE
        bm_settings.set_value("powerup_chance", 1)
        game._open_soft_wall(2, 3, blast)
        self.assertEqual(len(game.powerups), 1)

    def test_quad_delay_gates_the_spawn(self):
        game = self._arena()
        game.current_time = 1000
        bm_settings.set_value("quad_delay_s", 60)
        with patch("bm_classes.random.random", return_value=0.0):
            game.place_quad_damage_powerup()
        self.assertFalse(any(pu.type == "quad_damage" for pu in game.powerups))
        bm_settings.set_value("quad_delay_s", 0)
        with patch("bm_classes.random.random", return_value=0.0):
            game.place_quad_damage_powerup()
        self.assertTrue(any(pu.type == "quad_damage" for pu in game.powerups))

    def test_quad_time_and_strength_change_the_bonus(self):
        game = self._arena()
        player = game.players[0]
        player.bomb_capacity = 1
        player.fire_power = 1
        gx, gy = player.get_grid_pos()
        bm_settings.set_value("quad_power", 4)
        bm_settings.set_value("quad_time_s", 5)
        game.powerups = [PowerUp(gx, gy, "quad_damage")]
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            game.update()
        self.assertTrue(player.quad_damage)
        self.assertEqual(player.bomb_capacity, 5)
        self.assertEqual(player.fire_power, 5)
        player.quad_damage_start_time = 0
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", return_value=False
        ):
            player.update(16, game.board, [], 4999, set(), game=game)
            self.assertTrue(player.quad_damage)
            player.update(16, game.board, [], 5001, set(), game=game)
        self.assertFalse(player.quad_damage)
        self.assertEqual(player.bomb_capacity, 1)
        self.assertEqual(player.fire_power, 1)

    def test_quad_speed_changes_how_far_a_boosted_player_moves(self):
        game = self._arena()
        player = game.players[0]
        player.quad_damage = True
        player.pos[0] = 350.0
        player.pos[1] = 350.0
        start = float(player.pos[0])
        bm_settings.set_value("quad_speed", 2.0)
        with patch("bm_classes.get_pressed_keys", return_value={}), patch(
            "bm_classes.is_key_pressed", side_effect=lambda key: key == player.controls["right"]
        ):
            player.update(1000, game.board, [], 0, set(), game=game)
        moved = float(player.pos[0]) - start
        self.assertAlmostEqual(moved, player.speed * 2.0, delta=1.0)

    def test_crushing_wall_hint_lists_two_player_then_unconditional_start(self):
        game = self._arena()
        game.game_state = "playing"
        for count, state in ((2, "playing"), (4, "playing"), (2, "boss_fight")):
            game.starting_player_count = count
            game.game_state = state
            self.assertEqual(game.crushing_wall_start_seconds(), (80, 80))
        walls = game.to_dict()["crushing_walls"]
        self.assertEqual((walls["early_s"], walls["late_s"]), (80, 80))

    def test_aftergame_rows_follow_trophy_count(self):
        from bm_drawing import _players_by_trophies
        low = type("P", (), {"name": "Low", "trophies": 1})()
        high = type("P", (), {"name": "High", "trophies": 4})()
        tied = type("P", (), {"name": "Tied", "trophies": 4})()
        ordered = _players_by_trophies([low, high, tied])
        self.assertEqual([player.name for player in ordered], ["High", "Tied", "Low"])

    def test_wall_delays_follow_each_mode(self):
        game = self._arena()
        game.starting_player_count = 3
        game.destructible_at_round_start = 0
        bm_settings.set_value("walls_delay_s", 200)
        game.current_time = 120_000
        game.handle_crushing_walls()
        self.assertFalse(game.crushing_walls_active)
        game.current_time = 200_000
        game.handle_crushing_walls()
        self.assertTrue(game.crushing_walls_active)

        game.crushing_walls_active = False
        game.starting_player_count = 2
        game.current_time = 120_000
        game.handle_crushing_walls()
        self.assertFalse(game.crushing_walls_active)
        game.current_time = 200_000
        game.handle_crushing_walls()
        self.assertTrue(game.crushing_walls_active)

        game.crushing_walls_active = False
        game.game_state = "boss_fight"
        game.current_time = 120_000
        game.handle_crushing_walls()
        self.assertFalse(game.crushing_walls_active)
        game.current_time = 200_000
        game.handle_crushing_walls()
        self.assertTrue(game.crushing_walls_active)

    def test_wall_growth_intervals_follow_each_mode(self):
        game = self._arena()
        game.starting_player_count = 3
        game.destructible_at_round_start = 0
        game.current_time = 120_000
        game.handle_crushing_walls()
        self.assertTrue(game.crushing_walls_active)
        bm_settings.set_value("walls_growth_ms", 3000)
        game.current_time = 122_000
        game.handle_crushing_walls()
        self.assertEqual(game.crushing_walls_index, 0)
        bm_settings.set_value("walls_growth_ms", 400)
        game.current_time = 120_400
        game.handle_crushing_walls()
        self.assertGreater(game.crushing_walls_index, 0)

        game.crushing_walls_active = False
        game.crushing_walls_index = 0
        game.game_state = "boss_fight"
        game.current_time = 180_000
        game.handle_crushing_walls()
        self.assertTrue(game.crushing_walls_active)
        bm_settings.set_value("walls_boss_growth_ms", 3000)
        game.current_time = 182_000
        game.handle_crushing_walls()
        self.assertEqual(game.crushing_walls_index, 0)
        bm_settings.set_value("walls_boss_growth_ms", 400)
        game.current_time = 180_400
        game.handle_crushing_walls()
        self.assertGreater(game.crushing_walls_index, 0)

    def test_changed_values_are_marked_and_reset_restores_them(self):
        game = Game()
        game.prep_section = "settings"
        for key, _label, _kind, _default, *_rest in bm_settings.RULES:
            self.assertTrue(bm_settings.is_default(key), key)
        bm_settings.set_value("quad_chance", 0.002)
        bm_settings.set_value("big_blast_tiles", 20)
        self.assertFalse(bm_settings.is_default("quad_chance"))
        self.assertFalse(bm_settings.is_default("big_blast_tiles"))
        game.settings_cursor = bm_settings.RESET_ROW
        game.handle_prep_key_event(_event(Keys.ENTER))
        for key, _label, _kind, _default, *_rest in bm_settings.RULES:
            self.assertTrue(bm_settings.is_default(key), key)

    def test_quad_chance_is_per_tick(self):
        game = self._arena()
        game.current_time = 120_000
        bm_settings.set_value("quad_chance", 0)
        with patch("bm_classes.random.random", return_value=0.0):
            game.place_quad_damage_powerup()
        self.assertFalse(any(pu.type == "quad_damage" for pu in game.powerups))
        bm_settings.set_value("quad_chance", 0.01)
        with patch("bm_classes.random.random", return_value=0.0):
            game.place_quad_damage_powerup()
        self.assertTrue(any(pu.type == "quad_damage" for pu in game.powerups))

    def test_loud_hit_uses_size_delay_and_volume(self):
        game = self._arena()
        game.current_time = 1000
        game.recent_explosion_events = []
        game.big_explosion_over_threshold = False
        game.big_explosion_sound_at = []
        bm_settings.set_value("big_blast_tiles", 10)
        bm_settings.set_value("big_blast_window_ms", 700)
        bm_settings.set_value("big_blast_delay_ms", 100)
        bm_settings.set_value("big_blast_volume", 0.4)
        blast = Explosion([(i, 0) for i in range(10)], 1000)
        game._register_new_explosions([blast])
        self.assertEqual(game.big_explosion_sound_at, [1100])
        game.current_time = 1100
        sound = MagicMock()
        with patch("bm_classes.mocny_stral_sounds", [sound]):
            game._play_due_big_explosion_sounds()
        sound.set_volume.assert_called_with(0.4)
        sound.play.assert_called()
        payload = game.to_dict()["big_blast"]
        self.assertEqual(payload["tiles"], 10)
        self.assertEqual(payload["delay_ms"], 100)
        self.assertEqual(payload["volume"], 0.4)

    def test_loud_hit_does_not_retrigger_for_five_seconds(self):
        from bm_params import BIG_EXPLOSION_COOLDOWN_MS
        game = self._arena()
        game.current_time = 1000
        game.recent_explosion_events = []
        game.big_explosion_over_threshold = False
        game.big_explosion_sound_at = []
        game.big_explosion_last_trigger_ms = None
        bm_settings.set_value("big_blast_tiles", 10)
        bm_settings.set_value("big_blast_delay_ms", 0)
        blast = Explosion([(i, 0) for i in range(10)], 1000)
        game._register_new_explosions([blast])
        self.assertEqual(game.big_explosion_sound_at, [1000])
        game.current_time = 1000 + BIG_EXPLOSION_COOLDOWN_MS - 1
        game.recent_explosion_events = []
        game.big_explosion_over_threshold = False
        again = Explosion([(i, 2) for i in range(10)], game.current_time)
        game._register_new_explosions([again])
        self.assertEqual(game.big_explosion_sound_at, [1000])
        game.current_time = 1000 + BIG_EXPLOSION_COOLDOWN_MS
        game.recent_explosion_events = []
        game.big_explosion_over_threshold = False
        later = Explosion([(i, 3) for i in range(10)], game.current_time)
        game._register_new_explosions([later])
        self.assertEqual(game.big_explosion_sound_at, [1000, game.current_time])

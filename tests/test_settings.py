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
        game.consume_sound_events()
        sound = MagicMock()
        game._play_due_big_explosion_sounds()
        sound.play.assert_not_called()
        events = game.consume_sound_events()
        self.assertEqual(events, [{"type": "big_explosion", "t": 1100, "volume": 0.4}])
        with patch("bm_sounds.mocny_stral_sounds", [sound]):
            from bm_sounds import play_sound_events
            play_sound_events(events)
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

    def test_show_debug_hud_setting_and_top_left_overlay(self):
        import pygame
        from bm_drawing import draw_game_screen, format_debug_hud_lines
        from latency_metrics import build_hud_metrics
        from render_snapshot import build_render_snapshot

        pygame.init()
        pygame.font.init()
        game = self._arena()
        self.assertFalse(bm_settings.get("show_debug_hud"))
        self.assertFalse(game.show_debug_hud)

        game._cached_status = {
            "clients": {
                1: {"latency_samples_5s": 10, "min_latency": 4.0, "max_latency": 18.0, "avg_latency_5s": 9.0},
                2: {"latency_samples_5s": 8, "min_latency": 7.0, "max_latency": 29.0, "avg_latency_5s": 14.0},
            }
        }
        hud = build_hud_metrics(
            host_fps_5s=60.0,
            host_render_fps_5s=59.8,
            cached_status=game._cached_status,
        )
        self.assertEqual(hud["client_latency_min_ms"], 4.0)
        self.assertEqual(hud["client_latency_max_ms"], 29.0)

        lines = format_debug_hud_lines(game, hud)
        self.assertEqual(
            lines,
            (
                "Logic FPS: 60.0",
                "Render FPS: 59.8",
                "Latency (min/max): 4/29 ms",
            ),
        )

        surf_off = pygame.Surface((700, 700))
        snap_off = build_render_snapshot(game, seq=1, hud_metrics=hud)
        draw_game_screen(surf_off, snap_off)

        bm_settings.set_value("show_debug_hud", True)
        game.apply_match_rules()
        self.assertTrue(game.show_debug_hud)

        surf_on = pygame.Surface((700, 700))
        snap_on = build_render_snapshot(game, seq=2, hud_metrics=hud)
        self.assertTrue(snap_on.show_debug_hud)
        draw_game_screen(surf_on, snap_on)

        # Top-left region must differ when the debug HUD is turned on
        top_left_diff = any(
            surf_off.get_at((x, y)) != surf_on.get_at((x, y))
            for y in range(10, 90, 4)
            for x in range(10, 220, 4)
        )
        self.assertTrue(top_left_diff)

    def test_seven_ais_simulation_and_render_keep_up_with_60fps(self):
        import time
        import pygame
        from bm_drawing import draw_game_screen
        from render_snapshot import build_render_snapshot

        pygame.init()
        pygame.font.init()
        game = Game()
        game._detached_renderer = True
        game.prep_num_players = 1
        game.prep_ai_count = 7
        game.game_state = "game_prep"
        game.start_match_from_lobby()
        game.game_state = "playing"
        game.current_time = game.game_start_time + 100

        surf = pygame.Surface((game.grid_width * 100, game.grid_height * 100))
        # Warm up caches on frame 0
        draw_game_screen(surf, build_render_snapshot(game, seq=0))

        sim_samples_ms = []
        draw_samples_ms = []
        now = game.current_time
        for i in range(120):
            now += 16
            t0 = time.perf_counter()
            game.simulate(16, now_ms=now)
            t1 = time.perf_counter()
            snap = build_render_snapshot(game, seq=i + 1)
            draw_game_screen(surf, snap)
            t2 = time.perf_counter()
            sim_samples_ms.append((t1 - t0) * 1000.0)
            draw_samples_ms.append((t2 - t1) * 1000.0)

        avg_sim_ms = sum(sim_samples_ms) / len(sim_samples_ms)
        avg_draw_ms = sum(draw_samples_ms) / len(draw_samples_ms)
        self.assertLess(avg_sim_ms, 8.0, f"7-AI avg sim step too slow: {avg_sim_ms:.2f}ms")
        self.assertLess(avg_draw_ms, 10.0, f"7-AI avg draw frame too slow: {avg_draw_ms:.2f}ms")

    def test_frontend_renderer_handles_horizontal_and_vertical_letterboxing(self):
        import pygame
        from frontend import FrontendRenderer, FrontendScreen, FrontendWindow

        pygame.init()
        screen = FrontendScreen()
        screen.ensure_surface_size((1500, 1500))
        screen.surface.fill((40, 80, 120))
        window = FrontendWindow()

        for win_size in ((1200, 800), (960, 1200), (600, 1080), (1500, 1500)):
            fake_win = pygame.Surface(win_size)
            window.window = fake_win
            window.flip_display = lambda: None
            renderer = FrontendRenderer(screen, window)
            renderer.draw_adjust_screen_size()
            self.assertEqual(fake_win.get_size(), win_size)



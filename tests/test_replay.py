import os
import sys
import types
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from replay import (
    ReplayPlayer,
    build_replay_snapshot,
    freeze_kill_cam_clip,
    frame_at_time,
    hydrate_replay_snapshot,
    letterbox_dest,
    pick_kill_cam,
)


class ReplayTests(unittest.TestCase):
    def test_snapshot_serializes_entities(self):
        player = types.SimpleNamespace(
            name="Marv",
            color=(1, 2, 3),
            pos=(150.5, 250.0),
            alive=True,
            draw_radius=40,
            fire_power=2,
            bomb_capacity=3,
            direction=(1.0, 0.0),
            animation_time=80,
            quad_damage=True,
            quad_damage_start_time=10,
            death_animation_time=0,
            pickup_message="",
            pickup_message_end_time=0,
            global_id=7,
        )
        bomb = types.SimpleNamespace(x=1, y=2, start_time=40)
        explosion = types.SimpleNamespace(cells=[(1, 2), (1, 3)], start_time=80, quad_damage=True)
        powerup = types.SimpleNamespace(x=4, y=5, type="fire")
        game = types.SimpleNamespace(
            current_time=1234,
            players=[player],
            bombs=[bomb],
            explosions=[explosion],
            powerups=[powerup],
            board=[[0, 1], [2, 0]],
            grid_width=2,
            grid_height=2,
        )
        snap = build_replay_snapshot(game)
        self.assertEqual(snap["t"], 1234)
        self.assertEqual(snap["players"][0]["name"], "Marv")
        self.assertEqual(snap["players"][0]["pos"], (150.5, 250.0))
        self.assertEqual(snap["players"][0]["direction"], (1.0, 0.0))
        self.assertTrue(snap["players"][0]["quad_damage"])
        self.assertEqual(snap["board"][0][1], 1)
        self.assertEqual(snap["bombs"][0]["x"], 1)
        self.assertEqual(snap["explosions"][0]["qd"], True)
        self.assertEqual(snap["powerups"][0]["type"], "fire")

    def test_hydrate_replay_player_has_face_fields(self):
        snap = {
            "t": 50,
            "board": [[0]],
            "players": [
                {
                    "name": "Marv",
                    "color": (100, 150, 200),
                    "pos": (150.0, 150.0),
                    "alive": True,
                    "draw_radius": 42,
                    "direction": (0.0, 1.0),
                    "animation_time": 30,
                    "quad_damage": False,
                    "global_id": "p1",
                }
            ],
            "bombs": [],
            "explosions": [],
            "powerups": [],
        }
        frame = hydrate_replay_snapshot(snap)
        player = frame["players"][0]
        self.assertIsInstance(player, ReplayPlayer)
        self.assertEqual(player.direction, (0.0, 1.0))
        self.assertEqual(player.get_grid_pos(), (1, 1))
        self.assertEqual(player.name, "Marv")

    def test_letterbox_keeps_aspect_in_tall_panel(self):
        dest_w, dest_h, ox, oy = letterbox_dest(1100, 1100, 400, 900)
        self.assertEqual(dest_w, dest_h)
        self.assertEqual(dest_w, 400)
        self.assertEqual(ox, 0)
        self.assertGreater(oy, 0)
        self.assertEqual(dest_w / dest_h, 1)

    def test_letterbox_keeps_aspect_in_wide_panel(self):
        dest_w, dest_h, ox, oy = letterbox_dest(800, 400, 1000, 400)
        self.assertEqual(dest_w / dest_h, 2)
        self.assertEqual(dest_h, 400)
        self.assertGreater(ox, 0)
        self.assertEqual(oy, 0)

    def test_pick_kill_cam_plays_deaths_in_order_then_loops(self):
        clips = [
            {"name": "A", "death_time": 1000, "start": 0, "end": 1500, "frames": []},
            {"name": "B", "death_time": 3000, "start": 2000, "end": 3500, "frames": []},
        ]
        clip, target = pick_kill_cam(clips, 0)
        self.assertEqual(clip["name"], "A")
        self.assertEqual(target, 0)
        clip, target = pick_kill_cam(clips, 1499)
        self.assertEqual(clip["name"], "A")
        self.assertEqual(target, 1499)
        clip, target = pick_kill_cam(clips, 1500)
        self.assertEqual(clip["name"], "B")
        self.assertEqual(target, 2000)
        clip, target = pick_kill_cam(clips, 1500 + 500)
        self.assertEqual(clip["name"], "B")
        self.assertEqual(target, 2500)
        clip, target = pick_kill_cam(clips, 1500 + 1500)
        self.assertEqual(clip["name"], "A")
        self.assertEqual(target, 0)

    def test_kill_cam_clip_includes_post_death_tail(self):
        buffer = [(t, {"t": t, "players": []}) for t in range(0, 6000, 16)]
        clip = freeze_kill_cam_clip(buffer, "Marv", 3500, 6000, pre_ms=3500, post_ms=1500)
        self.assertEqual(clip["name"], "Marv")
        self.assertEqual(clip["start"], 0)
        self.assertEqual(clip["end"], 5000)
        self.assertTrue(all(0 <= t <= 5000 for t, _ in clip["frames"]))
        self.assertGreaterEqual(clip["end"] - 3500, 1500)

    def test_frame_at_time_interpolates_positions(self):
        frames = [
            (0, {"t": 0, "players": [{"name": "A", "pos": (0.0, 0.0), "alive": True, "animation_time": 0}], "bombs": [], "explosions": [], "powerups": [], "board": None}),
            (100, {"t": 100, "players": [{"name": "A", "pos": (100.0, 0.0), "alive": True, "animation_time": 40}], "bombs": [], "explosions": [], "powerups": [], "board": None}),
        ]
        mid = frame_at_time(frames, 50)
        self.assertAlmostEqual(mid["players"][0]["pos"][0], 50.0)
        self.assertEqual(mid["t"], 50)


if __name__ == "__main__":
    unittest.main()

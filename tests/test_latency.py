import unittest

from latency_metrics import (
    HUD_METRICS_INTERVAL_MS,
    IDLE_PUBLISH_INTERVAL_MS,
    board_fingerprint,
    build_hud_metrics,
    gameplay_fingerprint,
    prepare_wire_state,
    queue_delay_ms,
    rtt_ms,
    should_attach_hud_metrics,
    should_publish_snapshot,
    split_hud_metrics,
    wall_clock_ms,
)


class LatencyMetricsTests(unittest.TestCase):
    def test_queue_delay_clamps_missing_and_negative(self):
        self.assertEqual(queue_delay_ms(None, 100), 0)
        self.assertEqual(queue_delay_ms("nope", 100), 0)
        self.assertEqual(queue_delay_ms(120, 100), 0)
        self.assertEqual(queue_delay_ms(100.7, 108.2), 8)

    def test_rtt_same_clock_only(self):
        self.assertEqual(rtt_ms(10, 25), 15)
        self.assertEqual(rtt_ms(40, 10), 0)
        self.assertEqual(rtt_ms(None, 10), 0)

    def test_wall_clock_is_unix_ms(self):
        now = wall_clock_ms()
        self.assertIsInstance(now, int)
        self.assertGreater(now, 1_700_000_000_000)

    def test_idle_publish_throttles_until_interval_or_change(self):
        self.assertTrue(should_publish_snapshot("game_prep", "a", None, 1000, -1))
        self.assertTrue(should_publish_snapshot("playing", "a", "a", 1000, 999))
        self.assertTrue(should_publish_snapshot("get_ready", "a", "a", 1000, 999))
        self.assertFalse(should_publish_snapshot("game_prep", "a", "a", 1000, 900, interval_ms=250))
        self.assertTrue(should_publish_snapshot("game_prep", "a", "a", 1200, 900, interval_ms=250))
        self.assertTrue(should_publish_snapshot("game_prep", "b", "a", 910, 900, interval_ms=250))
        self.assertTrue(should_publish_snapshot("win", "a", "a", 1000, 1000, force=True))

    def test_fingerprint_ignores_clocks_and_metrics(self):
        a = {
            "state": "game_prep",
            "time": 1,
            "_sim_tick": 1,
            "_net_metrics": {"host_fps_5s": 60},
            "board": [[1, 0], [0, 1]],
            "players": [{"id": 1, "name": "A", "x": 10, "y": 10, "alive": True}],
            "bombs": [],
            "explosions": [],
            "powerups": [],
        }
        b = dict(a)
        b["time"] = 999
        b["_sim_tick"] = 50
        b["_host_published_at_ms"] = 123
        self.assertEqual(gameplay_fingerprint(a), gameplay_fingerprint(b))
        b["players"] = [{"id": 1, "name": "B", "x": 10, "y": 10, "alive": True}]
        self.assertNotEqual(gameplay_fingerprint(a), gameplay_fingerprint(b))

    def test_prepare_wire_state_strips_60hz_metrics(self):
        payload = {"state": "playing", "board": [[0]], "_net_metrics": {"host_fps_5s": 60}, "_sim_tick": 3}
        wire = prepare_wire_state(payload, wall_ms=50, hud_metrics={"host_fps_5s": 60}, sim_tick=4)
        self.assertNotIn("_net_metrics", wire)
        self.assertEqual(wire["_hud_metrics"]["host_fps_5s"], 60)
        self.assertEqual(wire["_host_published_at_ms"], 50)
        self.assertEqual(wire["_sim_tick"], 4)
        gameplay, hud = split_hud_metrics(wire)
        self.assertNotIn("_hud_metrics", gameplay)
        self.assertEqual(hud["host_fps_5s"], 60)

    def test_hud_metrics_interval_and_honest_labels(self):
        self.assertTrue(should_attach_hud_metrics(0, -1))
        self.assertFalse(should_attach_hud_metrics(100, 0, interval_ms=HUD_METRICS_INTERVAL_MS))
        self.assertTrue(should_attach_hud_metrics(500, 0, interval_ms=HUD_METRICS_INTERVAL_MS))
        hud = build_hud_metrics(input_queue_delay_samples_ms=[1, 2, 10], sim_tick=8, host_fps_5s=59.6)
        self.assertEqual(hud["clock"], "unix_ms")
        self.assertIn("queue delay", hud["meaning"])
        self.assertEqual(hud["input_queue_delay_p95_ms"], hud["input_apply_p95_ms"])
        self.assertEqual(hud["sim_tick"], 8)

    def test_board_fingerprint_stable(self):
        self.assertEqual(board_fingerprint([[1, 0], [0, 1]]), board_fingerprint([[1, 0], [0, 1]]))
        self.assertNotEqual(board_fingerprint([[1, 0], [0, 1]]), board_fingerprint([[0, 0], [0, 1]]))
        self.assertEqual(board_fingerprint(None), 0)

    def test_idle_interval_constant(self):
        self.assertGreaterEqual(IDLE_PUBLISH_INTERVAL_MS, 100)
        self.assertLessEqual(IDLE_PUBLISH_INTERVAL_MS, 500)


if __name__ == "__main__":
    unittest.main()

import unittest

from net_protocol import (
    MSG_GAME_INPUT,
    MSG_HELLO,
    MSG_REQUEST_KEYFRAME,
    MSG_RTC_ANSWER,
    MSG_RTC_FAILED,
    MSG_RTC_ICE_CANDIDATE,
    MSG_RTC_READY,
    PROTOCOL_VERSION,
    MAX_BOARD_PATCH_CELLS,
    apply_board_patches,
    apply_keepalive_to_state,
    apply_player_delta,
    apply_state_delta,
    build_state_delta,
    classify_state_diff,
    diff_board,
    diff_players,
    envelope,
    resolve_input_tick,
    resolve_ws_codec,
    should_buffer_remote_input,
    strip_wire_metrics,
    validate_client_message,
)


class NetProtocolTests(unittest.TestCase):
    def test_envelope_has_protocol(self):
        msg = envelope("ping", ts=123)
        self.assertEqual(msg["protocol"], PROTOCOL_VERSION)
        self.assertEqual(msg["type"], "ping")
        self.assertEqual(msg["ts"], 123)

    def test_validate_rejects_unknown_type(self):
        err = validate_client_message({"type": "unknown", "protocol": PROTOCOL_VERSION})
        self.assertIsNotNone(err)

    def test_validate_accepts_game_input(self):
        payload = {
            "type": MSG_GAME_INPUT,
            "protocol": PROTOCOL_VERSION,
            "input": [1, 1, 0, 0, 0, 0, 0],
        }
        err = validate_client_message(payload)
        self.assertIsNone(err)

    def test_validate_accepts_tick_input_frame(self):
        payload = {
            "type": MSG_GAME_INPUT,
            "protocol": PROTOCOL_VERSION,
            "tick_id": 42,
            "input_frame": {
                "player_id": 1,
                "up": 1,
                "down": 0,
                "left": 0,
                "right": 1,
                "bomb": 0,
            },
        }
        err = validate_client_message(payload)
        self.assertIsNone(err)

    def test_validate_rejects_protocol_mismatch(self):
        err = validate_client_message({"type": "ping", "protocol": 999})
        self.assertIsNotNone(err)

    def test_validate_accepts_rtc_answer(self):
        payload = {
            "type": MSG_RTC_ANSWER,
            "protocol": PROTOCOL_VERSION,
            "sdp": "v=0...",
            "sdp_type": "answer",
        }
        self.assertIsNone(validate_client_message(payload))

    def test_validate_accepts_rtc_ice_candidate(self):
        payload = {
            "type": MSG_RTC_ICE_CANDIDATE,
            "protocol": PROTOCOL_VERSION,
            "candidate": {
                "candidate": "candidate:1 1 UDP 2122252543 192.168.1.10 55555 typ host",
                "sdpMid": "0",
                "sdpMLineIndex": 0,
            },
        }
        self.assertIsNone(validate_client_message(payload))

    def test_validate_accepts_rtc_ready_and_failed(self):
        ready = {"type": MSG_RTC_READY, "protocol": PROTOCOL_VERSION, "transport": "rtc"}
        failed = {"type": MSG_RTC_FAILED, "protocol": PROTOCOL_VERSION, "reason": "channel closed"}
        self.assertIsNone(validate_client_message(ready))
        self.assertIsNone(validate_client_message(failed))

    def test_validate_accepts_request_keyframe(self):
        payload = {"type": MSG_REQUEST_KEYFRAME, "protocol": PROTOCOL_VERSION, "seq": 12}
        self.assertIsNone(validate_client_message(payload))

    def test_resolve_input_tick_skips_holes(self):
        action, expected, skipped = resolve_input_tick(4, 7)
        self.assertEqual(action, "apply")
        self.assertEqual(expected, 8)
        self.assertEqual(skipped, 3)

    def test_resolve_input_tick_drops_late(self):
        action, expected, skipped = resolve_input_tick(5, 3)
        self.assertEqual(action, "drop")
        self.assertEqual(expected, 5)
        self.assertEqual(skipped, 0)

    def test_resolve_input_tick_allows_repeat_of_last(self):
        action, expected, skipped = resolve_input_tick(8, 7)
        self.assertEqual(action, "apply")
        self.assertEqual(expected, 8)
        self.assertEqual(skipped, 0)

    def test_should_buffer_only_small_lead(self):
        self.assertTrue(should_buffer_remote_input(12, 10))
        self.assertFalse(should_buffer_remote_input(10, 10))
        self.assertFalse(should_buffer_remote_input(1000, 10))
        self.assertFalse(should_buffer_remote_input(None, 10))

    def test_validate_accepts_hello_ping_and_slot_list(self):
        self.assertIsNone(validate_client_message({"type": "hello", "protocol": PROTOCOL_VERSION}))
        self.assertIsNone(validate_client_message({"type": "ping", "protocol": PROTOCOL_VERSION}))
        self.assertIsNone(validate_client_message({"type": "request_slot_list"}))

    def test_validate_rejects_non_object(self):
        self.assertEqual(validate_client_message([]), "message must be an object")
        self.assertEqual(validate_client_message("hello"), "message must be an object")

    def test_validate_rejects_bad_slot_and_name(self):
        self.assertIsNotNone(validate_client_message({"type": "select_slot", "protocol": PROTOCOL_VERSION, "slot": "1"}))
        self.assertIsNotNone(
            validate_client_message({"type": "set_name", "protocol": PROTOCOL_VERSION, "name": "x" * 21})
        )
        self.assertIsNotNone(validate_client_message({"type": "set_name", "protocol": PROTOCOL_VERSION, "name": 12}))

    def test_validate_rejects_short_input_array(self):
        err = validate_client_message({"type": MSG_GAME_INPUT, "protocol": PROTOCOL_VERSION, "input": [1, 2, 3]})
        self.assertIsNotNone(err)

    def test_validate_rejects_bad_input_frame(self):
        payload = {
            "type": MSG_GAME_INPUT,
            "protocol": PROTOCOL_VERSION,
            "input_frame": {"player_id": "1", "up": 1, "down": 0, "left": 0, "right": 0, "bomb": 0},
        }
        self.assertIsNotNone(validate_client_message(payload))
        payload = {
            "type": MSG_GAME_INPUT,
            "protocol": PROTOCOL_VERSION,
            "input_frame": {"player_id": 1, "up": 2, "down": 0, "left": 0, "right": 0, "bomb": 0},
        }
        self.assertIsNotNone(validate_client_message(payload))

    def test_validate_rejects_missing_input(self):
        self.assertIsNotNone(validate_client_message({"type": MSG_GAME_INPUT, "protocol": PROTOCOL_VERSION}))

    def test_validate_rejects_negative_tick(self):
        self.assertIsNotNone(
            validate_client_message({"type": MSG_GAME_INPUT, "protocol": PROTOCOL_VERSION, "tick_id": -1, "input": [1, 1, 0, 0, 0, 0, 0]})
        )

    def test_validate_rejects_bad_rtc_answer(self):
        self.assertIsNotNone(validate_client_message({"type": MSG_RTC_ANSWER, "protocol": PROTOCOL_VERSION, "sdp": "", "sdp_type": "answer"}))
        self.assertIsNotNone(validate_client_message({"type": MSG_RTC_ANSWER, "protocol": PROTOCOL_VERSION, "sdp": "v=0", "sdp_type": "offer"}))

    def test_validate_rejects_bad_keyframe_seq(self):
        self.assertIsNotNone(validate_client_message({"type": MSG_REQUEST_KEYFRAME, "protocol": PROTOCOL_VERSION, "seq": -2}))

    def test_resolve_input_tick_first_packet(self):
        action, expected, skipped = resolve_input_tick(-1, 10)
        self.assertEqual(action, "apply")
        self.assertEqual(expected, 11)
        self.assertEqual(skipped, 0)

    def test_resolve_input_tick_in_order(self):
        action, expected, skipped = resolve_input_tick(5, 5)
        self.assertEqual(action, "apply")
        self.assertEqual(expected, 6)
        self.assertEqual(skipped, 0)

    def test_hello_encoding_validation(self):
        self.assertIsNone(validate_client_message({"type": MSG_HELLO, "protocol": PROTOCOL_VERSION, "encoding": "msgpack"}))
        self.assertIsNotNone(validate_client_message({"type": MSG_HELLO, "protocol": PROTOCOL_VERSION, "encoding": "protobuf"}))
        self.assertIsNotNone(validate_client_message({"type": MSG_HELLO, "protocol": PROTOCOL_VERSION, "rtc_codec": "cbor"}))

    def test_resolve_ws_codec_fallback(self):
        self.assertEqual(resolve_ws_codec("msgpack", True), "msgpack")
        self.assertEqual(resolve_ws_codec("msgpack", False), "json")
        self.assertEqual(resolve_ws_codec("nope", True), "json")
        self.assertEqual(resolve_ws_codec(None, True), "json")

    def test_classify_state_diff_keepalive_and_gameplay(self):
        self.assertEqual(classify_state_diff({}), "unchanged")
        self.assertEqual(classify_state_diff({"time": 2, "_sim_tick": 9}), "keepalive")
        self.assertEqual(classify_state_diff({"_net_metrics": {"host_fps_5s": 60}}), "unchanged")
        self.assertEqual(classify_state_diff({"players": []}), "gameplay")
        self.assertEqual(classify_state_diff({"player_patches": [{"id": 1, "x": 2}]}), "gameplay")
        self.assertEqual(classify_state_diff({"board_patches": [[1, 1, 0]]}), "gameplay")
        self.assertEqual(classify_state_diff({"time": 1, "board": [[0]]}), "gameplay")

    def test_build_state_delta_omits_metrics(self):
        previous = {"time": 1, "_sim_tick": 1, "_net_metrics": {"a": 1}, "players": [1]}
        current = {"time": 2, "_sim_tick": 2, "_net_metrics": {"a": 2}, "players": [1]}
        delta = build_state_delta(previous, current)
        self.assertEqual(delta["time"], 2)
        self.assertEqual(delta["_sim_tick"], 2)
        self.assertNotIn("_net_metrics", delta)
        self.assertNotIn("players", delta)

    def test_strip_metrics_and_apply_keepalive(self):
        state = {"time": 1, "board": [[0]], "_net_metrics": {"x": 1}, "_hud_metrics": {"y": 2}}
        stripped = strip_wire_metrics(state)
        self.assertNotIn("_net_metrics", stripped)
        self.assertNotIn("_hud_metrics", stripped)
        updated = apply_keepalive_to_state(stripped, {"time": 9, "_sim_tick": 4})
        self.assertEqual(updated["time"], 9)
        self.assertEqual(updated["_sim_tick"], 4)
        self.assertEqual(updated["board"], [[0]])

    def test_entity_grain_player_and_board_deltas(self):
        previous_players = [{"id": 1, "x": 10, "y": 10, "alive": True, "name": "A"}]
        current_players = [{"id": 1, "x": 14, "y": 10, "alive": True, "name": "A"}]
        patch = diff_players(previous_players, current_players)
        self.assertEqual(patch["player_patches"], [{"id": 1, "x": 14}])
        self.assertNotIn("players", patch)
        removed = diff_players(previous_players, [])
        self.assertEqual(removed["player_removed"], [1])
        fallback = diff_players([1], [2])
        self.assertEqual(fallback, {"players": [2]})

        board = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
        next_board = [[1, 1, 1], [1, 2, 1], [1, 1, 1]]
        self.assertEqual(diff_board(board, next_board), {"board_patches": [[1, 1, 2]]})
        smashed = [[0 for _ in row] for row in board]
        self.assertIn("board", diff_board(board, smashed, max_patches=2))

        previous = {"time": 1, "players": previous_players, "board": board, "state": "playing", "bombs": []}
        current = {"time": 2, "players": current_players, "board": next_board, "state": "playing", "bombs": []}
        delta = build_state_delta(previous, current)
        self.assertEqual(delta["player_patches"], [{"id": 1, "x": 14}])
        self.assertEqual(delta["board_patches"], [[1, 1, 2]])
        self.assertNotIn("players", delta)
        self.assertNotIn("board", delta)
        merged = apply_state_delta(previous, delta)
        self.assertEqual(merged["players"][0]["x"], 14)
        self.assertEqual(merged["board"][1][1], 2)
        self.assertEqual(merged["time"], 2)
        self.assertEqual(previous["players"][0]["x"], 10)
        self.assertEqual(previous["board"][1][1], 0)

        dropped = apply_player_delta(previous_players, {"player_removed": [1]})
        self.assertEqual(dropped, [])
        upserted = apply_player_delta(previous_players, {"player_patches": [{"id": 2, "x": 3, "y": 4, "name": "B"}]})
        self.assertEqual([player["id"] for player in upserted], [1, 2])
        self.assertEqual(apply_board_patches([[0, 0], [0, 0]], [[1, 0, 7]]), [[0, 7], [0, 0]])

        duplicate_ids = [{"id": 1, "x": 1}, {"id": 1, "x": 2}]
        self.assertEqual(diff_players(previous_players, duplicate_ids), {"players": duplicate_ids})
        resized = [[0, 0], [0, 0], [0, 0]]
        self.assertEqual(diff_board(board, resized), {"board": resized})
        exact = [[1] * 6 for _ in range(4)]
        exact_next = [[0] * 6 for _ in range(4)]
        exact_delta = diff_board(exact, exact_next)
        self.assertEqual(len(exact_delta["board_patches"]), MAX_BOARD_PATCH_CELLS)
        self.assertNotIn("board", exact_delta)
        over = [[1] * 5 for _ in range(5)]
        self.assertIn("board", diff_board(over, [[0] * 5 for _ in range(5)]))


if __name__ == "__main__":
    unittest.main()

import unittest

from net_protocol import (
    MSG_GAME_INPUT,
    MSG_RTC_ANSWER,
    MSG_RTC_FAILED,
    MSG_RTC_ICE_CANDIDATE,
    MSG_RTC_READY,
    PROTOCOL_VERSION,
    envelope,
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


if __name__ == "__main__":
    unittest.main()

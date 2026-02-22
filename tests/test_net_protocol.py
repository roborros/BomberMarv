import unittest

from net_protocol import MSG_GAME_INPUT, PROTOCOL_VERSION, envelope, validate_client_message


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

    def test_validate_rejects_protocol_mismatch(self):
        err = validate_client_message({"type": "ping", "protocol": 999})
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()

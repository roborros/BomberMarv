import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lobby import build_status_signature
from ws_stream_server import build_state_delta


class LobbySignatureTests(unittest.TestCase):
    def test_latency_is_not_part_of_signature(self):
        status_a = {
            "clients": {
                "1": {"registered": True, "slot": 2, "display_name": "Marv", "avg_latency_5s": 12.3}
            },
            "slots": {1: False, 2: True},
        }
        status_b = {
            "clients": {
                "1": {"registered": True, "slot": 2, "display_name": "Marv", "avg_latency_5s": 88.1}
            },
            "slots": {1: False, 2: True},
        }
        self.assertEqual(build_status_signature(status_a), build_status_signature(status_b))

    def test_name_change_is_part_of_signature(self):
        status_a = {"clients": {"1": {"registered": True, "slot": 2, "display_name": "Marv"}}, "slots": {}}
        status_b = {"clients": {"1": {"registered": True, "slot": 2, "display_name": "Tom"}}, "slots": {}}
        self.assertNotEqual(build_status_signature(status_a), build_status_signature(status_b))

    def test_none_and_non_dict_info_are_ignored(self):
        self.assertIsNone(build_status_signature(None))
        self.assertIsNone(build_status_signature("nope"))
        status = {"clients": {"1": "bad", "2": {"registered": True, "slot": 1, "display_name": "A"}}, "slots": {1: True}}
        sig = build_status_signature(status)
        self.assertEqual(len(sig[0]), 1)

    def test_mixed_slot_values_still_sort(self):
        status = {
            "clients": {
                "10": {"registered": True, "slot": None, "display_name": "A"},
                "2": {"registered": True, "slot": 4, "display_name": "B"},
                "3": "not-a-client",
            },
            "slots": {1: False, "8": True},
        }
        sig = build_status_signature(status)
        self.assertIsNotNone(sig)
        self.assertEqual(len(sig[0]), 2)

    def test_slot_change_changes_signature(self):
        a = {"clients": {}, "slots": {1: False}}
        b = {"clients": {}, "slots": {1: True}}
        self.assertNotEqual(build_status_signature(a), build_status_signature(b))


class StateDeltaTests(unittest.TestCase):
    def test_includes_boss_fight_winner(self):
        previous = {"boss_fight_winner": None, "players": []}
        current = {"boss_fight_winner": {"name": "Marv", "is_ai": False, "color": [1, 2, 3]}, "players": []}
        delta = build_state_delta(previous, current)
        self.assertIn("boss_fight_winner", delta)
        self.assertEqual(delta["boss_fight_winner"]["name"], "Marv")

    def test_includes_leave_prompt(self):
        previous = {"leave_prompt": {"open": False, "choice": "no", "title": ""}, "players": []}
        current = {"leave_prompt": {"open": True, "choice": "yes", "title": "Leave game?"}, "players": []}
        delta = build_state_delta(previous, current)
        self.assertEqual(delta["leave_prompt"]["open"], True)
        self.assertEqual(delta["leave_prompt"]["choice"], "yes")


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from powerups import choose_death_bonus_effect


class PowerupTests(unittest.TestCase):
    def test_death_bonus_is_one_of_three(self):
        with patch("powerups.random.choice", side_effect=lambda seq: seq[0]):
            self.assertEqual(choose_death_bonus_effect(), "speed")
        with patch("powerups.random.choice", side_effect=lambda seq: seq[1]):
            self.assertEqual(choose_death_bonus_effect(), "fire")
        with patch("powerups.random.choice", side_effect=lambda seq: seq[2]):
            self.assertEqual(choose_death_bonus_effect(), "bomb")

    def test_random_choice_stays_in_set(self):
        for _ in range(20):
            self.assertIn(choose_death_bonus_effect(), {"speed", "fire", "bomb"})


if __name__ == "__main__":
    unittest.main()

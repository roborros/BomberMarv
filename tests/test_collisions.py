import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib_collisions import circle_rect_collision


class CollisionTests(unittest.TestCase):
    def test_center_inside_rect_collides(self):
        self.assertTrue(circle_rect_collision((50, 50), 10, [0, 0, 100, 100]))

    def test_far_away_does_not_collide(self):
        self.assertFalse(circle_rect_collision((200, 200), 10, [0, 0, 40, 40]))

    def test_touching_edge_is_not_inside(self):
        # Distance equals radius: helper uses strict < so the rim is not a hit.
        self.assertFalse(circle_rect_collision((110, 50), 10, [0, 0, 100, 100]))

    def test_overlap_from_left(self):
        self.assertTrue(circle_rect_collision((98, 50), 10, [0, 0, 100, 100]))

    def test_corner_overlap(self):
        self.assertTrue(circle_rect_collision((103, 103), 8, [0, 0, 100, 100]))

    def test_zero_radius_never_collides(self):
        self.assertFalse(circle_rect_collision((50, 50), 0, [0, 0, 100, 100]))

    def test_tuple_rect_is_accepted(self):
        self.assertTrue(circle_rect_collision((50, 50), 10, (0, 0, 100, 100)))
        self.assertFalse(circle_rect_collision((200, 200), 10, (0, 0, 40, 40)))


if __name__ == "__main__":
    unittest.main()

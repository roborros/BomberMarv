"""Fullscreen presentation: cover the monitor, keep the picture's ratio."""
import os
import sys
import unittest

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import choose_desktop_size, monitor_size, present_rect

pygame.init()


class PresentRectTests(unittest.TestCase):
    def test_fullscreen_cover_fills_common_screens(self):
        src = (1500, 1500)
        screens = (
            (1920, 1080),
            (2560, 1440),
            (3840, 2160),
            (1280, 720),
            (1280, 800),
            (1024, 768),
            (3440, 1440),
            (1080, 1920),
            (800, 600),
        )
        for win_w, win_h in screens:
            with self.subTest(screen=(win_w, win_h)):
                dest_w, dest_h, ox, oy = present_rect(*src, win_w, win_h, cover=True)
                self.assertLessEqual(ox, 0)
                self.assertLessEqual(oy, 0)
                self.assertGreaterEqual(ox + dest_w, win_w)
                self.assertGreaterEqual(oy + dest_h, win_h)
                self.assertLessEqual(abs(dest_w * src[1] - dest_h * src[0]), max(src))

    def test_wide_screen_crops_top_and_bottom(self):
        dest_w, dest_h, ox, oy = present_rect(1500, 1500, 1920, 1080, cover=True)
        self.assertEqual(ox, 0)
        self.assertLess(oy, 0)
        self.assertEqual(dest_w, 1920)
        self.assertGreaterEqual(dest_h, 1080)

    def test_tall_screen_crops_the_sides(self):
        dest_w, dest_h, ox, oy = present_rect(1500, 1500, 1080, 1920, cover=True)
        self.assertEqual(oy, 0)
        self.assertLess(ox, 0)
        self.assertGreaterEqual(dest_w, 1080)
        self.assertEqual(dest_h, 1920)

    def test_matching_shape_has_no_crop_and_no_bar(self):
        self.assertEqual(present_rect(1500, 1500, 900, 900, cover=True), (900, 900, 0, 0))

    def test_windowed_fit_keeps_the_whole_picture(self):
        dest_w, dest_h, ox, oy = present_rect(1500, 1500, 1920, 1080, cover=False)
        self.assertGreaterEqual(ox, 0)
        self.assertGreaterEqual(oy, 0)
        self.assertLessEqual(dest_w, 1920)
        self.assertLessEqual(dest_h, 1080)
        self.assertEqual(dest_w, dest_h)

    def test_scaled_blit_paints_every_window_edge(self):
        src = pygame.Surface((100, 100))
        src.fill((12, 18, 28))
        win = pygame.Surface((160, 90))
        win.fill((0, 0, 0))
        dest_w, dest_h, ox, oy = present_rect(100, 100, 160, 90, cover=True)
        scaled = pygame.transform.scale(src, (dest_w, dest_h))
        win.blit(scaled, (ox, oy))
        for point in ((0, 0), (159, 0), (0, 89), (159, 89), (80, 45)):
            self.assertNotEqual(win.get_at(point)[:3], (0, 0, 0), point)


class DesktopSizeTests(unittest.TestCase):
    def test_prefers_the_primary_monitor(self):
        self.assertEqual(choose_desktop_size([(1920, 1080), (1280, 720)], 800, 600), (1920, 1080))

    def test_falls_back_to_display_info(self):
        self.assertEqual(choose_desktop_size((), 1366, 768), (1366, 768))
        self.assertEqual(choose_desktop_size([(0, 0)], 1280, 800), (1280, 800))

    def test_fullscreen_uses_the_monitor_the_window_is_on(self):
        sizes = [(1920, 1080), (1280, 720), (2560, 1440)]
        self.assertEqual(monitor_size(sizes, 1, 800, 600), (1280, 720))
        self.assertEqual(monitor_size(sizes, 2, 800, 600), (2560, 1440))
        self.assertEqual(monitor_size(sizes, 9, 1366, 768), (1366, 768))

    def test_fullscreen_fit_keeps_the_whole_picture_on_the_glass(self):
        src = (1500, 1500)
        screens = (
            (1920, 1080),
            (2560, 1440),
            (3840, 2160),
            (1280, 720),
            (1280, 800),
            (1024, 768),
            (3440, 1440),
            (1080, 1920),
            (800, 600),
        )
        for win_w, win_h in screens:
            with self.subTest(screen=(win_w, win_h)):
                dest_w, dest_h, ox, oy = present_rect(*src, win_w, win_h, cover=False)
                self.assertGreaterEqual(ox, 0)
                self.assertGreaterEqual(oy, 0)
                self.assertLessEqual(ox + dest_w, win_w)
                self.assertLessEqual(oy + dest_h, win_h)
                self.assertGreater(dest_w, 0)
                self.assertGreater(dest_h, 0)


if __name__ == "__main__":
    unittest.main()

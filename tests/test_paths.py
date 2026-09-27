import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_paths import (
    _is_usable_lan_ip,
    app_root,
    detect_lan_ip,
    find_client_static_dir,
    lan_join_label,
    list_lan_ips,
    resource_path,
)


class PathTests(unittest.TestCase):
    def test_resource_path_finds_repo_assets(self):
        root = app_root()
        self.assertTrue(os.path.isdir(root))
        self.assertTrue(os.path.isfile(resource_path("sounds", "pick-bonus.wav")))
        self.assertTrue(os.path.isfile(resource_path("img", "logo.png")))

    def test_client_static_dir_is_optional(self):
        found = find_client_static_dir()
        if found is not None:
            self.assertTrue(os.path.isfile(os.path.join(found, "index.html")))

    def test_lan_ip_is_a_string(self):
        ip = detect_lan_ip()
        self.assertIsInstance(ip, str)
        self.assertGreater(len(ip), 0)

    def test_loopback_is_not_a_lan_ip(self):
        self.assertFalse(_is_usable_lan_ip("127.0.0.1"))
        self.assertFalse(_is_usable_lan_ip("169.254.1.1"))
        self.assertTrue(_is_usable_lan_ip("192.168.1.20"))
        for ip in list_lan_ips():
            self.assertFalse(ip.startswith("127."))

    def test_lan_join_label_includes_ip_and_port(self):
        label = lan_join_label(8080)
        self.assertTrue(label.startswith("http://"))
        self.assertTrue(label.endswith(":8080"))
        self.assertIn(detect_lan_ip(), label)


if __name__ == "__main__":
    unittest.main()

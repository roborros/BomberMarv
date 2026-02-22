import queue
import unittest

from queue_utils import put_latest_nonblocking


class QueueUtilsTests(unittest.TestCase):
    def test_put_latest_nonblocking_replaces_old_item(self):
        q = queue.Queue(maxsize=1)
        metrics = {}
        put_latest_nonblocking(q, {"v": 1}, metrics, "sent", "dropped")
        put_latest_nonblocking(q, {"v": 2}, metrics, "sent", "dropped")
        item = q.get_nowait()
        self.assertEqual(item["v"], 2)
        self.assertGreaterEqual(metrics.get("dropped", 0), 1)


if __name__ == "__main__":
    unittest.main()

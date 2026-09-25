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
        self.assertEqual(metrics.get("dropped", 0), 1)
        self.assertEqual(metrics.get("sent", 0), 2)

    def test_empty_queue_does_not_drop(self):
        q = queue.Queue(maxsize=2)
        metrics = {}
        put_latest_nonblocking(q, "a", metrics, "sent", "dropped")
        self.assertEqual(metrics["sent"], 1)
        self.assertEqual(metrics.get("dropped", 0), 0)
        self.assertEqual(q.get_nowait(), "a")

    def test_second_replace_keeps_latest(self):
        q = queue.Queue(maxsize=1)
        metrics = {}
        put_latest_nonblocking(q, 1, metrics, "sent", "dropped")
        put_latest_nonblocking(q, 2, metrics, "sent", "dropped")
        put_latest_nonblocking(q, 3, metrics, "sent", "dropped")
        self.assertEqual(q.get_nowait(), 3)
        self.assertEqual(metrics["dropped"], 2)


if __name__ == "__main__":
    unittest.main()

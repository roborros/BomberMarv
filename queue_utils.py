"""Queue helpers for low-latency bounded pipelines."""

from __future__ import annotations

import queue
from typing import Any, Dict


def put_latest_nonblocking(target_queue, payload: Any, metrics: Dict[str, int], sent_key: str, dropped_key: str) -> None:
    """Push payload without blocking and prefer latest-state semantics."""
    try:
        target_queue.put_nowait(payload)
        metrics[sent_key] = metrics.get(sent_key, 0) + 1
        return
    except queue.Full:
        metrics[dropped_key] = metrics.get(dropped_key, 0) + 1
    except Exception:
        metrics[dropped_key] = metrics.get(dropped_key, 0) + 1
        return

    # Drop one old item and retry once.
    try:
        target_queue.get_nowait()
        metrics[dropped_key] = metrics.get(dropped_key, 0) + 1
    except Exception:
        pass
    try:
        target_queue.put_nowait(payload)
        metrics[sent_key] = metrics.get(sent_key, 0) + 1
    except Exception:
        metrics[dropped_key] = metrics.get(dropped_key, 0) + 1

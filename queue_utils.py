"""Queue helpers for low-latency bounded pipelines."""

from __future__ import annotations

import queue
from typing import Any, Dict


def _producer_shares_pipe(target_queue) -> bool:
    """True when get() reads a process pipe, not an in-process buffer.

    The host is the producer for the state queue and the consumer for the
    input queue. Calling get() on a full multiprocessing.Queue from the
    producer races the other process's read and can block the caller inside
    recv() even after get_nowait(). That freezes the pygame thread once a
    few remote clients fall behind.
    """
    module = getattr(type(target_queue), "__module__", "") or ""
    if module.startswith("multiprocessing"):
        return True
    return bool(getattr(target_queue, "shares_process_pipe", False))


def put_latest_nonblocking(target_queue, payload: Any, metrics: Dict[str, int], sent_key: str, dropped_key: str) -> None:
    """Push payload without blocking and prefer latest-state semantics."""
    try:
        target_queue.put_nowait(payload)
        metrics[sent_key] = metrics.get(sent_key, 0) + 1
        return
    except queue.Full:
        pass
    except Exception:
        metrics[dropped_key] = metrics.get(dropped_key, 0) + 1
        return

    if _producer_shares_pipe(target_queue):
        # Leave the queued items for the real consumer. Drop this newer payload
        # instead of reading the pipe from the producer.
        metrics[dropped_key] = metrics.get(dropped_key, 0) + 1
        return

    # In-process queues can drop one old item and retry. Count a single drop.
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

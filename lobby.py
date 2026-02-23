"""Lobby/status helper functions for incremental Game decomposition."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def build_status_signature(status: Optional[Dict[str, Any]]) -> Optional[Tuple[tuple, tuple]]:
    if not isinstance(status, dict):
        return None
    clients = status.get("clients", {})
    slots = status.get("slots", {})
    clients_sig = []
    for cid, info in clients.items():
        if not isinstance(info, dict):
            continue
        clients_sig.append(
            (
                str(cid),
                bool(info.get("registered", False)),
                info.get("slot"),
                str(info.get("display_name") or ""),
                round(float(info.get("avg_latency_5s", 0.0)), 1),
            )
        )
    slots_sig = [(str(slot_id), bool(is_taken)) for slot_id, is_taken in slots.items()]
    return (tuple(sorted(clients_sig)), tuple(sorted(slots_sig)))

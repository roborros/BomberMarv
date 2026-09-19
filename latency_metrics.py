"""Honest latency clocks and idle-publish throttling.

Queue delay uses one wall clock (unix ms from time.time_ns). It is not RTT
and must not be mixed with pygame get_ticks() or a remote Date.now().
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

HUD_METRICS_INTERVAL_MS = 500
IDLE_PUBLISH_INTERVAL_MS = 250
PLAYING_PUBLISH_STATES = frozenset({"playing", "get_ready", "boss_fight"})


def wall_clock_ms() -> int:
    import time

    return time.time_ns() // 1_000_000


def queue_delay_ms(received_at_ms: Any, applied_at_ms: Any) -> int:
    """Host input-queue delay: apply time minus WS/RTC enqueue time."""
    if not isinstance(received_at_ms, (int, float)) or not isinstance(applied_at_ms, (int, float)):
        return 0
    return max(0, int(applied_at_ms) - int(received_at_ms))


def rtt_ms(sent_at_ms: Any, received_at_ms: Any) -> int:
    """Same-clock round trip (client Date.now sent vs client Date.now on ack)."""
    if not isinstance(sent_at_ms, (int, float)) or not isinstance(received_at_ms, (int, float)):
        return 0
    return max(0, int(received_at_ms) - int(sent_at_ms))


def board_fingerprint(board: Any) -> int:
    if not isinstance(board, list):
        return 0
    h = 2166136261
    for row in board:
        if not isinstance(row, (list, tuple)):
            continue
        for cell in row:
            try:
                value = int(cell) & 0xFF
            except (TypeError, ValueError):
                value = 0
            h ^= value
            h = (h * 16777619) & 0xFFFFFFFF
    return h


def gameplay_fingerprint(state: Dict[str, Any]) -> Tuple[Any, ...]:
    """Identity of lobby/gameplay worth a full snapshot; ignores clocks/metrics."""
    players_raw = state.get("players") or []
    players = tuple(
        (
            p.get("id"),
            p.get("name"),
            tuple(p.get("color") or ()),
            p.get("alive"),
            int(p.get("x") or 0),
            int(p.get("y") or 0),
            p.get("owner_client_id"),
            p.get("owner_client_player_id"),
        )
        for p in players_raw
        if isinstance(p, dict)
    )
    bombs = tuple(
        (b.get("x"), b.get("y"), b.get("start_time"))
        for b in (state.get("bombs") or [])
        if isinstance(b, dict)
    )
    crushing = state.get("crushing_walls")
    crushing_sig = None
    if isinstance(crushing, dict):
        crushing_sig = (crushing.get("active"), crushing.get("index"))
    return (
        state.get("state"),
        state.get("local_player_count"),
        state.get("grid_width"),
        state.get("grid_height"),
        crushing_sig,
        board_fingerprint(state.get("board")),
        players,
        bombs,
        len(state.get("explosions") or []),
        len(state.get("powerups") or []),
        repr(state.get("boss_fight_winner")),
    )


def should_publish_snapshot(
    game_state: Any,
    fingerprint: Any,
    last_fingerprint: Any,
    now_ms: int,
    last_publish_ms: int,
    interval_ms: int = IDLE_PUBLISH_INTERVAL_MS,
    force: bool = False,
) -> bool:
    if force:
        return True
    if last_publish_ms < 0:
        return True
    if game_state in PLAYING_PUBLISH_STATES:
        return True
    if fingerprint != last_fingerprint:
        return True
    return (int(now_ms) - int(last_publish_ms)) >= int(interval_ms)


def should_attach_hud_metrics(now_ms: int, last_hud_ms: int, interval_ms: int = HUD_METRICS_INTERVAL_MS) -> bool:
    if last_hud_ms < 0:
        return True
    return (int(now_ms) - int(last_hud_ms)) >= int(interval_ms)


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    idx = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


def build_hud_metrics(
    *,
    input_queue_delay_samples_ms: Iterable[float] = (),
    sim_step_samples_ms: Iterable[float] = (),
    tick_lag_samples: Iterable[float] = (),
    input_events_processed: int = 0,
    input_events_errors: int = 0,
    state_queue_sent: int = 0,
    state_queue_dropped: int = 0,
    host_fps_5s: float = 0.0,
    host_render_fps_5s: float = 0.0,
    sim_tick: int = 0,
    input_tick_reused: int = 0,
    input_tick_buffered: int = 0,
) -> Dict[str, Any]:
    delay_samples = list(input_queue_delay_samples_ms)
    sim_samples = list(sim_step_samples_ms)
    lag_samples = list(tick_lag_samples)
    avg_delay = sum(delay_samples) / len(delay_samples) if delay_samples else 0.0
    avg_sim = sum(sim_samples) / len(sim_samples) if sim_samples else 0.0
    return {
        "clock": "unix_ms",
        "meaning": "input_apply is host queue delay, not client RTT",
        "input_queue_delay_avg_ms": round(avg_delay, 2),
        "input_queue_delay_p50_ms": round(percentile(delay_samples, 50), 2),
        "input_queue_delay_p95_ms": round(percentile(delay_samples, 95), 2),
        "input_queue_delay_p99_ms": round(percentile(delay_samples, 99), 2),
        # Aliases kept so existing HUDs keep working while labels are fixed.
        "avg_input_apply_ms": round(avg_delay, 2),
        "input_apply_p50_ms": round(percentile(delay_samples, 50), 2),
        "input_apply_p95_ms": round(percentile(delay_samples, 95), 2),
        "input_apply_p99_ms": round(percentile(delay_samples, 99), 2),
        "sim_step_avg_ms": round(avg_sim, 2),
        "sim_step_p95_ms": round(percentile(sim_samples, 95), 2),
        "host_fps_5s": round(float(host_fps_5s), 1),
        "host_render_fps_5s": round(float(host_render_fps_5s), 1),
        "sim_tick": int(sim_tick),
        "input_tick_reused": int(input_tick_reused),
        "input_tick_buffered": int(input_tick_buffered),
        "input_tick_apply_lag_p95": round(percentile(lag_samples, 95), 2),
        "input_events_processed": int(input_events_processed),
        "input_events_errors": int(input_events_errors),
        "state_queue_sent": int(state_queue_sent),
        "state_queue_dropped": int(state_queue_dropped),
    }


def prepare_wire_state(
    state_payload: Dict[str, Any],
    *,
    wall_ms: int,
    hud_metrics: Optional[Dict[str, Any]] = None,
    sim_tick: Optional[int] = None,
) -> Dict[str, Any]:
    """Copy a host snapshot for the state queue without 60 Hz HUD metrics."""
    wire = dict(state_payload)
    wire.pop("_net_metrics", None)
    wire.pop("_hud_metrics", None)
    if sim_tick is not None:
        wire["_sim_tick"] = int(sim_tick)
    wire["_host_published_at_ms"] = int(wall_ms)
    if hud_metrics is not None:
        wire["_hud_metrics"] = dict(hud_metrics)
    return wire


def split_hud_metrics(state: Any) -> Tuple[Any, Optional[Dict[str, Any]]]:
    if not isinstance(state, dict):
        return state, None
    gameplay = dict(state)
    gameplay.pop("_net_metrics", None)
    hud = gameplay.pop("_hud_metrics", None)
    if not isinstance(hud, dict):
        hud = None
    return gameplay, hud

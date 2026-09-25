"""Replay helpers extracted from Game for incremental modularization."""

from __future__ import annotations

from typing import Tuple
import types


def _player_direction(player) -> Tuple[float, float]:
    direction = getattr(player, "direction", (0.0, 0.0))
    try:
        return (float(direction[0]), float(direction[1]))
    except (TypeError, IndexError):
        return (0.0, 0.0)


def build_replay_snapshot(game) -> dict:
    players_state = []
    for p in game.players:
        players_state.append(
            {
                "name": p.name,
                "color": tuple(p.color),
                "pos": (float(p.pos[0]), float(p.pos[1])),
                "alive": bool(p.alive),
                "draw_radius": int(p.draw_radius),
                "fire_power": int(p.fire_power),
                "bomb_capacity": int(p.bomb_capacity),
                "direction": _player_direction(p),
                "animation_time": float(getattr(p, "animation_time", 0) or 0),
                "quad_damage": bool(getattr(p, "quad_damage", False)),
                "quad_damage_start_time": int(getattr(p, "quad_damage_start_time", 0) or 0),
                "death_animation_time": float(getattr(p, "death_animation_time", 0) or 0),
                "pickup_message": getattr(p, "pickup_message", "") or "",
                "pickup_message_end_time": int(getattr(p, "pickup_message_end_time", 0) or 0),
                "global_id": getattr(p, "global_id", None) or p.name,
            }
        )
    bombs_state = [{"x": b.x, "y": b.y, "start": int(b.start_time)} for b in game.bombs]
    explosions_state = []
    for e in game.explosions:
        explosions_state.append({"cells": [tuple(c) for c in e.cells], "start": int(e.start_time), "qd": bool(e.quad_damage)})
    powerups_state = [{"x": pu.x, "y": pu.y, "type": pu.type} for pu in game.powerups]
    board = [list(row) for row in game.board] if getattr(game, "board", None) is not None else None
    return {
        "t": int(game.current_time),
        "players": players_state,
        "bombs": bombs_state,
        "explosions": explosions_state,
        "powerups": powerups_state,
        "board": board,
        "grid_width": int(getattr(game, "grid_width", len(board[0]) if board else 0)),
        "grid_height": int(getattr(game, "grid_height", len(board) if board else 0)),
    }


class ReplayPlayer:
    """Lightweight player stand-in that draw_players can render like live gameplay."""

    def __init__(self, state: dict):
        self.name = state.get("name", "")
        self.color = tuple(state.get("color", (200, 200, 200)))
        self.pos = state.get("pos", (0.0, 0.0))
        self.alive = bool(state.get("alive", True))
        self.draw_radius = int(state.get("draw_radius", 40))
        self.direction = state.get("direction", (0.0, 0.0))
        self.animation_time = float(state.get("animation_time", 0) or 0)
        self.quad_damage = bool(state.get("quad_damage", False))
        self.quad_damage_start_time = int(state.get("quad_damage_start_time", 0) or 0)
        self.death_animation_time = float(state.get("death_animation_time", 0) or 0)
        self.pickup_message = state.get("pickup_message", "") or ""
        self.pickup_message_end_time = int(state.get("pickup_message_end_time", 0) or 0)
        self.global_id = state.get("global_id", self.name)

    def get_grid_pos(self):
        from bm_params import CELL_SIZE
        return (int(self.pos[0] // CELL_SIZE), int(self.pos[1] // CELL_SIZE))


def hydrate_replay_snapshot(snap: dict) -> dict:
    """Turn a stored snapshot into objects the live draw functions understand."""
    bombs = [
        types.SimpleNamespace(x=b["x"], y=b["y"], start_time=b["start"])
        for b in snap.get("bombs", [])
    ]
    explosions = [
        types.SimpleNamespace(
            cells=[tuple(c) for c in e.get("cells", [])],
            start_time=e["start"],
            quad_damage=bool(e.get("qd")),
        )
        for e in snap.get("explosions", [])
        if e.get("cells")
    ]
    powerups = [
        types.SimpleNamespace(x=pu["x"], y=pu["y"], type=pu["type"])
        for pu in snap.get("powerups", [])
    ]
    return {
        "t": int(snap.get("t", 0)),
        "board": snap.get("board"),
        "grid_width": snap.get("grid_width"),
        "grid_height": snap.get("grid_height"),
        "players": [ReplayPlayer(p) for p in snap.get("players", [])],
        "bombs": bombs,
        "explosions": explosions,
        "powerups": powerups,
    }


def replay_view_rect(
    cam_x: int,
    cam_y: int,
    world_w: int,
    world_h: int,
    cell_size: int,
    radius_cells: int,
) -> Tuple[int, int, int, int]:
    """Axis-aligned camera crop, clamped so edge deaths are not mostly empty."""
    desired = max(cell_size, (2 * int(radius_cells) + 1) * int(cell_size))
    view_w = min(desired, max(1, int(world_w)))
    view_h = min(desired, max(1, int(world_h)))
    x = int(cam_x) - view_w // 2
    y = int(cam_y) - view_h // 2
    x = max(0, min(x, int(world_w) - view_w))
    y = max(0, min(y, int(world_h) - view_h))
    return x, y, view_w, view_h


def letterbox_dest(src_w: int, src_h: int, avail_w: int, avail_h: int) -> Tuple[int, int, int, int]:
    """Fit src into avail with uniform scale. Returns (dest_w, dest_h, offset_x, offset_y)."""
    if src_w <= 0 or src_h <= 0 or avail_w <= 0 or avail_h <= 0:
        return 0, 0, 0, 0
    scale = min(avail_w / src_w, avail_h / src_h)
    dest_w = max(1, int(round(src_w * scale)))
    dest_h = max(1, int(round(src_h * scale)))
    dest_w = min(dest_w, avail_w)
    dest_h = min(dest_h, avail_h)
    return dest_w, dest_h, (avail_w - dest_w) // 2, (avail_h - dest_h) // 2


def slice_replay_frames(buffer, start_t: int, end_t: int):
    return [(t, snap) for (t, snap) in buffer if start_t <= t <= end_t]


def freeze_kill_cam_clip(buffer, name: str, death_time: int, now: int, pre_ms: int, post_ms: int):
    """Cut a kill-cam from the rolling buffer: pre-roll through death + post_ms (or now)."""
    end_t = min(int(now), int(death_time) + int(post_ms))
    start_t = max(0, int(death_time) - int(pre_ms))
    frames = slice_replay_frames(buffer, start_t, end_t)
    if not frames:
        return None
    return {
        "name": name,
        "death_time": int(death_time),
        "start": start_t,
        "end": end_t,
        "frames": frames,
    }


def pick_kill_cam(clips, elapsed_ms: int):
    """Cycle clips in death order. Returns (clip, target_t) or (None, None)."""
    if not clips:
        return None, None
    durations = [max(1, int(clip["end"] - clip["start"])) for clip in clips]
    total = sum(durations)
    offset = int(elapsed_ms) % total
    acc = 0
    for clip, duration in zip(clips, durations):
        if offset < acc + duration:
            return clip, clip["start"] + (offset - acc)
        acc += duration
    clip = clips[-1]
    return clip, clip["end"]


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def interpolate_replay_snapshots(snap_a: dict, snap_b: dict, u: float) -> dict:
    """Blend player positions between two snapshots. u in [0, 1]."""
    if snap_a is snap_b or u <= 0:
        return snap_a
    if u >= 1:
        return snap_b
    later = snap_b if u >= 0.5 else snap_a
    by_name = {p.get("name"): p for p in snap_b.get("players", [])}
    players = []
    for src in snap_a.get("players", []):
        dst = by_name.get(src.get("name"))
        if dst is None:
            players.append(src)
            continue
        blended = dict(src)
        ax, ay = src.get("pos", (0.0, 0.0))
        bx, by = dst.get("pos", (ax, ay))
        blended["pos"] = (_lerp(float(ax), float(bx), u), _lerp(float(ay), float(by), u))
        blended["animation_time"] = _lerp(
            float(src.get("animation_time", 0) or 0),
            float(dst.get("animation_time", 0) or 0),
            u,
        )
        blended["alive"] = src.get("alive") if u < 1 else dst.get("alive")
        blended["death_animation_time"] = _lerp(
            float(src.get("death_animation_time", 0) or 0),
            float(dst.get("death_animation_time", 0) or 0),
            u,
        )
        players.append(blended)
    out = dict(later)
    out["players"] = players
    out["t"] = int(_lerp(int(snap_a.get("t", 0)), int(snap_b.get("t", 0)), u))
    return out


def frame_at_time(frames, target_t: int) -> dict:
    """Nearest-at-or-before snapshot, interpolated toward the next sample."""
    if not frames:
        return None
    prev_t, prev_snap = frames[0]
    next_t, next_snap = frames[-1]
    for t, snap in frames:
        if t <= target_t:
            prev_t, prev_snap = t, snap
        if t >= target_t:
            next_t, next_snap = t, snap
            break
    if next_t <= prev_t:
        return prev_snap
    u = (target_t - prev_t) / float(next_t - prev_t)
    return interpolate_replay_snapshots(prev_snap, next_snap, u)

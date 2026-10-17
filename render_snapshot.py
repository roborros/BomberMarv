"""One-way, immutable render state snapshot from the 60 Hz backend to the local renderer.

The backend simulation thread builds a ``RenderSnapshot`` after each simulation step
and publishes it to ``RenderStateHub``. The local renderer thread only ever reads
``RenderSnapshot`` instances and never accesses or mutates live ``Game`` objects.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PlayerRenderSnapshot:
    name: str
    color: Tuple[int, int, int]
    pos: Tuple[float, float]
    grid_pos: Tuple[int, int]
    alive: bool
    draw_radius: int
    direction: Tuple[float, float]
    animation_time: float
    quad_damage: bool
    quad_damage_start_time: int
    death_animation_time: float
    pickup_message: str
    pickup_message_end_time: int
    global_id: Any
    sprite: str
    cleaver_swing_until: int
    boss_shield_until: int
    controls: Optional[Dict[str, Any]]
    trophies: int
    is_ai: bool
    ai_role: str
    title: str
    death_time_ms: Optional[int]
    death_time_rel_ms: Optional[int]
    fire_power: int
    bomb_capacity: int
    fire_power_at_death: Optional[int]
    bomb_capacity_at_death: Optional[int]
    walls_destroyed: int
    players_killed: int
    powerups_collected: int
    quad_damage_collected: int
    cells_walked: int
    total_walls_destroyed: int
    total_players_killed: int
    total_powerups_collected: int
    total_quad_damage_collected: int
    total_cells_walked: int

    def get_grid_pos(self) -> Tuple[int, int]:
        return self.grid_pos


@dataclass(frozen=True)
class BombRenderSnapshot:
    x: int
    y: int
    start_time: int
    fire_power: int
    quad_damage: bool


@dataclass(frozen=True)
class ExplosionRenderSnapshot:
    cells: Tuple[Tuple[int, int], ...]
    start_time: int
    quad_damage: bool
    lightning: bool = False
    lightning_style: str = ""


@dataclass(frozen=True)
class PowerUpRenderSnapshot:
    x: int
    y: int
    type: str
    spawn_time: int


@dataclass
class RenderSnapshot:
    """Detached, read-only view of the game state for the local Pygame renderer."""

    seq: int
    game_state: str
    current_time: int
    startup_start_time: int
    startup_jumps: Tuple[Any, ...]
    round_start_time: Optional[int]
    game_start_time: int
    grid_width: int
    grid_height: int
    surface_size: Optional[Tuple[int, int]]
    board: Tuple[Tuple[int, ...], ...]
    players: Tuple[PlayerRenderSnapshot, ...]
    bombs: Tuple[BombRenderSnapshot, ...]
    explosions: Tuple[ExplosionRenderSnapshot, ...]
    powerups: Tuple[PowerUpRenderSnapshot, ...]
    crushing_walls_active: bool
    crushing_walls_index: int
    _crushing_wall_start_seconds: Tuple[int, int]
    _trophy_threshold: int
    _result_prompt: str
    _leave_prompt_title: str
    leave_prompt_open: bool
    leave_prompt_choice: str
    quit_prompt_open: bool
    quit_prompt_choice: str
    quit_requested: bool
    boss_fight_winner: Optional[PlayerRenderSnapshot]
    boss_advance: str
    boss_stage: str
    _marv_killer_result: bool
    _boss_result_copy: Tuple[str, str, Tuple[int, int, int], str]
    _champion_player: Optional[PlayerRenderSnapshot]
    kill_cam_clips: Tuple[Dict[str, Any], ...]
    replay_segment: Optional[List[Any]]
    replay_segment_start_time: int
    replay_segment_end_time: int
    replay_loop_anchor_time: Optional[int]
    replay_focus_player: Optional[str]
    replay_end_time: Optional[int]
    replay_start_time: Optional[int]
    replay_buffer: List[Any]
    prep_section: str
    settings_cursor: int
    prep_num_players: int
    prep_ai_count: int
    prep_grid_offset: int
    prep_cursor_row: int
    prep_cursor_col: int
    prep_editing_name: bool
    prep_name_edit_index: int
    prep_controls: List[Dict[str, Any]]
    _cached_status: Optional[Dict[str, Any]]
    _all_players_info: Tuple[Dict[str, Any], ...]
    sound_events: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def crushing_wall_start_seconds(self) -> Tuple[int, int]:
        return self._crushing_wall_start_seconds

    def trophy_threshold(self) -> int:
        return self._trophy_threshold

    def result_prompt(self) -> str:
        return self._result_prompt

    def leave_prompt_title(self) -> str:
        return self._leave_prompt_title

    def marv_killer_result(self) -> bool:
        return self._marv_killer_result

    def boss_result_copy(self) -> Tuple[str, str, Tuple[int, int, int], str]:
        return self._boss_result_copy

    def champion_player(self) -> Optional[PlayerRenderSnapshot]:
        return self._champion_player

    def get_all_players_info(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._all_players_info]


def _snapshot_player(p: Any) -> PlayerRenderSnapshot:
    raw_color = getattr(p, "color", (255, 255, 255))
    if isinstance(raw_color, (list, tuple)) and len(raw_color) >= 3:
        color = (int(raw_color[0]), int(raw_color[1]), int(raw_color[2]))
    else:
        color = (255, 255, 255)
    raw_pos = getattr(p, "pos", (0.0, 0.0))
    pos = (float(raw_pos[0]), float(raw_pos[1]))
    if hasattr(p, "get_grid_pos") and callable(p.get_grid_pos):
        gp = p.get_grid_pos()
        grid_pos = (int(gp[0]), int(gp[1]))
    else:
        grid_pos = (0, 0)
    raw_dir = getattr(p, "direction", (0.0, 0.0))
    if raw_dir is not None and len(raw_dir) >= 2:
        direction = (float(raw_dir[0]), float(raw_dir[1]))
    else:
        direction = (0.0, 0.0)
    raw_controls = getattr(p, "controls", None)
    controls = dict(raw_controls) if isinstance(raw_controls, dict) else None
    return PlayerRenderSnapshot(
        name=str(getattr(p, "name", "") or ""),
        color=color,
        pos=pos,
        grid_pos=grid_pos,
        alive=bool(getattr(p, "alive", True)),
        draw_radius=int(getattr(p, "draw_radius", 20) or 20),
        direction=direction,
        animation_time=float(getattr(p, "animation_time", 0.0) or 0.0),
        quad_damage=bool(getattr(p, "quad_damage", False)),
        quad_damage_start_time=int(getattr(p, "quad_damage_start_time", 0) or 0),
        death_animation_time=float(getattr(p, "death_animation_time", 0.0) or 0.0),
        pickup_message=str(getattr(p, "pickup_message", "") or ""),
        pickup_message_end_time=int(getattr(p, "pickup_message_end_time", 0) or 0),
        global_id=getattr(p, "global_id", None),
        sprite=str(getattr(p, "sprite", "") or ""),
        cleaver_swing_until=int(getattr(p, "cleaver_swing_until", 0) or 0),
        boss_shield_until=int(getattr(p, "boss_shield_until", 0) or 0),
        controls=controls,
        trophies=int(getattr(p, "trophies", 0) or 0),
        is_ai=bool(getattr(p, "is_ai", False)),
        ai_role=str(getattr(p, "ai_role", "") or ""),
        title=str(getattr(p, "title", "") or ""),
        death_time_ms=getattr(p, "death_time_ms", None),
        death_time_rel_ms=getattr(p, "death_time_rel_ms", None),
        fire_power=int(getattr(p, "fire_power", 1) or 1),
        bomb_capacity=int(getattr(p, "bomb_capacity", 1) or 1),
        fire_power_at_death=getattr(p, "fire_power_at_death", None),
        bomb_capacity_at_death=getattr(p, "bomb_capacity_at_death", None),
        walls_destroyed=int(getattr(p, "walls_destroyed", 0) or 0),
        players_killed=int(getattr(p, "players_killed", 0) or 0),
        powerups_collected=int(getattr(p, "powerups_collected", 0) or 0),
        quad_damage_collected=int(getattr(p, "quad_damage_collected", 0) or 0),
        cells_walked=int(getattr(p, "cells_walked", 0) or 0),
        total_walls_destroyed=int(getattr(p, "total_walls_destroyed", 0) or 0),
        total_players_killed=int(getattr(p, "total_players_killed", 0) or 0),
        total_powerups_collected=int(getattr(p, "total_powerups_collected", 0) or 0),
        total_quad_damage_collected=int(getattr(p, "total_quad_damage_collected", 0) or 0),
        total_cells_walked=int(getattr(p, "total_cells_walked", 0) or 0),
    )


def build_render_snapshot(
    game: Any,
    seq: int = 0,
    sound_events: Optional[List[Dict[str, Any]]] = None,
) -> RenderSnapshot:
    """Create a completely detached ``RenderSnapshot`` from the backend ``Game`` instance."""
    if isinstance(game, RenderSnapshot):
        return game

    state = str(getattr(game, "game_state", "startup") or "startup")
    raw_board = getattr(game, "board", ()) or ()
    board = tuple(tuple(int(cell) for cell in row) for row in raw_board)
    gw = int(getattr(game, "grid_width", len(board[0]) if board else 13) or 13)
    gh = int(getattr(game, "grid_height", len(board) if board else 13) or 13)
    raw_surf_size = getattr(game, "_desired_surface_size", None)
    surface_size = (int(raw_surf_size[0]), int(raw_surf_size[1])) if isinstance(raw_surf_size, (tuple, list)) and len(raw_surf_size) == 2 else None

    players = tuple(_snapshot_player(p) for p in list(getattr(game, "players", ()) or ()))
    bombs = tuple(
        BombRenderSnapshot(
            x=int(b.x),
            y=int(b.y),
            start_time=int(b.start_time),
            fire_power=int(getattr(b, "fire_power", 1) or 1),
            quad_damage=bool(getattr(b, "quad_damage", False)),
        )
        for b in list(getattr(game, "bombs", ()) or ())
    )
    explosions = tuple(
        ExplosionRenderSnapshot(
            cells=tuple((int(c[0]), int(c[1])) for c in (e.cells or ())),
            start_time=int(e.start_time),
            quad_damage=bool(getattr(e, "quad_damage", False)),
            lightning=bool(getattr(e, "lightning", False)),
            lightning_style=str(getattr(e, "lightning_style", "") or ""),
        )
        for e in list(getattr(game, "explosions", ()) or ())
    )
    powerups = tuple(
        PowerUpRenderSnapshot(
            x=int(pu.x),
            y=int(pu.y),
            type=str(pu.type),
            spawn_time=int(getattr(pu, "spawn_time", 0) or 0),
        )
        for pu in list(getattr(game, "powerups", ()) or ())
    )

    if hasattr(game, "crushing_wall_start_seconds") and callable(game.crushing_wall_start_seconds):
        cw_start = tuple(int(v) for v in game.crushing_wall_start_seconds())
    else:
        cw_start = (60, 60)

    trophy_goal = int(game.trophy_threshold()) if hasattr(game, "trophy_threshold") else 1
    result_prompt = str(game.result_prompt()) if hasattr(game, "result_prompt") else ""
    leave_title = str(game.leave_prompt_title()) if hasattr(game, "leave_prompt_title") else "Leave game?"

    raw_boss_winner = getattr(game, "boss_fight_winner", None)
    boss_winner = _snapshot_player(raw_boss_winner) if raw_boss_winner is not None else None

    raw_champ = game.champion_player() if hasattr(game, "champion_player") and state == "champion" else None
    champion_snap = _snapshot_player(raw_champ) if raw_champ is not None else None

    marv_killer = bool(game.marv_killer_result()) if hasattr(game, "marv_killer_result") else False
    if hasattr(game, "boss_result_copy") and callable(game.boss_result_copy):
        b_copy = game.boss_result_copy()
        boss_copy = (str(b_copy[0]), str(b_copy[1]), tuple(b_copy[2]), str(b_copy[3]))
    else:
        boss_copy = ("Draw", "", (220, 224, 232), "Enter: back to the lobby")

    intermission = state in ("win", "champion", "boss_result")
    kill_cams = tuple(dict(c) for c in (getattr(game, "kill_cam_clips", None) or ())) if intermission else ()
    raw_seg = getattr(game, "replay_segment", None) if intermission else None
    replay_seg = list(raw_seg) if raw_seg else None
    replay_buf = list(getattr(game, "replay_buffer", None) or []) if (intermission and not kill_cams and not replay_seg) else []

    if state in ("game_prep", "startup") and hasattr(game, "get_all_players_info"):
        all_players_info = tuple(dict(info) for info in game.get_all_players_info())
    else:
        all_players_info = ()

    raw_status = getattr(game, "_cached_status", None)
    cached_status = dict(raw_status) if isinstance(raw_status, dict) else None
    prep_controls = [dict(c) for c in (getattr(game, "prep_controls", None) or []) if isinstance(c, dict)]

    if sound_events is None:
        if hasattr(game, "consume_sound_events") and callable(game.consume_sound_events):
            drained_sounds = tuple(dict(ev) for ev in game.consume_sound_events())
        else:
            drained_sounds = tuple(dict(ev) for ev in (getattr(game, "pending_sound_events", None) or ()))
    else:
        drained_sounds = tuple(dict(ev) for ev in sound_events)

    return RenderSnapshot(
        seq=int(seq),
        game_state=state,
        current_time=int(getattr(game, "current_time", 0) or 0),
        startup_start_time=int(getattr(game, "startup_start_time", 0) or 0),
        startup_jumps=tuple(getattr(game, "startup_jumps", ()) or ()),
        round_start_time=getattr(game, "round_start_time", None),
        game_start_time=int(getattr(game, "game_start_time", 0) or 0),
        grid_width=gw,
        grid_height=gh,
        surface_size=surface_size,
        board=board,
        players=players,
        bombs=bombs,
        explosions=explosions,
        powerups=powerups,
        crushing_walls_active=bool(getattr(game, "crushing_walls_active", False)),
        crushing_walls_index=int(getattr(game, "crushing_walls_index", 0) or 0),
        _crushing_wall_start_seconds=(int(cw_start[0]), int(cw_start[1])),
        _trophy_threshold=trophy_goal,
        _result_prompt=result_prompt,
        _leave_prompt_title=leave_title,
        leave_prompt_open=bool(getattr(game, "leave_prompt_open", False)),
        leave_prompt_choice=str(getattr(game, "leave_prompt_choice", "no") or "no"),
        quit_prompt_open=bool(getattr(game, "quit_prompt_open", False)),
        quit_prompt_choice=str(getattr(game, "quit_prompt_choice", "no") or "no"),
        quit_requested=bool(getattr(game, "quit_requested", False)),
        boss_fight_winner=boss_winner,
        boss_advance=str(getattr(game, "boss_advance", "lobby") or "lobby"),
        boss_stage=str(getattr(game, "boss_stage", "bombermarv") or "bombermarv"),
        _marv_killer_result=marv_killer,
        _boss_result_copy=boss_copy,
        _champion_player=champion_snap,
        kill_cam_clips=kill_cams,
        replay_segment=replay_seg,
        replay_segment_start_time=int(getattr(game, "replay_segment_start_time", 0) or 0),
        replay_segment_end_time=int(getattr(game, "replay_segment_end_time", 0) or 0),
        replay_loop_anchor_time=getattr(game, "replay_loop_anchor_time", None),
        replay_focus_player=getattr(game, "replay_focus_player", None),
        replay_end_time=getattr(game, "replay_end_time", None),
        replay_start_time=getattr(game, "replay_start_time", None),
        replay_buffer=replay_buf,
        prep_section=str(getattr(game, "prep_section", "local_players") or "local_players"),
        settings_cursor=int(getattr(game, "settings_cursor", 0) or 0),
        prep_num_players=int(getattr(game, "prep_num_players", 1) or 1),
        prep_ai_count=int(getattr(game, "prep_ai_count", 0) or 0),
        prep_grid_offset=int(getattr(game, "prep_grid_offset", 0) or 0),
        prep_cursor_row=int(getattr(game, "prep_cursor_row", 0) or 0),
        prep_cursor_col=int(getattr(game, "prep_cursor_col", 0) or 0),
        prep_editing_name=bool(getattr(game, "prep_editing_name", False)),
        prep_name_edit_index=int(getattr(game, "prep_name_edit_index", 0) or 0),
        prep_controls=prep_controls,
        _cached_status=cached_status,
        _all_players_info=all_players_info,
        sound_events=drained_sounds,
    )


class RenderStateHub:
    """One-way, non-blocking handoff from the 60 Hz backend thread to the local renderer thread.

    - ``publish(snapshot)`` never blocks the backend thread; it atomically replaces the latest
      snapshot and accumulates any unconsumed ``sound_events`` so a skipped render frame never
      drops a sound effect.
    - ``consume_latest()`` returns the newest ``RenderSnapshot`` with all pending sound events
      since the renderer's last read, clearing the pending sound queue so sounds play once.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Optional[RenderSnapshot] = None
        self._pending_sounds: List[Dict[str, Any]] = []
        self._seq = 0

    def publish(self, snapshot: RenderSnapshot) -> RenderSnapshot:
        with self._lock:
            self._seq += 1
            if snapshot.sound_events:
                self._pending_sounds.extend(snapshot.sound_events)
                if len(self._pending_sounds) > 64:
                    del self._pending_sounds[:-64]
            self._latest = RenderSnapshot(
                **{
                    **snapshot.__dict__,
                    "sound_events": (),
                }
            )
            return snapshot

    def consume_latest(self) -> Optional[RenderSnapshot]:
        with self._lock:
            snap = self._latest
            if snap is None:
                return None
            if not self._pending_sounds:
                return snap
            sounds = tuple(self._pending_sounds)
            self._pending_sounds.clear()
            return RenderSnapshot(
                **{
                    **snap.__dict__,
                    "sound_events": sounds,
                }
            )

    def peek_latest(self) -> Optional[RenderSnapshot]:
        with self._lock:
            return self._latest

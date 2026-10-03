"""Host match rules. Saved values override the defaults in bm_params and survive restart."""
from __future__ import annotations

import json
import os
import sys

from bm_params import (
    BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS,
    CRUSHING_WALLS_DELAY,
    CRUSHING_WALLS_GROWTH_INTERVAL_MS,
    EXPLOSION_DURATION,
    PLAYER_SPEED_MULTIPLIER,
    POWERUP_PROBABILITY,
    BIG_EXPLOSION_SOUND_DELAY_MS,
    BIG_EXPLOSION_TILE_THRESHOLD,
    BIG_EXPLOSION_VOLUME,
    BIG_EXPLOSION_WINDOW_MS,
    QUAD_DAMAGE_DELAY,
    QUAD_DAMAGE_POWER,
    QUAD_DAMAGE_PROBABILITY,
    QUAD_DAMAGE_SPEEDUP,
    QUAD_DAMAGE_TIME,
)
from bm_paths import user_settings_path

# key, label, kind, default, min, max, step
RULES = (
    ("players_block", "Players block each other", "bool", True, None, None, None),
    ("friendly_fire", "Friendly fire", "bool", False, None, None, None),
    ("speed_multiplier", "Player speed", "float", PLAYER_SPEED_MULTIPLIER, 0.8, 2.0, 0.05),
    ("start_bombs", "Starting bombs", "int", 1, 1, 5, 1),
    ("start_fire", "Starting fire", "int", 1, 1, 8, 1),
    ("bomb_fuse_s", "Bomb fuse (s)", "float", 3.0, 1.0, 8.0, 0.5),
    ("blast_ms", "Blast duration (ms)", "int", EXPLOSION_DURATION, 200, 1200, 100),
    ("powerup_chance", "Powerup chance", "float", POWERUP_PROBABILITY, 0.0, 1.0, 0.05),
    ("quad_chance", "Quad Damage chance / tick", "float", QUAD_DAMAGE_PROBABILITY, 0.0, 0.01, 0.0001),
    ("quad_delay_s", "Quad Damage delay (s)", "int", QUAD_DAMAGE_DELAY, 0, 180, 5),
    ("quad_time_s", "Quad Damage time (s)", "int", QUAD_DAMAGE_TIME, 5, 60, 5),
    ("quad_power", "Quad Damage strength", "int", QUAD_DAMAGE_POWER, 2, 15, 1),
    ("quad_speed", "Quad Damage speed", "float", QUAD_DAMAGE_SPEEDUP, 1.0, 2.5, 0.1),
    ("walls_delay_s", "Crushing walls start (s)", "int", CRUSHING_WALLS_DELAY, 60, 360, 10),
    ("walls_growth_ms", "Walls close every (ms)", "int", CRUSHING_WALLS_GROWTH_INTERVAL_MS, 50, 3000, 50),
    ("walls_boss_growth_ms", "Boss walls close every (ms)", "int", BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS, 50, 4000, 50),
    ("big_blast_tiles", "Loud hit size (tiles)", "int", BIG_EXPLOSION_TILE_THRESHOLD, 10, 200, 5),
    ("big_blast_window_ms", "Loud hit window (ms)", "int", BIG_EXPLOSION_WINDOW_MS, 100, 3000, 100),
    ("big_blast_delay_ms", "Loud hit delay (ms)", "int", BIG_EXPLOSION_SOUND_DELAY_MS, 0, 2000, 50),
    ("big_blast_volume", "Loud hit volume", "float", BIG_EXPLOSION_VOLUME, 0.0, 1.0, 0.05),
)

RESET_ROW = len(RULES)

_VALUES = {row[0]: row[3] for row in RULES}


def rule_spec(key):
    for row in RULES:
        if row[0] == key:
            return row
    raise KeyError(key)


def get(key):
    return _VALUES[key]


def snapshot():
    return dict(_VALUES)


def _clamp(key, value):
    _name, _label, kind, default, low, high, _step = rule_spec(key)
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        number = max(float(low), number)
    if high is not None:
        number = min(float(high), number)
    if kind == "int":
        return int(round(number))
    return round(number, 6)


def set_value(key, value):
    _VALUES[key] = _clamp(key, value)
    return _VALUES[key]


def step_value(key, direction):
    _name, _label, kind, _default, _low, _high, step = rule_spec(key)
    current = get(key)
    if kind == "bool":
        return set_value(key, not current)
    return set_value(key, float(current) + float(step) * (1 if direction > 0 else -1))


def reset_defaults():
    for key, _label, _kind, default, *_rest in RULES:
        _VALUES[key] = default
    return snapshot()


def is_default(key):
    value = get(key)
    default = rule_spec(key)[3]
    kind = rule_spec(key)[2]
    if kind == "bool":
        return bool(value) == bool(default)
    if kind == "int":
        return int(value) == int(default)
    return round(float(value), 6) == round(float(default), 6)


def format_value(key):
    value = get(key)
    kind = rule_spec(key)[2]
    if kind == "bool":
        return "On" if value else "Off"
    if kind == "float":
        if key in ("powerup_chance", "quad_chance", "big_blast_volume"):
            pct = float(value) * 100
            if key == "quad_chance":
                return f"{pct:.4f}%"
            return f"{int(round(pct))}%"
        text = f"{float(value):.2f}".rstrip("0").rstrip(".")
        return text
    return str(int(value))


def _disk_enabled():
    if os.environ.get("BOMBERMARV_SETTINGS") == "-":
        return False
    for mod in sys.modules.values():
        base = os.path.basename(getattr(mod, "__file__", "") or "")
        if base.startswith("test_") and base.endswith(".py"):
            return False
    return True


def load():
    if not _disk_enabled():
        reset_defaults()
        return snapshot()
    path = user_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return snapshot()
    if isinstance(raw, dict):
        for key in _VALUES:
            if key in raw:
                set_value(key, raw[key])
    return snapshot()


def save():
    if not _disk_enabled():
        return False
    path = user_settings_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {key: get(key) for key in _VALUES}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(tmp, path)
    return True


def player_speed():
    from bm_params import CELL_SIZE
    return int(CELL_SIZE * 2.5 * float(get("speed_multiplier")))


def bomb_timer_ms():
    return int(round(float(get("bomb_fuse_s")) * 1000))


def explosion_duration_ms():
    return int(get("blast_ms"))


def quad_speedup():
    return float(get("quad_speed"))

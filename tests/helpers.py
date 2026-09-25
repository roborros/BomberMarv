"""Shared helpers for BomberMarv unit tests."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bm_params import CELL_SIZE, EMPTY, INDESTRUCTIBLE


def silence_sounds() -> None:
    class _SilentSound:
        def play(self, *args, **kwargs):
            return None

        def set_volume(self, *args, **kwargs):
            return None

    silent = _SilentSound()
    names = (
        "bonus_sound",
        "explosion_sound",
        "explosion_sound_qd",
        "death_sound",
        "qd_sound",
        "mocny_stral_sound",
        "fresh_meat_sound",
    )
    try:
        import bm_sounds
        import bm_classes
    except Exception:
        return
    for name in names:
        if hasattr(bm_sounds, name):
            setattr(bm_sounds, name, silent)
        if hasattr(bm_classes, name):
            setattr(bm_classes, name, silent)


def open_board(width=9, height=9):
    board = [[EMPTY for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                board[y][x] = INDESTRUCTIBLE
    return board


def cell_center(x, y):
    return [x * CELL_SIZE + CELL_SIZE // 2, y * CELL_SIZE + CELL_SIZE // 2]

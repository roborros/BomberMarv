"""Powerup helper functions for incremental modularization."""

from __future__ import annotations

import random


def choose_death_bonus_effect() -> str:
    return random.choice(["speed", "fire", "bomb"])

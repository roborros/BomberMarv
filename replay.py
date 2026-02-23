"""Replay helpers extracted from Game for incremental modularization."""

from __future__ import annotations


def build_replay_snapshot(game) -> dict:
    players_state = []
    for p in game.players:
        players_state.append(
            {
                "name": p.name,
                "color": p.color,
                "pos": (float(p.pos[0]), float(p.pos[1])),
                "alive": bool(p.alive),
                "draw_radius": int(p.draw_radius),
                "fire_power": int(p.fire_power),
                "bomb_capacity": int(p.bomb_capacity),
            }
        )
    bombs_state = [{"x": b.x, "y": b.y, "start": int(b.start_time)} for b in game.bombs]
    explosions_state = []
    for e in game.explosions:
        explosions_state.append({"cells": list(e.cells), "start": int(e.start_time), "qd": bool(e.quad_damage)})
    powerups_state = [{"x": pu.x, "y": pu.y, "type": pu.type} for pu in game.powerups]
    return {
        "t": int(game.current_time),
        "players": players_state,
        "bombs": bombs_state,
        "explosions": explosions_state,
        "powerups": powerups_state,
    }

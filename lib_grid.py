from bm_params import *
import random
import numpy as np
from timing_abstraction import get_ticks




def clear_safe_zone(board, sx, sy, offsets):
    w, h = len(board[0]), len(board)
    for dx, dy in offsets:
        nx, ny = sx + dx, sy + dy
        if 0 <= nx < w and 0 <= ny < h:
            if board[ny][nx] == DESTRUCTIBLE:
                board[ny][nx] = EMPTY


def snap_walkable_spawn(x, y, gw, gh):
    """Keep spawn cells off even-even pillars and inside the maze interior."""
    sx = max(1, min(int(gw) - 2, int(x)))
    sy = max(1, min(int(gh) - 2, int(y)))
    if sx % 2 == 0 and sy % 2 == 0:
        sx = sx - 1 if sx > 1 else sx + 1
    return sx, sy


def spawn_offsets(sx, sy, gw, gh):
    """L / plus opening from a spawn cell toward the interior."""
    if sx <= 1 and sy <= 1:
        return [(0, 0), (1, 0), (0, 1)]
    if sx >= gw - 2 and sy <= 1:
        return [(0, 0), (-1, 0), (0, 1)]
    if sx <= 1 and sy >= gh - 2:
        return [(0, 0), (1, 0), (0, -1)]
    if sx >= gw - 2 and sy >= gh - 2:
        return [(0, 0), (-1, 0), (0, -1)]
    if sx <= 1:
        return [(0, 0), (1, 0), (0, 1), (0, -1)]
    if sx >= gw - 2:
        return [(0, 0), (-1, 0), (0, 1), (0, -1)]
    if sy <= 1:
        return [(0, 0), (0, 1), (1, 0), (-1, 0)]
    if sy >= gh - 2:
        return [(0, 0), (0, -1), (1, 0), (-1, 0)]
    return [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1)]


def spawn_slots(gw, gh, count):
    """Up to 8 spawn slots: 4 corners, then interior mid lanes for players 5-8."""
    mid_x, mid_y = gw // 2, gh // 2
    raw = [
        (1, 1),
        (gw - 2, 1),
        (1, gh - 2),
        (gw - 2, gh - 2),
        (gw // 4, mid_y),
        (3 * gw // 4, mid_y),
        (mid_x, gh // 4),
        (mid_x, 3 * gh // 4),
    ]
    slots = []
    seen = set()
    for x, y in raw:
        sx, sy = snap_walkable_spawn(x, y, gw, gh)
        if (sx, sy) in seen:
            continue
        seen.add((sx, sy))
        slots.append((sx, sy, spawn_offsets(sx, sy, gw, gh)))
        if len(slots) >= count:
            break
    return slots

def get_random_L_pattern():
    patterns = [
        [(0,0), (1,0), (0,1)],
        
        [(0,0), (-1,0), (0,1)],
        [(0,0), (1,0), (0,-1)],
        [(0,0), (-1,0), (0,-1)],
        [(0,0), (0,1), (1,1)],
        [(0,0), (0,1), (-1,1)],
        [(0,0), (0,-1), (1,-1)],
        [(0,0), (0,-1), (-1,-1)]
    ]
    return random.choice(patterns)

def generate_maze(width=None, height=None):
    w = width if width is not None else GRID_WIDTH
    h = height if height is not None else GRID_HEIGHT
    board = [[EMPTY for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                board[y][x] = INDESTRUCTIBLE
            elif x % 2 == 0 and y % 2 == 0:
                board[y][x] = INDESTRUCTIBLE
            elif random.random() < 0.7:
                board[y][x] = DESTRUCTIBLE
    return board

def automate_player(player, dt, board, bombs):
    """
    Automates a player:
    - Chooses a random direction every 500-1500 ms.
    - Moves the player along the chosen direction.
    - Occasionally drops a bomb.
    
    dt: time elapsed in milliseconds since last iteration.
    board: current game board.
    bombs: list of active bombs.
    
    while True:
        dt = clock.tick(60)
        automate_player(theGame.players[0], dt, board, bombs)
    
    """
    # Initialize automation attributes if not already present
    if not hasattr(player, "automation_timer"):
        player.automation_timer = 0
    if not hasattr(player, "automation_direction"):
        player.automation_direction = np.array([0.0, 0.0], dtype=np.float64)
    
    # Decrement the timer by the elapsed time
    player.automation_timer -= dt
    if player.automation_timer <= 0:
        # Set a new timer between 500 ms and 1500 ms.
        player.automation_timer = random.randint(500, 1500)
        # Choose a random direction; sometimes the bot stops.
        possible_directions = [
            np.array([0.0, 0.0], dtype=np.float64),
            np.array([1.0, 0.0], dtype=np.float64),
            np.array([-1.0, 0.0], dtype=np.float64),
            np.array([0.0, 1.0], dtype=np.float64),
            np.array([0.0, -1.0], dtype=np.float64)
        ]
        player.automation_direction = random.choice(possible_directions)
    
    # Simulate the movement using the automation direction.
    import bm_settings
    spd = player.speed if not player.quad_damage else int(player.speed * bm_settings.quad_speedup())
    original_pos = player.pos.copy()
    # Compute the change in position (dt is in ms)
    delta_move = player.automation_direction * spd * (dt / 1000.0)
    player.pos = player.pos + delta_move
    
    # If the new position would result in a collision, revert.
    if player.collides_with_walls(board) or player.collides_with_bombs(bombs, original_pos):
        player.pos = original_pos

    # Occasionally drop a bomb (e.g. ~1% chance each frame)
    if random.random() < 0.01:
        player.drop_bomb(bombs, get_ticks())
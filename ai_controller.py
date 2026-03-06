"""
AI controller for boss fight. Computes movement direction and bomb placement.
"""

import random
from typing import Tuple, Optional, Set
import numpy as np

# Import from bm_params to avoid circular imports at module load
def _get_params():
    from bm_params import (
        EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE,
        BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT,
    )
    return EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT


# Danger lead time: treat bombs as dangerous this many ms before explosion
DANGER_LEAD_MS = 500


def _get_danger_cells(game) -> set:
    """Return set of (x, y) grid cells that are dangerous (explosions or imminent bomb blasts)."""
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT = _get_params()
    danger = set()
    t = game.current_time

    # Active explosions: always dangerous
    for exp in game.explosions:
        if exp.is_active(t):
            for cell in exp.cells:
                danger.add(cell)

    # Bombs: dangerous when imminent (consistent lead time)
    for bomb in game.bombs:
        if t - bomb.start_time >= BOMB_TIMER - DANGER_LEAD_MS:
            cells = _explosion_cells_for_bomb(bomb, game)
            for cell in cells:
                danger.add(cell)

    return danger


def _explosion_cells_for_bomb(bomb, game) -> list:
    """Compute explosion cells for a bomb (mirrors Game.get_explosion_cells)."""
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT = _get_params()
    cells = [(bomb.x, bomb.y)]
    fp = getattr(bomb, 'fire_power', 1)
    board = game.board
    gw, gh = len(board[0]), len(board)
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        for i in range(1, fp + 1):
            nx, ny = bomb.x + dx * i, bomb.y + dy * i
            if nx < 0 or nx >= gw or ny < 0 or ny >= gh:
                break
            if board[ny][nx] == INDESTRUCTIBLE:
                break
            cells.append((nx, ny))
            if board[ny][nx] == DESTRUCTIBLE:
                break
    return cells


def _cells_with_bombs(bombs) -> Set[Tuple[int, int]]:
    """Return set of (x, y) cells occupied by bombs. All bomb cells are non-walkable for pathfinding."""
    return {(bomb.x, bomb.y) for bomb in bombs}


def _cell_walkable(board, x: int, y: int, danger: set, bomb_cells: Optional[Set[Tuple[int, int]]] = None) -> bool:
    """True if cell is empty, not in danger, and not occupied by a bomb."""
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT = _get_params()
    w, h = len(board[0]), len(board)
    if not (0 <= x < w and 0 <= y < h):
        return False
    if (x, y) in danger:
        return False
    if bomb_cells and (x, y) in bomb_cells:
        return False
    return board[y][x] == EMPTY


def _bfs_safe_direction(
    board, start_x: int, start_y: int, danger: set,
    bombs: Optional[list] = None, bomb_cells: Optional[Set[Tuple[int, int]]] = None
) -> Optional[Tuple[int, int]]:
    """BFS from start to find nearest safe cell. Returns (dx, dy) to move, or None."""
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT = _get_params()
    w, h = len(board[0]), len(board)
    if bomb_cells is None and bombs is not None:
        bomb_cells = _cells_with_bombs(bombs)

    def walkable(x, y):
        return _cell_walkable(board, x, y, danger, bomb_cells)

    if walkable(start_x, start_y):
        return (0, 0)  # Already safe

    from collections import deque
    q = deque([(start_x, start_y)])
    parent = {(start_x, start_y): None}
    found = None

    while q:
        cx, cy = q.popleft()
        if walkable(cx, cy):
            found = (cx, cy)
            break
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in parent:
                if board[ny][nx] == EMPTY and (not bomb_cells or (nx, ny) not in bomb_cells):
                    parent[(nx, ny)] = (cx, cy)
                    q.append((nx, ny))

    if found is None:
        return None
    cur = found
    while parent[cur] is not None and parent[cur] != (start_x, start_y):
        cur = parent[cur]
    if parent[cur] == (start_x, start_y):
        return (cur[0] - start_x, cur[1] - start_y)
    return (0, 0)


def _nearest_powerup(
    board, px: int, py: int, powerups: list, danger: set,
    bomb_cells: Optional[Set[Tuple[int, int]]] = None
) -> Optional[Tuple[int, int]]:
    """Return (dx, dy) toward nearest powerup, or None."""
    if not powerups:
        return None
    best = None
    best_dist = float('inf')
    for pu in powerups:
        dist = abs(pu.x - px) + abs(pu.y - py)
        if dist < best_dist and _cell_walkable(board, pu.x, pu.y, danger, bomb_cells):
            best_dist = dist
            best = (pu.x, pu.y)
    if best is None:
        return None
    dx = 1 if best[0] > px else (-1 if best[0] < px else 0)
    dy = 1 if best[1] > py else (-1 if best[1] < py else 0)
    return (dx, dy)


def _opponent_has_line_of_sight(player, opponent, game) -> bool:
    """
    True if opponent is in bomb blast range AND there is clear line-of-sight
    (no indestructible or destructible wall between player and opponent along the blast line).
    """
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE = _get_params()[:3]
    px, py = player.get_grid_pos()
    ox, oy = opponent.get_grid_pos()
    fp = player.fire_power
    board = game.board

    # Same row: check horizontal line
    if oy == py:
        step = 1 if ox > px else -1
        for x in range(px + step, ox, step) if px != ox else []:
            if board[py][x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                return False
        return abs(ox - px) <= fp

    # Same column: check vertical line
    if ox == px:
        step = 1 if oy > py else -1
        for y in range(py + step, oy, step) if py != oy else []:
            if board[y][px] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                return False
        return abs(oy - py) <= fp

    return False


def _opponent_in_blast_range_with_los(player, game) -> bool:
    """True if any opponent is within bomb blast range with clear line-of-sight."""
    for p in game.players:
        if p != player and p.alive:
            if _opponent_has_line_of_sight(player, p, game):
                return True
    return False


def _can_escape_after_bomb(player, game, danger: set) -> bool:
    """
    Simulate placing a bomb at player's cell. Return True if there exists
    a path to a safe cell (considering the new bomb's future blast).
    """
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT = _get_params()
    px, py = player.get_grid_pos()
    t = game.current_time

    # Simulate danger: current danger + our hypothetical bomb's blast at explosion time
    future_danger = set(danger)
    # Add cells that would be hit when our bomb explodes (at BOMB_TIMER from now)
    fp = player.fire_power
    board = game.board
    gw, gh = len(board[0]), len(board)
    blast_cells = [(px, py)]
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        for i in range(1, fp + 1):
            nx, ny = px + dx * i, py + dy * i
            if nx < 0 or nx >= gw or ny < 0 or ny >= gh:
                break
            if board[ny][nx] == INDESTRUCTIBLE:
                break
            blast_cells.append((nx, ny))
            if board[ny][nx] == DESTRUCTIBLE:
                break
    for c in blast_cells:
        future_danger.add(c)

    # Bomb cells: existing bombs + our new bomb at (px, py)
    bomb_cells = _cells_with_bombs(game.bombs)
    bomb_cells.add((px, py))

    # BFS from current cell - can we reach a safe cell?
    direction = _bfs_safe_direction(
        board, px, py, future_danger,
        bomb_cells=bomb_cells
    )
    return direction is not None


def _should_place_bomb(player, game, danger: set) -> bool:
    """Decide whether to place a bomb."""
    if player.active_bombs >= player.bomb_capacity:
        return False
    px, py = player.get_grid_pos()
    if (px, py) in danger:
        return False

    # Opponent in blast range with line-of-sight
    if _opponent_in_blast_range_with_los(player, game):
        if _can_escape_after_bomb(player, game, danger):
            return True
        return False

    # Place near destructible walls sometimes (only if we can escape)
    board = game.board
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE = _get_params()[:3]
    near_destructible = any(
        0 <= px + dx < len(board[0]) and 0 <= py + dy < len(board)
        and board[py + dy][px + dx] == DESTRUCTIBLE
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
    )
    if near_destructible and _can_escape_after_bomb(player, game, danger) and random.random() < 0.15:
        return True
    return False


def _random_safe_direction(
    board, px: int, py: int, danger: set,
    bomb_cells: Optional[Set[Tuple[int, int]]] = None
) -> Tuple[int, int]:
    """Pick a random valid movement direction."""
    candidates = [(0, 0)]
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        nx, ny = px + dx, py + dy
        if _cell_walkable(board, nx, ny, danger, bomb_cells):
            candidates.append((dx, dy))
    return random.choice(candidates)


def compute_ai_input(player, game) -> Tuple[np.ndarray, bool]:
    """
    Compute AI movement and bomb decision.
    Returns (direction, place_bomb) where direction is numpy array [dx, dy] normalized.
    """
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT = _get_params()
    px, py = player.get_grid_pos()
    board = game.board
    danger = _get_danger_cells(game)
    bomb_cells = _cells_with_bombs(game.bombs)

    place_bomb = _should_place_bomb(player, game, danger)

    direction = (0, 0)
    in_or_near_danger = (px, py) in danger or any(
        (px + dx, py + dy) in danger for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
    )
    if in_or_near_danger:
        direction = _bfs_safe_direction(board, px, py, danger, bombs=game.bombs, bomb_cells=bomb_cells)
        if direction is None:
            direction = _random_safe_direction(board, px, py, danger, bomb_cells)
    elif game.powerups:
        direction = _nearest_powerup(board, px, py, game.powerups, danger, bomb_cells)
        if direction is None:
            direction = _random_safe_direction(board, px, py, danger, bomb_cells)
    else:
        direction = _random_safe_direction(board, px, py, danger, bomb_cells)

    dx, dy = direction
    arr = np.array([float(dx), float(dy)], dtype=np.float64)
    if np.dot(arr, arr) > 1:
        arr = arr / np.linalg.norm(arr)
    return arr, place_bomb

"""Explosion-domain helpers extracted from Game for incremental modularization."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

Cell = Tuple[int, int]
ExplosionTileEvent = Tuple[int, Sequence[Cell]]


def compute_explosion_active_cells(explosion, current_time: int, explosion_duration: int) -> List[Tuple[int, int]]:
    """Return currently active explosion cells based on host animation timing."""
    norm = (current_time - explosion.start_time) / explosion_duration
    norm = min(norm, 1)
    if norm < 0.2:
        arm_factor = norm / 0.2
    elif norm <= 0.7:
        arm_factor = 1
    else:
        arm_factor = (1 - (norm - 0.7) / 0.3)

    if arm_factor <= 0:
        return []

    cx, cy = explosion.cells[0]
    up_max = max([cy - cell[1] for cell in explosion.cells if cell[0] == cx and cell[1] < cy] or [0])
    down_max = max([cell[1] - cy for cell in explosion.cells if cell[0] == cx and cell[1] > cy] or [0])
    left_max = max([cx - cell[0] for cell in explosion.cells if cell[1] == cy and cell[0] < cx] or [0])
    right_max = max([cell[0] - cx for cell in explosion.cells if cell[1] == cy and cell[0] > cx] or [0])

    up_length = int(arm_factor * up_max)
    down_length = int(arm_factor * down_max)
    left_length = int(arm_factor * left_max)
    right_length = int(arm_factor * right_max)

    active_cells: List[Tuple[int, int]] = [(cx, cy)]
    for i in range(1, up_length + 1):
        active_cells.append((cx, cy - i))
    for i in range(1, down_length + 1):
        active_cells.append((cx, cy + i))
    for i in range(1, left_length + 1):
        active_cells.append((cx - i, cy))
    for i in range(1, right_length + 1):
        active_cells.append((cx + i, cy))
    return active_cells


def prune_explosion_events(
    events: Iterable[ExplosionTileEvent],
    current_time: int,
    window_ms: int,
) -> List[ExplosionTileEvent]:
    """Keep explosion tile events whose start_time is inside the rolling window."""
    cutoff = current_time - window_ms
    return [event for event in events if event[0] >= cutoff]


def count_unique_explosion_tiles(
    events: Iterable[ExplosionTileEvent],
    current_time: int,
    window_ms: int,
) -> int:
    """Count unique tiles covered by explosions that started within the window."""
    cutoff = current_time - window_ms
    tiles = set()
    for start_time, cells in events:
        if start_time < cutoff:
            continue
        for cell in cells:
            tiles.add((int(cell[0]), int(cell[1])))
    return len(tiles)


def crossed_big_explosion_threshold(was_over: bool, tile_count: int, threshold: int) -> bool:
    """True once unique tiles reach the threshold from below."""
    return (not was_over) and tile_count >= threshold


def planned_blast_cells(
    bomb_x: int,
    bomb_y: int,
    fire_power: int,
    board,
    grid_width: int,
    grid_height: int,
    max_range: int | None = None,
    empty: int = 0,
    indestructible: int = 1,
    destructible: int = 2,
) -> List[Tuple[int, int]]:
    """Cells a live bomb will cover, stopping at walls. Optional cap for scared-face preview."""
    reach = max(0, int(fire_power))
    if max_range is not None:
        reach = min(reach, int(max_range))
    cells: List[Tuple[int, int]] = [(int(bomb_x), int(bomb_y))]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for step in range(1, reach + 1):
            nx = int(bomb_x) + dx * step
            ny = int(bomb_y) + dy * step
            if nx < 0 or nx >= int(grid_width) or ny < 0 or ny >= int(grid_height):
                break
            tile = board[ny][nx]
            if tile == indestructible:
                break
            cells.append((nx, ny))
            if tile == destructible:
                break
    return cells


def is_player_in_planned_blast(
    grid_x: int,
    grid_y: int,
    bombs,
    board,
    grid_width: int,
    grid_height: int,
    max_range: int = 5,
) -> bool:
    for bomb in bombs or []:
        cells = planned_blast_cells(
            int(bomb.x),
            int(bomb.y),
            int(getattr(bomb, "fire_power", 1) or 1),
            board,
            grid_width,
            grid_height,
            max_range=max_range,
        )
        if (int(grid_x), int(grid_y)) in cells:
            return True
    return False


def explosion_cell_rect(
    cell_x: int,
    cell_y: int,
    cell_size: int,
    scale: float,
    clip_outward: str | None = None,
) -> Tuple[float, float, float, float]:
    margin = cell_size * (1.0 - float(scale)) / 2.0
    hit = cell_size * float(scale)
    x = cell_x * cell_size + margin
    y = cell_y * cell_size + margin
    w = hit
    h = hit
    mid_x = cell_x * cell_size + cell_size / 2.0
    mid_y = cell_y * cell_size + cell_size / 2.0
    if clip_outward == "right":
        w = max(0.0, mid_x - x)
    elif clip_outward == "left":
        new_x = mid_x
        w = max(0.0, (x + w) - new_x)
        x = new_x
    elif clip_outward == "down":
        h = max(0.0, mid_y - y)
    elif clip_outward == "up":
        new_y = mid_y
        h = max(0.0, (y + h) - new_y)
        y = new_y
    return (x, y, w, h)


def explosion_tip_clip(
    cx: int, cy: int, cell_x: int, cell_y: int, active_cells: Sequence[Cell]
) -> str | None:
    """Last cell on an arm clips at the cell center, where the flame tip stops."""
    on_row = [x for x, y in active_cells if y == cy]
    on_col = [y for x, y in active_cells if x == cx]
    if cell_y == cy and on_row:
        if cell_x == max(on_row) and cell_x != cx:
            return "right"
        if cell_x == min(on_row) and cell_x != cx:
            return "left"
    if cell_x == cx and on_col:
        if cell_y == max(on_col) and cell_y != cy:
            return "down"
        if cell_y == min(on_col) and cell_y != cy:
            return "up"
    return None


def explosion_arm_pixel_length(arm_factor: float, cell_reach: int, cell_size: int) -> float:
    """Painted flame stops at the center of the last reached cell."""
    if cell_reach <= 0 or arm_factor <= 0:
        return 0.0
    return float(arm_factor) * int(cell_reach) * float(cell_size)


def explosion_player_radius(cell_size: int, player_hit_scale: float) -> float:
    return max(1.0, (cell_size / 2.0) * float(player_hit_scale))

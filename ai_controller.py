"""
AI controller for regular CPU opponents and the champion boss fight.

Grid BFS with a timed danger map. Think at ~12.5 Hz; steering (center-then-turn)
runs every sim tick via compute_ai_input.

CPU personalities are cautious, normal, or crazy. The champion boss uses the
boss script: chase and bomb. A bot plants when a brick or a lane is worth it
and one exit is still open, instead of waiting until both sides close.
"""

from collections import deque
from typing import Dict, List, Optional, Set, Tuple
import random
import numpy as np

Coord = Tuple[int, int]
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _note_visit(player, cell: Coord) -> None:
    recent = list(getattr(player, "_ai_recent_cells", ()) or ())
    if not recent or recent[-1] != cell:
        recent.append(cell)
    player._ai_recent_cells = tuple(recent[-6:])


def _step_hint(origin: Coord, cell: Coord) -> Coord:
    dx = cell[0] - origin[0]
    dy = cell[1] - origin[1]
    if dx == 0 and dy == 0:
        return (0, 0)
    if abs(dx) >= abs(dy):
        return (1 if dx > 0 else -1, 0)
    return (0, 1 if dy > 0 else -1)


def _move_cost(player, cell: Coord, step: Coord, now: int) -> float:
    """Lower is better. Noise breaks exact ties; reversing and revisiting cost more."""
    if player is None:
        return 0.0
    gid = getattr(player, "global_id", None)
    if gid is None:
        gid = id(player)
    # Stable for the match. A clock bucket made symmetrical ties flip on a timer.
    token = (
        (int(gid) & 0x7FFFFFFF) * 73856093
        ^ (int(cell[0]) & 0xFFFF) * 19349663
        ^ (int(cell[1]) & 0xFFFF) * 83492791
        ^ (int(step[0]) & 3) * 83492791
        ^ (int(step[1]) & 3) * 19349663
    ) & 0x7FFFFFFF
    unit = random.Random(token).random()
    cost = unit * AI_TASTE_NOISE
    last = tuple(getattr(player, "_ai_last_dir", (0, 0)) or (0, 0))
    if last != (0, 0) and step != (0, 0):
        if step == last:
            cost -= AI_COMMIT_BONUS
        elif step == (-last[0], -last[1]):
            cost += AI_COMMIT_BONUS
    if cell in (getattr(player, "_ai_recent_cells", ()) or ()):
        cost += AI_REVISIT_PENALTY
    goal = getattr(player, "_ai_goal_cell", None)
    if goal is not None and tuple(goal) == cell:
        cost -= AI_COMMIT_BONUS
    return cost


def _search_dirs(player, origin: Coord, now: int):
    if player is None:
        return DIRS
    scored = []
    for dx, dy in DIRS:
        cell = (origin[0] + dx, origin[1] + dy)
        scored.append((_move_cost(player, cell, (dx, dy), now), (dx, dy)))
    scored.sort(key=lambda item: item[0])
    return tuple(step for _cost, step in scored)

# Backward-compatible names. Flee uses path-vs-fuse, not this boolean window.
DANGER_LEAD_MS = 700
BOSS_DANGER_LEAD_MS = 1100

BOMB_COOLDOWN_MS = 70
CAUTIOUS_BOMB_COOLDOWN_MS = 140
BOSS_BOMB_COOLDOWN_MS = 30
CRAZY_BOMB_COOLDOWN_MS = 40
POWERUP_HUNT_LIMIT = 14
BOSS_POWERUP_HUNT_LIMIT = 22
CAUTIOUS_POWERUP_HUNT_LIMIT = 18
CRAZY_POWERUP_HUNT_LIMIT = 28
AI_CENTER_LOCK_PX = 12
AI_BOMB_CENTER_PX = 18
AI_THINK_INTERVAL_MS = 80
AI_STICKY_MS = 1100
# Tie noise is smaller than one extra step. Continuing the current heading
# beats that noise, so a corridor does not flip the bot around every think.
AI_TASTE_MS = 900
AI_TASTE_NOISE = 0.45
AI_COMMIT_BONUS = 0.7
AI_REVISIT_PENALTY = 1.5
CPU_SAFETY_MARGIN_MS = 60
BOSS_SAFETY_MARGIN_MS = 20
CAUTIOUS_SAFETY_MARGIN_MS = 100
CRAZY_SAFETY_MARGIN_MS = 30
CLOSE_COMBAT_MANHATTAN = 4
CAUTIOUS_NEAR_CELLS = 4
# How far past the fuse a bot will still throw down an open lane.
LANE_LEAD_CELLS = 2
BOSS_LANE_LEAD_CELLS = 4
HEAD_START_CELLS = 1
TRAP_SAFE_NEIGHBORS = 2
BOSS_TRAP_SAFE_NEIGHBORS = 3
FARM_SEARCH_LIMIT = 10
BLOCK_SEARCH_LIMIT = 12
AI_PERSONALITIES = ("cautious", "normal", "crazy")
# Slow cautious bots keep one spare cell. Faster bots spend the fuse on the run.
ESCAPE_RESERVE_CELLS = 0

_INF = 10**12


def _get_params():
    from bm_params import (
        EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE,
        BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT,
    )
    return EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, EXPLOSION_DURATION, GRID_WIDTH, GRID_HEIGHT


def _is_boss(player) -> bool:
    role = getattr(player, "ai_role", "")
    if role in ("boss", "uber"):
        return True
    if getattr(player, "ai_personality", None) == "boss":
        return True
    return bool(getattr(player, "boss_lives_remaining", 0))


def ai_personality(player) -> str:
    """boss, or a random CPU style: cautious, normal, crazy."""
    if _is_boss(player):
        return "boss"
    name = getattr(player, "ai_personality", None)
    if name in AI_PERSONALITIES:
        return name
    return "normal"


def roll_cpu_personality() -> str:
    return random.choice(AI_PERSONALITIES)


def assign_random_personality(player) -> str:
    """Roll a CPU style. The champion boss keeps the boss script."""
    if _is_boss(player):
        player.ai_personality = "boss"
        return "boss"
    player.ai_personality = roll_cpu_personality()
    return player.ai_personality


def _danger_lead_ms(player) -> int:
    return BOSS_DANGER_LEAD_MS if _is_boss(player) else DANGER_LEAD_MS


def _safety_margin_ms(player) -> int:
    persona = ai_personality(player)
    if persona == "boss":
        return BOSS_SAFETY_MARGIN_MS
    if persona == "cautious":
        return CAUTIOUS_SAFETY_MARGIN_MS
    if persona == "crazy":
        return CRAZY_SAFETY_MARGIN_MS
    return CPU_SAFETY_MARGIN_MS


def _powerup_limit(player, quad: bool = False) -> int:
    persona = ai_personality(player)
    if persona == "crazy" and quad:
        return CRAZY_POWERUP_HUNT_LIMIT
    if persona == "boss":
        return BOSS_POWERUP_HUNT_LIMIT
    if persona == "cautious":
        return CAUTIOUS_POWERUP_HUNT_LIMIT
    return POWERUP_HUNT_LIMIT


def _bomb_cooldown_ms(player) -> int:
    persona = ai_personality(player)
    if persona == "cautious":
        return CAUTIOUS_BOMB_COOLDOWN_MS
    if persona == "boss":
        return BOSS_BOMB_COOLDOWN_MS
    if persona == "crazy":
        return CRAZY_BOMB_COOLDOWN_MS
    return BOMB_COOLDOWN_MS


def _max_live_bombs(player) -> int:
    raw = getattr(player, "bomb_capacity", 1)
    return 1 if raw is None else max(0, int(raw))


def _trap_neighbor_limit(player) -> int:
    return BOSS_TRAP_SAFE_NEIGHBORS if _is_boss(player) else TRAP_SAFE_NEIGHBORS


def _bomb_timer() -> int:
    import bm_settings
    return bm_settings.bomb_timer_ms()


def _explosion_duration() -> int:
    import bm_settings
    return bm_settings.explosion_duration_ms()


def _default_travel_ms() -> int:
    from bm_params import CELL_SIZE, PLAYER_SPEED
    return max(1, int(round(CELL_SIZE * 1000 / max(1, PLAYER_SPEED))))


def _cell_travel_ms(player) -> int:
    from bm_params import CELL_SIZE, PLAYER_SPEED
    import bm_settings
    spd = getattr(player, "speed", None) or PLAYER_SPEED
    if getattr(player, "quad_damage", False):
        spd = int(spd * bm_settings.quad_speedup())
    return max(1, int(round(CELL_SIZE * 1000 / max(1, spd))))


def _blast_cells(board, x: int, y: int, fire_power: int) -> List[Coord]:
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, *_ = _get_params()
    cells = [(x, y)]
    gw, gh = len(board[0]), len(board)
    for dx, dy in DIRS:
        for i in range(1, fire_power + 1):
            nx, ny = x + dx * i, y + dy * i
            if nx < 0 or nx >= gw or ny < 0 or ny >= gh:
                break
            if board[ny][nx] == INDESTRUCTIBLE:
                break
            cells.append((nx, ny))
            if board[ny][nx] == DESTRUCTIBLE:
                break
    return cells


def _explosion_cells_for_bomb(bomb, game) -> list:
    fp = getattr(bomb, "fire_power", 1)
    return _blast_cells(game.board, bomb.x, bomb.y, fp)


def _danger_times(game) -> Dict[Coord, int]:
    """Earliest ms when each cell becomes lethal."""
    duration = _explosion_duration()
    timer = _bomb_timer()
    times: Dict[Coord, int] = {}
    t = int(getattr(game, "current_time", 0))

    def mark(cell: Coord, boom: int) -> None:
        prev = times.get(cell)
        if prev is None or boom < prev:
            times[cell] = boom

    for exp in getattr(game, "explosions", None) or []:
        start = int(getattr(exp, "start_time", t))
        active = True
        if hasattr(exp, "is_active"):
            active = bool(exp.is_active(t))
        elif t < start or t >= start + duration:
            active = False
        if not active:
            continue
        for cell in exp.cells:
            mark(tuple(cell), start)

    pending = []
    for bomb in getattr(game, "bombs", None) or []:
        cells = [tuple(cell) for cell in _explosion_cells_for_bomb(bomb, game)]
        pending.append(((int(bomb.x), int(bomb.y)), int(bomb.start_time) + timer, cells))
    booms = [item[1] for item in pending]
    # A blast that reaches another bomb detonates it at that earlier time.
    for _ in range(max(1, len(pending))):
        changed = False
        for i, (origin, _boom, _cells) in enumerate(pending):
            for j, (_other, _other_boom, other_cells) in enumerate(pending):
                if i == j:
                    continue
                if origin in other_cells and booms[j] < booms[i]:
                    booms[i] = booms[j]
                    changed = True
        if not changed:
            break
    for i, (_origin, _boom, cells) in enumerate(pending):
        for cell in cells:
            mark(cell, booms[i])
    return times


def _get_danger_cells(game, lead_ms: int = DANGER_LEAD_MS) -> set:
    """Cells exploding now, or whose blast starts within lead_ms (test helper)."""
    now = int(getattr(game, "current_time", 0))
    duration = _explosion_duration()
    danger = set()
    for cell, boom in _danger_times(game).items():
        if boom <= now < boom + duration:
            danger.add(cell)
        elif boom > now and boom - now <= lead_ms:
            danger.add(cell)
    return danger


def _cells_with_bombs(bombs) -> Set[Coord]:
    return {(bomb.x, bomb.y) for bomb in bombs}


def _other_player_cells(player, game) -> Set[Coord]:
    cells: Set[Coord] = set()
    for other in getattr(game, "players", None) or []:
        if other is player or not getattr(other, "alive", True):
            continue
        cells.add(other.get_grid_pos())
    return cells


def _cell_walkable(board, x: int, y: int, danger: set, bomb_cells: Optional[Set[Coord]] = None) -> bool:
    EMPTY, *_ = _get_params()
    w, h = len(board[0]), len(board)
    if not (0 <= x < w and 0 <= y < h):
        return False
    if (x, y) in danger:
        return False
    if bomb_cells and (x, y) in bomb_cells:
        return False
    return board[y][x] == EMPTY


def _can_occupy(
    cell: Coord,
    arrival: int,
    stay_ms: int,
    danger_times: Dict[Coord, int],
    duration: int,
    margin_ms: int,
    now: int,
) -> bool:
    boom = danger_times.get(cell)
    if boom is None:
        return True
    blast_end = boom + duration
    # Walking into a cell that is already exploding is lethal now, even if
    # the planned arrival is after the blast ends.
    if boom <= now < blast_end:
        return False
    boom_eff = boom - margin_ms
    leave = arrival + stay_ms
    if leave <= boom_eff:
        return True
    if arrival >= blast_end:
        return True
    return False


def _safe_to_stay(cell: Coord, at_time: int, danger_times: Dict[Coord, int], duration: int) -> bool:
    boom = danger_times.get(cell)
    if boom is None:
        return True
    return at_time >= boom + duration


def _in_bounds_empty(board, x: int, y: int) -> bool:
    EMPTY, *_ = _get_params()
    w, h = len(board[0]), len(board)
    return 0 <= x < w and 0 <= y < h and board[y][x] == EMPTY


def _empty_neighbor_count(
    board, cell: Coord,
    bomb_cells: Optional[Set[Coord]] = None,
    occupied: Optional[Set[Coord]] = None,
) -> int:
    n = 0
    for dx, dy in DIRS:
        nx, ny = cell[0] + dx, cell[1] + dy
        nxt = (nx, ny)
        if not _in_bounds_empty(board, nx, ny):
            continue
        if bomb_cells and nxt in bomb_cells:
            continue
        if occupied and nxt in occupied:
            continue
        n += 1
    return n


def _center_dir(player) -> Coord:
    """Walk toward the current cell center, or (0,0) if already locked."""
    cx, cy = _cell_center_px(player)
    off_x = player.pos[0] - cx
    off_y = player.pos[1] - cy
    if abs(off_x) <= AI_CENTER_LOCK_PX and abs(off_y) <= AI_CENTER_LOCK_PX:
        return (0, 0)
    if abs(off_x) >= abs(off_y):
        return (-1 if off_x > 0 else 1, 0)
    return (0, -1 if off_y > 0 else 1)


def _leave_pocket(
    board, start: Coord, bomb_cells: Set[Coord], occupied: Set[Coord],
    danger_times=None, now: int = 0, travel_ms: int = 0, margin_ms: int = 0,
    player=None,
) -> Coord:
    """Step out of a 1-exit crate pocket toward the neighbor with the most exits."""
    best = (0, 0)
    best_key = (-1, -10**9)
    duration = _explosion_duration()
    for dx, dy in DIRS:
        nx, ny = start[0] + dx, start[1] + dy
        nxt = (nx, ny)
        if not _in_bounds_empty(board, nx, ny):
            continue
        if nxt in bomb_cells or nxt in occupied:
            continue
        if danger_times is not None and travel_ms:
            arrival = now + travel_ms
            if not _can_occupy(nxt, arrival, travel_ms, danger_times, duration, margin_ms, now):
                continue
        deg = _empty_neighbor_count(board, nxt, bomb_cells, occupied)
        cost = _move_cost(player, nxt, (dx, dy), now) if player is not None else 0.0
        key = (deg, -cost)
        if key > best_key:
            best_key = key
            best = (dx, dy)
    return best


def _idle_step(player, board, start, bomb_cells, occupied, danger_times=None, now=0) -> Coord:
    """Leave a lit cell immediately. Otherwise center, wait out a safe fuse, or leave a pocket."""
    duration = _explosion_duration()
    now_i = int(now)
    if danger_times is not None and not _safe_to_stay(start, now_i, danger_times, duration):
        travel = _cell_travel_ms(player)
        margin = _safety_margin_ms(player)
        plan = _timed_escape_step(
            board, start, danger_times, bomb_cells, now_i, travel, margin, occupied=None,
        )
        if plan is not None and plan[0] != (0, 0):
            return plan[0]
        return _leave_pocket(
            board, start, bomb_cells, occupied, danger_times, now_i, travel, margin, player,
        )
    centering = _center_dir(player)
    if centering != (0, 0):
        return centering
    duration = _explosion_duration()
    if (
        danger_times is not None
        and int(getattr(player, "active_bombs", 0) or 0) > 0
        and _safe_to_stay(start, int(now), danger_times, duration)
    ):
        return (0, 0)
    if _empty_neighbor_count(board, start, bomb_cells, occupied) <= 1:
        travel = _cell_travel_ms(player)
        margin = _safety_margin_ms(player)
        return _leave_pocket(
            board, start, bomb_cells, occupied, danger_times, int(now), travel, margin, player,
        )
    return (0, 0)


def _first_step(
    board,
    start: Coord,
    is_goal,
    danger: set,
    bomb_cells: Optional[Set[Coord]] = None,
    allow_start_unsafe: bool = False,
    player=None,
    now: int = 0,
) -> Optional[Coord]:
    """BFS first step toward the nearest cell matching is_goal. (0,0) if already there."""
    w, h = len(board[0]), len(board)
    sx, sy = start
    if is_goal(sx, sy):
        return (0, 0)

    q = deque([(sx, sy)])
    parent: Dict[Coord, Optional[Coord]] = {(sx, sy): None}
    found = None
    start_unsafe = allow_start_unsafe or not _cell_walkable(board, sx, sy, danger, bomb_cells)
    dirs = _search_dirs(player, start, now)

    while q:
        cx, cy = q.popleft()
        if (cx, cy) != (sx, sy) and is_goal(cx, cy):
            found = (cx, cy)
            break
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in parent:
                continue
            neighbor_ok = _cell_walkable(board, nx, ny, danger, bomb_cells)
            if not neighbor_ok and start_unsafe:
                neighbor_ok = _in_bounds_empty(board, nx, ny) and (not bomb_cells or (nx, ny) not in bomb_cells)
            if neighbor_ok:
                parent[(nx, ny)] = (cx, cy)
                q.append((nx, ny))

    if found is None:
        return None
    cur = found
    while parent[cur] is not None and parent[cur] != (sx, sy):
        cur = parent[cur]
    if parent[cur] == (sx, sy):
        return (cur[0] - sx, cur[1] - sy)
    return (0, 0)


def _bfs_safe_direction(
    board, start_x: int, start_y: int, danger: set,
    bombs: Optional[list] = None, bomb_cells: Optional[Set[Coord]] = None
) -> Optional[Coord]:
    if bomb_cells is None and bombs is not None:
        bomb_cells = _cells_with_bombs(bombs)

    def walkable(x, y):
        return _cell_walkable(board, x, y, danger, bomb_cells)

    return _first_step(
        board, (start_x, start_y), walkable, danger, bomb_cells, allow_start_unsafe=True
    )


def _reconstruct_first(parent: Dict[Coord, Optional[Coord]], found: Coord, start: Coord) -> Coord:
    cur = found
    while parent[cur] is not None and parent[cur] != start:
        cur = parent[cur]
    if parent[cur] == start:
        return (cur[0] - start[0], cur[1] - start[1])
    return (0, 0)


def _timed_first_step(
    board,
    start: Coord,
    is_goal,
    danger_times: Dict[Coord, int],
    bomb_cells: Set[Coord],
    now: int,
    travel_ms: int,
    margin_ms: int,
    occupied: Optional[Set[Coord]] = None,
    stay_goal: bool = True,
    player=None,
) -> Optional[Tuple[Coord, int, Coord]]:
    """Return (first_delta, steps, goal_cell) or None."""
    duration = _explosion_duration()
    occupied = occupied or set()
    w, h = len(board[0]), len(board)
    sx, sy = start
    start_arrival = now
    if is_goal(sx, sy) and (not stay_goal or _safe_to_stay(start, start_arrival, danger_times, duration)):
        return (0, 0), 0, start

    q = deque([(sx, sy, 0)])
    parent: Dict[Coord, Optional[Coord]] = {start: None}
    dirs = _search_dirs(player, start, now)

    def consider(nx, ny, cx, cy, depth) -> None:
        nxt = (nx, ny)
        if nxt in parent or not (0 <= nx < w and 0 <= ny < h):
            return
        if not _in_bounds_empty(board, nx, ny):
            return
        if nxt in bomb_cells:
            return
        # Another player is not a wall. Dodging their cell every think makes
        # two bots reverse in a corridor. Movement collision handles the overlap.
        n_arrival = now + (depth + 1) * travel_ms
        if not _can_occupy(nxt, n_arrival, travel_ms, danger_times, duration, margin_ms, now):
            return
        parent[nxt] = (cx, cy)
        q.append((nx, ny, depth + 1))

    while q:
        cx, cy, depth = q.popleft()
        arrival = now + depth * travel_ms
        if depth > 0 and is_goal(cx, cy):
            if not stay_goal or _safe_to_stay((cx, cy), arrival, danger_times, duration):
                return _reconstruct_first(parent, (cx, cy), start), depth, (cx, cy)
        if depth >= w * h:
            continue
        delayed = []
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if (
                depth == 0
                and not is_goal(nx, ny)
                and _empty_neighbor_count(board, nxt, bomb_cells, occupied) <= 1
            ):
                delayed.append((nx, ny))
                continue
            consider(nx, ny, cx, cy, depth)
        if depth == 0 and not any(parent[c] is not None for c in parent if c != start):
            for nx, ny in delayed:
                consider(nx, ny, cx, cy, depth)
    return None


def _timed_escape_step(
    board,
    start: Coord,
    danger_times: Dict[Coord, int],
    bomb_cells: Set[Coord],
    now: int,
    travel_ms: int,
    margin_ms: int,
    occupied: Optional[Set[Coord]] = None,
    player=None,
) -> Optional[Tuple[Coord, int, Coord]]:
    """Nearest stay-safe cell, walking through future blast if the fuse allows."""
    return _timed_first_step(
        board, start, lambda x, y: True, danger_times, bomb_cells, now, travel_ms, margin_ms,
        occupied=occupied, stay_goal=True, player=player,
    )


def _must_flee(
    player, game, danger_times: Dict[Coord, int],
    bomb_cells: Set[Coord], occupied: Set[Coord],
    travel_ms: int, margin_ms: int,
) -> bool:
    """Leave as soon as this cell is in a pending or live blast.

    Waiting until the path is already too slow is what left bots standing on
    their own bomb: the last centering step then used up the safety margin.
    """
    del bomb_cells, occupied, travel_ms, margin_ms
    now = int(getattr(game, "current_time", 0))
    start = player.get_grid_pos()
    return not _safe_to_stay(start, now, danger_times, _explosion_duration())


def _escape_reserve_cells(player) -> int:
    """Spare cells before a plant. Speed replaces the spare: a fast bot clears the cell."""
    persona = ai_personality(player)
    if persona in ("boss", "crazy"):
        return 0
    if _cell_travel_ms(player) < _default_travel_ms():
        return 0
    if persona == "cautious":
        return 1
    return ESCAPE_RESERVE_CELLS


def _closing_cells(player, game) -> Set[Coord]:
    """Where a nearby opponent is standing or about to step. Those are not exits."""
    start = player.get_grid_pos()
    closing: Set[Coord] = set()
    for opp in _alive_opponents(player, game):
        og = opp.get_grid_pos()
        if _manhattan(start, og) > 5:
            continue
        closing.add(og)
        face = _facing_step(opp)
        if face == (0, 0):
            continue
        step = (og[0] + face[0], og[1] + face[1])
        if _manhattan(start, step) <= 2:
            closing.add(step)
    closing.discard(start)
    return closing


def _open_lane(board, start: Coord, goal: Coord) -> bool:
    """True when start and goal share a row or column of empty cells."""
    sx, sy = start
    gx, gy = goal
    if sx != gx and sy != gy:
        return False
    if start == goal:
        return True
    step_x = 0 if sx == gx else (1 if gx > sx else -1)
    step_y = 0 if sy == gy else (1 if gy > sy else -1)
    x, y = sx + step_x, sy + step_y
    while (x, y) != goal:
        if not _in_bounds_empty(board, x, y):
            return False
        x += step_x
        y += step_y
    return True


def _lane_lead(player) -> int:
    persona = ai_personality(player)
    fire = max(1, int(getattr(player, "fire_power", 1) or 1))
    if persona == "boss":
        return fire + BOSS_LANE_LEAD_CELLS
    if persona == "crazy":
        return fire + LANE_LEAD_CELLS + 1
    if persona == "cautious":
        return fire + 1
    return fire + LANE_LEAD_CELLS


def _open_lane_toward_opponent(player, game) -> bool:
    """Bosses and crazy bots cut an open lane a little before the shot connects."""
    if ai_personality(player) not in ("boss", "crazy"):
        return False
    start = player.get_grid_pos()
    reach = _lane_lead(player)
    for opp in _alive_opponents(player, game):
        og = opp.get_grid_pos()
        dist = _manhattan(start, og)
        if dist <= 0 or dist > reach:
            continue
        if _open_lane(game.board, start, og):
            return True
    return False


def _can_escape_after_bomb(player, game, danger: set = None, origin: Coord = None) -> bool:
    """True if a timed path from origin reaches a stay-safe cell before our fuse ends."""
    now = int(getattr(game, "current_time", 0))
    timer = _bomb_timer()
    times = _danger_times(game)
    if danger:
        for cell in danger:
            times[cell] = min(times.get(cell, now), now)
    if origin is None:
        px, py = player.get_grid_pos()
    else:
        px, py = origin
    boom = now + timer
    for cell in _blast_cells(game.board, px, py, player.fire_power):
        times[cell] = min(times.get(cell, boom), boom)
    bomb_cells = _cells_with_bombs(game.bombs)
    bomb_cells.add((px, py))
    # Cells an opponent already stands on, or is stepping into, are not an exit.
    bomb_cells.update(_closing_cells(player, game))
    travel = _cell_travel_ms(player)
    margin = _safety_margin_ms(player)
    plan = _timed_escape_step(
        game.board, (px, py), times, bomb_cells, now, travel, margin, occupied=None, player=player,
    )
    if plan is None:
        return False
    _step, dist, _goal = plan
    reserve = _escape_reserve_cells(player)
    return (dist + reserve) * travel + margin < timer


def _alive_opponents(player, game) -> list:
    others = [p for p in game.players if p is not player and getattr(p, "alive", False)]
    humans = [p for p in others if not getattr(p, "is_ai", False)]
    return humans or others


def _opponent_has_line_of_sight(player, opponent, game) -> bool:
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE = _get_params()[:3]
    px, py = player.get_grid_pos()
    ox, oy = opponent.get_grid_pos()
    fp = player.fire_power
    board = game.board

    if oy == py:
        step = 1 if ox > px else -1
        for x in range(px + step, ox, step) if px != ox else []:
            if board[py][x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                return False
        return abs(ox - px) <= fp

    if ox == px:
        step = 1 if oy > py else -1
        for y in range(py + step, oy, step) if py != oy else []:
            if board[y][px] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                return False
        return abs(oy - py) <= fp

    return False


def _opponent_in_blast_range_with_los(player, game) -> bool:
    for p in _alive_opponents(player, game):
        if _opponent_has_line_of_sight(player, p, game):
            return True
    return False


def _manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _safe_neighbor_count(
    board, pos: Coord, danger_times: Dict[Coord, int],
    bomb_cells: Set[Coord], now: int, travel_ms: int, margin_ms: int,
) -> int:
    duration = _explosion_duration()
    n = 0
    for dx, dy in DIRS:
        nx, ny = pos[0] + dx, pos[1] + dy
        cell = (nx, ny)
        if not _in_bounds_empty(board, nx, ny):
            continue
        if cell in bomb_cells:
            continue
        if not _can_occupy(cell, now + travel_ms, travel_ms, danger_times, duration, margin_ms, now):
            continue
        n += 1
    return n


def _adjacent_destructible(board, px: int, py: int) -> List[Coord]:
    EMPTY, DESTRUCTIBLE, *_ = _get_params()
    hits = []
    h, w = len(board), len(board[0])
    for dx, dy in DIRS:
        nx, ny = px + dx, py + dy
        if 0 <= nx < w and 0 <= ny < h and board[ny][nx] == DESTRUCTIBLE:
            hits.append((nx, ny))
    return hits


def _wall_between(board, a: Coord, b: Coord) -> Optional[Coord]:
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE = _get_params()[:3]
    ax, ay = a
    bx, by = b
    if ay == by:
        step = 1 if bx > ax else -1
        for x in range(ax + step, bx, step):
            if board[ay][x] == DESTRUCTIBLE:
                return (x, ay)
            if board[ay][x] == INDESTRUCTIBLE:
                return None
    elif ax == bx:
        step = 1 if by > ay else -1
        for y in range(ay + step, by, step):
            if board[y][ax] == DESTRUCTIBLE:
                return (ax, y)
            if board[y][ax] == INDESTRUCTIBLE:
                return None
    return None


def _empty_path_exists(board, start: Coord, goal: Coord) -> bool:
    EMPTY, *_ = _get_params()
    if start == goal:
        return True
    w, h = len(board[0]), len(board)
    q = deque([start])
    seen = {start}
    while q:
        cx, cy = q.popleft()
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if nxt in seen or not (0 <= nx < w and 0 <= ny < h):
                continue
            if board[ny][nx] != EMPTY:
                continue
            if nxt == goal:
                return True
            seen.add(nxt)
            q.append(nxt)
    return False


def _first_destructible_on_path(board, start: Coord, goal: Coord) -> Optional[Coord]:
    """First crate on a path to goal, only when no empty path exists."""
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE = _get_params()[:3]
    if start == goal or _empty_path_exists(board, start, goal):
        return None
    w, h = len(board[0]), len(board)
    q = deque([start])
    parent: Dict[Coord, Optional[Coord]] = {start: None}
    found = None
    while q:
        cx, cy = q.popleft()
        if (cx, cy) == goal:
            found = (cx, cy)
            break
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if nxt in parent or not (0 <= nx < w and 0 <= ny < h):
                continue
            tile = board[ny][nx]
            if tile == INDESTRUCTIBLE:
                continue
            if tile in (EMPTY, DESTRUCTIBLE):
                parent[nxt] = (cx, cy)
                q.append(nxt)
    if found is None:
        return None
    cur = found
    first_soft = None
    while parent[cur] is not None:
        x, y = cur
        if board[y][x] == DESTRUCTIBLE:
            first_soft = cur
        cur = parent[cur]
    return first_soft


def _los_kill_ok(
    player, opponent, game, danger_times, bomb_cells, now, travel_ms, margin_ms,
) -> bool:
    if not _opponent_has_line_of_sight(player, opponent, game):
        return False
    dist = _manhattan(player.get_grid_pos(), opponent.get_grid_pos())
    if dist >= HEAD_START_CELLS:
        return True
    cap = _trap_neighbor_limit(player)
    return _safe_neighbor_count(
        game.board, opponent.get_grid_pos(), danger_times, bomb_cells, now, travel_ms, margin_ms,
    ) <= cap


def _soft_walls_hit(board, x: int, y: int, fire_power: int) -> int:
    """How many soft bricks a bomb on this cell would break."""
    EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE = _get_params()[:3]
    gw, gh = len(board[0]), len(board)
    hits = 0
    reach = max(0, int(fire_power))
    for dx, dy in DIRS:
        for step in range(1, reach + 1):
            nx, ny = x + dx * step, y + dy * step
            if nx < 0 or nx >= gw or ny < 0 or ny >= gh:
                break
            tile = board[ny][nx]
            if tile == INDESTRUCTIBLE:
                break
            if tile == DESTRUCTIBLE:
                hits += 1
                break
    return hits


def _reachable_wall_cells(
    board, start: Coord, fire_power: int, bomb_cells: Set[Coord],
    danger_times: Dict[Coord, int], now: int, travel_ms: int, margin_ms: int,
    limit: int = FARM_SEARCH_LIMIT,
) -> List[Tuple[int, int, Coord]]:
    """(soft bricks, steps, cell) for reachable floors whose blast breaks a brick."""
    duration = _explosion_duration()
    found: List[Tuple[int, int, Coord]] = []
    q = deque([(start, 0)])
    seen = {start}
    w, h = len(board[0]), len(board)
    while q:
        (cx, cy), dist = q.popleft()
        score = _soft_walls_hit(board, cx, cy, fire_power)
        if score > 0:
            found.append((score, dist, (cx, cy)))
        if dist >= limit:
            continue
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if nxt in seen or not (0 <= nx < w and 0 <= ny < h):
                continue
            if not _in_bounds_empty(board, nx, ny) or nxt in bomb_cells:
                continue
            arrival = now + (dist + 1) * travel_ms
            if not _can_occupy(nxt, arrival, travel_ms, danger_times, duration, margin_ms, now):
                continue
            seen.add(nxt)
            q.append((nxt, dist + 1))
    return found


def _nearest_opponent_dist(player, game) -> int:
    start = player.get_grid_pos()
    opps = _alive_opponents(player, game)
    if not opps:
        return 99
    return min(_manhattan(start, opp.get_grid_pos()) for opp in opps)


def _opponents_nearby(player, game, dist: int = CLOSE_COMBAT_MANHATTAN) -> list:
    start = player.get_grid_pos()
    return [
        opp for opp in _alive_opponents(player, game)
        if _manhattan(start, opp.get_grid_pos()) <= dist
    ]


def _can_block_opponent(
    player, opponent, game, danger_times, bomb_cells, now, travel_ms, margin_ms, blast: set,
) -> bool:
    """True when a bomb here hits them or the brick between you, and they are nearby."""
    start = player.get_grid_pos()
    og = opponent.get_grid_pos()
    if _manhattan(start, og) > CLOSE_COMBAT_MANHATTAN and not _opponent_has_line_of_sight(player, opponent, game):
        return False
    if og in blast:
        return _los_kill_ok(player, opponent, game, danger_times, bomb_cells, now, travel_ms, margin_ms) or _manhattan(start, og) <= CLOSE_COMBAT_MANHATTAN
    wall = _wall_between(game.board, start, og)
    if wall in blast and _manhattan(start, og) <= CLOSE_COMBAT_MANHATTAN + player.fire_power:
        return True
    blocking = _first_destructible_on_path(game.board, start, og)
    return blocking in blast and _manhattan(start, og) <= CLOSE_COMBAT_MANHATTAN + 2


def _attack_available(
    player, game, danger_times, bomb_cells, now, travel_ms, margin_ms, nearby_only: bool,
) -> bool:
    start = player.get_grid_pos()
    blast = set(_blast_cells(game.board, start[0], start[1], player.fire_power))
    for opp in _alive_opponents(player, game):
        og = opp.get_grid_pos()
        close = _manhattan(start, og) <= CLOSE_COMBAT_MANHATTAN
        los = _opponent_has_line_of_sight(player, opp, game)
        if nearby_only and not close:
            continue
        if og in blast or los:
            if nearby_only:
                if _can_block_opponent(player, opp, game, danger_times, bomb_cells, now, travel_ms, margin_ms, blast):
                    return True
            elif _los_kill_ok(player, opp, game, danger_times, bomb_cells, now, travel_ms, margin_ms) or og in blast:
                return True
        if not nearby_only:
            wall = _wall_between(game.board, start, og)
            blocking = _first_destructible_on_path(game.board, start, og)
            if wall in blast or blocking in blast:
                return True
    return False


def _retreat_plan(
    player, game, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
) -> Optional[Tuple[Coord, Coord]]:
    """Step toward the reachable floor farthest from nearby players."""
    start = player.get_grid_pos()
    threats = [opp.get_grid_pos() for opp in _alive_opponents(player, game)]
    if not threats:
        return None
    duration = _explosion_duration()
    best_cell = start
    best_key = (min(_manhattan(start, cell) for cell in threats), 0)
    q = deque([(start, 0)])
    seen = {start}
    w, h = len(game.board[0]), len(game.board)
    while q:
        cell, dist = q.popleft()
        gap = min(_manhattan(cell, threat) for threat in threats)
        key = (gap, -dist)
        if key > best_key:
            best_key = key
            best_cell = cell
        if dist >= FARM_SEARCH_LIMIT:
            continue
        cx, cy = cell
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if nxt in seen or not (0 <= nx < w and 0 <= ny < h):
                continue
            if not _in_bounds_empty(game.board, nx, ny) or nxt in bomb_cells or nxt in occupied:
                continue
            arrival = now + (dist + 1) * travel_ms
            if not _can_occupy(nxt, arrival, travel_ms, danger_times, duration, margin_ms, now):
                continue
            seen.add(nxt)
            q.append((nxt, dist + 1))
    if best_cell == start:
        return (0, 0), start
    plan = _timed_first_step(
        game.board, start, lambda x, y, goal=best_cell: (x, y) == goal,
        danger_times, bomb_cells, now, travel_ms, margin_ms,
        occupied=occupied, stay_goal=True, player=player,
    )
    if plan is None:
        return None
    return plan[0], plan[2]


def _should_place_bomb(
    player, game, danger_times: Dict[Coord, int],
    bomb_cells: Set[Coord], occupied: Set[Coord],
    travel_ms: int, margin_ms: int,
) -> bool:
    if int(getattr(player, "active_bombs", 0) or 0) >= _max_live_bombs(player):
        return False
    px, py = player.get_grid_pos()
    now = int(getattr(game, "current_time", 0))
    duration = _explosion_duration()
    if not _safe_to_stay((px, py), now, danger_times, duration):
        return False
    last = getattr(player, "_ai_last_bomb_ms", -10_000)
    if now - last < _bomb_cooldown_ms(player):
        return False
    if not _is_cell_centered(player, max_off=AI_BOMB_CENTER_PX):
        return False
    if not _can_escape_after_bomb(player, game):
        return False

    here = _soft_walls_hit(game.board, px, py, int(getattr(player, "fire_power", 1) or 1))
    # Any brick is worth a bomb when a way out exists. Walking to a slightly
    # richer cell is how they used to stand still and get flanked.
    if here > 0:
        return True
    if _attack_available(
        player, game, danger_times, bomb_cells, now, travel_ms, margin_ms,
        nearby_only=False,
    ):
        return True
    return _open_lane_toward_opponent(player, game)


def _random_safe_direction(
    board, px: int, py: int, danger: set,
    bomb_cells: Optional[Set[Coord]] = None,
    preferred: Optional[Coord] = None,
) -> Coord:
    candidates = [(0, 0)]
    for dx, dy in DIRS:
        nx, ny = px + dx, py + dy
        if _cell_walkable(board, nx, ny, danger, bomb_cells):
            candidates.append((dx, dy))
    if preferred in candidates and preferred != (0, 0):
        return preferred
    moving = [c for c in candidates if c != (0, 0)]
    if moving:
        return random.choice(moving)
    return (0, 0)


def _random_timed(
    board, start: Coord, danger_times, bomb_cells, occupied,
    now, travel_ms, margin_ms, preferred, require_stay: bool = True,
) -> Coord:
    duration = _explosion_duration()
    options = []
    for dx, dy in DIRS:
        nx, ny = start[0] + dx, start[1] + dy
        cell = (nx, ny)
        if not _in_bounds_empty(board, nx, ny):
            continue
        if cell in bomb_cells or cell in occupied:
            continue
        arrival = now + travel_ms
        if not _can_occupy(cell, arrival, travel_ms, danger_times, duration, margin_ms, now):
            continue
        if require_stay and not _safe_to_stay(cell, arrival, danger_times, duration):
            continue
        options.append((dx, dy))
    if preferred in options:
        return preferred
    if options:
        return random.choice(options)
    return (0, 0)


def _count_soft_walls(board) -> int:
    _empty, destructible, *_ = _get_params()
    return sum(1 for row in board for cell in row if cell == destructible)


def _open_arena(game) -> bool:
    """True once fewer than 15% of the round's soft walls are still standing."""
    from bm_params import CRUSHING_WALLS_STALE_WALL_FRACTION
    start = int(getattr(game, "destructible_at_round_start", 0) or 0)
    if start <= 0:
        return False
    return _count_soft_walls(game.board) < start * CRUSHING_WALLS_STALE_WALL_FRACTION


def _shot_reaches(board, ax: int, ay: int, bx: int, by: int, fire: int) -> bool:
    """A bomb at (ax, ay) would hit (bx, by) along a clear row or column."""
    if (ax == bx and ay == by) or (ax != bx and ay != by):
        return False
    if abs(ax - bx) + abs(ay - by) > fire:
        return False
    step_x = 0 if ax == bx else (1 if bx > ax else -1)
    step_y = 0 if ay == by else (1 if by > ay else -1)
    x, y = ax + step_x, ay + step_y
    while (x, y) != (bx, by):
        if not _in_bounds_empty(board, x, y):
            return False
        x += step_x
        y += step_y
    return True


def _block_plan(
    player, game, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
) -> Optional[Tuple[Coord, Coord]]:
    """On a cleared map, walk onto a row or column that a bomb can cut."""
    if not _open_arena(game):
        return None
    opps = [opp.get_grid_pos() for opp in _alive_opponents(player, game)]
    if not opps:
        return None
    start = player.get_grid_pos()
    fire = max(1, int(getattr(player, "fire_power", 1) or 1))
    board = game.board

    def hits(cell: Coord) -> bool:
        return any(_shot_reaches(board, cell[0], cell[1], ox, oy, fire) for ox, oy in opps)

    def trap_exits(cell: Coord) -> int:
        exits = [
            _empty_neighbor_count(board, opp, bomb_cells, occupied)
            for opp in opps
            if _shot_reaches(board, cell[0], cell[1], opp[0], opp[1], fire)
        ]
        return min(exits) if exits else 99

    if hits(start) and (not _is_cell_centered(player) or _can_escape_after_bomb(player, game)):
        return (0, 0), start

    candidates = []
    q = deque([(start, 0)])
    seen = {start}
    w, h = len(board[0]), len(board)
    while q:
        cell, dist = q.popleft()
        if dist > 0 and hits(cell):
            candidates.append((trap_exits(cell), dist, cell))
        if dist >= BLOCK_SEARCH_LIMIT:
            continue
        cx, cy = cell
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if nxt in seen or not (0 <= nx < w and 0 <= ny < h):
                continue
            if not _in_bounds_empty(board, nx, ny) or nxt in bomb_cells or nxt in occupied:
                continue
            seen.add(nxt)
            q.append((nxt, dist + 1))
    candidates.sort(key=lambda item: (
        item[0], item[1],
        _move_cost(player, item[2], _step_hint(start, item[2]), now),
        item[2][0], item[2][1],
    ))
    for _exits, _dist, goal in candidates:
        plan = _timed_first_step(
            board, start, lambda x, y, goal=goal: (x, y) == goal,
            danger_times, bomb_cells, now, travel_ms, margin_ms, player=player,
            occupied=occupied, stay_goal=True,
        )
        if plan is not None:
            return plan[0], plan[2]
    return None


def _facing_step(actor) -> Coord:
    raw = getattr(actor, "direction", None)
    if raw is None:
        return (0, 0)
    dx, dy = float(raw[0]), float(raw[1])
    if abs(dx) < 0.25 and abs(dy) < 0.25:
        return (0, 0)
    if abs(dx) >= abs(dy):
        return (1 if dx > 0 else -1, 0)
    return (0, 1 if dy > 0 else -1)


def _boss_pressure_plan(
    player, game, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
) -> Optional[Tuple[Coord, Coord]]:
    """Close in, cut the lane, and stand on an exit so the body blocks it."""
    opponents = _alive_opponents(player, game)
    if not opponents:
        return None
    start = player.get_grid_pos()
    opp = min(opponents, key=lambda other: _manhattan(start, other.get_grid_pos()))
    og = opp.get_grid_pos()
    board = game.board
    fire = max(1, int(getattr(player, "fire_power", 1) or 1))
    facing = _facing_step(opp)
    adjacent = []
    lanes = []
    for dx, dy in DIRS:
        for step in range(1, fire + 1):
            cell = (og[0] + dx * step, og[1] + dy * step)
            if cell in bomb_cells or not _in_bounds_empty(board, cell[0], cell[1]):
                break
            if step == 1:
                adjacent.append(cell)
            lanes.append(cell)
    last_bomb = int(getattr(player, "_ai_last_bomb_ms", -10_000))
    on_them = start in adjacent
    orbit = on_them and _is_cell_centered(player) and (
        now - last_bomb < _bomb_cooldown_ms(player) or not _can_escape_after_bomb(player, game)
    )
    if on_them and not orbit:
        return (0, 0), start

    def rank(cell: Coord):
        step = (cell[0] - og[0], cell[1] - og[1])
        body = abs(step[0]) + abs(step[1]) == 1
        intercept = 0 if facing != (0, 0) and step == facing else 1
        exits = _empty_neighbor_count(board, cell, bomb_cells, occupied)
        recent = 1 if cell in (getattr(player, "_ai_recent_cells", ()) or ()) else 0
        return (0 if body else 1, intercept, -exits, recent, _manhattan(start, cell))

    candidates = []
    seen = set()
    for cell in adjacent + lanes:
        if cell in seen or cell == start:
            continue
        seen.add(cell)
        candidates.append(cell)
    feasible = []
    for goal in candidates:
        plan = _timed_first_step(
            board, start, lambda x, y, goal=goal: (x, y) == goal,
            danger_times, bomb_cells, now, travel_ms, margin_ms,
            occupied=occupied, stay_goal=True, player=player,
        )
        if plan is None:
            continue
        step = plan[0]
        step_cell = (start[0] + step[0], start[1] + step[1])
        feasible.append((rank(goal), _move_cost(player, step_cell, step, now), step, plan[2]))
    if not feasible:
        return None
    feasible.sort(key=lambda item: (item[0], item[1]))
    best_rank = feasible[0][0]
    held = tuple(getattr(player, "_ai_goal_cell", None) or ())
    kept = [item for item in feasible if item[0] == best_rank and item[3] == held]
    _rank, _cost, step, goal = kept[0] if kept else feasible[0]
    return step, goal


def _hunt_plan(
    player, game, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
) -> Optional[Tuple[Coord, Coord]]:
    targets = _alive_opponents(player, game)
    if not targets:
        return None
    start = player.get_grid_pos()
    goals: Set[Coord] = set()
    for opp in targets:
        gx, gy = opp.get_grid_pos()
        if start == (gx, gy):
            return (0, 0), start
        for dx, dy in DIRS:
            cell = (gx + dx, gy + dy)
            if _in_bounds_empty(game.board, cell[0], cell[1]) and cell not in bomb_cells:
                goals.add(cell)
    if not goals:
        return None
    blocked = set(occupied)
    for opp in targets:
        blocked.discard(opp.get_grid_pos())
    plan = _timed_first_step(
        game.board, start, lambda x, y: (x, y) in goals,
        danger_times, bomb_cells, now, travel_ms, margin_ms,
        occupied=blocked, stay_goal=True, player=player,
    )
    if plan is None:
        return None
    step, _dist, goal = plan
    return step, goal


def _farm_plan(
    player, game, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
) -> Optional[Tuple[Coord, Coord]]:
    """Walk to the reachable cell whose bomb breaks the most soft bricks."""
    start = player.get_grid_pos()
    options = _reachable_wall_cells(
        game.board, start, int(getattr(player, "fire_power", 1) or 1), bomb_cells,
        danger_times, now, travel_ms, margin_ms,
    )
    if not options:
        return None
    # A richer cell that fills the only exit is not a plant. In a 3-cell corner
    # the junction hits every brick and also every floor, so the bot used to
    # pace back to it and never bomb the arm it can leave.
    best_score = max(score for score, _dist, _cell in options)
    plantable = [
        item for item in options
        if item[0] == best_score and _can_escape_after_bomb(player, game, origin=item[2])
    ]
    if not plantable:
        plantable = [
            item for item in options
            if _can_escape_after_bomb(player, game, origin=item[2])
        ]
    if not plantable:
        return None
    options = plantable
    best_score = max(score for score, _dist, _cell in options)
    last = tuple(getattr(player, "_ai_last_dir", (0, 0)) or (0, 0))
    recent = getattr(player, "_ai_recent_cells", ()) or ()
    contenders = []
    for index, (score, dist, cell) in enumerate(options):
        if score != best_score:
            continue
        # With no heading yet, keep the old nearest-cell order. Noise is for
        # breaking a tie once the bot is already moving, so it does not reverse.
        taste = 0.0
        if last != (0, 0) or cell in recent:
            taste = _move_cost(player, cell, _step_hint(start, cell), now)
        contenders.append((dist, taste, index, cell))
    # Stay only to plant. A tie the bot cannot bomb from is not a decision.
    here = any(item[3] == start for item in contenders)
    moving = [item for item in contenders if item[3] != start]
    if here and _can_escape_after_bomb(player, game):
        if not _safe_to_stay(start, now, danger_times, _explosion_duration()):
            return None
        return (0, 0), start
    if not moving:
        return None
    held = tuple(getattr(player, "_ai_goal_cell", None) or ())
    if any(item[3] == held for item in moving):
        goal = held
    else:
        _dist, _taste, _index, goal = min(moving, key=lambda item: (item[0], item[1], item[2]))
    plan = _timed_first_step(
        game.board, start, lambda x, y, goal=goal: (x, y) == goal,
        danger_times, bomb_cells, now, travel_ms, margin_ms,
        occupied=occupied, stay_goal=True, player=player,
    )
    if plan is None:
        return None
    return plan[0], plan[2]


def _powerup_plan(
    player, game, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
    mode: str = "other",
) -> Optional[Tuple[Coord, Coord]]:
    powerups = list(getattr(game, "powerups", None) or [])
    if not powerups:
        return None
    start = player.get_grid_pos()
    limit = _powerup_limit(player, quad=(mode == "qd"))
    picked = []
    for pu in powerups:
        kind = getattr(pu, "type", "")
        if mode == "qd" and kind != "quad_damage":
            continue
        if mode == "other" and kind == "quad_damage":
            continue
        cell = (pu.x, pu.y)
        if _manhattan(start, cell) > limit:
            continue
        if not _in_bounds_empty(game.board, pu.x, pu.y) or cell in bomb_cells:
            continue
        picked.append(cell)
    if not picked:
        return None
    held = tuple(getattr(player, "_ai_goal_cell", None) or ())
    if held in picked:
        picked = [held]
    goals = set(picked)
    plan = _timed_first_step(
        game.board, start, lambda x, y: (x, y) in goals,
        danger_times, bomb_cells, now, travel_ms, margin_ms,
        occupied=occupied, stay_goal=True, player=player,
    )
    if plan is None:
        return None
    step, _dist, goal = plan
    return step, goal


def _close_combat(player, game) -> bool:
    start = player.get_grid_pos()
    for opp in _alive_opponents(player, game):
        if _manhattan(start, opp.get_grid_pos()) <= CLOSE_COMBAT_MANHATTAN:
            return True
        if _opponent_has_line_of_sight(player, opp, game):
            return True
    return False


def _commit_goal(player, kind: str, cell: Optional[Coord], now: int) -> None:
    player._ai_goal_kind = kind
    player._ai_goal_cell = cell
    if kind == "wait":
        stick = _bomb_timer() + _explosion_duration() + 100
    elif kind in ("flee", "wander"):
        stick = 0
    else:
        stick = AI_STICKY_MS
    player._ai_goal_until = now + stick


def _follow_sticky(
    player, board, danger_times, bomb_cells, occupied, now, travel_ms, margin_ms,
) -> Optional[Coord]:
    kind = getattr(player, "_ai_goal_kind", None)
    cell = getattr(player, "_ai_goal_cell", None)
    until = int(getattr(player, "_ai_goal_until", 0) or 0)
    if kind in (None, "flee", "wander") or cell is None or now >= until:
        return None
    if not _in_bounds_empty(board, cell[0], cell[1]) or cell in bomb_cells:
        return None
    plan = _timed_first_step(
        board, player.get_grid_pos(), lambda x, y: (x, y) == cell,
        danger_times, bomb_cells, now, travel_ms, margin_ms,
        occupied=occupied, stay_goal=True, player=player,
    )
    if plan is None:
        return None
    if plan[0] == (0, 0):
        return (0, 0) if kind == "wait" else None
    return plan[0]


def _nearest_powerup(
    board, px: int, py: int, powerups: list, danger: set,
    bomb_cells: Optional[Set[Coord]] = None
) -> Optional[Coord]:
    """Test helper: BFS toward Quad Damage if reachable, else any reachable PU."""
    if not powerups:
        return None
    qds = [
        (pu.x, pu.y)
        for pu in powerups
        if getattr(pu, "type", "") == "quad_damage"
        and _cell_walkable(board, pu.x, pu.y, danger, bomb_cells)
    ]
    if qds:
        step = _first_step(board, (px, py), lambda x, y: (x, y) in set(qds), danger, bomb_cells)
        if step is not None:
            return step
    goals = {
        (pu.x, pu.y)
        for pu in powerups
        if _cell_walkable(board, pu.x, pu.y, danger, bomb_cells)
    }
    if not goals:
        return None
    return _first_step(board, (px, py), lambda x, y: (x, y) in goals, danger, bomb_cells)


def _hunt_direction(player, game, danger: set, bomb_cells: Set[Coord]) -> Optional[Coord]:
    now = int(getattr(game, "current_time", 0))
    times = {cell: now for cell in danger}
    plan = _hunt_plan(
        player, game, times, bomb_cells, set(), now, _cell_travel_ms(player), _safety_margin_ms(player),
    )
    return None if plan is None else plan[0]


def _farm_direction(board, px: int, py: int, danger: set, bomb_cells: Set[Coord]) -> Optional[Coord]:
    EMPTY, DESTRUCTIBLE, *_ = _get_params()
    h, w = len(board), len(board[0])
    goals = set()
    for y in range(h):
        for x in range(w):
            if board[y][x] != DESTRUCTIBLE:
                continue
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if _cell_walkable(board, nx, ny, danger, bomb_cells):
                    goals.add((nx, ny))
    if not goals:
        return None
    return _first_step(board, (px, py), lambda x, y: (x, y) in goals, danger, bomb_cells)


def _cell_center_px(player) -> Tuple[float, float]:
    from bm_params import CELL_SIZE
    gx = int(player.pos[0] // CELL_SIZE)
    gy = int(player.pos[1] // CELL_SIZE)
    return ((gx + 0.5) * CELL_SIZE, (gy + 0.5) * CELL_SIZE)


def _is_cell_centered(player, max_off: float = AI_CENTER_LOCK_PX) -> bool:
    cx, cy = _cell_center_px(player)
    return abs(player.pos[0] - cx) <= max_off and abs(player.pos[1] - cy) <= max_off


def _align_then_turn(player, direction: Coord) -> Coord:
    """Center on the current cell before accepting a 90-degree turn."""
    wanted = direction or (0, 0)
    last = tuple(getattr(player, "_ai_last_dir", (0, 0))) or (0, 0)
    cx, cy = _cell_center_px(player)
    off_x = player.pos[0] - cx
    off_y = player.pos[1] - cy

    if wanted == (0, 0):
        return _center_dir(player)

    def toward_center_x() -> Coord:
        if abs(off_x) <= AI_CENTER_LOCK_PX:
            return wanted
        if last[0] != 0 and ((last[0] > 0 and off_x < 0) or (last[0] < 0 and off_x > 0)):
            return last
        return (-1 if off_x > 0 else 1, 0)

    def toward_center_y() -> Coord:
        if abs(off_y) <= AI_CENTER_LOCK_PX:
            return wanted
        if last[1] != 0 and ((last[1] > 0 and off_y < 0) or (last[1] < 0 and off_y > 0)):
            return last
        return (0, -1 if off_y > 0 else 1)

    if wanted[0] != 0 and wanted[1] == 0:
        return toward_center_y()
    if wanted[1] != 0 and wanted[0] == 0:
        return toward_center_x()
    return wanted


def think_ai(player, game) -> Tuple[Coord, bool]:
    """Grid intent and bomb flag. Called at think rate, and whenever fleeing."""
    now = int(getattr(game, "current_time", 0))
    board = game.board
    start = player.get_grid_pos()
    _note_visit(player, start)
    times = _danger_times(game)
    bombs = _cells_with_bombs(game.bombs)
    occupied = _other_player_cells(player, game)
    travel = _cell_travel_ms(player)
    margin = _safety_margin_ms(player)
    preferred = tuple(getattr(player, "_ai_intent_dir", None) or getattr(player, "_ai_last_dir", (0, 0))) or (0, 0)

    flee = _must_flee(player, game, times, bombs, occupied, travel, margin)
    place = False
    if not flee:
        place = _should_place_bomb(player, game, times, bombs, occupied, travel, margin)

    if flee or place:
        times_m = dict(times)
        bombs_m = set(bombs)
        if place:
            boom = now + _bomb_timer()
            for cell in _blast_cells(board, start[0], start[1], player.fire_power):
                times_m[cell] = min(times_m.get(cell, boom), boom)
            bombs_m.add(start)
            player._ai_last_bomb_ms = now
        plan = _timed_escape_step(
            board, start, times_m, bombs_m, now, travel, margin, occupied=None,
        )
        duration = _explosion_duration()
        still_lit = not _safe_to_stay(start, now, times_m, duration)
        if plan is None or (still_lit and plan[0] == (0, 0)):
            _commit_goal(player, "flee", None, now)
            step = _random_timed(
                board, start, times_m, bombs_m, set(), now, travel, margin, preferred, require_stay=False
            )
            if step == (0, 0):
                step = _leave_pocket(
                    board, start, bombs_m, set(), times_m, now, travel, margin, player,
                )
            return step, place
        _commit_goal(player, "wait", plan[2], now)
        return plan[0], place

    sticky = _follow_sticky(player, board, times, bombs, occupied, now, travel, margin)
    if sticky is not None:
        return sticky, False
    persona = ai_personality(player)

    def _finish(kind: str, plan: Tuple[Coord, Coord]):
        step, goal = plan
        _commit_goal(player, kind, goal, now)
        if step == (0, 0):
            step = _idle_step(player, board, start, bombs, occupied, times, now)
        return step, False

    if _open_arena(game) and persona != "boss":
        block = _block_plan(player, game, times, bombs, occupied, now, travel, margin)
        if block is not None:
            return _finish("block", block)

    if persona == "crazy":
        qd = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="qd")
        if qd is not None:
            return _finish("powerup", qd)
        hunt = _hunt_plan(player, game, times, bombs, occupied, now, travel, margin)
        if hunt is not None:
            return _finish("hunt", hunt)
        bonus = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="other")
        if bonus is not None:
            return _finish("powerup", bonus)
    elif persona == "boss":
        # Fight first. Grab a quad only when it is closer than the opponent.
        near = _nearest_opponent_dist(player, game)
        qd = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="qd")
        if qd is not None and _manhattan(start, qd[1]) + 1 < near:
            return _finish("powerup", qd)
        pressure = _boss_pressure_plan(player, game, times, bombs, occupied, now, travel, margin)
        if pressure is not None:
            return _finish("block", pressure)
        hunt = _hunt_plan(player, game, times, bombs, occupied, now, travel, margin)
        if hunt is not None:
            return _finish("hunt", hunt)
        bonus = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="other")
        if bonus is not None:
            return _finish("powerup", bonus)
    elif persona == "cautious":
        if _opponents_nearby(player, game) or _open_lane_toward_opponent(player, game):
            hunt = _hunt_plan(player, game, times, bombs, occupied, now, travel, margin)
            if hunt is not None:
                return _finish("hunt", hunt)
        bonus = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="any")
        if bonus is not None:
            return _finish("powerup", bonus)
    else:
        if _opponents_nearby(player, game):
            hunt = _hunt_plan(player, game, times, bombs, occupied, now, travel, margin)
            if hunt is not None:
                return _finish("hunt", hunt)
        else:
            qd = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="qd")
            if qd is not None:
                return _finish("powerup", qd)
            bonus = _powerup_plan(player, game, times, bombs, occupied, now, travel, margin, mode="other")
            if bonus is not None:
                return _finish("powerup", bonus)

    farm = _farm_plan(player, game, times, bombs, occupied, now, travel, margin)
    if farm is not None:
        return _finish("farm", farm)

    if persona in ("normal", "boss", "crazy", "cautious") or _open_arena(game):
        hunt = _hunt_plan(player, game, times, bombs, occupied, now, travel, margin)
        if hunt is not None:
            return _finish("hunt", hunt)

    _commit_goal(player, "wander", None, now)
    wander = _random_timed(board, start, times, bombs, occupied, now, travel, margin, preferred)
    if wander == (0, 0):
        wander = _idle_step(player, board, start, bombs, occupied, times, now)
    return wander, False


def _as_dir_array(direction: Coord) -> np.ndarray:
    dx, dy = direction
    arr = np.array([float(dx), float(dy)], dtype=np.float64)
    if np.dot(arr, arr) > 1:
        arr = arr / np.linalg.norm(arr)
    return arr


def compute_ai_input(player, game) -> Tuple[np.ndarray, bool]:
    """
    Steer every call; rethink on interval or when a fuse race starts.
    Returns (direction, place_bomb).
    """
    now = int(getattr(game, "current_time", 0))
    times = _danger_times(game)
    bombs = _cells_with_bombs(game.bombs)
    occupied = _other_player_cells(player, game)
    travel = _cell_travel_ms(player)
    margin = _safety_margin_ms(player)
    flee = _must_flee(player, game, times, bombs, occupied, travel, margin)

    last = getattr(player, "_ai_last_think_ms", None)
    intent = getattr(player, "_ai_intent_dir", None)
    grid = player.get_grid_pos()
    need_think = (
        intent is None
        or last is None
        or flee
        or grid != getattr(player, "_ai_think_grid", None)
        or (now - int(last) >= AI_THINK_INTERVAL_MS)
    )

    place_bomb = False
    if need_think:
        wanted, place_bomb = think_ai(player, game)
        player._ai_intent_dir = wanted
        player._ai_last_think_ms = now
        player._ai_think_grid = grid
    else:
        wanted = intent or (0, 0)

    # Centering before a turn spends the exit. While the cell is already lit, step out now.
    steered = wanted if flee else _align_then_turn(player, wanted)
    player._ai_last_dir = steered
    return _as_dir_array(steered), place_bomb


def reset_ai_memory(player) -> None:
    player._ai_last_dir = (0, 0)
    player._ai_intent_dir = None
    player._ai_last_think_ms = None
    player._ai_last_bomb_ms = -10_000
    player._ai_goal_kind = None
    player._ai_goal_cell = None
    player._ai_goal_until = 0
    player._ai_think_grid = None
    player._ai_recent_cells = ()

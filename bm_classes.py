import math
import numpy as np
from bm_params import *
from lib_collisions import *
from lib_grid import *
from bm_sounds import *
from bm_drawing import *
from input_abstraction import get_pressed_keys, is_key_pressed, Keys
from timing_abstraction import get_ticks, Clock
from frontend import FrontendManager
from backend_game_logic import BackendGameLogic
from explosions import (
    compute_explosion_active_cells,
    count_unique_explosion_tiles,
    crossed_big_explosion_threshold,
    explosion_cell_rect,
    explosion_player_radius,
    explosion_tip_clip,
    planned_blast_cells,
    prune_explosion_events,
)
from powerups import choose_death_bonus_effect
from replay import build_replay_snapshot, freeze_kill_cam_clip



class Player:
    def __init__(self, grid_x, grid_y, color, controls, name):
        self.start_grid_x = grid_x
        self.start_grid_y = grid_y
        self.pos = np.array([grid_x * CELL_SIZE + CELL_SIZE // 2,
                                        grid_y * CELL_SIZE + CELL_SIZE // 2], dtype=np.float64)
        self.color = color
        self.controls = controls
        self.bomb_capacity = 1
        self.fire_power = 1
        self.active_bombs = 0
        self.alive = True
        self.speed = PLAYER_SPEED
        self.trophies = 0
        self.draw_radius = int(CELL_SIZE * PLAYER_DRAW_SCALE / 2)
        self.collision_radius = int(CELL_SIZE * PLAYER_COLLISION_SCALE / 2)
        self.animation_time = 0
        self.quad_damage = False
        self.quad_damage_start_time = 0
        self.name = name
        self.death_animation_time = 0
        self.direction = np.array([0.0, 0.0], dtype=np.float64)  # Initialize direction
        # Transient pickup message (shows for a few seconds on pickup)
        self.pickup_message = ""
        self.pickup_message_end_time = 0
        # Death time tracking (absolute and relative to round start)
        self.death_time_ms = None
        self.death_time_rel_ms = None
        # Stats snapshot at death
        self.fire_power_at_death = None
        self.bomb_capacity_at_death = None
        # Match statistics (per-round)
        self.walls_destroyed = 0
        self.players_killed = 0
        self.powerups_collected = 0
        self.quad_damage_collected = 0
        self.cells_walked = 0
        # Cumulative stats across rounds (persistent until champion)
        self.total_walls_destroyed = 0
        self.total_players_killed = 0
        self.total_powerups_collected = 0
        self.total_quad_damage_collected = 0
        self.total_cells_walked = 0
        self._last_grid_pos = None
        # Team mode (0 by default, assigned in create_players)
        self.team = 0
        self._bomb_key_held = False
        self.is_ai = False
        self.ai_role = ""
        self.ai_personality = ""
        self._ai_last_dir = (0, 0)
        self._ai_intent_dir = None
        self._ai_last_think_ms = None
        self._ai_last_bomb_ms = -10_000
        self._ai_goal_kind = None
        self._ai_goal_cell = None
        self._ai_goal_until = 0
        self._ai_think_grid = None
        self.boss_lives_remaining = 0
        self.boss_shield_until = 0

    def get_circle(self):
        return (self.pos, self.draw_radius)

    def get_grid_pos(self):
        return (int(self.pos[0] // CELL_SIZE), int(self.pos[1] // CELL_SIZE))

    def update(self, dt, board, bombs, current_time, web_keys=None, game=None):
        if not self.alive:
            if self.death_animation_time > 0:
                self.death_animation_time -= dt
            self.direction = np.array([0.0, 0.0], dtype=np.float64)  # No direction if dead
            return
        direction = np.array([0.0, 0.0], dtype=np.float64)
        mapped_web_keys = set()
        is_ai_turn = bool(getattr(self, 'is_ai', False) and game is not None)
        if is_ai_turn:
            from ai_controller import compute_ai_input
            direction, place_bomb = compute_ai_input(self, game)
            if DEGUG:
                gx, gy = self.get_grid_pos()
                print(f"[AI] {self.name} @({gx},{gy}) dir=({direction[0]:.0f},{direction[1]:.0f}) bomb={place_bomb}")
            if place_bomb:
                self.drop_bomb(bombs, current_time, game=game)
        else:
            keys = get_pressed_keys()
            # Remap all web_keys using browser_key_to_pygame
            if web_keys:
                for k in web_keys:
                    mapped = browser_key_to_pygame(k)
                    if mapped:
                        mapped_web_keys.add(mapped.lower())
        # Use mapped_web_keys as an OR with local keys
        # Handle both local players (with controls) and client players (web_keys only)
        if not is_ai_turn and self.controls is not None:
            # Local player - use local controls + web keys
            if is_key_pressed(self.controls['up']) or (mapped_web_keys and 'up' in mapped_web_keys):
                direction[1] -= 1
            if is_key_pressed(self.controls['down']) or (mapped_web_keys and 'down' in mapped_web_keys):
                direction[1] += 1
            if is_key_pressed(self.controls['left']) or (mapped_web_keys and 'left' in mapped_web_keys):
                direction[0] -= 1
            if is_key_pressed(self.controls['right']) or (mapped_web_keys and 'right' in mapped_web_keys):
                direction[0] += 1
        elif not is_ai_turn:
            # Client player - use web keys only
            if mapped_web_keys and 'up' in mapped_web_keys:
                direction[1] -= 1
            if mapped_web_keys and 'down' in mapped_web_keys:
                direction[1] += 1
            if mapped_web_keys and 'left' in mapped_web_keys:
                direction[0] -= 1
            if mapped_web_keys and 'right' in mapped_web_keys:
                direction[0] += 1
        if np.dot(direction, direction) > 1:
            length = np.linalg.norm(direction)
            if length > 0:
                direction = direction / length
        if np.dot(direction, direction) > 0:
            self.animation_time += dt
        else:
            self.animation_time = 0
            
        # Store original direction for green cell detection (same logic as draw_player_directions)
        original_direction = direction.copy()
        self.direction = direction  # Always store the current direction vector

        # Corner sliding assistance - help when trying to move toward green cells but hitting corners
        if np.dot(original_direction, original_direction) > 0:  # Player is trying to move
            # Check if target cell would be green (same logic as draw_player_directions)
            cell_x = int((self.pos[0] + original_direction[0] * CELL_SIZE) // CELL_SIZE)
            cell_y = int((self.pos[1] + original_direction[1] * CELL_SIZE) // CELL_SIZE)
            
            # Check if target cell is empty and in bounds
            target_is_empty = (0 <= cell_y < len(board) and 0 <= cell_x < len(board[0]) and 
                              board[cell_y][cell_x] == EMPTY)
            
            # Only help with pure cardinal directions when target is empty (green)
            if target_is_empty:
                dx, dy = int(original_direction[0]), int(original_direction[1])
                is_cardinal = (dx == 1 and dy == 0) or (dx == -1 and dy == 0) or (dx == 0 and dy == 1) or (dx == 0 and dy == -1)
                
                if is_cardinal:
                    # Try a test move in the desired direction
                    spd = self.speed if not self.quad_damage else int(self.speed * QUAD_DAMAGE_SPEEDUP)
                    test_pos = self.pos + original_direction * spd * (dt / 1000.0)
                    
                    # Temporarily set position to test for collisions
                    original_actual_pos = self.pos.copy()
                    self.pos = test_pos
                    would_collide = self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_actual_pos)
                    self.pos = original_actual_pos  # Restore position
                    
                    # If the direct movement would be blocked, apply corner sliding
                    if would_collide:
                        slide_direction = np.array([0.0, 0.0], dtype=np.float64)
                        
                        # Get position within current cell
                        cell_pos_x = (self.pos[0] % CELL_SIZE) / CELL_SIZE
                        cell_pos_y = (self.pos[1] % CELL_SIZE) / CELL_SIZE
                        
                        # Apply corner sliding based on position within cell
                        if dx != 0:  # Moving horizontally
                            if cell_pos_y < 0.4:  # Upper part - slide up
                                slide_direction[1] = 0.6
                            elif cell_pos_y > 0.6:  # Lower part - slide down  
                                slide_direction[1] = -0.6
                        
                        if dy != 0:  # Moving vertically
                            if cell_pos_x < 0.4:  # Left part - slide left
                                slide_direction[0] = 0.6
                            elif cell_pos_x > 0.6:  # Right part - slide right
                                slide_direction[0] = -0.6
                        
                        # Apply the corner sliding
                        if np.dot(slide_direction, slide_direction) > 0:
                            direction = original_direction + slide_direction
                            if np.dot(direction, direction) > 1:
                                length = np.linalg.norm(direction)
                                if length > 0:
                                    direction = direction / length

        # Hold-to-plant: keep dropping while the bomb button is down.
        if not is_ai_turn:
            bomb_down = self._bomb_button_down(mapped_web_keys)
            if bomb_down:
                self.drop_bomb(bombs, current_time, game=game)
            self._bomb_key_held = bomb_down

        original_pos = self.pos.copy()
        spd = self.speed if not self.quad_damage else int(self.speed * QUAD_DAMAGE_SPEEDUP)
        self.pos = self.pos + direction * spd * (dt / 1000.0)

        # Update bomb ownership if the player has left their bomb cell.
        for bomb in bombs:
            if bomb.owner == self and not bomb.owner_left:
                if self.get_grid_pos() != (bomb.x, bomb.y):
                    bomb.owner_left = True

        # Use our new collision check.
        if self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos):
            # Try moving only along x
            self.pos = original_pos + np.array([direction[0] * spd * (dt / 1000.0), 0], dtype=np.float64)
            if not (self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos)):
                pass  # x-only succeeded
            else:
                # Try moving only along y
                self.pos = original_pos + np.array([0, direction[1] * spd * (dt / 1000.0)], dtype=np.float64)
                if not (self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos)):
                    pass  # y-only succeeded
                else:
                    # Both attempts failed, revert.
                    self.pos = original_pos

        # Count cells walked only after final position is known (avoid counting when we collide and revert)
        current_grid = self.get_grid_pos()
        start_grid = (int(original_pos[0] // CELL_SIZE), int(original_pos[1] // CELL_SIZE))
        if self._last_grid_pos is not None and current_grid != self._last_grid_pos:
            self.cells_walked += 1
        self._last_grid_pos = current_grid

        # Extra plants: if still holding and this cell is newly entered / empty, drop again.
        if not is_ai_turn and self._bomb_key_held and current_grid != start_grid:
            self.drop_bomb(bombs, current_time, game=game)

        # Handle quad damage duration.
        if self.quad_damage and current_time - self.quad_damage_start_time > QUAD_DAMAGE_TIME * 1000:
            self.quad_damage = False
            self.bomb_capacity -= QUAD_DAMAGE_POWER
            self.fire_power -= QUAD_DAMAGE_POWER
            
    def collides_with_walls(self, board):
        center_x = int(self.pos[0] // CELL_SIZE)
        center_y = int(self.pos[1] // CELL_SIZE)
        bw, bh = len(board[0]), len(board)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                x = center_x + dx
                y = center_y + dy
                if 0 <= x < bw and 0 <= y < bh:
                    if board[y][x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                        wall_rect = (x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                        if circle_rect_collision((self.pos[0], self.pos[1]), self.collision_radius, wall_rect):
                            return True
        return False

    def collides_with_bombs(self, bombs, original_pos):
        for bomb in bombs:
            # Skip your own bomb that hasn't been left yet.
            if bomb.owner == self and not bomb.owner_left:
                continue

            # Get bomb's cell and center.
            bomb_cell = (bomb.x, bomb.y)
            bomb_cx = bomb.x * CELL_SIZE + CELL_SIZE / 2
            bomb_cy = bomb.y * CELL_SIZE + CELL_SIZE / 2
            # If the player originally was in the bomb's cell:
            if (int(original_pos[0] // CELL_SIZE), int(original_pos[1] // CELL_SIZE)) == bomb_cell:
                # If the new position is further from the bomb center than the starting position, let the player exit:
                orig_dx = original_pos[0] - bomb_cx
                orig_dy = original_pos[1] - bomb_cy
                new_dx = self.pos[0] - bomb_cx
                new_dy = self.pos[1] - bomb_cy
                if (new_dx * new_dx + new_dy * new_dy) ** 0.5 + int(CELL_SIZE / 10) > (orig_dx * orig_dx + orig_dy * orig_dy) ** 0.5:
                    continue  # allow the move out

            # Otherwise (or if not exiting), use a reduced bomb collision box.
            margin = CELL_SIZE * 0.35  # tweak margin as needed
            bomb_rect = (
                bomb.x * CELL_SIZE + margin,
                bomb.y * CELL_SIZE + margin,
                CELL_SIZE - 2 * margin,
                CELL_SIZE - 2 * margin,
            )
            if circle_rect_collision((self.pos[0], self.pos[1]), self.collision_radius, bomb_rect):
                return True
        return False
    

    def _bomb_button_down(self, mapped_web_keys):
        if self.controls is not None:
            return is_key_pressed(self.controls['bomb']) or (mapped_web_keys and 'space' in mapped_web_keys)
        return bool(mapped_web_keys and 'space' in mapped_web_keys)

    def drop_bomb(self, bombs, current_time, game=None):
        if not self.alive or self.active_bombs >= self.bomb_capacity:
            return
        grid_x, grid_y = self.get_grid_pos()
        for bomb in bombs:
            if bomb.x == grid_x and bomb.y == grid_y:
                return
        # Forbid placing bombs on powerup cells
        if game is not None:
            for pu in game.powerups:
                if pu.x == grid_x and pu.y == grid_y:
                    return
        new_bomb = Bomb(grid_x, grid_y, current_time, self.fire_power, self)
        if self.quad_damage:
            new_bomb.quad_damage = True
        
        bombs.append(new_bomb)
        self.active_bombs += 1
        

    def reset(self):
        self.pos = np.array([self.start_grid_x * CELL_SIZE + CELL_SIZE // 2,
                                        self.start_grid_y * CELL_SIZE + CELL_SIZE // 2], dtype=np.float64)
        self.alive = True
        self.bomb_capacity = 1
        self.fire_power = 1
        self.active_bombs = 0
        self.animation_time = 0
        self.quad_damage = False  # Add this line
        self.quad_damage_start_time = 0  # Add this lines
        self.pickup_message = ""
        self.pickup_message_end_time = 0
        self.death_time_ms = None
        self.death_time_rel_ms = None
        self.fire_power_at_death = None
        self.bomb_capacity_at_death = None
        self.walls_destroyed = 0
        self.players_killed = 0
        self.powerups_collected = 0
        self.quad_damage_collected = 0
        self.cells_walked = 0
        self._last_grid_pos = self.get_grid_pos()
        self._bomb_key_held = False
        self.boss_shield_until = 0
        from ai_controller import reset_ai_memory
        reset_ai_memory(self)

    def to_dict(self):
        # Handle numpy arrays for serialization
        return {
            'id': getattr(self, 'global_id', 0),
            'name': self.name,
            'x': float(self.pos[0]),
            'y': float(self.pos[1]),
            'color': self.color,  # Assuming tuple/list
            'alive': self.alive,
            'direction': [float(self.direction[0]), float(self.direction[1])],
            'quad_damage': self.quad_damage,
            'trophies': int(self.trophies),
            'death_time_rel_ms': None if self.death_time_rel_ms is None else int(self.death_time_rel_ms),
            'fire_power_at_death': None if self.fire_power_at_death is None else int(self.fire_power_at_death),
            'bomb_capacity_at_death': None if self.bomb_capacity_at_death is None else int(self.bomb_capacity_at_death),
            'death_anim_time': self.death_animation_time,
            'fire_power': int(self.fire_power),
            'bomb_capacity': int(self.bomb_capacity),
            'walls_destroyed': int(self.walls_destroyed),
            'players_killed': int(self.players_killed),
            'powerups_collected': int(self.powerups_collected),
            'quad_damage_collected': int(self.quad_damage_collected),
            'cells_walked': int(self.cells_walked),
            'total_walls_destroyed': int(getattr(self, 'total_walls_destroyed', 0)),
            'total_players_killed': int(getattr(self, 'total_players_killed', 0)),
            'total_powerups_collected': int(getattr(self, 'total_powerups_collected', 0)),
            'total_quad_damage_collected': int(getattr(self, 'total_quad_damage_collected', 0)),
            'total_cells_walked': int(getattr(self, 'total_cells_walked', 0)),
            'team': int(self.team),
            'owner_client_id': int(getattr(self, 'client_id', -1)) if getattr(self, 'client_id', None) is not None else None,
            'owner_client_player_id': int(getattr(self, 'client_player_id', -1)) if getattr(self, 'client_player_id', None) is not None else None,
            'is_ai': getattr(self, 'is_ai', False),
            'shield_until': int(getattr(self, 'boss_shield_until', 0) or 0),
            'boss_lives_remaining': int(getattr(self, 'boss_lives_remaining', 0) or 0),
        }

class Bomb:
    def __init__(self, x, y, start_time, fire_power, owner):
        self.x = x
        self.y = y
        self.start_time = start_time
        self.fire_power = fire_power
        self.owner = owner
        self.exploded = False
        self.owner_left = False
        self.quad_damage = False
        
    def update(self, current_time):
        if current_time - self.start_time >= BOMB_TIMER:
            self.exploded = True
        return current_time - self.start_time >= BOMB_TIMER

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'start_time': self.start_time,
            'fire_power': self.fire_power,
            'quad_damage': self.quad_damage
        }

class Explosion:
    def __init__(self, cells, start_time, quad_damage=False, owner=None):
        self.cells = cells
        self.start_time = start_time
        self.quad_damage = quad_damage
        self.owner = owner

    def is_active(self, current_time):
        return current_time - self.start_time < EXPLOSION_DURATION

    def to_dict(self):
        return {
            'cells': self.cells,
            'start_time': self.start_time,
            'quad_damage': self.quad_damage,
            'owner_player_id': int(getattr(self.owner, "global_id", 0)) if self.owner is not None else None,
        }

class PowerUp:
    def __init__(self, x, y, type, spawn_time=0):
        self.x = x
        self.y = y
        self.type = type
        self.spawn_time = spawn_time

    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'type': self.type
        }



class Game:
    def __init__(self):
        self.board = generate_maze()
        self.grid_width = len(self.board[0])
        self.grid_height = len(self.board)
        self.bombs = []
        self.explosions = []
        self.recent_explosion_events = []
        self.big_explosion_over_threshold = False
        self.big_explosion_sound_at = []
        self.powerups = []
        self.game_start_time = get_ticks()
        self.players = []
        self.game_state = "game_prep"
        self.startup_start_time = get_ticks()
        self.current_time = self.startup_start_time
        self.clock = Clock()
        self.dt = 0
        
        self.is_fullscreen = False
        self.web_keys = set()  # Track keys pressed from web client
        self.screen = None  # Will be set by main game loop
        
        # Initialize event handling system
        self.frontend = None  # Will be set after frontend is available
        self.backend_logic = BackendGameLogic(self)
        self.friendly_fire = False
        # Team rules are opt-in; default gameplay remains free-for-all.
        self.team_mode_enabled = False
        self._cached_status = None
        self._status_queue = None  # Optional: for draining web client status before init_game
        
        self.starting_player_count = 0

        # Crushing walls feature variables
        self.crushing_walls_active = False
        self.crushing_walls_last_time = 0
        self.crushing_walls_pattern = []
        self.crushing_walls_index = 0

        # End-of-round resolution hold (delay final decision by 0.5s)
        self.endgame_hold_until = None
        # Post-win delayed transition scheduling
        self.post_win_transition_time = None
        self.post_win_target_state = None

        # Track death event times within a round (ms)
        self.death_events = []

        # Replay buffer: list of (timestamp_ms, snapshot_dict)
        self.replay_buffer = []
        self.last_replay_log_time = 0
        # Frozen replay segment captured at round end (list of (t, snapshot))
        self.replay_segment = None
        self.replay_segment_start_time = 0
        self.replay_segment_end_time = 0
        self.replay_loop_anchor_time = None
        self.kill_cam_clips = []
        self._pending_kill_cams = []
        
        # Game preparation screen state
        self.prep_num_players = NUM_PLAYERS
        self.prep_ai_count = DEFAULT_AI_COUNT if NUM_PLAYERS <= 1 else 0
        self.prep_ai_personalities = []
        self.prep_trophy_threshold = TROPHY_WIN_THRESHOLD
        self.prep_grid_offset = 0
        self.prep_player_names = player_names.copy()
        self.prep_player_colors = list(range(len(colors)))  # Store color indices instead of colors
        self.prep_player_teams = [i % 2 for i in range(len(player_names))]
        self.prep_controls = [controls.copy() for controls in controls_list]
        self._pad_prep_roster()
        
        # Lobby navigation system
        self.prep_cursor_row = 0  # Row in current section
        self.prep_cursor_col = max(0, self.prep_num_players - 1)  # Column in current section (0-based, so -1)
        self.prep_section = 'local_players'  # 'local_players' or 'start_game'
        self.prep_editing_name = False  # Whether we're editing a player name
        self.prep_name_edit_index = 0  # Which player name we're editing
        self.prep_web_player_names = {}  # Store web player names {global_id: name}
        self.prep_web_player_colors = {}  # Store web player colors {global_id: color_index}
        self.prep_ai_names = []
        self.leave_prompt_open = False
        self.leave_prompt_choice = "no"
        self.leave_prompt_paused_at = None
        
        # Track if prep screen has been shown
        self.prep_screen_completed = False
        
        # Create initial players based on current settings
        self.create_players()

    def _pad_prep_roster(self):
        while len(self.prep_player_names) < MAX_PLAYERS:
            self.prep_player_names.append(f"P{len(self.prep_player_names) + 1}")
        while len(self.prep_player_colors) < MAX_PLAYERS:
            self.prep_player_colors.append(len(self.prep_player_colors) % max(1, len(colors)))
        while len(self.prep_player_teams) < MAX_PLAYERS:
            self.prep_player_teams.append(len(self.prep_player_teams) % 2)

    def trophy_threshold(self):
        raw = getattr(self, "prep_trophy_threshold", TROPHY_WIN_THRESHOLD)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = TROPHY_WIN_THRESHOLD
        return max(MIN_TROPHY_WIN, min(MAX_TROPHY_WIN, value))

    def grid_offset(self):
        from bm_params import clamp_grid_offset
        return clamp_grid_offset(getattr(self, "prep_grid_offset", 0))

    def resolved_grid_size(self, player_count=None, is_boss_fight=False):
        from bm_params import get_grid_size
        if player_count is None:
            if self.game_state in ("startup", "game_prep"):
                player_count = len(self.get_all_players_info())
            else:
                player_count = len(getattr(self, "players", []) or [])
        return get_grid_size(
            player_count,
            is_boss_fight=is_boss_fight,
            offset=0 if is_boss_fight else self.grid_offset(),
        )

    def champion_player(self):
        """Player who reached the trophy goal, otherwise the last survivor."""
        threshold = self.trophy_threshold()
        reached = [p for p in self.players if int(getattr(p, "trophies", 0) or 0) >= threshold]
        if reached:
            return max(reached, key=lambda p: (int(p.trophies), 1 if p.alive else 0))
        return next((p for p in self.players if p.alive), None)

    def _clamp_prep_ai(self):
        humans = min(MAX_PLAYERS, max(1, int(self.prep_num_players)))
        if hasattr(self, "_cached_status") and self._cached_status:
            clients = self._cached_status.get("clients", {}) or {}
            remote = sum(1 for info in clients.values() if isinstance(info, dict) and info.get("registered"))
            humans = min(MAX_PLAYERS, humans + remote)
        remaining = max(0, MAX_PLAYERS - humans)
        self.prep_ai_count = min(max(0, int(getattr(self, "prep_ai_count", 0) or 0)), remaining)
    
    def get_all_players_info(self):
        """Get all players (local + client) information"""
        all_players = []
        global_player_id = 1
        
        # Add local players first
        for i in range(min(int(self.prep_num_players), MAX_PLAYERS)):
            player_name = self.prep_player_names[i % len(self.prep_player_names)]
            color_idx = self.prep_player_colors[i % len(self.prep_player_colors)]
            all_players.append({
                'id': global_player_id,
                'name': player_name,
                'color': color_idx,
                'team': self.prep_player_teams[i % len(self.prep_player_teams)],
                'type': 'local',
                'source': i,  # Index for local player data
                'controls': self.prep_controls[i % len(self.prep_controls)]
            })
            global_player_id += 1
        
        # Add client players
        if hasattr(self, '_cached_status') and self._cached_status:
            status_data = self._cached_status
            clients = status_data.get('clients', {})
            players = status_data.get('players', {})
            
            for client_id, client_info in clients.items():
                if len(all_players) >= MAX_PLAYERS:
                    break
                if client_info.get('registered', False):
                    client_players = client_info.get('players', [])
                    display_name = client_info.get('display_name')
                    for player_id in client_players:
                        if len(all_players) >= MAX_PLAYERS:
                            break
                        # Use stored name and color if available, otherwise use defaults
                        default_name = str(display_name).strip() if display_name else f"Client {client_id} P{player_id}"
                        stored_name = self.prep_web_player_names.get(global_player_id, default_name)
                        stored_color = self.prep_web_player_colors.get(global_player_id, global_player_id % len(colors))
                        
                        all_players.append({
                            'id': global_player_id,
                            'name': stored_name,
                            'color': stored_color,
                            'team': (global_player_id - 1) % 2,
                            'type': 'client',
                            'source': (client_id, player_id),  # Client and player ID
                            'controls': None  # Client players don't use local controls
                        })
                        global_player_id += 1

        used_names = {p['name'] for p in all_players}
        human_count = len(all_players)
        ai_count = min(int(getattr(self, "prep_ai_count", 0) or 0), MAX_PLAYERS - human_count)
        ai_names = self._ensure_ai_names(ai_count, used_names)
        ai_styles = list(getattr(self, "prep_ai_personalities", []) or [])
        for slot in range(max(0, ai_count)):
            all_players.append({
                'id': global_player_id,
                'name': ai_names[slot],
                'color': (human_count + slot) % len(colors),
                'team': (human_count + slot) % 2,
                'type': 'ai',
                'source': slot,
                'controls': None,
                'personality': ai_styles[slot] if slot < len(ai_styles) else None,
            })
            global_player_id += 1
        
        return all_players

    def _ensure_ai_names(self, count, used_names):
        wanted = max(0, int(count or 0))
        human_used = set(used_names or [])
        names = [name for name in (getattr(self, "prep_ai_names", []) or []) if name not in human_used]
        used = set(human_used) | set(names)
        while len(names) < wanted:
            candidate = None
            for _ in range(80):
                trial = f"{random.choice(AI_NAME_LEFT)} {random.choice(AI_NAME_RIGHT)}"
                if trial not in used:
                    candidate = trial
                    break
            if candidate is None:
                candidate = f"CPU {len(names) + 1}"
            names.append(candidate)
            used.add(candidate)
        self.prep_ai_names = names[:wanted]
        self._sync_ai_personalities(wanted)
        return self.prep_ai_names

    def _sync_ai_personalities(self, count):
        """Keep one style per AI slot. New slots are rolled; existing slots stay."""
        from ai_controller import AI_PERSONALITIES, roll_cpu_personality
        wanted = max(0, int(count or 0))
        styles = [
            style for style in (getattr(self, "prep_ai_personalities", None) or [])
            if style in AI_PERSONALITIES
        ]
        while len(styles) < wanted:
            styles.append(roll_cpu_personality())
        self.prep_ai_personalities = styles[:wanted]
        return self.prep_ai_personalities
    
    def create_players(self):
        """Create players based on current prep screen settings and client players"""
        previous_keys = {}
        if hasattr(self, 'web_keys_by_player') and self.web_keys_by_player:
            for player_obj, keys in list(self.web_keys_by_player.items()):
                previous_keys[self._player_persist_key(player_obj)] = set(keys)
        self.players = []
        all_players_info = self.get_all_players_info()
        
        for player_info in all_players_info:
            if player_info['type'] == 'local':
                p = Player(1, 1, 
                          colors[player_info['color'] % len(colors)], 
                          player_info['controls'], 
                          player_info['name'])
                p.is_local = True
                p.is_ai = False
                p.client_id = None
                p.client_player_id = None
            elif player_info['type'] == 'ai':
                p = Player(1, 1,
                          colors[player_info['color'] % len(colors)],
                          None,
                          player_info['name'])
                p.is_local = False
                p.is_ai = True
                p.ai_role = 'cpu'
                p.ai_slot = int(player_info['source'])
                from ai_controller import AI_PERSONALITIES, assign_random_personality
                style = player_info.get('personality')
                if style in AI_PERSONALITIES:
                    p.ai_personality = style
                else:
                    assign_random_personality(p)
                p.client_id = None
                p.client_player_id = None
            else:
                p = Player(1, 1, 
                          colors[player_info['color'] % len(colors)], 
                          None,
                          player_info['name'])
                p.is_local = False
                p.is_ai = False
                p.client_id = player_info['source'][0]
                p.client_player_id = player_info['source'][1]
            
            p.global_id = player_info['id']
            p.team = int(player_info.get('team', (p.global_id - 1) % 2))
            self.players.append(p)
        remapped = {}
        for player_obj in self.players:
            persisted = previous_keys.get(self._player_persist_key(player_obj))
            if persisted:
                remapped[player_obj] = persisted
        self.web_keys_by_player = remapped

    def _player_persist_key(self, player):
        if getattr(player, 'is_ai', False):
            return ('ai', int(getattr(player, 'ai_slot', getattr(player, 'global_id', 0))))
        if getattr(player, 'is_local', False):
            return ('local', int(getattr(player, 'global_id', 0)))
        return ('client', getattr(player, 'client_id', None), getattr(player, 'client_player_id', None))
    
    def _refresh_client_status(self):
        """Status refresh is now queue-driven in the host loop."""
        return self._cached_status
    
    def set_status_queue(self, queue):
        """Set the status queue for draining web client status (used for grid size)."""
        self._status_queue = queue

    def init_game(self):
        # Drain status queue to get latest web client count (local + web = total for grid size)
        if getattr(self, '_status_queue', None) is not None:
            try:
                import queue as queue_module
                while True:
                    msg = self._status_queue.get_nowait()
                    if isinstance(msg, dict) and msg.get("type") == "status":
                        self._cached_status = msg.get("status")
            except queue_module.Empty:
                pass
        # Refresh client status before creating players
        self._refresh_client_status()
        
        # Recreate players based on current prep settings and client players (local + web)
        # Accumulate round stats into totals, then preserve trophies and totals by player identity
        previous_players = self._accumulate_round_into_totals()
        self.create_players()
        if len(self.players) < 2:
            self.prep_ai_count = max(1, int(getattr(self, "prep_ai_count", 0) or 0))
            self.create_players()
        for p in self.players:
            key = self._player_persist_key(p)
            if key in previous_players:
                data = previous_players[key]
                p.trophies = data['trophies']
                p.total_walls_destroyed = data['total_walls_destroyed']
                p.total_players_killed = data['total_players_killed']
                p.total_powerups_collected = data['total_powerups_collected']
                p.total_quad_damage_collected = data['total_quad_damage_collected']
                p.total_cells_walked = data['total_cells_walked']
                saved_style = data.get('ai_personality')
                if saved_style and getattr(p, 'is_ai', False) and getattr(p, 'ai_role', '') != 'boss':
                    p.ai_personality = saved_style
                    from ai_controller import AI_PERSONALITIES
                    if saved_style in AI_PERSONALITIES:
                        slot = int(getattr(p, 'ai_slot', 0) or 0)
                        styles = list(getattr(self, 'prep_ai_personalities', []) or [])
                        while len(styles) <= slot:
                            styles.append(saved_style)
                        styles[slot] = saved_style
                        self.prep_ai_personalities = styles
        
        num_players = len(self.players)
        self.starting_player_count = num_players
        grid_size = self.resolved_grid_size(num_players)
        self.board = generate_maze(grid_size, grid_size)
        self._set_arena_size(grid_size)
        self.bombs = []
        self.explosions = []
        self.recent_explosion_events = []
        self.big_explosion_over_threshold = False
        self.big_explosion_sound_at = []
        self.powerups = []
        self.endgame_hold_until = None
        self.death_events = []
        self.post_win_transition_time = None
        self.post_win_target_state = None
        self.replay_buffer = []
        self.last_replay_log_time = 0
        # Clear any previous replay segment/state
        self.replay_segment = None
        self.replay_segment_start_time = 0
        self.replay_segment_end_time = 0
        self.replay_loop_anchor_time = None
        self.replay_focus_player = None
        self.replay_end_time = None
        self.replay_start_time = None
        self.kill_cam_clips = []
        self._pending_kill_cams = []
        # Mark round start to compute relative death times for display
        self.current_time = get_ticks()
        self.round_start_time = self.current_time
        for p in self.players:
            p.death_time_ms = None
            p.death_time_rel_ms = None
        
        gw, gh = self.grid_width, self.grid_height
        random.shuffle(self.players)
        for player, (sx, sy, offsets) in zip(self.players, spawn_slots(gw, gh, len(self.players))):
            player.start_grid_x, player.start_grid_y = sx, sy
            clear_safe_zone(self.board, player.start_grid_x, player.start_grid_y, offsets)
            player.reset()
            # Apply initial gameplay params (use defaults)
            player.bomb_capacity = 1
            player.fire_power = 1
            player.speed = PLAYER_SPEED
        self.game_start_time = self.current_time + 2000  # Add a 2-second freeze time
        
        # Reset crushing walls state
        self.crushing_walls_active = False
        self.crushing_walls_last_time = 0
        self.crushing_walls_pattern = []
        self.crushing_walls_index = 0

    def _accumulate_round_into_totals(self):
        """Fold this round's counters into series totals. Returns persist snapshot."""
        previous_players = {}
        for p in getattr(self, 'players', []):
            p.total_walls_destroyed = getattr(p, 'total_walls_destroyed', 0) + p.walls_destroyed
            p.total_players_killed = getattr(p, 'total_players_killed', 0) + p.players_killed
            p.total_powerups_collected = getattr(p, 'total_powerups_collected', 0) + p.powerups_collected
            p.total_quad_damage_collected = getattr(p, 'total_quad_damage_collected', 0) + p.quad_damage_collected
            p.total_cells_walked = getattr(p, 'total_cells_walked', 0) + p.cells_walked
            key = self._player_persist_key(p)
            previous_players[key] = {
                'trophies': p.trophies,
                'total_walls_destroyed': p.total_walls_destroyed,
                'total_players_killed': p.total_players_killed,
                'total_powerups_collected': p.total_powerups_collected,
                'total_quad_damage_collected': p.total_quad_damage_collected,
                'total_cells_walked': p.total_cells_walked,
                'ai_personality': getattr(p, 'ai_personality', None) or None,
            }
        return previous_players

    def _set_arena_size(self, grid_size):
        """Keep sim grid and host draw surface on the same odd tile count."""
        self.grid_width = int(grid_size)
        self.grid_height = int(grid_size)
        if self.screen:
            self.screen.surface = pygame.Surface((int(grid_size) * CELL_SIZE, int(grid_size) * CELL_SIZE))

    def init_boss_fight(self, champion):
        """Set up 1v1 boss fight: champion vs AI. Keeps champion, adds boosted AI boss."""
        from bm_params import (
            BOSS_SPEED_MULTIPLIER, BOSS_START_FIRE_POWER, BOSS_START_BOMB_CAPACITY,
            BOSS_NAME, BOSS_COLOR, BOSS_EXTRA_LIVES, GRID_SIZE_BOSS, get_grid_size
        )
        self._accumulate_round_into_totals()
        grid_size = get_grid_size(player_count=2, is_boss_fight=True) or GRID_SIZE_BOSS
        self.board = generate_maze(grid_size, grid_size)
        self._set_arena_size(grid_size)
        champion.start_grid_x, champion.start_grid_y = 1, 1
        boss_grid_x, boss_grid_y = grid_size - 2, grid_size - 2

        boss = Player(boss_grid_x, boss_grid_y, BOSS_COLOR, None, BOSS_NAME)
        boss.is_local = False
        boss.is_ai = True
        boss.ai_role = "boss"
        boss.ai_personality = "boss"
        boss.ai_slot = 0
        boss.client_id = None
        boss.client_player_id = None
        boss.global_id = 999
        boss.team = 1
        boss.boss_lives_remaining = BOSS_EXTRA_LIVES
        boss.bomb_capacity = BOSS_START_BOMB_CAPACITY
        boss.fire_power = BOSS_START_FIRE_POWER
        boss.speed = int(PLAYER_SPEED * BOSS_SPEED_MULTIPLIER)

        self.players = [champion, boss]
        self.starting_player_count = 2
        self.bombs = []
        self.explosions = []
        self.recent_explosion_events = []
        self.big_explosion_over_threshold = False
        self.big_explosion_sound_at = []
        self.powerups = []
        self.endgame_hold_until = None
        self.death_events = []
        self.post_win_transition_time = None
        self.post_win_target_state = None
        self.replay_buffer = []
        self.last_replay_log_time = 0
        self.replay_segment = None
        self.replay_segment_start_time = 0
        self.replay_segment_end_time = 0
        self.replay_loop_anchor_time = None
        self.replay_focus_player = None
        self.replay_end_time = None
        self.replay_start_time = None
        self.kill_cam_clips = []
        self._pending_kill_cams = []
        self.current_time = get_ticks()
        self.round_start_time = self.current_time

        corner_patterns = {
            (1, 1): [(0, 0), (1, 0), (0, 1)],
            (boss_grid_x, boss_grid_y): [(0, 0), (-1, 0), (0, -1)],
        }
        for p in self.players:
            p.death_time_ms = None
            p.death_time_rel_ms = None
            offsets = corner_patterns.get((p.start_grid_x, p.start_grid_y), [(0, 0), (1, 0), (0, 1)])
            clear_safe_zone(self.board, p.start_grid_x, p.start_grid_y, offsets)
            p.reset()
            if p is boss:
                p.bomb_capacity = BOSS_START_BOMB_CAPACITY
                p.fire_power = BOSS_START_FIRE_POWER
                p.speed = int(PLAYER_SPEED * BOSS_SPEED_MULTIPLIER)
                p.boss_lives_remaining = BOSS_EXTRA_LIVES
                p.ai_role = "boss"
                p.ai_personality = "boss"

        self.game_start_time = self.current_time + 2000
        self.crushing_walls_active = False
        self.crushing_walls_last_time = 0
        self.crushing_walls_pattern = []
        self.crushing_walls_index = 0

    def generate_clockwise_pattern(self):
        """Generate a clockwise traversal pattern starting from top-left corner, 
        but skip cells that are already indestructible walls"""
        pattern = []
        visited = set()
        gw, gh = self.grid_width, self.grid_height
        # Start from the outermost layer and work inward
        for layer in range(min(gw, gh) // 2):
            # Top row (left to right)
            for x in range(layer, gw - layer):
                if (x, layer) not in visited and self.board[layer][x] != INDESTRUCTIBLE:
                    pattern.append((x, layer))
                    visited.add((x, layer))
            
            # Right column (top to bottom, skip top corner)
            for y in range(layer + 1, gh - layer):
                if (gw - 1 - layer, y) not in visited and self.board[y][gw - 1 - layer] != INDESTRUCTIBLE:
                    pattern.append((gw - 1 - layer, y))
                    visited.add((gw - 1 - layer, y))
            
            # Bottom row (right to left, skip right corner)
            if gh - 1 - layer > layer:
                for x in range(gw - 2 - layer, layer - 1, -1):
                    if (x, gh - 1 - layer) not in visited and self.board[gh - 1 - layer][x] != INDESTRUCTIBLE:
                        pattern.append((x, gh - 1 - layer))
                        visited.add((x, gh - 1 - layer))
            
            # Left column (bottom to top, skip both corners)
            if gw - 1 - layer > layer:
                for y in range(gh - 2 - layer, layer, -1):
                    if (layer, y) not in visited and self.board[y][layer] != INDESTRUCTIBLE:
                        pattern.append((layer, y))
                        visited.add((layer, y))
        
        return pattern

    def reset_trophies(self):
        """Reset trophies and all match stats when leaving the champion screen."""
        for p in self.players:
            p.trophies = 0
            p.total_walls_destroyed = 0
            p.total_players_killed = 0
            p.total_powerups_collected = 0
            p.total_quad_damage_collected = 0
            p.total_cells_walked = 0
            p.walls_destroyed = 0
            p.players_killed = 0
            p.powerups_collected = 0
            p.quad_damage_collected = 0
            p.cells_walked = 0

    def result_prompt(self):
        if self.game_state == "win":
            return "Enter: next round   ·   Esc: leave game"
        if self.game_state == "champion":
            return f"Enter: fight {BOSS_NAME}   ·   R: reset trophies   ·   Esc: leave game"
        if self.game_state == "boss_result":
            return "Enter or R: reset trophies from zero   ·   Esc: leave game"
        return ""

    def reset_series_and_start(self):
        """Clear trophies/stats and start a fresh series from the lobby roster."""
        self.reset_trophies()
        self.boss_fight_winner = None
        self.boss_fight_champion = None
        self.init_game()
        self.game_state = "get_ready"
        return True

    def continue_from_champion(self):
        """Trophy winner fights BomberMarv 1v1, including when that winner is AI."""
        champion = self.champion_player()
        if champion is None:
            return self.reset_series_and_start()
        self.boss_fight_champion = champion
        self.init_boss_fight(champion)
        self.game_state = "boss_fight"
        return True

    def continue_from_intermission(self):
        if getattr(self, "leave_prompt_open", False):
            return False
        if self.game_state == "win":
            self.init_game()
            self.game_state = "get_ready"
            return True
        if self.game_state == "champion":
            return self.continue_from_champion()
        if self.game_state == "boss_result":
            return self.reset_series_and_start()
        return False

    def leave_prompt_states(self):
        return {"playing", "get_ready", "boss_fight", "win", "champion", "boss_result"}

    def leave_prompt_title(self):
        if self.game_state in ("win", "champion", "boss_result"):
            return "Leave game?"
        return "Do you want to cancel the game session?"

    def open_leave_prompt(self):
        if self.game_state not in self.leave_prompt_states():
            return False
        if not getattr(self, "leave_prompt_open", False):
            self.leave_prompt_paused_at = int(self.current_time or get_ticks())
        self.leave_prompt_open = True
        self.leave_prompt_choice = "no"
        return True

    def close_leave_prompt(self):
        if not getattr(self, "leave_prompt_open", False):
            return False
        now = get_ticks()
        paused_at = getattr(self, "leave_prompt_paused_at", None)
        if paused_at is None:
            paused_at = int(self.current_time or now)
        if self.game_state in ("playing", "get_ready", "boss_fight"):
            self.current_time = int(paused_at)
            self._shift_game_clocks(now - int(paused_at))
        self.leave_prompt_open = False
        self.leave_prompt_choice = "no"
        self.leave_prompt_paused_at = None
        return True

    def toggle_leave_prompt_choice(self):
        if not getattr(self, "leave_prompt_open", False):
            return False
        self.leave_prompt_choice = "yes" if self.leave_prompt_choice == "no" else "no"
        return True

    def confirm_leave_prompt(self):
        if not getattr(self, "leave_prompt_open", False):
            return False
        if self.leave_prompt_choice == "yes":
            return self.return_to_lobby()
        return self.close_leave_prompt()

    def return_to_lobby(self):
        """Abort the session and return to the lobby with the current roster."""
        self.leave_prompt_open = False
        self.leave_prompt_choice = "no"
        self.reset_trophies()
        self.boss_fight_winner = None
        self.boss_fight_champion = None
        self.bombs = []
        self.explosions = []
        self.powerups = []
        self.kill_cam_clips = []
        self._pending_kill_cams = []
        self.replay_buffer = []
        self.replay_segment = None
        self.replay_loop_anchor_time = None
        self.endgame_hold_until = None
        self.post_win_target_state = None
        self.post_win_transition_time = None
        self.crushing_walls_active = False
        self.prep_screen_completed = False
        self.leave_prompt_paused_at = None
        self.game_state = "game_prep"
        self.create_players()
        return True

    def _shift_game_clocks(self, delta_ms):
        delta = int(delta_ms or 0)
        if delta <= 0:
            return
        self.current_time = int(self.current_time) + delta
        for attr in (
            "game_start_time",
            "round_start_time",
            "startup_start_time",
            "crushing_walls_last_time",
            "last_replay_log_time",
            "replay_loop_anchor_time",
            "endgame_hold_until",
            "post_win_transition_time",
        ):
            value = getattr(self, attr, None)
            if isinstance(value, (int, float)):
                setattr(self, attr, int(value) + delta)
        for bomb in getattr(self, "bombs", []) or []:
            bomb.start_time = int(bomb.start_time) + delta
        for explosion in getattr(self, "explosions", []) or []:
            explosion.start_time = int(explosion.start_time) + delta
        for powerup in getattr(self, "powerups", []) or []:
            spawn = getattr(powerup, "spawn_time", None)
            if isinstance(spawn, (int, float)):
                powerup.spawn_time = int(spawn) + delta
        sounds_at = getattr(self, "big_explosion_sound_at", None)
        if sounds_at:
            self.big_explosion_sound_at = [int(t) + delta for t in sounds_at]
        for player in getattr(self, "players", []) or []:
            for attr in ("quad_damage_start_time", "boss_shield_until", "pickup_message_end_time"):
                value = getattr(player, attr, None)
                if isinstance(value, (int, float)) and value:
                    setattr(player, attr, int(value) + delta)
        if getattr(self, "replay_buffer", None):
            self.replay_buffer = [(int(t) + delta, snap) for t, snap in self.replay_buffer]

    def count_destroyable_cells(self):
        """Count the number of destroyable cells on the board"""
        count = 0
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                if self.board[y][x] == DESTRUCTIBLE:
                    count += 1
        return count

    def count_empty_cells(self):
        """Count the number of empty (walkable) cells on the board."""
        count = 0
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                if self.board[y][x] == EMPTY:
                    count += 1
        return count

    def find_nearest_safe_position(self, player, avoid_cell_x, avoid_cell_y):
        """Find the nearest safe position for a player, avoiding a specific cell"""
        player_grid_x, player_grid_y = player.get_grid_pos()
        
        # Search in expanding rings around the player's current position
        gw, gh = self.grid_width, self.grid_height
        for radius in range(1, max(gw, gh)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    # Only check cells on the perimeter of the current radius
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                        
                    new_grid_x = player_grid_x + dx
                    new_grid_y = player_grid_y + dy
                    
                    # Skip if out of bounds
                    if (new_grid_x < 0 or new_grid_x >= gw or 
                        new_grid_y < 0 or new_grid_y >= gh):
                        continue
                    
                    # Skip if this is the cell we're trying to avoid
                    if new_grid_x == avoid_cell_x and new_grid_y == avoid_cell_y:
                        continue
                    
                    # Skip if this cell has a wall
                    if self.board[new_grid_y][new_grid_x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                        continue
                    
                    # Test if the player can be positioned in this cell
                    test_pos = np.array([
                        new_grid_x * CELL_SIZE + CELL_SIZE // 2,
                        new_grid_y * CELL_SIZE + CELL_SIZE // 2
                    ], dtype=np.float64)
                    
                    # Temporarily set player position to test
                    original_pos = player.pos.copy()
                    player.pos = test_pos
                    
                    # Check if this position is valid (no collisions)
                    if not (player.collides_with_walls(self.board) or player.collides_with_bombs(self.bombs, original_pos)):
                        # Found a valid position, keep it
                        return test_pos
                    
                    # Restore original position for next test
                    player.pos = original_pos
        
        # If no safe position found, return current position
        return player.pos.copy()

    def push_player_away_from_cell(self, player, cell_x, cell_y):
        """Push a player away from a cell that's about to become a wall"""
        if not player.alive:
            return
            
        player_grid_x, player_grid_y = player.get_grid_pos()
        if player_grid_x != cell_x or player_grid_y != cell_y:
            return  # Player is not in this cell
        
        # Find the nearest safe position
        safe_pos = self.find_nearest_safe_position(player, cell_x, cell_y)
        
        # Move the player to the safe position
        player.pos = safe_pos

    def handle_crushing_walls(self):
        """Handle the crushing walls feature"""
        alive_players = [p for p in self.players if p.alive]
        
        # Boss fight: 50% slower growth, start 1 minute later
        if self.game_state == "boss_fight":
            from bm_params import BOSS_CRUSHING_WALLS_DELAY, BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS
            crushing_delay = BOSS_CRUSHING_WALLS_DELAY
            crushing_min_destroyable = CRUSHING_WALLS_MIN_DESTROYABLE
            crushing_max_alive = CRUSHING_WALLS_MAX_ALIVE
            growth_interval_ms = BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS
        else:
            crushing_delay = CRUSHING_WALLS_DELAY
            if int(getattr(self, "starting_player_count", 0) or 0) == 2:
                crushing_delay = CRUSHING_WALLS_2P_DELAY
            crushing_min_destroyable = CRUSHING_WALLS_MIN_DESTROYABLE
            crushing_max_alive = CRUSHING_WALLS_MAX_ALIVE
            growth_interval_ms = CRUSHING_WALLS_GROWTH_INTERVAL_MS
        crushing_delay = max(int(crushing_delay), int(CRUSHING_WALLS_MIN_START_S))
        
        if len(alive_players) <= crushing_max_alive and \
           (self.current_time - self.game_start_time) >= crushing_delay * 1000 and \
           self.count_destroyable_cells() < crushing_min_destroyable:
            
            if not self.crushing_walls_active:
                # Initialize crushing walls
                self.crushing_walls_active = True
                self.crushing_walls_pattern = self.generate_clockwise_pattern()
                self.crushing_walls_index = 0
                self.crushing_walls_last_time = self.current_time
                return
            
            # Add new walls at configured interval
            if self.current_time - self.crushing_walls_last_time >= growth_interval_ms:
                if self.crushing_walls_index < len(self.crushing_walls_pattern):
                    x, y = self.crushing_walls_pattern[self.crushing_walls_index]
                    
                    # Check if there's a player in this cell and push them away BEFORE placing the wall
                    for player in alive_players:
                        self.push_player_away_from_cell(player, x, y)
                    
                    # Double-check: make sure no players are still in this cell after pushing
                    players_still_in_cell = []
                    for player in alive_players:
                        if player.get_grid_pos() == (x, y):
                            players_still_in_cell.append(player)
                    
                    # If players are still in the cell, try to move them to any adjacent empty cell
                    for player in players_still_in_cell:
                        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:  # Up, Right, Down, Left
                            adj_x, adj_y = x + dx, y + dy
                            if (0 <= adj_x < self.grid_width and 0 <= adj_y < self.grid_height and 
                                self.board[adj_y][adj_x] == EMPTY):
                                # Move player to adjacent empty cell
                                player.pos = np.array([
                                    adj_x * CELL_SIZE + CELL_SIZE // 2,
                                    adj_y * CELL_SIZE + CELL_SIZE // 2
                                ], dtype=np.float64)
                                break
                    
                    # Replace whatever is in the cell with an indestructible wall
                    self.board[y][x] = INDESTRUCTIBLE
                    
                    # Remove any powerups in this cell
                    self.powerups = [pu for pu in self.powerups if not (pu.x == x and pu.y == y)]
                    
                    # Remove any bombs in this cell (they explode immediately)
                    crush_explosions = []
                    for bomb in self.bombs[:]:
                        if bomb.x == x and bomb.y == y:
                            exp = Explosion(self.get_explosion_cells(bomb), self.current_time, bomb.quad_damage, owner=bomb.owner)
                            self.explosions.append(exp)
                            crush_explosions.append(exp)
                            bomb.owner.active_bombs -= 1
                            self.bombs.remove(bomb)
                    self._register_new_explosions(crush_explosions)
                    
                    self.crushing_walls_index += 1
                    self.crushing_walls_last_time = self.current_time

                    # If walls filled all empty space, all remaining players die (draw)
                    if self.count_empty_cells() == 0:
                        for player in alive_players:
                            if player.alive:
                                player.alive = False
                                player.death_animation_time = 1000
                                self.death_events.append(self.current_time)
                                player.death_time_ms = self.current_time
                                if hasattr(self, 'round_start_time') and self.round_start_time:
                                    player.death_time_rel_ms = max(0, self.current_time - self.round_start_time)
                                player.fire_power_at_death = player.fire_power
                                player.bomb_capacity_at_death = player.bomb_capacity
                                death_sound.play()
                                self._queue_kill_cam(player)

    def get_explosion_cells(self, bomb):
        return planned_blast_cells(
            bomb.x,
            bomb.y,
            bomb.fire_power,
            self.board,
            self.grid_width,
            self.grid_height,
            max_range=bomb.fire_power,
            empty=EMPTY,
            indestructible=INDESTRUCTIBLE,
            destructible=DESTRUCTIBLE,
        )

    def _detonate_bomb(self, bomb):
        """Remove a live bomb and return its explosion. Safe if already removed."""
        if bomb not in self.bombs:
            return None
        exp = Explosion(self.get_explosion_cells(bomb), self.current_time, bomb.quad_damage, owner=bomb.owner)
        if bomb.owner is not None:
            bomb.owner.active_bombs -= 1
        self.bombs.remove(bomb)
        return exp

    def _explode_with_chain(self, initial_bombs):
        """Detonate the given bombs and any bombs their blasts chain into."""
        triggered = []
        chain_cells = set()
        for bomb in list(initial_bombs):
            exp = self._detonate_bomb(bomb)
            if exp is None:
                continue
            triggered.append(exp)
            chain_cells.update(exp.cells)
        chain_triggered = True
        while chain_triggered:
            chain_triggered = False
            for bomb in self.bombs[:]:
                if (bomb.x, bomb.y) in chain_cells:
                    exp = self._detonate_bomb(bomb)
                    if exp is None:
                        continue
                    triggered.append(exp)
                    for cell in exp.cells:
                        chain_cells.add(cell)
                    chain_triggered = True
        if triggered:
            self.explosions.extend(triggered)
            self._register_new_explosions(triggered)
        return triggered

    def _register_new_explosions(self, explosions):
        """Track new blasts and play mocny_stral once unique tiles reach the window threshold."""
        if not explosions:
            return
        self.recent_explosion_events = prune_explosion_events(
            self.recent_explosion_events, self.current_time, BIG_EXPLOSION_WINDOW_MS
        )
        aged_count = count_unique_explosion_tiles(
            self.recent_explosion_events, self.current_time, BIG_EXPLOSION_WINDOW_MS
        )
        self.big_explosion_over_threshold = aged_count >= BIG_EXPLOSION_TILE_THRESHOLD
        for exp in explosions:
            cells = tuple((int(cell[0]), int(cell[1])) for cell in exp.cells)
            self.recent_explosion_events.append((exp.start_time, cells))
            if exp.quad_damage:
                explosion_sound_qd.play()
            else:
                explosion_sound.play()
        tile_count = count_unique_explosion_tiles(
            self.recent_explosion_events, self.current_time, BIG_EXPLOSION_WINDOW_MS
        )
        if crossed_big_explosion_threshold(
            self.big_explosion_over_threshold, tile_count, BIG_EXPLOSION_TILE_THRESHOLD
        ):
            self.big_explosion_sound_at.append(self.current_time + BIG_EXPLOSION_SOUND_DELAY_MS)
        self.big_explosion_over_threshold = tile_count >= BIG_EXPLOSION_TILE_THRESHOLD

    def _play_due_big_explosion_sounds(self):
        if not self.big_explosion_sound_at:
            return
        due, pending = [], []
        for play_at in self.big_explosion_sound_at:
            (due if play_at <= self.current_time else pending).append(play_at)
        for _ in due:
            mocny_stral_sound.play()
        self.big_explosion_sound_at = pending
    
    def handle_explosions(self):
        
        for explosion in self.explosions[:]:
            active_cells = compute_explosion_active_cells(explosion, self.current_time, EXPLOSION_DURATION)
            # Only check for kills when explosion arms are active
            if active_cells:
                hit_radius = explosion_player_radius(CELL_SIZE, EXPLOSION_PLAYER_HIT_SCALE)

                # Check for player deaths only in currently active cells
                for player in self.players:
                    if player.alive:
                        if getattr(player, 'boss_shield_until', 0) > self.current_time:
                            continue
                        if (
                            self.team_mode_enabled
                            and not self.friendly_fire
                            and explosion.owner is not None
                            and getattr(explosion.owner, "team", None) == getattr(player, "team", None)
                            and explosion.owner is not player
                        ):
                            continue
                        for cell in active_cells:
                            cell_x, cell_y = cell
                            explosion_rect = explosion_cell_rect(
                                cell_x,
                                cell_y,
                                CELL_SIZE,
                                EXPLOSION_COLLISION_SCALE,
                                clip_outward=explosion_tip_clip(
                                    explosion.cells[0][0],
                                    explosion.cells[0][1],
                                    cell_x,
                                    cell_y,
                                    active_cells,
                                ),
                            )
                            if circle_rect_collision((player.pos[0], player.pos[1]), hit_radius, explosion_rect):
                                if getattr(player, 'is_ai', False) and getattr(player, 'boss_lives_remaining', 0) > 0:
                                    player.boss_lives_remaining -= 1
                                    player.boss_shield_until = self.current_time + BOSS_SHIELD_DURATION_MS
                                    player.alive = True
                                    player.death_animation_time = 0
                                    player._bomb_key_held = False
                                    break
                                player.alive = False
                                player.death_animation_time = 1000  # 1 second death animation
                                # Record death time for potential tie detection
                                self.death_events.append(self.current_time)
                                player.death_time_ms = self.current_time
                                # Relative to round start
                                if hasattr(self, 'round_start_time') and self.round_start_time:
                                    player.death_time_rel_ms = max(0, self.current_time - self.round_start_time)
                                # Snapshot stats at death
                                player.fire_power_at_death = player.fire_power
                                player.bomb_capacity_at_death = player.bomb_capacity
                                if explosion.owner is not None and explosion.owner is not player:
                                    explosion.owner.players_killed += 1
                                # Spawn a death bonus powerup where the player died
                                gx, gy = player.get_grid_pos()
                                death_cell_bombs = [bomb for bomb in self.bombs if bomb.x == gx and bomb.y == gy]
                                if death_cell_bombs:
                                    self._explode_with_chain(death_cell_bombs)
                                self.powerups.append(PowerUp(gx, gy, "death_bonus", spawn_time=self.current_time))
                                death_sound.play()
                                self._queue_kill_cam(player)
                                break
            
            # Clear soft walls as soon as the blast arm covers them
            for (x, y) in active_cells:
                if self.board[y][x] == DESTRUCTIBLE:
                    self.board[y][x] = EMPTY
                    if explosion.owner is not None:
                        explosion.owner.walls_destroyed += 1
                    if random.random() < POWERUP_PROBABILITY:
                        pu_type = random.choice(["bomb", "fire"])
                        self.powerups.append(PowerUp(x, y, pu_type, spawn_time=explosion.start_time))

            # Remove explosion when it ends
            if not explosion.is_active(self.current_time):
                for (x, y) in explosion.cells:
                    if self.board[y][x] == DESTRUCTIBLE:
                        self.board[y][x] = EMPTY
                        if explosion.owner is not None:
                            explosion.owner.walls_destroyed += 1
                        if random.random() < POWERUP_PROBABILITY:
                            pu_type = random.choice(["bomb", "fire"])
                            self.powerups.append(PowerUp(x, y, pu_type, spawn_time=explosion.start_time))
                for pu in self.powerups[:]:
                    if pu.spawn_time < explosion.start_time and (pu.x, pu.y) in explosion.cells:
                        self.powerups.remove(pu)
                self.explosions.remove(explosion)
                    
    def place_quad_damage_powerup(self):        
        # Use parameters from bm_params
        from bm_params import QUAD_DAMAGE_DELAY, QUAD_DAMAGE_PROBABILITY
        
        # Check if enough time has passed since game start
        if (self.current_time - self.game_start_time) >= QUAD_DAMAGE_DELAY * 1000:
            # Only place if no quad damage powerup already exists
            if not any(pu.type == "quad_damage" for pu in self.powerups):
                # Find empty cells
                empty_cells = [(x, y) for y in range(self.grid_height) for x in range(self.grid_width) if self.board[y][x] == EMPTY]
                if empty_cells and random.random() < QUAD_DAMAGE_PROBABILITY:
                    x, y = random.choice(empty_cells)
                    self.powerups.append(PowerUp(x, y, "quad_damage"))
                                
    def log_replay_if_due(self):
        """Capture a replay snapshot without sleeping (host loop owns timing)."""
        if (
            self.game_state in ("get_ready", "playing", "win", "boss_fight", "champion", "boss_result")
            and self.current_time - getattr(self, 'last_replay_log_time', 0) >= REPLAY_LOG_INTERVAL_MS
        ):
            self._log_replay_snapshot()
            self.last_replay_log_time = self.current_time
        self._flush_kill_cams()

    def _queue_kill_cam(self, player):
        pending = getattr(self, "_pending_kill_cams", None)
        if pending is None:
            self._pending_kill_cams = []
            pending = self._pending_kill_cams
        pending.append({"name": player.name, "death_time": int(self.current_time)})

    def _flush_kill_cams(self, force=False):
        pending = list(getattr(self, "_pending_kill_cams", None) or [])
        if not pending:
            return
        clips = list(getattr(self, "kill_cam_clips", None) or [])
        still = []
        for item in pending:
            clip = freeze_kill_cam_clip(
                self.replay_buffer,
                item["name"],
                item["death_time"],
                self.current_time,
                REPLAY_KILLCAM_PRE_MS,
                REPLAY_KILLCAM_POST_MS,
            )
            ready = force or self.current_time >= item["death_time"] + REPLAY_KILLCAM_POST_MS
            if ready and clip:
                clips.append(clip)
            elif not ready:
                still.append(item)
        clips.sort(key=lambda c: (c["death_time"], c["name"]))
        self.kill_cam_clips = clips
        self._pending_kill_cams = still

    def simulate(self, dt_ms, now_ms=None):
        """Advance one host sim step. The caller owns the clock; this does not sleep."""
        if getattr(self, "leave_prompt_open", False):
            frozen = getattr(self, "leave_prompt_paused_at", None)
            if frozen is not None:
                self.current_time = int(frozen)
            return None
        self.dt = int(dt_ms)
        self.current_time = int(now_ms) if now_ms is not None else get_ticks()
        countdown_second = None
        if self.game_state == "get_ready":
            remaining_ms = max(0, int(self.game_start_time - self.current_time))
            countdown_second = (remaining_ms + 999) // 1000
            if self.current_time >= self.game_start_time:
                self.game_state = "playing"
        elif self.game_state == "boss_fight":
            remaining_ms = max(0, int(self.game_start_time - self.current_time))
            countdown_second = (remaining_ms + 999) // 1000
            if self.current_time >= self.game_start_time:
                self.update()
        elif self.game_state == "playing":
            self.update()
        self.log_replay_if_due()
        return countdown_second

    def tick(self, dt_ms=None, now_ms=None):
        """Compatibility wrapper around simulate(). Do not call clock.tick() here (it sleeps)."""
        step = self.dt if dt_ms is None else dt_ms
        return self.simulate(step, now_ms=now_ms)
                    
    def handle_window_events(self):
        """Handle window events using the new frontend/backend separation"""
        if self.frontend is None:
            self.frontend = FrontendManager(self)
        
        self.frontend.process_events()
    
    def set_frontend(self, frontend):
        """Set the frontend reference"""
        self.frontend = frontend
        self.screen = frontend.screen

    def get_ticks(self):
        from timing_abstraction import get_ticks as ticks_now
        return ticks_now()

    def _prep_last_player_row(self):
        return PREP_ROW_PLAYERS + len(self.get_all_players_info()) - 1

    def _sync_prep_cursor_col(self):
        if self.prep_cursor_row == PREP_ROW_LOCAL:
            self.prep_cursor_col = max(0, min(MAX_PLAYERS - 1, self.prep_num_players - 1))
        elif self.prep_cursor_row == PREP_ROW_AI:
            self.prep_cursor_col = max(0, min(MAX_PLAYERS - 1, int(getattr(self, "prep_ai_count", 0) or 0)))
        elif self.prep_cursor_row == PREP_ROW_TROPHY:
            self.prep_cursor_col = max(0, min(MAX_TROPHY_WIN - 1, self.trophy_threshold() - 1))
        elif self.prep_cursor_row == PREP_ROW_ARENA:
            from bm_params import GRID_SIZE_OFFSETS, grid_offset_index
            self.prep_cursor_col = max(0, min(len(GRID_SIZE_OFFSETS) - 1, grid_offset_index(self.grid_offset())))

    def _log_replay_snapshot(self):
        """Capture a lightweight snapshot of the current game state for replay."""
        snapshot = build_replay_snapshot(self)
        self.replay_buffer.append((self.current_time, snapshot))
        # Trim to buffer window
        min_time = self.current_time - REPLAY_BUFFER_MS
        while self.replay_buffer and self.replay_buffer[0][0] < min_time:
            self.replay_buffer.pop(0)
    
    def handle_prep_key_event(self, event):
        """Handle key events for game lobby navigation"""
        last_player_row = self._prep_last_player_row()
        # Switch between sections
        if event.key == Keys.TAB:
            self.prep_section = 'start_game' if self.prep_section == 'local_players' else 'local_players'
            self.prep_cursor_row = 0
            self._sync_prep_cursor_col()
            self.prep_editing_name = False
            return
        
        # Vertical navigation between sections
        if event.key == Keys.UP:
            if self.prep_section == 'start_game':
                self.prep_section = 'local_players'
                self.prep_cursor_row = last_player_row
                self._sync_prep_cursor_col()
            elif self.prep_section == 'local_players':
                if self.prep_cursor_row > 0:
                    self.prep_cursor_row -= 1
                    self._sync_prep_cursor_col()
            return
        
        if event.key == Keys.DOWN:
            if self.prep_section == 'local_players':
                if self.prep_cursor_row < last_player_row:
                    self.prep_cursor_row += 1
                    self._sync_prep_cursor_col()
                else:
                    self.prep_section = 'start_game'
                    self.prep_cursor_row = 0
                    self.prep_cursor_col = 0
            return
        
        if self.prep_section == 'local_players':
            if self.prep_cursor_row == PREP_ROW_LOCAL:
                if event.key == Keys.LEFT:
                    if self.prep_cursor_col > 0:
                        self.prep_cursor_col -= 1
                elif event.key == Keys.RIGHT:
                    if self.prep_cursor_col < MAX_PLAYERS - 1:
                        self.prep_cursor_col += 1
                elif event.key == Keys.ENTER:
                    self.prep_num_players = self.prep_cursor_col + 1
                    self._clamp_prep_ai()
                    self.create_players()
            elif self.prep_cursor_row == PREP_ROW_AI:
                if event.key == Keys.LEFT:
                    if self.prep_cursor_col > 0:
                        self.prep_cursor_col -= 1
                elif event.key == Keys.RIGHT:
                    if self.prep_cursor_col < MAX_PLAYERS - 1:
                        self.prep_cursor_col += 1
                elif event.key == Keys.ENTER:
                    self.prep_ai_count = self.prep_cursor_col
                    self._clamp_prep_ai()
                    self.prep_cursor_col = int(self.prep_ai_count)
                    self.create_players()
            elif self.prep_cursor_row == PREP_ROW_TROPHY:
                if event.key == Keys.LEFT:
                    if self.prep_cursor_col > 0:
                        self.prep_cursor_col -= 1
                elif event.key == Keys.RIGHT:
                    if self.prep_cursor_col < MAX_TROPHY_WIN - 1:
                        self.prep_cursor_col += 1
                elif event.key == Keys.ENTER:
                    self.prep_trophy_threshold = self.prep_cursor_col + 1
            elif self.prep_cursor_row == PREP_ROW_ARENA:
                from bm_params import GRID_SIZE_OFFSETS
                last_idx = len(GRID_SIZE_OFFSETS) - 1
                if event.key == Keys.LEFT:
                    if self.prep_cursor_col > 0:
                        self.prep_cursor_col -= 1
                elif event.key == Keys.RIGHT:
                    if self.prep_cursor_col < last_idx:
                        self.prep_cursor_col += 1
                elif event.key == Keys.ENTER:
                    self.prep_grid_offset = GRID_SIZE_OFFSETS[max(0, min(last_idx, self.prep_cursor_col))]
            elif self.prep_cursor_row >= PREP_ROW_PLAYERS:
                player_index = self.prep_cursor_row - PREP_ROW_PLAYERS
                all_players_info = self.get_all_players_info()
                if player_index >= len(all_players_info):
                    return
                player_info = all_players_info[player_index]
                if event.key == Keys.ENTER:
                    if player_info['type'] != 'ai':
                        self.prep_editing_name = True
                        self.prep_name_edit_index = player_index
                elif event.key == Keys.LEFT:
                    if player_info['type'] == 'local':
                        self.prep_player_colors[player_info['source']] = (self.prep_player_colors[player_info['source']] + 1) % len(colors)
                    elif player_info['type'] == 'client':
                        current_color = self.prep_web_player_colors.get(player_info['id'], player_info['color'])
                        self.prep_web_player_colors[player_info['id']] = (current_color + 1) % len(colors)
                elif event.key == Keys.RIGHT:
                    if player_info['type'] == 'local':
                        self.prep_player_colors[player_info['source']] = (self.prep_player_colors[player_info['source']] - 1) % len(colors)
                    elif player_info['type'] == 'client':
                        current_color = self.prep_web_player_colors.get(player_info['id'], player_info['color'])
                        self.prep_web_player_colors[player_info['id']] = (current_color - 1) % len(colors)
                elif str(getattr(event, "unicode", "")).lower() == "t":
                    if player_info['type'] == 'local':
                        self.team_mode_enabled = True
                        source_idx = player_info['source']
                        self.prep_player_teams[source_idx] = (self.prep_player_teams[source_idx] + 1) % 2
                        self.create_players()
        
        elif self.prep_section == 'start_game':
            if event.key == Keys.ENTER:
                self.prep_screen_completed = True
                self.init_game()
                self.game_state = "get_ready"
        
        # Handle text input when editing names
        if self.prep_editing_name and hasattr(event, 'unicode') and event.unicode:
            # Get all players to find the one being edited
            all_players_info = self.get_all_players_info()
            if self.prep_name_edit_index < len(all_players_info):
                player_info = all_players_info[self.prep_name_edit_index]
                if player_info['type'] == 'local':
                    if len(self.prep_player_names[player_info['source']]) < 15:
                        self.prep_player_names[player_info['source']] += event.unicode
                elif player_info['type'] != 'ai':
                    current_name = self.prep_web_player_names.get(player_info['id'], player_info['name'])
                    if len(current_name) < 15:
                        self.prep_web_player_names[player_info['id']] = current_name + event.unicode
        
        # Handle BACKSPACE when editing names
        if self.prep_editing_name and event.key == Keys.BACKSPACE:
            # Get all players to find the one being edited
            all_players_info = self.get_all_players_info()
            if self.prep_name_edit_index < len(all_players_info):
                player_info = all_players_info[self.prep_name_edit_index]
                if player_info['type'] == 'local':
                    if len(self.prep_player_names[player_info['source']]) > 0:
                        self.prep_player_names[player_info['source']] = self.prep_player_names[player_info['source']][:-1]
                elif player_info['type'] != 'ai':
                    current_name = self.prep_web_player_names.get(player_info['id'], player_info['name'])
                    if len(current_name) > 0:
                        self.prep_web_player_names[player_info['id']] = current_name[:-1]
        
        # ESC goes back to main menu
        if event.key == Keys.ESCAPE:
            if self.prep_editing_name:
                self.prep_editing_name = False
            else:
                self.game_state = "startup"
                
    def handle_web_key_event(self, event):
        # event: dict with 'type', 'key', 'code', 'ts', 'player_id', 'client_id'
        player_id = int(event.get('player_id', 0) or 0)
        client_id = int(event.get('client_id', 0) or 0)
        
        if DEGUG:
            print(f"DEBUG: handle_web_key_event called with event: {event}")
            print(f"DEBUG: Looking for client_id={client_id}, player_id={player_id}")
        
        if not hasattr(self, 'web_keys_by_player'):
            self.web_keys_by_player = {}
        
        # Find the corresponding player object
        player_obj = None
        for player in self.players:
            if DEGUG:
                print(f"DEBUG: Checking player: is_local={player.is_local}, client_id={getattr(player, 'client_id', None)}, client_player_id={getattr(player, 'client_player_id', None)}")
            # Normalize stored ids to int for robust comparison
            try:
                stored_client = int(getattr(player, 'client_id', -1)) if getattr(player, 'client_id', None) is not None else -1
            except Exception:
                stored_client = -1
            try:
                stored_player = int(getattr(player, 'client_player_id', -1)) if getattr(player, 'client_player_id', None) is not None else -1
            except Exception:
                stored_player = -1
            if (not player.is_local and 
                stored_client == client_id and 
                stored_player == player_id):
                player_obj = player
                if DEGUG:
                    print(f"DEBUG: Found matching player object!")
                break
        
        if player_obj is None:
            if DEGUG:
                print(f"DEBUG: No matching player found for client_id={client_id}, player_id={player_id}")
                print(f"DEBUG: Available players: {[(p.is_local, getattr(p, 'client_id', None), getattr(p, 'client_player_id', None)) for p in self.players]}")
        
        if player_obj is not None:
            if player_obj not in self.web_keys_by_player:
                self.web_keys_by_player[player_obj] = set()
            if event['type'] == 'set_input_state':
                keys_payload = event.get('keys', {}) if isinstance(event, dict) else {}
                new_keys = set()
                if isinstance(keys_payload, dict):
                    if int(keys_payload.get('up', 0)):
                        new_keys.add('arrowup')
                    if int(keys_payload.get('down', 0)):
                        new_keys.add('arrowdown')
                    if int(keys_payload.get('left', 0)):
                        new_keys.add('arrowleft')
                    if int(keys_payload.get('right', 0)):
                        new_keys.add('arrowright')
                    if int(keys_payload.get('bomb', 0)):
                        new_keys.add('space')
                self.web_keys_by_player[player_obj] = new_keys
                if DEGUG:
                    print(f"DEBUG: Player {player_obj.client_id}:{player_obj.client_player_id} KEYS SET -> {sorted(list(new_keys))}")
            elif event['type'] == 'keydown':
                # Normalize key to lowercase for consistent comparisons
                keyname = str(event['key']).lower()
                self.web_keys_by_player[player_obj].add(keyname)
                if DEGUG:
                    print(f"DEBUG: Player {player_obj.client_id}:{player_obj.client_player_id} KEYS DOWN -> {sorted(list(self.web_keys_by_player[player_obj]))}")
                # Allow Enter/Return to start the game from browser
                if keyname in ('enter', 'return'):
                    if self.game_state == "startup":
                        self.game_state = "game_prep"
                    elif self.game_state == "game_prep":
                        self.prep_screen_completed = True
                        self.init_game()
                        self.game_state = "get_ready"
                    elif self.game_state in ("win", "champion", "boss_result"):
                        self.continue_from_intermission()
                elif keyname == 'r' and self.game_state in ("champion", "boss_result"):
                    self.reset_series_and_start()
            elif event['type'] == 'keyup':
                keyname = str(event['key']).lower()
                self.web_keys_by_player[player_obj].discard(keyname)
                if DEGUG:
                    print(f"DEBUG: Player {player_obj.client_id}:{player_obj.client_player_id} KEYS UP -> {sorted(list(self.web_keys_by_player[player_obj]))}")

    def update(self):
        # update players
        for idx, player in enumerate(self.players):
            web_keys = set()
            if hasattr(self, 'web_keys_by_player') and player in self.web_keys_by_player:
                web_keys = self.web_keys_by_player[player]
                if idx in (0, 1):
                    allowed = {'arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' ', 'space'}
                    web_keys = set(k for k in web_keys if k.lower() in allowed)
            player.update(self.dt, self.board, self.bombs, self.current_time, web_keys, game=self)
        
        # update bombs & check for explosions
        expired = [bomb for bomb in self.bombs if bomb.update(self.current_time)]
        self._explode_with_chain(expired)
    
        self.handle_explosions()
        
        for player in self.players: 
            if not player.alive:
                continue
            for pu in self.powerups[:]:
                if player.get_grid_pos() == (pu.x, pu.y):
                    if pu.type == "bomb":
                        player.bomb_capacity += 1
                        bonus_sound.play()
                        player.powerups_collected += 1
                    elif pu.type == "fire":
                        player.fire_power += 1
                        bonus_sound.play()
                        player.powerups_collected += 1
                    elif pu.type == "death_bonus":
                        # Randomly apply one of the effects:
                        # - Speed x1.05
                        # - +2 fire power
                        # - +3 bomb capacity
                        choice = choose_death_bonus_effect()
                        if choice == "speed":
                            # Multiply current speed by 1.05 (respect quad damage later when applied)
                            player.speed = int(player.speed * 1.05)
                            player.pickup_message = "+5% SPEED"
                            player.pickup_message_end_time = self.current_time + 3000
                        elif choice == "fire":
                            player.fire_power += 2
                            player.pickup_message = "+2 FLAMES"
                            player.pickup_message_end_time = self.current_time + 3000
                        else:
                            player.bomb_capacity += 3
                            player.pickup_message = "+3 BOMBS"
                            player.pickup_message_end_time = self.current_time + 3000
                        bonus_sound.play()
                        player.powerups_collected += 1
                    elif pu.type == "quad_damage":
                        player.quad_damage = True
                        player.quad_damage_start_time = self.current_time
                        player.bomb_capacity += QUAD_DAMAGE_POWER
                        player.fire_power += QUAD_DAMAGE_POWER
                        qd_sound.play()
                        player.quad_damage_collected += 1
                    self.powerups.remove(pu)
                    
        # Use adjustable powerup logic
        self.place_quad_damage_powerup()
        
        # Handle crushing walls feature
        self.handle_crushing_walls()
        self._play_due_big_explosion_sounds()
        
        alive_players = [p for p in self.players if p.alive]
        alive_teams = {getattr(p, "team", 0) for p in alive_players}
        round_over = len(alive_players) <= 1
        if self.team_mode_enabled:
            round_over = round_over or len(alive_teams) <= 1
        # If round appears to be over (0/1 alive or only one team alive), start a 0.5s hold if not started
        if round_over and self.post_win_target_state is None:
            if self.endgame_hold_until is None:
                self.endgame_hold_until = self.current_time + 500  # 0.5 seconds
            # Once hold elapses, resolve winner or tie and schedule post-win transition
            if self.current_time >= self.endgame_hold_until:
                # Boss fight: transition to boss_result (no trophy, reset happens on exit)
                if self.game_state == "boss_fight":
                    if alive_players:
                        self.boss_fight_winner = alive_players[0]
                    else:
                        self.boss_fight_winner = None  # Tie
                    self.post_win_target_state = "boss_result"
                    self.post_win_transition_time = self.current_time + ENDGAME_POST_DELAY_MS
                else:
                    recent_deaths = [t for t in self.death_events if t >= self.current_time - 500]
                    if len(recent_deaths) >= 2 or len(alive_players) == 0:
                        # Tie: no trophy assignment
                        self.post_win_target_state = "win"
                    else:
                        # Winner is surviving player (or first player on surviving team)
                        if alive_players:
                            winner = alive_players[0]
                            if self.team_mode_enabled and len(alive_teams) == 1:
                                winner_team = next(iter(alive_teams))
                                for player in alive_players:
                                    if getattr(player, "team", 0) == winner_team:
                                        winner = player
                                        break
                            winner.trophies += 1
                            if winner.trophies >= self.trophy_threshold():
                                self.post_win_target_state = "champion"
                            else:
                                self.post_win_target_state = "win"
                        else:
                            self.post_win_target_state = "win"
                    self.post_win_transition_time = self.current_time + ENDGAME_POST_DELAY_MS
                # Prepare replay segment metadata: find last-dead player and replay window bounds
                last_dead_time = None
                last_dead_player_name = None
                for p in self.players:
                    if p.death_time_ms is not None and (last_dead_time is None or p.death_time_ms > last_dead_time):
                        last_dead_time = p.death_time_ms
                        last_dead_player_name = p.name
                self.replay_focus_player = last_dead_player_name
                self.replay_end_time = self.current_time
                self.replay_start_time = max(0, self.replay_end_time - REPLAY_BUFFER_MS)
                # Freeze the replay segment now so it doesn't get trimmed while on win screen
                self.replay_segment_start_time = self.replay_start_time
                self.replay_segment_end_time = self.replay_end_time
                self.replay_segment = [(t, snap) for (t, snap) in self.replay_buffer if self.replay_start_time <= t <= self.replay_end_time]
                self._flush_kill_cams(force=True)
                self.replay_loop_anchor_time = None

        # If a post-win transition has been scheduled, execute it when time comes
        if self.post_win_target_state is not None and self.post_win_transition_time is not None:
            if self.current_time >= self.post_win_transition_time:
                self.game_state = self.post_win_target_state
                # Clear schedule to avoid repeat
                self.post_win_target_state = None
                self.post_win_transition_time = None
                if self.game_state == "boss_fight" and hasattr(self, 'boss_fight_champion'):
                    self.init_boss_fight(self.boss_fight_champion)

    def _serialize_boss_winner(self):
        """Serialize boss fight winner for client display."""
        if self.game_state != "boss_result":
            return None
        winner = getattr(self, 'boss_fight_winner', None)
        if winner is None:
            return None
        return {
            'name': winner.name,
            'is_ai': getattr(winner, 'is_ai', False),
            'color': list(winner.color) if hasattr(winner.color, '__iter__') else winner.color,
        }

    def to_dict(self):
        # Ensure board is serializable (convert from numpy array if needed)
        board_data = self.board.tolist() if hasattr(self.board, 'tolist') else self.board
        
        return {
            'time': self.current_time,
            'state': self.game_state,
            'board': board_data,
            'grid_width': self.grid_width,
            'grid_height': self.grid_height,
            'players': [p.to_dict() for p in self.players],
            'bombs': [b.to_dict() for b in self.bombs],
            'explosions': [e.to_dict() for e in self.explosions],
            'powerups': [p.to_dict() for p in self.powerups],
            'crushing_walls': {
                'active': self.crushing_walls_active,
                'index': self.crushing_walls_index
            },
            'local_player_count': int(self.prep_num_players if self.game_state in ["startup", "game_prep"] else sum(1 for p in self.players if getattr(p, 'is_local', False))),
            'ai_count': int(getattr(self, "prep_ai_count", 0) if self.game_state in ["startup", "game_prep"] else sum(1 for p in self.players if getattr(p, "is_ai", False))),
            'trophy_win_threshold': int(self.trophy_threshold()),
            'result_prompt': self.result_prompt(),
            'boss_fight_winner': self._serialize_boss_winner(),
            'leave_prompt': {
                'open': bool(getattr(self, "leave_prompt_open", False)),
                'choice': getattr(self, "leave_prompt_choice", "no"),
                'title': self.leave_prompt_title() if getattr(self, "leave_prompt_open", False) else "",
            },
        }
            
# Screen class and methods moved to frontend.py

def browser_key_to_pygame(key):
    """
    Map browser key names (from event.key or event.code) to pygame key names as returned by pygame.key.name().
    Returns the pygame key name as a lowercase string, or None if not mapped.
    """
    key = key.lower()
    mapping = {
        # Arrow keys
        'arrowup': 'up',
        'arrowdown': 'down',
        'arrowleft': 'left',
        'arrowright': 'right',
        # Space and enter
        ' ': 'space',
        'space': 'space',
        'enter': 'return',
        # Control keys
        'control': 'left ctrl',  # Default to left ctrl for generic 'control'
        'ctrl': 'left ctrl',
        'left control': 'left ctrl',
        'right control': 'right ctrl',
        'controlleft': 'left ctrl',
        'controlright': 'right ctrl',
        'shift': 'shift',
        'left shift': 'left shift',
        'right shift': 'right shift',
        'shiftleft': 'left shift',
        'shiftright': 'right shift',
        'alt': 'alt',
        'left alt': 'left alt',
        'right alt': 'right alt',
        'altleft': 'left alt',
        'altright': 'right alt',
        'backspace': 'backspace',
        'delete': 'delete',
        'home': 'home',
        'end': 'end',
        'pageup': 'page up',
        'pagedown': 'page down',
        # Numpad
        'numpad0': 'kp0',
        'numpad1': 'kp1',
        'numpad2': 'kp2',
        'numpad3': 'kp3',
        'numpad4': 'kp4',
        'numpad5': 'kp5',
        'numpad6': 'kp6',
        'numpad7': 'kp7',
        'numpad8': 'kp8',
        'numpad9': 'kp9',
        'numpaddivide': 'kp_divide',
        # Letters and numbers
    }
    if key in mapping:
        return mapping[key]
    # Letters and digits
    if len(key) == 1 and key.isalnum():
        return key
    return None



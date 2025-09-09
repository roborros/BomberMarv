import pygame
import math
import numpy as np
from bm_params import *
from lib_collisions import *
from lib_grid import *
from bm_sounds import *
from bm_drawing import *
from input_abstraction import get_pressed_keys, is_key_pressed, Keys
from timing_abstraction import get_ticks, Clock



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
        self.wins = 0
        self.trophies = 0
        self.draw_radius = int(CELL_SIZE * PLAYER_DRAW_SCALE / 2)
        self.collision_radius = int(CELL_SIZE * PLAYER_COLLISION_SCALE / 2)
        self.animation_time = 0
        self.quad_damage = False
        self.quad_damage_start_time = 0
        self.name = name
        self.death_animation_time = 0
        self.direction = np.array([0.0, 0.0], dtype=np.float64)  # Initialize direction

    def get_circle(self):
        return (self.pos, self.draw_radius)

    def get_grid_pos(self):
        return (int(self.pos[0] // CELL_SIZE), int(self.pos[1] // CELL_SIZE))

    def update(self, dt, board, bombs, current_time, web_keys=None):
        if not self.alive:
            if self.death_animation_time > 0:
                self.death_animation_time -= dt
            self.direction = np.array([0.0, 0.0], dtype=np.float64)  # No direction if dead
            return
        keys = get_pressed_keys()
        direction = np.array([0.0, 0.0], dtype=np.float64)
        # Remap all web_keys using browser_key_to_pygame
        mapped_web_keys = set()
        if web_keys:
            for k in web_keys:
                mapped = browser_key_to_pygame(k)
                if mapped:
                    mapped_web_keys.add(mapped.lower())
        # Use mapped_web_keys as an OR with local keys
        if is_key_pressed(self.controls['up']) or (mapped_web_keys and 'up' in mapped_web_keys):
            direction[1] -= 1
        if is_key_pressed(self.controls['down']) or (mapped_web_keys and 'down' in mapped_web_keys):
            direction[1] += 1
        if is_key_pressed(self.controls['left']) or (mapped_web_keys and 'left' in mapped_web_keys):
            direction[0] -= 1
        if is_key_pressed(self.controls['right']) or (mapped_web_keys and 'right' in mapped_web_keys):
            direction[0] += 1
        if np.dot(direction, direction) > 1:
            length = np.linalg.norm(direction)
            if length > 0:
                direction = direction / length
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

        if is_key_pressed(self.controls['bomb']) or (mapped_web_keys and 'space' in mapped_web_keys):  
            self.drop_bomb(bombs, current_time)

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
                return
            # Try moving only along y
            self.pos = original_pos + np.array([0, direction[1] * spd * (dt / 1000.0)], dtype=np.float64)
            if not (self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos)):
                return
            # Both attempts failed, revert.
            self.pos = original_pos

        # Handle quad damage duration.
        if self.quad_damage and get_ticks() - self.quad_damage_start_time > QUAD_DAMAGE_TIME * 1000:
            self.quad_damage = False
            self.bomb_capacity -= QUAD_DAMAGE_POWER
            self.fire_power -= QUAD_DAMAGE_POWER
            
    def collides_with_walls(self, board):
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if board[y][x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                    wall_rect = np.array([x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
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
            bomb_center = np.array([bomb.x * CELL_SIZE + CELL_SIZE / 2,
                                                bomb.y * CELL_SIZE + CELL_SIZE / 2], dtype=np.float64)
            # If the player originally was in the bomb's cell:
            if (int(original_pos[0] // CELL_SIZE), int(original_pos[1] // CELL_SIZE)) == bomb_cell:
                # If the new position is further from the bomb center than the starting position, let the player exit:
                if np.linalg.norm(self.pos - bomb_center)+int(CELL_SIZE/10) > np.linalg.norm(original_pos - bomb_center):
                    continue  # allow the move out

            # Otherwise (or if not exiting), use a reduced bomb collision box.
            margin = CELL_SIZE * 0.35  # tweak margin as needed
            bomb_rect = np.array([
                bomb.x * CELL_SIZE + margin,
                bomb.y * CELL_SIZE + margin,
                CELL_SIZE - 2 * margin,
                CELL_SIZE - 2 * margin
            ], dtype=np.float64)
            if circle_rect_collision((self.pos[0], self.pos[1]), self.collision_radius, bomb_rect):
                return True
        return False
    

    def drop_bomb(self, bombs, current_time):
        if not self.alive or self.active_bombs >= self.bomb_capacity:
            return
        grid_x, grid_y = self.get_grid_pos()
        for bomb in bombs:
            if bomb.x == grid_x and bomb.y == grid_y:
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

class Explosion:
    def __init__(self, cells, start_time, quad_damage=False):
        self.cells = cells
        self.start_time = start_time
        self.quad_damage = quad_damage

    def is_active(self, current_time):
        return current_time - self.start_time < EXPLOSION_DURATION

class PowerUp:
    def __init__(self, x, y, type, spawn_time=0):
        self.x = x
        self.y = y
        self.type = type
        self.spawn_time = spawn_time



class Game:
    def __init__(self):
        self.board = generate_maze()
        self.bombs = []
        self.explosions = []
        self.powerups = []
        self.game_start_time = get_ticks()
        self.players = []
        self.game_state = "startup"
        self.startup_start_time = get_ticks()
        self.current_time = self.startup_start_time
        self.clock = Clock()
        self.dt = 0
        
        self.is_fullscreen = False
        self.web_keys = set()  # Track keys pressed from web client
        self.screen = None  # Will be set by main game loop
        
        # Crushing walls feature variables
        self.crushing_walls_active = False
        self.crushing_walls_last_time = 0
        self.crushing_walls_pattern = []
        self.crushing_walls_index = 0
        
        # Game preparation screen state
        self.prep_num_players = NUM_PLAYERS
        self.prep_player_names = player_names.copy()
        self.prep_player_colors = list(range(len(colors)))  # Store color indices instead of colors
        self.prep_controls = [controls.copy() for controls in controls_list]
        
        # Simple navigation system
        self.prep_cursor_row = 0  # 0=num_players, 1-N=players, N+1=start_game
        self.prep_cursor_col = 0  # 0=name, 1=color, 2=controls (only when on player rows)
        self.prep_section = 'players'  # 'players' or 'game'
        self.prep_game_cursor = 0  # index within game settings list
        self.prep_editing_mode = False  # True when editing values, False when navigating
        
        # Editing states
        self.prep_editing_control = None  # Which control key we're currently changing
        self.prep_editing_name = False  # Whether we're typing a custom name
        self.prep_custom_name = ""  # Buffer for custom name input
        
        # Track if prep screen has been shown
        self.prep_screen_completed = False

        # Gameplay settings (can be edited in prep screen)
        self.prep_initial_bomb_capacity = 1
        self.prep_initial_fire_power = 1
        self.prep_player_speed = PLAYER_SPEED
        self.prep_qd_probability = QUAD_DAMAGE_PROBABILITY
        self.prep_qd_delay = QUAD_DAMAGE_DELAY
        self.prep_crushing_delay = CRUSHING_WALLS_DELAY
        self.prep_crushing_min_destroyable = CRUSHING_WALLS_MIN_DESTROYABLE
        self.prep_trophy_threshold = TROPHY_WIN_THRESHOLD
        
        # Create initial players based on current settings
        self.create_players()
    
    def create_players(self):
        """Create players based on current prep screen settings"""
        self.players = []
        for i in range(self.prep_num_players):
            color_idx = self.prep_player_colors[i % len(self.prep_player_colors)]
            p = Player(1, 1, 
                      colors[color_idx % len(colors)], 
                      self.prep_controls[i % len(self.prep_controls)], 
                      self.prep_player_names[i % len(self.prep_player_names)])
            self.players.append(p)
    
    def init_game(self):
        # Recreate players based on current prep settings
        self.create_players()
        
        self.board = generate_maze()
        self.bombs = []
        self.explosions = []
        self.powerups = []
        
        fixed_positions = [(1, 1), (GRID_WIDTH - 2, 1), (1, GRID_HEIGHT - 2), (GRID_WIDTH - 2, GRID_HEIGHT - 2)]
        corner_patterns = {
            (1, 1): [(0,0), (1,0), (0,1)],
            (GRID_WIDTH - 2, 1): [(0,0), (-1,0), (0,1)],
            (1, GRID_HEIGHT - 2): [(0,0), (1,0), (0,-1)],
            (GRID_WIDTH - 2, GRID_HEIGHT - 2): [(0,0), (-1,0), (0,-1)]
        }
        
        #random.shuffle(self.players)

        for i, player in enumerate(self.players):
            if i < 4:
                pos = fixed_positions[i]
                player.start_grid_x, player.start_grid_y = pos
                offsets = corner_patterns.get(pos, [(0,0), (1,0), (0,1)])
            elif i == 4:
                player.start_grid_x = GRID_WIDTH // 4
                player.start_grid_y = GRID_HEIGHT // 2
                offsets = [(0,0), (1,0), (0,1), (1,1), (-1,0), (0,-1), (-1,-1), (1,-1), (-1,1)]
            elif i == 5:
                player.start_grid_x = 3 * GRID_WIDTH // 4
                player.start_grid_y = GRID_HEIGHT // 2
                offsets = [(0,0), (-1,0), (0,1), (-1,1), (1,0), (0,-1), (1,-1), (-1,-1), (1,1)]
            
            clear_safe_zone(self.board, player.start_grid_x, player.start_grid_y, offsets)
            player.reset()
            # Apply initial gameplay params
            player.bomb_capacity = max(1, int(self.prep_initial_bomb_capacity))
            player.fire_power = max(1, int(self.prep_initial_fire_power))
            player.speed = max(50, int(self.prep_player_speed))
        self.game_start_time = get_ticks() + 2000  # Add a 2-second freeze time
        
        # Reset crushing walls state
        self.crushing_walls_active = False
        self.crushing_walls_last_time = 0
        self.crushing_walls_pattern = []
        self.crushing_walls_index = 0

    def generate_clockwise_pattern(self):
        """Generate a clockwise traversal pattern starting from top-left corner, 
        but skip cells that are already indestructible walls"""
        pattern = []
        visited = set()
        
        # Start from the outermost layer and work inward
        for layer in range(min(GRID_WIDTH, GRID_HEIGHT) // 2):
            # Top row (left to right)
            for x in range(layer, GRID_WIDTH - layer):
                if (x, layer) not in visited and self.board[layer][x] != INDESTRUCTIBLE:
                    pattern.append((x, layer))
                    visited.add((x, layer))
            
            # Right column (top to bottom, skip top corner)
            for y in range(layer + 1, GRID_HEIGHT - layer):
                if (GRID_WIDTH - 1 - layer, y) not in visited and self.board[y][GRID_WIDTH - 1 - layer] != INDESTRUCTIBLE:
                    pattern.append((GRID_WIDTH - 1 - layer, y))
                    visited.add((GRID_WIDTH - 1 - layer, y))
            
            # Bottom row (right to left, skip right corner)
            if GRID_HEIGHT - 1 - layer > layer:
                for x in range(GRID_WIDTH - 2 - layer, layer - 1, -1):
                    if (x, GRID_HEIGHT - 1 - layer) not in visited and self.board[GRID_HEIGHT - 1 - layer][x] != INDESTRUCTIBLE:
                        pattern.append((x, GRID_HEIGHT - 1 - layer))
                        visited.add((x, GRID_HEIGHT - 1 - layer))
            
            # Left column (bottom to top, skip both corners)
            if GRID_WIDTH - 1 - layer > layer:
                for y in range(GRID_HEIGHT - 2 - layer, layer, -1):
                    if (layer, y) not in visited and self.board[y][layer] != INDESTRUCTIBLE:
                        pattern.append((layer, y))
                        visited.add((layer, y))
        
        return pattern

    def count_destroyable_cells(self):
        """Count the number of destroyable cells on the board"""
        count = 0
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if self.board[y][x] == DESTRUCTIBLE:
                    count += 1
        return count

    def find_nearest_safe_position(self, player, avoid_cell_x, avoid_cell_y):
        """Find the nearest safe position for a player, avoiding a specific cell"""
        player_grid_x, player_grid_y = player.get_grid_pos()
        
        # Search in expanding rings around the player's current position
        for radius in range(1, max(GRID_WIDTH, GRID_HEIGHT)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    # Only check cells on the perimeter of the current radius
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                        
                    new_grid_x = player_grid_x + dx
                    new_grid_y = player_grid_y + dy
                    
                    # Skip if out of bounds
                    if (new_grid_x < 0 or new_grid_x >= GRID_WIDTH or 
                        new_grid_y < 0 or new_grid_y >= GRID_HEIGHT):
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
        
        # Check if conditions are met to activate crushing walls
        if len(alive_players) == 2 and \
           (self.current_time - self.game_start_time) >= self.prep_crushing_delay * 1000 and \
           self.count_destroyable_cells() < self.prep_crushing_min_destroyable:
            
            if not self.crushing_walls_active:
                # Initialize crushing walls
                self.crushing_walls_active = True
                self.crushing_walls_pattern = self.generate_clockwise_pattern()
                self.crushing_walls_index = 0
                self.crushing_walls_last_time = self.current_time
                return
            
            # Add a new wall every second
            if self.current_time - self.crushing_walls_last_time >= 1000:
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
                            if (0 <= adj_x < GRID_WIDTH and 0 <= adj_y < GRID_HEIGHT and 
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
                    for bomb in self.bombs[:]:
                        if bomb.x == x and bomb.y == y:
                            exp = Explosion(self.get_explosion_cells(bomb), self.current_time, bomb.quad_damage)
                            self.explosions.append(exp)
                            bomb.owner.active_bombs -= 1
                            self.bombs.remove(bomb)
                    
                    self.crushing_walls_index += 1
                    self.crushing_walls_last_time = self.current_time

    def get_explosion_cells(self,bomb):
        cells = [(bomb.x, bomb.y)]
        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
            for i in range(1, bomb.fire_power + 1):
                nx = bomb.x + dx * i
                ny = bomb.y + dy * i
                if nx < 0 or nx >= GRID_WIDTH or ny < 0 or ny >= GRID_HEIGHT:
                    break
                if self.board[ny][nx] == INDESTRUCTIBLE:
                    break
                cells.append((nx, ny))
                if self.board[ny][nx] == DESTRUCTIBLE:
                    break
        return cells
    
    def handle_explosions(self):
        
        for explosion in self.explosions[:]:
            if not explosion.is_active(self.current_time):
                if explosion.quad_damage:
                    explosion_sound_qd.play()
                else:
                    explosion_sound.play()
                    
                for (x, y) in explosion.cells:
                    if self.board[y][x] == DESTRUCTIBLE:
                        self.board[y][x] = EMPTY
                        if random.random() < POWERUP_PROBABILITY:
                            pu_type = random.choice(["bomb", "fire"])
                            self.powerups.append(PowerUp(x, y, pu_type, spawn_time=explosion.start_time))
                for pu in self.powerups[:]:
                    if pu.spawn_time < explosion.start_time and (pu.x, pu.y) in explosion.cells:
                        self.powerups.remove(pu)
                for player in self.players:
                    if player.alive:
                        for cell in explosion.cells:
                            explosion_rect = np.array([cell[0]*CELL_SIZE, cell[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
                            if circle_rect_collision((player.pos[0], player.pos[1]), player.collision_radius, explosion_rect):
                                player.alive = False
                                player.death_animation_time = 1000  # 1 second death animation
                                death_sound.play()
                                break           
                self.explosions.remove(explosion)
                    
    def place_quad_damage_powerup(self):        
        if (get_ticks() - self.game_start_time) >= self.prep_qd_delay*1000:
            if not any(pu.type == "quad_damage" for pu in self.powerups):
                empty_cells = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH) if self.board[y][x] == EMPTY]
                if empty_cells and random.random() < self.prep_qd_probability:
                    x, y = random.choice(empty_cells)
                    self.powerups.append(PowerUp(x, y, "quad_damage"))
                                
    def tick(self):
        self.dt = self.clock.tick(FPS)
        self.current_time = get_ticks()                
                    
    def handle_window_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                if self.screen:
                    self.screen.update_window_size(event.size)
            elif event.type == pygame.KEYDOWN:
                if event.key == Keys.F11:
                    self.is_fullscreen = not self.is_fullscreen
                    if self.is_fullscreen:
                        window = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
                        if self.screen:
                            self.screen.update_window_size(window.get_size())
                    else:
                        window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
                        if self.screen:
                            self.screen.update_window_size(INITIAL_WINDOW_SIZE)
                elif event.key in (Keys.ENTER, Keys.KP_ENTER):
                    print(f"ENTER pressed, game_state={self.game_state}")
                    if self.game_state == "startup":
                        if not self.prep_screen_completed:
                            self.game_state = "game_prep"
                        else:
                            self.init_game()
                            self.game_state = "get_ready"
                    elif self.game_state == "game_prep":
                        self.handle_prep_enter_key()
                    elif self.game_state in ["win", "champion"]:
                        self.init_game()
                        self.game_state = "get_ready"
                
                # Handle prep screen navigation
                elif self.game_state == "game_prep":
                    self.handle_prep_key_event(event)
    
    def handle_prep_enter_key(self):
        """Handle ENTER key presses in the game prep screen"""
        if self.prep_editing_control:
            # Cancel control editing
            self.prep_editing_control = None
            return
        
        if self.prep_editing_name:
            # Save custom name
            if self.prep_custom_name.strip():
                player_idx = self.prep_cursor_row - 1
                self.prep_player_names[player_idx] = self.prep_custom_name.strip()
                self.create_players()
            self.prep_editing_name = False
            self.prep_custom_name = ""
            return
        
        # Handle "Start Game" option
        if self.prep_section == 'game' and self.prep_game_cursor == 9:  # "Start Game" is the 10th item (index 9)
            self.prep_screen_completed = True
            self.init_game()
            self.game_state = "get_ready"
            return
        
        # Toggle editing mode
        if self.prep_section == 'players':
            if self.prep_cursor_row == 0:
                # Number of players - toggle editing
                self.prep_editing_mode = not self.prep_editing_mode
            elif 1 <= self.prep_cursor_row <= self.prep_num_players:
                # Player row
                if self.prep_cursor_col == 0:  # Name
                    self.prep_editing_name = True
                    player_idx = self.prep_cursor_row - 1
                    self.prep_custom_name = self.prep_player_names[player_idx]
                elif self.prep_cursor_col == 1:  # Color
                    self.prep_editing_mode = not self.prep_editing_mode
                elif self.prep_cursor_col == 2:  # Controls
                    self.prep_editing_control = 'up'
        else:
            # Game settings section
            if self.prep_game_cursor < 9:  # Not "Start Game"
                self.prep_editing_mode = not self.prep_editing_mode
    
    def handle_prep_key_event(self, event):
        """Handle key events for game prep screen navigation"""
        # Handle text input for custom names
        if self.prep_editing_name:
            if event.key == Keys.BACKSPACE:
                self.prep_custom_name = self.prep_custom_name[:-1]
            elif event.key == Keys.ESCAPE:
                # Cancel name editing
                self.prep_editing_name = False
                self.prep_custom_name = ""
            elif event.unicode and event.unicode.isprintable() and len(self.prep_custom_name) < 12:
                self.prep_custom_name += event.unicode
            return
        
        if self.prep_editing_control:
            # We're editing a control key
            if event.key != Keys.ESCAPE:  # Don't allow ESC as a control key
                player_idx = self.prep_cursor_row - 1
                controls = self.prep_controls[player_idx % len(self.prep_controls)]
                controls[self.prep_editing_control] = event.key
                
                # Move to next control or finish
                control_order = ['up', 'down', 'left', 'right', 'bomb']
                current_idx = control_order.index(self.prep_editing_control)
                if current_idx < len(control_order) - 1:
                    self.prep_editing_control = control_order[current_idx + 1]
                else:
                    self.prep_editing_control = None
                    self.create_players()
            else:
                # ESC cancels control editing
                self.prep_editing_control = None
            return
        
        # Switch section
        if event.key == Keys.TAB:
            self.prep_section = 'game' if self.prep_section == 'players' else 'players'
            return

        if self.prep_section == 'players':
            if event.key == Keys.UP:
                if not self.prep_editing_mode:
                    if self.prep_cursor_row > 0:
                        self.prep_cursor_row -= 1
                        if self.prep_cursor_row == 0:
                            self.prep_cursor_col = 0
            elif event.key == Keys.DOWN:
                if not self.prep_editing_mode:
                    if self.prep_cursor_row < self.prep_num_players:
                        self.prep_cursor_row += 1
            elif event.key == Keys.LEFT:
                if self.prep_editing_mode:
                    # Edit values
                    if self.prep_cursor_row == 0:
                        self.prep_num_players = max(2, self.prep_num_players - 1)
                        self.create_players()
                        if self.prep_cursor_row > self.prep_num_players:
                            self.prep_cursor_row = self.prep_num_players
                    elif 1 <= self.prep_cursor_row <= self.prep_num_players:
                        player_idx = self.prep_cursor_row - 1
                        if self.prep_cursor_col == 0:
                            try:
                                current_idx = player_names.index(self.prep_player_names[player_idx])
                                new_idx = (current_idx - 1) % len(player_names)
                                self.prep_player_names[player_idx] = player_names[new_idx]
                                self.create_players()
                            except ValueError:
                                self.prep_player_names[player_idx] = player_names[-1]
                                self.create_players()
                        elif self.prep_cursor_col == 1:
                            current_color = self.prep_player_colors[player_idx]
                            self.prep_player_colors[player_idx] = (current_color - 1) % len(colors)
                            self.create_players()
                else:
                    # Navigate columns
                    if 1 <= self.prep_cursor_row <= self.prep_num_players and self.prep_cursor_col > 0:
                        self.prep_cursor_col -= 1
            elif event.key == Keys.RIGHT:
                if self.prep_editing_mode:
                    # Edit values
                    if self.prep_cursor_row == 0:
                        self.prep_num_players = min(6, self.prep_num_players + 1)
                        self.create_players()
                    elif 1 <= self.prep_cursor_row <= self.prep_num_players:
                        player_idx = self.prep_cursor_row - 1
                        if self.prep_cursor_col == 0:
                            try:
                                current_idx = player_names.index(self.prep_player_names[player_idx])
                                new_idx = (current_idx + 1) % len(player_names)
                                self.prep_player_names[player_idx] = player_names[new_idx]
                                self.create_players()
                            except ValueError:
                                self.prep_player_names[player_idx] = player_names[0]
                                self.create_players()
                        elif self.prep_cursor_col == 1:
                            current_color = self.prep_player_colors[player_idx]
                            self.prep_player_colors[player_idx] = (current_color + 1) % len(colors)
                            self.create_players()
                else:
                    # Navigate columns
                    if 1 <= self.prep_cursor_row <= self.prep_num_players and self.prep_cursor_col < 2:
                        self.prep_cursor_col += 1

        else:
            # Game settings navigation
            settings = [
                ('prep_initial_bomb_capacity', 1, 10, 1),
                ('prep_initial_fire_power', 1, 10, 1),
                ('prep_player_speed', 100, 600, 10),
                ('prep_qd_probability', 0.0, 0.02, 0.0005),
                ('prep_qd_delay', 0, 600, 5),
                ('prep_crushing_delay', 0, 600, 5),
                ('prep_crushing_min_destroyable', 0, 200, 1),
                ('prep_trophy_threshold', 1, 10, 1),
            ]

            if event.key == Keys.UP:
                if not self.prep_editing_mode:
                    if self.prep_game_cursor > 0:
                        self.prep_game_cursor -= 1
            elif event.key == Keys.DOWN:
                if not self.prep_editing_mode:
                    # Allow navigation to "Start Game" (index 9)
                    if self.prep_game_cursor < 9:
                        self.prep_game_cursor += 1
            elif event.key in (Keys.LEFT, Keys.RIGHT):
                if self.prep_editing_mode and self.prep_game_cursor < len(settings):
                    attr, mn, mx, step = settings[self.prep_game_cursor]
                    val = getattr(self, attr)
                    if isinstance(val, float):
                        delta = step if event.key == Keys.RIGHT else -step
                        val = max(mn, min(mx, float(val) + delta))
                        setattr(self, attr, round(val, 4))
                    else:
                        delta = step if event.key == Keys.RIGHT else -step
                        val = max(mn, min(mx, int(val) + delta))
                        setattr(self, attr, val)
        
        if event.key == Keys.ESCAPE:
            # Go back to startup
            self.game_state = "startup"
            self.startup_start_time = get_ticks()
                
    def handle_web_key_event(self, event):
        # event: dict with 'type', 'key', 'code', 'ts', 'player_id'
        player_id = event.get('player_id', 0)
        if not hasattr(self, 'web_keys_by_player'):
            self.web_keys_by_player = {}
        if not hasattr(self, 'player_id_to_player'):
            self.player_id_to_player = {}
        # Assign player_id to next available Player if not already mapped
        if player_id not in self.player_id_to_player:
            assigned = set(self.player_id_to_player.values())
            for player in self.players:
                if player not in assigned:
                    self.player_id_to_player[player_id] = player
                    break
        player_obj = self.player_id_to_player.get(player_id, None)
        if player_obj is not None:
            if player_obj not in self.web_keys_by_player:
                self.web_keys_by_player[player_obj] = set()
            if event['type'] == 'keydown':
                self.web_keys_by_player[player_obj].add(event['key'])
                # Allow Enter/Return to start the game from browser
                if event['key'].lower() in ('enter', 'return'):
                    if self.game_state == "startup":
                        self.game_state = "game_prep"
                    if self.game_state in ["win", "champion", "game_prep"]:
                        self.init_game()
                        self.game_state = "get_ready"
            elif event['type'] == 'keyup':
                self.web_keys_by_player[player_obj].discard(event['key'])

    def update(self):
        # update players
        for idx, player in enumerate(self.players):
            web_keys = set()
            if hasattr(self, 'web_keys_by_player') and player in self.web_keys_by_player:
                web_keys = self.web_keys_by_player[player]
                if idx in (0, 1):
                    allowed = {'arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' ', 'space'}
                    web_keys = set(k for k in web_keys if k.lower() in allowed)
            player.update(self.dt, self.board, self.bombs, self.current_time, web_keys)
        
        # update bombs & check for explosions
        triggered_explosions = []
        for bomb in self.bombs[:]:
            if bomb.update(self.current_time):
                exp = Explosion(self.get_explosion_cells(bomb), self.current_time, bomb.quad_damage)
                triggered_explosions.append(exp)
                bomb.owner.active_bombs -= 1
                self.bombs.remove(bomb)
        chain_cells = set()
        for exp in triggered_explosions:
            for cell in exp.cells:
                chain_cells.add(cell)
        chain_triggered = True
        while chain_triggered:
            chain_triggered = False
            for bomb in self.bombs[:]:
                if (bomb.x, bomb.y) in chain_cells:
                    exp = Explosion(self.get_explosion_cells(bomb), self.current_time,bomb.quad_damage)
                    triggered_explosions.append(exp)
                    for cell in exp.cells:
                        chain_cells.add(cell)
                    bomb.owner.active_bombs -= 1
                    self.bombs.remove(bomb)
                    chain_triggered = True
        self.explosions.extend(triggered_explosions)         
    
        self.handle_explosions()
        
        for player in self.players: 
            if not player.alive:
                continue
            for pu in self.powerups[:]:
                if player.get_grid_pos() == (pu.x, pu.y):
                    if pu.type == "bomb":
                        player.bomb_capacity += 1
                        bonus_sound.play()
                    elif pu.type == "fire":
                        player.fire_power += 1
                        bonus_sound.play()
                    elif pu.type == "quad_damage":
                        player.quad_damage = True
                        player.quad_damage_start_time = self.current_time
                        player.bomb_capacity += QUAD_DAMAGE_POWER
                        player.fire_power += QUAD_DAMAGE_POWER
                        qd_sound.play()
                    self.powerups.remove(pu)
                    
        # Use adjustable powerup logic
        self.place_quad_damage_powerup()
        
        # Handle crushing walls feature
        self.handle_crushing_walls()
        
        alive_players = [p for p in self.players if p.alive]
        if len(alive_players) <= 1:
            if alive_players:
                alive_players[0].trophies += 1
                if alive_players[0].trophies >= self.prep_trophy_threshold:
                    self.game_state = "champion"
                else:
                    self.game_state = "win"
            else:
                self.game_state = "win"   
            
class Screen:
    def __init__(self):
        self.surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
        self.window_size = INITIAL_WINDOW_SIZE
        self.window = None
    
    def set_window(self, window):
        self.window = window
    
    def update_window_size(self, window_size):
        self.window_size = window_size
    
    def draw_startup(self,Game):
        elapsed = Game.current_time - Game.startup_start_time
        if elapsed < 2000:
            alpha = 255
        elif elapsed < 2800:
            alpha = int(255 * (2500 - elapsed) / 500)
        else:
            alpha = 0
            
        draw_title_page(self.surface, alpha)
        
        if int(elapsed) >= 2200:
            draw_controls(self.surface, Game.players)

            # Display "Press Enter to start the game" message
            start_text = font_small.render("Press Enter to start the game", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            self.surface.blit(start_text, start_rect)
            
    def draw_game_prep(self, Game):
        # Gray background panels and minimalist UI
        self.surface.fill(COLOR_BG)

        left_panel = np.array([40, 80, BASE_WIDTH//2 - 60, BASE_HEIGHT - 160], dtype=np.float64)
        right_panel = np.array([BASE_WIDTH//2 + 20, 80, BASE_WIDTH//2 - 60, BASE_HEIGHT - 160], dtype=np.float64)
        pygame.draw.rect(self.surface, (70,70,70), left_panel)
        pygame.draw.rect(self.surface, (70,70,70), right_panel)
        pygame.draw.rect(self.surface, (120,120,120), left_panel, 1)
        pygame.draw.rect(self.surface, (120,120,120), right_panel, 1)

        title_font = pygame.font.SysFont("arial", 32, bold=True)
        self.surface.blit(title_font.render("Players", True, (255,255,255)), (left_panel[0]+10, left_panel[1]-36))
        self.surface.blit(title_font.render("Game Settings", True, (255,255,255)), (right_panel[0]+10, right_panel[1]-36))

        # Left: players section
        y = left_panel[1] + 10
        line_h = 34
        sel_color = (255,255,160)
        norm = (255,255,255)
        # Number of players
        selected = (Game.prep_section=='players' and Game.prep_cursor_row==0)
        self.surface.blit(font_small.render(f"Players: {Game.prep_num_players}", True, sel_color if selected else norm), (left_panel[0]+12, y))
        pygame.draw.line(self.surface, (110,110,110), (left_panel[0]+10, y+line_h-8), (left_panel[0]+left_panel[2]-10, y+line_h-8), 1)
        y += line_h

        for i in range(Game.prep_num_players):
            row_sel = (Game.prep_section=='players' and Game.prep_cursor_row==i+1)
            name_c = sel_color if (row_sel and Game.prep_cursor_col==0) else norm
            col_c = sel_color if (row_sel and Game.prep_cursor_col==1) else norm
            ctrl_c = sel_color if (row_sel and Game.prep_cursor_col==2) else norm
            name = Game.prep_player_names[i % len(Game.prep_player_names)]
            name_disp = Game.prep_custom_name + '|' if (row_sel and Game.prep_editing_name and Game.prep_cursor_col==0) else name
            self.surface.blit(font_small.render(f"{i+1}. Name: {name_disp}", True, name_c), (left_panel[0]+12, y))
            self.surface.blit(font_small.render("Color:", True, col_c), (left_panel[0]+280, y))
            color_idx = Game.prep_player_colors[i % len(Game.prep_player_colors)]
            sw = np.array([left_panel[0]+350, y+6, 26, 20], dtype=np.float64)
            pygame.draw.rect(self.surface, colors[color_idx % len(colors)], sw)
            pygame.draw.rect(self.surface, (255,255,255), sw, 1)
            self.surface.blit(font_small.render("Controls", True, ctrl_c), (left_panel[0]+410, y))
            pygame.draw.line(self.surface, (110,110,110), (left_panel[0]+10, y+line_h-8), (left_panel[0]+left_panel[2]-10, y+line_h-8), 1)
            y += line_h

        # Right: game settings
        settings = [
            ("Initial Bomb Capacity", 'prep_initial_bomb_capacity', 1, 10, 1),
            ("Initial Fire Power", 'prep_initial_fire_power', 1, 10, 1),
            ("Player Speed", 'prep_player_speed', 100, 600, 10),
            ("QD Probability", 'prep_qd_probability', 0.0, 0.02, 0.0005),
            ("QD Delay (s)", 'prep_qd_delay', 0, 600, 5),
            ("Crush Delay (s)", 'prep_crushing_delay', 0, 600, 5),
            ("Crush Min Destroyable", 'prep_crushing_min_destroyable', 0, 200, 1),
            ("Trophy Threshold", 'prep_trophy_threshold', 1, 10, 1),
        ]

        y = right_panel[1] + 10
        for idx, (label, attr, _mn, _mx, _st) in enumerate(settings):
            val = getattr(Game, attr)
            sel = (Game.prep_section=='game' and Game.prep_game_cursor==idx)
            edit_indicator = " [EDIT]" if (sel and Game.prep_editing_mode) else ""
            self.surface.blit(font_small.render(f"{label}: {val}{edit_indicator}", True, sel_color if sel else norm), (right_panel[0]+12, y))
            pygame.draw.line(self.surface, (110,110,110), (right_panel[0]+10, y+line_h-8), (right_panel[0]+right_panel[2]-10, y+line_h-8), 1)
            y += line_h

        # Add "Start Game" option
        start_sel = (Game.prep_section=='game' and Game.prep_game_cursor==9)
        start_text = ">>> START GAME <<<"
        start_color = (120, 255, 120) if start_sel else (200, 200, 200)
        self.surface.blit(font_small.render(start_text, True, start_color), (right_panel[0]+12, y))
        
        # Footer with mode indication
        mode_text = "[EDIT MODE]" if Game.prep_editing_mode else "[NAVIGATE]"
        footer_text = f"{mode_text}   TAB: Switch   Arrows: Navigate/Change   ENTER: Edit/Start   ESC: Back"
        footer = pygame.font.SysFont("arial", 20).render(footer_text, True, (255,255,255))
        self.surface.blit(footer, (40, BASE_HEIGHT-46))

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



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
        # Handle both local players (with controls) and client players (web_keys only)
        if self.controls is not None:
            # Local player - use local controls + web keys
            if is_key_pressed(self.controls['up']) or (mapped_web_keys and 'up' in mapped_web_keys):
                direction[1] -= 1
            if is_key_pressed(self.controls['down']) or (mapped_web_keys and 'down' in mapped_web_keys):
                direction[1] += 1
            if is_key_pressed(self.controls['left']) or (mapped_web_keys and 'left' in mapped_web_keys):
                direction[0] -= 1
            if is_key_pressed(self.controls['right']) or (mapped_web_keys and 'right' in mapped_web_keys):
                direction[0] += 1
        else:
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

        # Handle bomb placement for both local and client players
        if self.controls is not None:
            # Local player - use local controls + web keys
            if is_key_pressed(self.controls['bomb']) or (mapped_web_keys and 'space' in mapped_web_keys):  
                self.drop_bomb(bombs, current_time)
        else:
            # Client player - use web keys only
            if mapped_web_keys and 'space' in mapped_web_keys:  
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
        self.game_state = "game_prep"  # Start directly in prep mode for testing
        print(f"Game initialized with state: {self.game_state}")
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
        
        # Lobby navigation system
        self.prep_cursor_row = 0  # Row in current section
        self.prep_cursor_col = max(0, self.prep_num_players - 1)  # Column in current section (0-based, so -1)
        self.prep_section = 'local_players'  # 'local_players' or 'start_game'
        self.prep_editing_name = False  # Whether we're editing a player name
        self.prep_name_edit_index = 0  # Which player name we're editing
        self.prep_web_player_names = {}  # Store web player names {global_id: name}
        self.prep_web_player_colors = {}  # Store web player colors {global_id: color_index}
        
        # Track if prep screen has been shown
        self.prep_screen_completed = False
        
        # Create initial players based on current settings
        self.create_players()
    
    def get_all_players_info(self):
        """Get all players (local + client) information"""
        all_players = []
        global_player_id = 1
        
        # Add local players first
        for i in range(self.prep_num_players):
            player_name = self.prep_player_names[i % len(self.prep_player_names)]
            color_idx = self.prep_player_colors[i % len(self.prep_player_colors)]
            all_players.append({
                'id': global_player_id,
                'name': player_name,
                'color': color_idx,
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
                if client_info.get('registered', False):
                    client_players = client_info.get('players', [])
                    for player_id in client_players:
                        # Use stored name and color if available, otherwise use defaults
                        stored_name = self.prep_web_player_names.get(global_player_id, f"Client {client_id} P{player_id}")
                        stored_color = self.prep_web_player_colors.get(global_player_id, global_player_id % len(colors))
                        
                        all_players.append({
                            'id': global_player_id,
                            'name': stored_name,
                            'color': stored_color,
                            'type': 'client',
                            'source': (client_id, player_id),  # Client and player ID
                            'controls': None  # Client players don't use local controls
                        })
                        global_player_id += 1
        
        return all_players
    
    def create_players(self):
        """Create players based on current prep screen settings and client players"""
        self.players = []
        all_players_info = self.get_all_players_info()
        
        for player_info in all_players_info:
            if player_info['type'] == 'local':
                # Create local player
                p = Player(1, 1, 
                          colors[player_info['color'] % len(colors)], 
                          player_info['controls'], 
                          player_info['name'])
                p.is_local = True
                p.client_id = None
                p.client_player_id = None
            else:
                # Create client player
                p = Player(1, 1, 
                          colors[player_info['color'] % len(colors)], 
                          None,  # No local controls for client players
                          player_info['name'])
                p.is_local = False
                p.client_id = player_info['source'][0]
                p.client_player_id = player_info['source'][1]
            
            p.global_id = player_info['id']
            self.players.append(p)
    
    def _refresh_client_status(self):
        """Refresh client status from server"""
        try:
            import requests
            response = requests.get('http://localhost:8080/status', timeout=0.5)
            if response.status_code == 200:
                self._cached_status = response.json()
            else:
                self._cached_status = None
        except Exception as e:
            self._cached_status = None
    
    def init_game(self):
        # Refresh client status before creating players
        self._refresh_client_status()
        
        # Recreate players based on current prep settings and client players
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
            # Apply initial gameplay params (use defaults)
            player.bomb_capacity = 1
            player.fire_power = 1
            player.speed = PLAYER_SPEED
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
        # Use default values for crushing walls
        crushing_delay = 60  # 60 seconds delay
        crushing_min_destroyable = 20  # Minimum destroyable cells
        
        if len(alive_players) == 2 and \
           (self.current_time - self.game_start_time) >= crushing_delay * 1000 and \
           self.count_destroyable_cells() < crushing_min_destroyable:
            
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
            # Calculate animation timing (same as in draw_explosions)
            norm = (self.current_time - explosion.start_time) / EXPLOSION_DURATION
            norm = min(norm, 1)
            if norm < 0.2:
                arm_factor = norm / 0.2
            elif norm <= 0.7:
                arm_factor = 1
            else:
                arm_factor = (1 - (norm - 0.7) / 0.3)
            
            # Only check for kills when explosion arms are active
            if arm_factor > 0:
                # Get explosion center
                cx, cy = explosion.cells[0]
                
                # Calculate maximum arm lengths in each direction
                up_max = max([cy - cell[1] for cell in explosion.cells if cell[0] == cx and cell[1] < cy] or [0])
                down_max = max([cell[1] - cy for cell in explosion.cells if cell[0] == cx and cell[1] > cy] or [0])
                left_max = max([cx - cell[0] for cell in explosion.cells if cell[1] == cy and cell[0] < cx] or [0])
                right_max = max([cell[0] - cx for cell in explosion.cells if cell[1] == cy and cell[0] > cx] or [0])
                
                # Calculate current arm lengths based on animation
                up_length = int(arm_factor * up_max)
                down_length = int(arm_factor * down_max)
                left_length = int(arm_factor * left_max)
                right_length = int(arm_factor * right_max)
                
                # Determine which cells are currently active based on arm lengths
                active_cells = []
                
                # Add center cell
                active_cells.append((cx, cy))
                
                # Add cells in each direction based on current arm length
                for i in range(1, up_length + 1):
                    active_cells.append((cx, cy - i))
                for i in range(1, down_length + 1):
                    active_cells.append((cx, cy + i))
                for i in range(1, left_length + 1):
                    active_cells.append((cx - i, cy))
                for i in range(1, right_length + 1):
                    active_cells.append((cx + i, cy))
                
                # Check for player deaths only in currently active cells
                for player in self.players:
                    if player.alive:
                        for cell in active_cells:
                            explosion_rect = np.array([cell[0]*CELL_SIZE, cell[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
                            if circle_rect_collision((player.pos[0], player.pos[1]), player.collision_radius, explosion_rect):
                                player.alive = False
                                player.death_animation_time = 1000  # 1 second death animation
                                death_sound.play()
                                break
            
            # Remove explosion when it ends
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
                self.explosions.remove(explosion)
                    
    def place_quad_damage_powerup(self):        
        # Use parameters from bm_params
        from bm_params import QUAD_DAMAGE_DELAY, QUAD_DAMAGE_PROBABILITY
        
        # Check if enough time has passed since game start
        if (get_ticks() - self.game_start_time) >= QUAD_DAMAGE_DELAY * 1000:
            # Only place if no quad damage powerup already exists
            if not any(pu.type == "quad_damage" for pu in self.powerups):
                # Find empty cells
                empty_cells = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH) if self.board[y][x] == EMPTY]
                if empty_cells and random.random() < QUAD_DAMAGE_PROBABILITY:
                    x, y = random.choice(empty_cells)
                    self.powerups.append(PowerUp(x, y, "quad_damage"))
                                
    def tick(self):
        self.dt = self.clock.tick(FPS)
        self.current_time = get_ticks()                
                    
    def handle_window_events(self):
        """Handle window events using the new frontend/backend separation"""
        if self.frontend is None:
            self.frontend = FrontendManager(self)
        
        self.frontend.process_events()
    
    def set_frontend(self, frontend):
        """Set the frontend reference"""
        self.frontend = frontend
        self.screen = frontend.screen
    
    def handle_prep_key_event(self, event):
        """Handle key events for game lobby navigation"""
        # Switch between sections
        if event.key == Keys.TAB:
            self.prep_section = 'start_game' if self.prep_section == 'local_players' else 'local_players'
            self.prep_cursor_row = 0
            self.prep_cursor_col = 0
            self.prep_editing_name = False
            return
        
        # Vertical navigation between sections
        if event.key == Keys.UP:
            if self.prep_section == 'start_game':
                self.prep_section = 'local_players'
                self.prep_cursor_row = self.prep_num_players  # Go to last player
            elif self.prep_section == 'local_players':
                # Navigate within player list (row 0 = player count buttons, row 1+ = players)
                if self.prep_cursor_row > 0:
                    self.prep_cursor_row -= 1
            return
        
        if event.key == Keys.DOWN:
            if self.prep_section == 'local_players':
                # Navigate within player list (row 0 = player count buttons, row 1+ = players)
                if self.prep_cursor_row < self.prep_num_players:  # Can go up to last player
                    self.prep_cursor_row += 1
                else:
                    # Move to start game section
                    self.prep_section = 'start_game'
                    self.prep_cursor_row = 0
                    self.prep_cursor_col = 0
            return
        
        if self.prep_section == 'local_players':
            # Handle player count buttons (when cursor_row is 0)
            if self.prep_cursor_row == 0:
                if event.key == Keys.LEFT:
                    if self.prep_cursor_col > 0:
                        self.prep_cursor_col -= 1
                elif event.key == Keys.RIGHT:
                    if self.prep_cursor_col < 5:  # 6 buttons (0-5)
                        self.prep_cursor_col += 1
                elif event.key == Keys.ENTER:
                    # Select player count
                    self.prep_num_players = self.prep_cursor_col + 1
                    self.create_players()
                    # Ensure cursor stays within bounds
                    if self.prep_cursor_col >= self.prep_num_players:
                        self.prep_cursor_col = self.prep_num_players - 1
            
            # Handle player editing (when cursor_row > 0)
            elif self.prep_cursor_row > 0:
                player_index = self.prep_cursor_row - 1  # Adjust for player count buttons (row 0)
                if event.key == Keys.ENTER:
                    # Start editing name
                    self.prep_editing_name = True
                    self.prep_name_edit_index = player_index
                elif event.key == Keys.LEFT:
                    # Change color (cycle through colors)
                    all_players_info = self.get_all_players_info()
                    if player_index < len(all_players_info):
                        player_info = all_players_info[player_index]
                        if player_info['type'] == 'local':
                            # Change local player color
                            self.prep_player_colors[player_info['source']] = (self.prep_player_colors[player_info['source']] + 1) % len(colors)
                        else:
                            # Change web player color
                            current_color = self.prep_web_player_colors.get(player_info['id'], player_info['color'])
                            self.prep_web_player_colors[player_info['id']] = (current_color + 1) % len(colors)
                elif event.key == Keys.RIGHT:
                    # Change color (cycle backwards)
                    all_players_info = self.get_all_players_info()
                    if player_index < len(all_players_info):
                        player_info = all_players_info[player_index]
                        if player_info['type'] == 'local':
                            # Change local player color
                            self.prep_player_colors[player_info['source']] = (self.prep_player_colors[player_info['source']] - 1) % len(colors)
                        else:
                            # Change web player color
                            current_color = self.prep_web_player_colors.get(player_info['id'], player_info['color'])
                            self.prep_web_player_colors[player_info['id']] = (current_color - 1) % len(colors)
        
        elif self.prep_section == 'start_game':
            # Start game
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
                    # Edit local player name
                    if len(self.prep_player_names[player_info['source']]) < 15:
                        self.prep_player_names[player_info['source']] += event.unicode
                else:
                    # Edit web player name
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
                    # Delete character from local player name
                    if len(self.prep_player_names[player_info['source']]) > 0:
                        self.prep_player_names[player_info['source']] = self.prep_player_names[player_info['source']][:-1]
                else:
                    # Delete character from web player name
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
        player_id = event.get('player_id', 0)
        client_id = event.get('client_id', 0)
        
        if not hasattr(self, 'web_keys_by_player'):
            self.web_keys_by_player = {}
        
        # Find the corresponding player object
        player_obj = None
        for player in self.players:
            if (not player.is_local and 
                player.client_id == client_id and 
                player.client_player_id == player_id):
                player_obj = player
                break
        
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
                # Use default trophy threshold
                trophy_threshold = 3  # Need 3 wins to become champion
                if alive_players[0].trophies >= trophy_threshold:
                    self.game_state = "champion"
                else:
                    self.game_state = "win"
            else:
                self.game_state = "win"   
            
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



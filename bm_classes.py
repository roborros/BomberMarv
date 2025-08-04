import pygame
from bm_params import *
from lib_collisions import *
from lib_grid import *
from bm_sounds import *
from bm_drawing import *



class Player:
    def __init__(self, grid_x, grid_y, color, controls, name):
        self.start_grid_x = grid_x
        self.start_grid_y = grid_y
        self.pos = pygame.math.Vector2(grid_x * CELL_SIZE + CELL_SIZE // 2,
                                        grid_y * CELL_SIZE + CELL_SIZE // 2)
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
        self.direction = pygame.math.Vector2(0, 0)  # Initialize direction

    def get_circle(self):
        return (self.pos, self.draw_radius)

    def get_grid_pos(self):
        return (int(self.pos.x // CELL_SIZE), int(self.pos.y // CELL_SIZE))

    def update(self, dt, board, bombs, current_time, web_keys=None):
        if not self.alive:
            if self.death_animation_time > 0:
                self.death_animation_time -= dt
            self.direction = pygame.math.Vector2(0, 0)  # No direction if dead
            return
        keys = pygame.key.get_pressed()
        direction = pygame.math.Vector2(0, 0)
        # Remap all web_keys using browser_key_to_pygame
        mapped_web_keys = set()
        if web_keys:
            for k in web_keys:
                mapped = browser_key_to_pygame(k)
                if mapped:
                    mapped_web_keys.add(mapped.lower())
        # Use mapped_web_keys as an OR with local keys
        if keys[self.controls['up']] or (mapped_web_keys and 'up' in mapped_web_keys):
            direction.y -= 1
        if keys[self.controls['down']] or (mapped_web_keys and 'down' in mapped_web_keys):
            direction.y += 1
        if keys[self.controls['left']] or (mapped_web_keys and 'left' in mapped_web_keys):
            direction.x -= 1
        if keys[self.controls['right']] or (mapped_web_keys and 'right' in mapped_web_keys):
            direction.x += 1
        if direction.length_squared() > 1:
            direction = direction.normalize()
            self.animation_time += dt
        else:
            self.animation_time = 0
            
        # Store original direction for green cell detection (same logic as draw_player_directions)
        original_direction = direction.copy()
        self.direction = direction  # Always store the current direction vector

        # Corner sliding assistance - help when trying to move toward green cells but hitting corners
        if original_direction.length_squared() > 0:  # Player is trying to move
            # Check if target cell would be green (same logic as draw_player_directions)
            cell_x = int((self.pos.x + original_direction.x * CELL_SIZE) // CELL_SIZE)
            cell_y = int((self.pos.y + original_direction.y * CELL_SIZE) // CELL_SIZE)
            
            # Check if target cell is empty and in bounds
            target_is_empty = (0 <= cell_y < len(board) and 0 <= cell_x < len(board[0]) and 
                              board[cell_y][cell_x] == EMPTY)
            
            # Only help with pure cardinal directions when target is empty (green)
            if target_is_empty:
                dx, dy = int(original_direction.x), int(original_direction.y)
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
                        slide_direction = pygame.math.Vector2(0, 0)
                        
                        # Get position within current cell
                        cell_pos_x = (self.pos.x % CELL_SIZE) / CELL_SIZE
                        cell_pos_y = (self.pos.y % CELL_SIZE) / CELL_SIZE
                        
                        # Apply corner sliding based on position within cell
                        if dx != 0:  # Moving horizontally
                            if cell_pos_y < 0.4:  # Upper part - slide up
                                slide_direction.y = 0.6
                            elif cell_pos_y > 0.6:  # Lower part - slide down  
                                slide_direction.y = -0.6
                        
                        if dy != 0:  # Moving vertically
                            if cell_pos_x < 0.4:  # Left part - slide left
                                slide_direction.x = 0.6
                            elif cell_pos_x > 0.6:  # Right part - slide right
                                slide_direction.x = -0.6
                        
                        # Apply the corner sliding
                        if slide_direction.length_squared() > 0:
                            direction = original_direction + slide_direction
                            if direction.length_squared() > 1:
                                direction = direction.normalize()

        if keys[self.controls['bomb']] or (mapped_web_keys and 'space' in mapped_web_keys):  
            self.drop_bomb(bombs, current_time)

        original_pos = self.pos.copy()
        spd = self.speed if not self.quad_damage else int(self.speed * QUAD_DAMAGE_SPEEDUP)
        self.pos += direction * spd * (dt / 1000.0)

        # Update bomb ownership if the player has left their bomb cell.
        for bomb in bombs:
            if bomb.owner == self and not bomb.owner_left:
                if self.get_grid_pos() != (bomb.x, bomb.y):
                    bomb.owner_left = True

        # Use our new collision check.
        if self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos):
            # Try moving only along x
            self.pos = original_pos + pygame.math.Vector2(direction.x * spd * (dt / 1000.0), 0)
            if not (self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos)):
                return
            # Try moving only along y
            self.pos = original_pos + pygame.math.Vector2(0, direction.y * spd * (dt / 1000.0))
            if not (self.collides_with_walls(board) or self.collides_with_bombs(bombs, original_pos)):
                return
            # Both attempts failed, revert.
            self.pos = original_pos

        # Handle quad damage duration.
        if self.quad_damage and pygame.time.get_ticks() - self.quad_damage_start_time > QUAD_DAMAGE_TIME * 1000:
            self.quad_damage = False
            self.bomb_capacity -= QUAD_DAMAGE_POWER
            self.fire_power -= QUAD_DAMAGE_POWER
            
    def collides_with_walls(self, board):
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if board[y][x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                    wall_rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    if circle_rect_collision((self.pos.x, self.pos.y), self.collision_radius, wall_rect):
                        return True
        return False

    def collides_with_bombs(self, bombs, original_pos):
        for bomb in bombs:
            # Skip your own bomb that hasn't been left yet.
            if bomb.owner == self and not bomb.owner_left:
                continue

            # Get bomb's cell and center.
            bomb_cell = (bomb.x, bomb.y)
            bomb_center = pygame.math.Vector2(bomb.x * CELL_SIZE + CELL_SIZE / 2,
                                                bomb.y * CELL_SIZE + CELL_SIZE / 2)
            # If the player originally was in the bomb's cell:
            if (int(original_pos.x // CELL_SIZE), int(original_pos.y // CELL_SIZE)) == bomb_cell:
                # If the new position is further from the bomb center than the starting position, let the player exit:
                if (self.pos - bomb_center).length()+int(CELL_SIZE/10) > (original_pos - bomb_center).length():
                    continue  # allow the move out

            # Otherwise (or if not exiting), use a reduced bomb collision box.
            margin = CELL_SIZE * 0.35  # tweak margin as needed
            bomb_rect = pygame.Rect(
                bomb.x * CELL_SIZE + margin,
                bomb.y * CELL_SIZE + margin,
                CELL_SIZE - 2 * margin,
                CELL_SIZE - 2 * margin
            )
            if circle_rect_collision((self.pos.x, self.pos.y), self.collision_radius, bomb_rect):
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
        self.pos = pygame.math.Vector2(self.start_grid_x * CELL_SIZE + CELL_SIZE // 2,
                                        self.start_grid_y * CELL_SIZE + CELL_SIZE // 2)
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
        self.game_start_time = pygame.time.get_ticks()
        self.players = []
        self.game_state = "startup"
        self.startup_start_time = pygame.time.get_ticks()
        self.current_time = self.startup_start_time
        self.window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.game_surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
        self.dt = 0
        
        self.window_size = INITIAL_WINDOW_SIZE
        self.is_fullscreen = False
        self.web_keys = set()  # Track keys pressed from web client
        
<<<<<<< HEAD
        # Crushing walls feature variables
        self.crushing_walls_active = False
        self.crushing_walls_last_time = 0
        self.crushing_walls_pattern = []
        self.crushing_walls_index = 0
        
        for i in range(NUM_PLAYERS):
            p = Player(1, 1, colors[i % len(colors)], controls_list[i % len(controls_list)], player_names[i % len(player_names)])
=======
        # Game preparation screen state
        self.prep_num_players = NUM_PLAYERS
        self.prep_player_names = player_names.copy()
        self.prep_player_colors = list(range(len(colors)))  # Store color indices instead of colors
        self.prep_controls = [controls.copy() for controls in controls_list]
        
        # Simple navigation system
        self.prep_cursor_row = 0  # 0=num_players, 1-N=players, N+1=start_game
        self.prep_cursor_col = 0  # 0=name, 1=color, 2=controls (only when on player rows)
        
        # Editing states
        self.prep_editing_control = None  # Which control key we're currently changing
        self.prep_editing_name = False  # Whether we're typing a custom name
        self.prep_custom_name = ""  # Buffer for custom name input
        
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
>>>>>>> 0e77396 (checkpoint before checking out cursor/add-indestructible-cells-to-increase-pressure-2048)
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
        self.game_start_time = pygame.time.get_ticks() + 2000  # Add a 2-second freeze time
        
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
                    test_pos = pygame.math.Vector2(
                        new_grid_x * CELL_SIZE + CELL_SIZE // 2,
                        new_grid_y * CELL_SIZE + CELL_SIZE // 2
                    )
                    
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
           (self.current_time - self.game_start_time) >= CRUSHING_WALLS_DELAY * 1000 and \
           self.count_destroyable_cells() < CRUSHING_WALLS_MIN_DESTROYABLE:
            
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
                                player.pos = pygame.math.Vector2(
                                    adj_x * CELL_SIZE + CELL_SIZE // 2,
                                    adj_y * CELL_SIZE + CELL_SIZE // 2
                                )
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
                            explosion_rect = pygame.Rect(cell[0]*CELL_SIZE, cell[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE)
                            if circle_rect_collision((player.pos.x, player.pos.y), player.collision_radius, explosion_rect):
                                player.alive = False
                                player.death_animation_time = 1000  # 1 second death animation
                                death_sound.play()
                                break           
                self.explosions.remove(explosion)
                    
    def place_quad_damage_powerup(self):        
        if (pygame.time.get_ticks() - self.game_start_time) >= QUAD_DAMAGE_DELAY*1000:  # 2 minutes
            if not any(pu.type == "quad_damage" for pu in self.powerups):
                empty_cells = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH) if self.board[y][x] == EMPTY]
                if empty_cells and random.random() < QUAD_DAMAGE_PROBABILITY:
                    x, y = random.choice(empty_cells)
                    self.powerups.append(PowerUp(x, y, "quad_damage"))
                                
    def tick(self):
        self.dt = self.clock.tick(FPS)
        self.current_time = pygame.time.get_ticks()                
                    
    def handle_window_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                self.window_size = event.size
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    self.is_fullscreen = not self.is_fullscreen
                    if self.is_fullscreen:
                        window = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
                        self.window_size = window.get_size()
                    else:
                        window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
                        self.window_size = INITIAL_WINDOW_SIZE
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    print(f"ENTER pressed, game_state={self.game_state}")
                    if self.game_state == "startup":
                        self.game_state = "game_prep"
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
            
        if self.prep_cursor_row == 0:
            # Number of players row - nothing special on ENTER
            pass
        elif 1 <= self.prep_cursor_row <= self.prep_num_players:
            # Player row
            player_idx = self.prep_cursor_row - 1
            if self.prep_cursor_col == 0:  # Name
                # Start custom name input
                self.prep_editing_name = True
                self.prep_custom_name = self.prep_player_names[player_idx]
            elif self.prep_cursor_col == 1:  # Color
                # Nothing special - use left/right to change
                pass
            elif self.prep_cursor_col == 2:  # Controls
                # Start controls editing
                self.prep_editing_control = 'up'
        elif self.prep_cursor_row == self.prep_num_players + 1:
            # Start game
            self.init_game()
            self.game_state = "get_ready"
    
    def handle_prep_key_event(self, event):
        """Handle key events for game prep screen navigation"""
        # Handle text input for custom names
        if self.prep_editing_name:
            if event.key == pygame.K_BACKSPACE:
                self.prep_custom_name = self.prep_custom_name[:-1]
            elif event.key == pygame.K_ESCAPE:
                # Cancel name editing
                self.prep_editing_name = False
                self.prep_custom_name = ""
            elif event.unicode and event.unicode.isprintable() and len(self.prep_custom_name) < 12:
                self.prep_custom_name += event.unicode
            return
        
        if self.prep_editing_control:
            # We're editing a control key
            if event.key != pygame.K_ESCAPE:  # Don't allow ESC as a control key
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
        
        # Simple row/column navigation
        if event.key == pygame.K_UP:
            # Move up one row
            if self.prep_cursor_row > 0:
                self.prep_cursor_row -= 1
                # Reset column to 0 when moving to number of players row
                if self.prep_cursor_row == 0:
                    self.prep_cursor_col = 0
        
        elif event.key == pygame.K_DOWN:
            # Move down one row
            max_row = self.prep_num_players + 1  # +1 for start game row
            if self.prep_cursor_row < max_row:
                self.prep_cursor_row += 1
                # Reset column to 0 when moving to start game row
                if self.prep_cursor_row == max_row:
                    self.prep_cursor_col = 0
        
        elif event.key == pygame.K_LEFT:
            if self.prep_cursor_row == 0:
                # Number of players row - decrease number
                self.prep_num_players = max(2, self.prep_num_players - 1)
                self.create_players()
                # Adjust cursor if it's beyond the new number of players
                if self.prep_cursor_row > self.prep_num_players:
                    self.prep_cursor_row = self.prep_num_players
            elif 1 <= self.prep_cursor_row <= self.prep_num_players:
                # Player row - move left or change value
                player_idx = self.prep_cursor_row - 1
                if self.prep_cursor_col == 0:  # Name
                    # Change to previous name
                    try:
                        current_idx = player_names.index(self.prep_player_names[player_idx])
                        new_idx = (current_idx - 1) % len(player_names)
                        self.prep_player_names[player_idx] = player_names[new_idx]
                        self.create_players()
                    except ValueError:
                        # Custom name, cycle to last predefined name
                        self.prep_player_names[player_idx] = player_names[-1]
                        self.create_players()
                elif self.prep_cursor_col == 1:  # Color
                    # Change to previous color
                    current_color = self.prep_player_colors[player_idx]
                    self.prep_player_colors[player_idx] = (current_color - 1) % len(colors)
                    self.create_players()
                elif self.prep_cursor_col > 0:
                    # Move to previous column
                    self.prep_cursor_col -= 1
        
        elif event.key == pygame.K_RIGHT:
            if self.prep_cursor_row == 0:
                # Number of players row - increase number
                self.prep_num_players = min(6, self.prep_num_players + 1)
                self.create_players()
            elif 1 <= self.prep_cursor_row <= self.prep_num_players:
                # Player row - move right or change value
                player_idx = self.prep_cursor_row - 1
                if self.prep_cursor_col == 0:  # Name
                    # Change to next name
                    try:
                        current_idx = player_names.index(self.prep_player_names[player_idx])
                        new_idx = (current_idx + 1) % len(player_names)
                        self.prep_player_names[player_idx] = player_names[new_idx]
                        self.create_players()
                    except ValueError:
                        # Custom name, cycle to first predefined name
                        self.prep_player_names[player_idx] = player_names[0]
                        self.create_players()
                elif self.prep_cursor_col == 1:  # Color
                    # Change to next color
                    current_color = self.prep_player_colors[player_idx]
                    self.prep_player_colors[player_idx] = (current_color + 1) % len(colors)
                    self.create_players()
                elif self.prep_cursor_col < 2:
                    # Move to next column
                    self.prep_cursor_col += 1
        
        elif event.key == pygame.K_TAB:
            if 1 <= self.prep_cursor_row <= self.prep_num_players:
                # Quick switch between columns in player rows
                self.prep_cursor_col = (self.prep_cursor_col + 1) % 3
        
        elif event.key == pygame.K_ESCAPE:
            # Go back to startup
            self.game_state = "startup"
            self.startup_start_time = pygame.time.get_ticks()
                
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
                    
        self.place_quad_damage_powerup()
        
        # Handle crushing walls feature
        self.handle_crushing_walls()
        
        alive_players = [p for p in self.players if p.alive]
        if len(alive_players) <= 1:
            if alive_players:
                alive_players[0].trophies += 1
                if alive_players[0].trophies >= TROPHY_WIN_THRESHOLD:
                    self.game_state = "champion"
                else:
                    self.game_state = "win"
            else:
                self.game_state = "win"   
            
class Screen:
    def __init__(self):
        self.surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
    
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
        # Simple background
        self.surface.fill((40, 45, 50))
        
        # Title
        title_font = pygame.font.SysFont("arial", 48, bold=True)
        title_text = title_font.render("🎮 GAME SETUP", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(BASE_WIDTH // 2, 60))
        self.surface.blit(title_text, title_rect)
        
        y_start = 140
        row_height = 60
        
        # Row 0: Number of players
        row_y = y_start
        is_selected = (Game.prep_cursor_row == 0)
        bg_color = (70, 90, 120) if is_selected else (50, 55, 60)
        
        row_rect = pygame.Rect(50, row_y - 5, BASE_WIDTH - 100, row_height - 10)
        pygame.draw.rect(self.surface, bg_color, row_rect, border_radius=10)
        if is_selected:
            pygame.draw.rect(self.surface, (255, 255, 100), row_rect, 3, border_radius=10)
        
        text_color = (255, 255, 100) if is_selected else (255, 255, 255)
        num_text = font_small.render(f"Number of Players: {Game.prep_num_players}", True, text_color)
        self.surface.blit(num_text, (70, row_y + 15))
        
        if is_selected:
            hint_text = font_small.render("← → to change  ENTER to confirm", True, (255, 255, 100))
            self.surface.blit(hint_text, (BASE_WIDTH - 300, row_y + 15))
        
        # Player rows
        for i in range(Game.prep_num_players):
            row_y = y_start + (i + 1) * row_height
            is_selected = (Game.prep_cursor_row == i + 1)
            
            # Row background
            bg_color = (70, 90, 120) if is_selected else (50, 55, 60)
            row_rect = pygame.Rect(50, row_y - 5, BASE_WIDTH - 100, row_height - 10)
            pygame.draw.rect(self.surface, bg_color, row_rect, border_radius=10)
            if is_selected:
                pygame.draw.rect(self.surface, (255, 255, 100), row_rect, 3, border_radius=10)
            
            # Player number badge
            color_idx = Game.prep_player_colors[i % len(Game.prep_player_colors)]
            badge_color = colors[color_idx % len(colors)]
            badge_rect = pygame.Rect(70, row_y + 10, 35, 30)
            pygame.draw.rect(self.surface, badge_color, badge_rect, border_radius=5)
            pygame.draw.rect(self.surface, (255, 255, 255), badge_rect, 2, border_radius=5)
            
            num_text = font_small.render(str(i + 1), True, (255, 255, 255))
            num_rect = num_text.get_rect(center=(87, row_y + 25))
            self.surface.blit(num_text, num_rect)
            
            # Player name
            name_x = 120
            name = Game.prep_player_names[i % len(Game.prep_player_names)]
            
            if Game.prep_editing_name and is_selected and Game.prep_cursor_col == 0:
                display_name = Game.prep_custom_name + "|"
                name_color = (255, 255, 100)
            else:
                display_name = name
                name_color = (255, 255, 100) if is_selected and Game.prep_cursor_col == 0 else (255, 255, 255)
            
            name_text = font_small.render(display_name, True, name_color)
            self.surface.blit(name_text, (name_x, row_y + 15))
            
            # Color circles
            color_start_x = 300
            for c_idx, color in enumerate(colors):
                circle_x = color_start_x + c_idx * 30
                circle_pos = (circle_x, row_y + 25)
                pygame.draw.circle(self.surface, color, circle_pos, 8)
                
                # Highlight current color
                if color_idx == c_idx:
                    pygame.draw.circle(self.surface, (255, 255, 255), circle_pos, 10, 3)
                    if is_selected and Game.prep_cursor_col == 1:
                        pygame.draw.circle(self.surface, (255, 255, 100), circle_pos, 12, 2)
                else:
                    pygame.draw.circle(self.surface, (150, 150, 150), circle_pos, 8, 1)
            
            # Controls
            controls_x = 500
            controls = Game.prep_controls[i % len(Game.prep_controls)]
            controls_color = (255, 255, 100) if is_selected and Game.prep_cursor_col == 2 else (200, 200, 200)
            
            up_key = pygame.key.name(controls['up']).upper()
            bomb_key = pygame.key.name(controls['bomb']).upper()
            controls_text = f"Controls: {up_key}..."
            controls_surface = font_small.render(controls_text, True, controls_color)
            self.surface.blit(controls_surface, (controls_x, row_y + 15))
            
            # Column indicators for selected row
            if is_selected:
                if Game.prep_cursor_col == 0:  # Name
                    pygame.draw.line(self.surface, (255, 255, 100), (name_x, row_y + 40), (name_x + 150, row_y + 40), 2)
                elif Game.prep_cursor_col == 1:  # Color
                    pygame.draw.line(self.surface, (255, 255, 100), (color_start_x - 10, row_y + 40), (color_start_x + len(colors) * 30, row_y + 40), 2)
                elif Game.prep_cursor_col == 2:  # Controls
                    pygame.draw.line(self.surface, (255, 255, 100), (controls_x, row_y + 40), (controls_x + 150, row_y + 40), 2)
        
        # Start game button
        start_row_y = y_start + (Game.prep_num_players + 1) * row_height
        is_selected = (Game.prep_cursor_row == Game.prep_num_players + 1)
        
        start_rect = pygame.Rect(BASE_WIDTH // 2 - 100, start_row_y, 200, 50)
        start_color = (100, 150, 100) if is_selected else (60, 80, 60)
        pygame.draw.rect(self.surface, start_color, start_rect, border_radius=15)
        
        border_color = (255, 255, 100) if is_selected else (100, 150, 100)
        pygame.draw.rect(self.surface, border_color, start_rect, 3, border_radius=15)
        
        start_text_color = (255, 255, 255)
        start_text = font_small.render("🚀 START GAME", True, start_text_color)
        start_text_rect = start_text.get_rect(center=start_rect.center)
        self.surface.blit(start_text, start_text_rect)
        
        # Instructions
        instr_y = BASE_HEIGHT - 50
        instructions = "↑↓ Navigate  ←→ Change values  ENTER Edit/Confirm  ESC Back"
        instr_text = font_small.render(instructions, True, (200, 200, 255))
        instr_rect = instr_text.get_rect(center=(BASE_WIDTH // 2, instr_y))
        self.surface.blit(instr_text, instr_rect)

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



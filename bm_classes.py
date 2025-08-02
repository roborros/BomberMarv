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
            
        self.direction = direction  # Always store the current direction vector

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
        
        for i in range(NUM_PLAYERS):
            p = Player(1, 1, colors[i % len(colors)], controls_list[i % len(controls_list)], player_names[i % len(player_names)])
            self.players.append(p)
    
    def init_game(self):

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
                    elif self.game_state in ["win", "champion", "game_prep"]:
                        self.init_game()
                        self.game_state = "get_ready"
                
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
        self.surface.fill(COLOR_BG)
        # Draw 'Game Prep' text centered
        font = pygame.font.SysFont("arial", 60, bold=True)
        prep_text = font.render("Game Prep", True, (255, 255, 255))
        prep_rect = prep_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT // 2))
        self.surface.blit(prep_text, prep_rect)
        # Optionally: show player list, colors, etc. here

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





import pygame
from bm_params import *
from lib_collisions import *
from lib_grid import *
from bm_sounds import *

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

    def get_circle(self):
        return (self.pos, self.draw_radius)

    def get_grid_pos(self):
        return (int(self.pos.x // CELL_SIZE), int(self.pos.y // CELL_SIZE))

    def update(self, dt, board, bombs):
        if not self.alive:
            if self.death_animation_time > 0:
                self.death_animation_time -= dt
            return
        keys = pygame.key.get_pressed()
        direction = pygame.math.Vector2(0, 0)
        if keys[self.controls['up']]:
            direction.y -= 1
        if keys[self.controls['down']]:
            direction.y += 1
        if keys[self.controls['left']]:
            direction.x -= 1
        if keys[self.controls['right']]:
            direction.x += 1
        if direction.length_squared() > 0:
            direction = direction.normalize()
            self.animation_time += dt
        else:
            self.animation_time = 0

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
        
        for i in range(NUM_PLAYERS):
            p = Player(1, 1, colors[i % len(colors)], controls_list[i % len(controls_list)], player_names[i % len(player_names)])
            self.players.append(p)
    
    def init_game(self):
    
    #global board, bombs, explosions, powerups, game_start_time , players

        fixed_positions = [(1, 1), (GRID_WIDTH - 2, 1), (1, GRID_HEIGHT - 2), (GRID_WIDTH - 2, GRID_HEIGHT - 2)]
        corner_patterns = {
            (1, 1): [(0,0), (1,0), (0,1)],
            (GRID_WIDTH - 2, 1): [(0,0), (-1,0), (0,1)],
            (1, GRID_HEIGHT - 2): [(0,0), (1,0), (0,-1)],
            (GRID_WIDTH - 2, GRID_HEIGHT - 2): [(0,0), (-1,0), (0,-1)]
        }
        
        random.shuffle(self.players)

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
    
    def handle_explosion(self,explosion):
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
                    
    def place_quad_damage_powerup(self):        
        if (pygame.time.get_ticks() - self.game_start_time) >= QUAD_DAMAGE_DELAY*1000:  # 2 minutes
            if not any(pu.type == "quad_damage" for pu in self.powerups):
                empty_cells = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH) if self.board[y][x] == EMPTY]
                if empty_cells and random.random() < QUAD_DAMAGE_PROBABILITY:
                    x, y = random.choice(empty_cells)
                    self.powerups.append(PowerUp(x, y, "quad_damage"))
                                
    def tick(self):
        self.current_time = pygame.time.get_ticks()                
                    

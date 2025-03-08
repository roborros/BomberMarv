from bm_params import *
import random


def clear_safe_zone(board, sx, sy, offsets):
    for dx, dy in offsets:
        nx, ny = sx + dx, sy + dy
        if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT:
            if board[ny][nx] == DESTRUCTIBLE:
                board[ny][nx] = EMPTY

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

def generate_maze():
    board = [[EMPTY for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            if x == 0 or y == 0 or x == GRID_WIDTH - 1 or y == GRID_HEIGHT - 1:
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
        player.automation_direction = pygame.math.Vector2(0, 0)
    
    # Decrement the timer by the elapsed time
    player.automation_timer -= dt
    if player.automation_timer <= 0:
        # Set a new timer between 500 ms and 1500 ms.
        player.automation_timer = random.randint(500, 1500)
        # Choose a random direction; sometimes the bot stops.
        possible_directions = [
            pygame.math.Vector2(0, 0),
            pygame.math.Vector2(1, 0),
            pygame.math.Vector2(-1, 0),
            pygame.math.Vector2(0, 1),
            pygame.math.Vector2(0, -1)
        ]
        player.automation_direction = random.choice(possible_directions)
    
    # Simulate the movement using the automation direction.
    spd = player.speed if not player.quad_damage else int(player.speed * QUAD_DAMAGE_SPEEDUP)
    original_pos = player.pos.copy()
    # Compute the change in position (dt is in ms)
    delta_move = player.automation_direction * spd * (dt / 1000.0)
    player.pos += delta_move
    
    # If the new position would result in a collision, revert.
    if player.collides_with_walls(board) or player.collides_with_bombs(bombs, original_pos):
        player.pos = original_pos

    # Occasionally drop a bomb (e.g. ~1% chance each frame)
    if random.random() < 0.01:
        player.drop_bomb(bombs, pygame.time.get_ticks())
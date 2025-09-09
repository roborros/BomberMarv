"""
New drawing module using abstract rendering backend
This replaces pygame-specific drawing with backend-agnostic calls
"""
from rendering_backend import RenderingBackend
from bm_params import *
import math
import pygame  # Still needed for pygame.time.get_ticks() in some functions

def draw_brick_pattern(backend: RenderingBackend, x: float, y: float, width: float, height: float):
    """Draw brick pattern using backend"""
    brick_height = height // 4
    brick_width = width // 3
    mortar_color = (80, 80, 80)
    rows = 2
    
    for row in range(rows):
        offset = brick_width // 2 if row % 2 == 1 else 0
        row_y = y + row * (height // rows)
        brick_x = x + offset
        
        while brick_x < x + width:
            backend.draw_rect(brick_x, row_y, brick_width, height // rows, 
                            COLOR_DESTRUCTIBLE, 1, mortar_color)
            brick_x += brick_width

def draw_title_page(backend: RenderingBackend, alpha: float = 1.0):
    """Draw title page"""
    backend.fill_background(COLOR_BG)
    
    # Logo (placeholder for now - would need image loading abstraction)
    logo_x = BASE_WIDTH // 2 - 200
    logo_y = BASE_HEIGHT // 4 - 100
    backend.draw_rect(logo_x, logo_y, 400, 200, (100, 100, 100), 2, (200, 200, 200))
    
    # Game title
    backend.draw_text("BomberMarv", BASE_WIDTH // 2, BASE_HEIGHT // 2, 
                     "comic_sans", 90, (255, 255, 255), center=True)
    
    # Version
    backend.draw_text(VERSION, BASE_WIDTH - 10, BASE_HEIGHT - 10, 
                     "arial", 24, (255, 255, 255))

def draw_board(backend: RenderingBackend, game):
    """Draw the game board"""
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            cell_x = x * CELL_SIZE
            cell_y = y * CELL_SIZE
            
            if game.board[y][x] == EMPTY:
                backend.draw_rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE, COLOR_BG)
            elif game.board[y][x] == INDESTRUCTIBLE:
                backend.draw_rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE, COLOR_INDESTRUCTIBLE, 1, (80, 80, 80))
            elif game.board[y][x] == DESTRUCTIBLE:
                backend.draw_rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE, COLOR_DESTRUCTIBLE)
                draw_brick_pattern(backend, cell_x, cell_y, CELL_SIZE, CELL_SIZE)

def draw_players(backend: RenderingBackend, players, current_time: int = 0):
    """Draw all players"""
    for player in players:
        if not player.alive and player.death_animation_time <= 0:
            continue
            
        x, y = int(player.pos.x), int(player.pos.y)
        r = player.draw_radius
        
        if player.alive:
            # Main body
            backend.draw_circle(x, y, r, player.color)
            
            # Helmet highlight
            helmet_color = (min(player.color[0] + 30, 255), 
                          min(player.color[1] + 30, 255), 
                          min(player.color[2] + 30, 255))
            # Draw helmet arc (approximated with small circles)
            for angle in range(180, 360, 10):
                arc_x = x + int(r * 0.8 * math.cos(math.radians(angle)))
                arc_y = y + int(r * 0.8 * math.sin(math.radians(angle)))
                backend.draw_circle(arc_x, arc_y, 2, helmet_color)
            
            # Eyes
            eye_r = max(1, r // 8)
            eye_offset_x = r // 3
            eye_offset_y = r // 3
            backend.draw_circle(x - eye_offset_x, y - eye_offset_y, eye_r, (0, 0, 0))
            backend.draw_circle(x + eye_offset_x, y - eye_offset_y, eye_r, (0, 0, 0))
            
            # Animated legs
            leg_width = r // 3
            leg_height = r // 4
            leg_offset = int(6 * math.sin(player.animation_time / 150.0))
            leg_color = (player.color[0] // 2, player.color[1] // 2, player.color[2] // 2)
            
            backend.draw_rect(x - r // 2 - leg_width // 2, y + r - 2 + leg_offset, 
                            leg_width, leg_height, leg_color)
            backend.draw_rect(x + r // 2 - leg_width // 2, y + r - 2 - leg_offset, 
                            leg_width, leg_height, leg_color)
            
            # Quad damage effect
            if player.quad_damage:
                elapsed = current_time - player.quad_damage_start_time
                pulse = 1 + 0.1 * math.sin(2 * math.pi * (elapsed / 500.0))
                rect_size = int((2 * r + 10) * pulse)
                backend.draw_rect(x - rect_size // 2, y - rect_size // 2, 
                                rect_size, rect_size, (0, 0, 0), 4, (0, 255, 255))
            
            # Player name
            backend.draw_text(player.name, x, y - r - 10, "arial", 32, (255, 255, 255), center=True)
        
        else:
            # Death animation
            alpha = player.death_animation_time / 1000.0
            death_color = (int(255 * alpha), 0, 0)
            backend.draw_circle(x, y, r, death_color)

def draw_bombs(backend: RenderingBackend, current_time: int, bombs):
    """Draw all bombs"""
    for bomb in bombs:
        center_x = bomb.x * CELL_SIZE + CELL_SIZE // 2
        center_y = bomb.y * CELL_SIZE + CELL_SIZE // 2
        
        elapsed = current_time - bomb.start_time
        pulse = 1 + BOMB_PULSE_AMPLITUDE * math.sin(2 * math.pi * (elapsed / BOMB_PULSE_SPEED))
        bomb_radius = int(BOMB_BASE_RADIUS * pulse)
        
        # Main bomb body
        backend.draw_circle(center_x, center_y, bomb_radius, COLOR_BOMB_FILL, 2, COLOR_BOMB_OUTLINE)
        
        # Fuse
        fuse_radius = max(2, bomb_radius // 3)
        fuse_offset = int(bomb_radius * 0.6)
        fuse_center_x = center_x
        fuse_center_y = center_y - fuse_offset
        backend.draw_circle(fuse_center_x, fuse_center_y, fuse_radius, COLOR_FUSE)

def draw_explosions(backend: RenderingBackend, current_time: int, explosions):
    """Draw all explosions"""
    for explosion in explosions:
        norm = (current_time - explosion.start_time) / EXPLOSION_DURATION
        norm = min(norm, 1)
        
        if norm < 0.2:
            arm_factor = norm / 0.2
        elif norm <= 0.7:
            arm_factor = 1
        else:
            arm_factor = (1 - (norm - 0.7) / 0.3)
        
        # Get explosion center
        cx, cy = explosion.cells[0]
        center_pixel_x = cx * CELL_SIZE + CELL_SIZE // 2
        center_pixel_y = cy * CELL_SIZE + CELL_SIZE // 2
        
        # Calculate arm lengths
        up_max = max([cy - cell[1] for cell in explosion.cells if cell[0] == cx and cell[1] < cy] or [0])
        down_max = max([cell[1] - cy for cell in explosion.cells if cell[0] == cx and cell[1] > cy] or [0])
        left_max = max([cx - cell[0] for cell in explosion.cells if cell[1] == cy and cell[0] < cx] or [0])
        right_max = max([cell[0] - cx for cell in explosion.cells if cell[1] == cy and cell[0] > cx] or [0])
        
        # Colors
        if explosion.quad_damage:
            explosion_color = (255, 100, 255)  # Magenta for quad damage
        else:
            explosion_color = (255, 200, 0)    # Orange for normal
        
        # Draw center
        center_size = int(CELL_SIZE * FLAME_ARM_THICKNESS_RATIO)
        backend.draw_rect(center_pixel_x - center_size // 2, center_pixel_y - center_size // 2,
                         center_size, center_size, explosion_color)
        
        # Draw arms
        arm_thickness = int(CELL_SIZE * FLAME_ARM_THICKNESS_RATIO)
        
        if up_max > 0:
            arm_length = int(arm_factor * up_max * CELL_SIZE)
            backend.draw_rect(center_pixel_x - arm_thickness // 2, center_pixel_y - arm_length,
                             arm_thickness, arm_length, explosion_color)
        
        if down_max > 0:
            arm_length = int(arm_factor * down_max * CELL_SIZE)
            backend.draw_rect(center_pixel_x - arm_thickness // 2, center_pixel_y,
                             arm_thickness, arm_length, explosion_color)
        
        if left_max > 0:
            arm_length = int(arm_factor * left_max * CELL_SIZE)
            backend.draw_rect(center_pixel_x - arm_length, center_pixel_y - arm_thickness // 2,
                             arm_length, arm_thickness, explosion_color)
        
        if right_max > 0:
            arm_length = int(arm_factor * right_max * CELL_SIZE)
            backend.draw_rect(center_pixel_x, center_pixel_y - arm_thickness // 2,
                             arm_length, arm_thickness, explosion_color)

def draw_powerups(backend: RenderingBackend, game):
    """Draw all powerups"""
    for powerup in game.powerups:
        center_x = powerup.x * CELL_SIZE + CELL_SIZE // 2
        center_y = powerup.y * CELL_SIZE + CELL_SIZE // 2
        size = CELL_SIZE - 20
        
        # Border
        backend.draw_rect(center_x - size // 2, center_y - size // 2, size, size, 
                         (0, 0, 0), 4, (0, 255, 255))
        
        if powerup.type == "bomb":
            # Draw bomb icon
            bomb_r = size // 3
            backend.draw_circle(center_x, center_y, bomb_r, COLOR_BOMB_FILL, 2, COLOR_BOMB_OUTLINE)
            fuse_r = max(2, bomb_r // 3)
            backend.draw_circle(center_x, center_y - int(bomb_r * 0.6), fuse_r, COLOR_FUSE)
        
        elif powerup.type == "fire":
            # Draw fire icon (simplified)
            backend.draw_circle(center_x, center_y, size // 3, (255, 100, 0))
            backend.draw_circle(center_x - 5, center_y - 5, size // 4, (255, 200, 0))
            backend.draw_circle(center_x + 5, center_y - 5, size // 4, (255, 150, 0))
        
        elif powerup.type == "quad_damage":
            # Draw QD icon
            backend.draw_text("QD", center_x, center_y, "arial", 20, (255, 0, 255), center=True)

def draw_player_directions(backend: RenderingBackend, players, game):
    """Draw player direction indicators"""
    if not SHOW_PLAYER_DIRECTIONS:
        return
        
    for player in players:
        if not player.alive or not hasattr(player, 'direction'):
            continue
            
        if player.direction.length_squared() > 0:
            start_x, start_y = int(player.pos.x), int(player.pos.y)
            end_x = int(player.pos.x + player.direction.x * CELL_SIZE)
            end_y = int(player.pos.y + player.direction.y * CELL_SIZE)
            
            # Direction line
            backend.draw_line(start_x, start_y, end_x, end_y, (255, 0, 0), 4)
            backend.draw_circle(end_x, end_y, 7, (255, 0, 0))
            
            # Highlight target cell
            cell_x = int((player.pos.x + player.direction.x * CELL_SIZE) // CELL_SIZE)
            cell_y = int((player.pos.y + player.direction.y * CELL_SIZE) // CELL_SIZE)
            
            if 0 <= cell_x < GRID_WIDTH and 0 <= cell_y < GRID_HEIGHT:
                cell_empty = game.board[cell_y][cell_x] == EMPTY
                highlight_color = (0, 255, 0) if cell_empty else (255, 0, 0)
                
                # Semi-transparent overlay (approximated with border)
                backend.draw_rect(cell_x * CELL_SIZE, cell_y * CELL_SIZE, CELL_SIZE, CELL_SIZE,
                                (0, 0, 0), 4, highlight_color)

def draw_game_screen(backend: RenderingBackend, game):
    """Draw the complete game screen"""
    backend.fill_background(COLOR_BG)
    draw_board(backend, game)
    draw_powerups(backend, game)
    draw_bombs(backend, game.current_time, game.bombs)
    draw_explosions(backend, game.current_time, game.explosions)
    draw_players(backend, game.players, game.current_time)
    draw_player_directions(backend, game.players, game)

def draw_get_ready(backend: RenderingBackend):
    """Draw get ready screen"""
    backend.draw_text("Get Ready!", BASE_WIDTH // 2, BASE_HEIGHT - 500, 
                     "comic_sans", 90, (180, 60, 120), center=True)

def draw_controls(backend: RenderingBackend, players):
    """Draw control instructions"""
    y_offset = BASE_HEIGHT - BASE_HEIGHT // 3
    backend.draw_text("Controls: Up - Down - Left - Right - Bomb", BASE_WIDTH // 2, y_offset, 
                     "arial", 40, (255, 255, 255), center=True)
    
    y_offset += 50
    for i, player in enumerate(players):
        controls = player.controls
        # Note: This would need pygame key name conversion - simplified for now
        control_text = f"{player.name}: WASD + SHIFT (simplified)"
        backend.draw_text(control_text, BASE_WIDTH // 2, y_offset, "arial", 40, player.color, center=True)
        y_offset += 50

def draw_stat_screen(backend: RenderingBackend, winner, players):
    """Draw statistics screen"""
    draw_title_page(backend, 1.0)
    
    if winner:
        # Draw trophies (simplified)
        trophy_y = BASE_HEIGHT // 2 + 70
        for i in range(winner.trophies):
            trophy_x = BASE_WIDTH // 2 + 150 + i * 30
            backend.draw_rect(trophy_x, trophy_y, 24, 24, (212, 175, 55))
        
        backend.draw_text(f"{winner.name} wins!", BASE_WIDTH // 2, BASE_HEIGHT // 2 + 80, 
                         "arial", 48, winner.color, center=True)
    else:
        backend.draw_text("No one wins!", BASE_WIDTH // 2, BASE_HEIGHT // 2 + 80, 
                         "arial", 48, (255, 255, 255), center=True)
    
    # Player stats
    y_offset = BASE_HEIGHT // 2 + 110
    for player in players:
        backend.draw_text(f"{player.name}:", 50, y_offset, "arial", 32, player.color)
        # Draw trophy count
        for j in range(player.trophies):
            backend.draw_rect(200 + j * 30, y_offset, 24, 24, (212, 175, 55))
        y_offset += 40

def draw_champion_screen(backend: RenderingBackend, champion):
    """Draw champion screen"""
    backend.fill_background(COLOR_BG)
    draw_title_page(backend, 1.0)
    
    backend.draw_text(f"Champion: {champion.name}", BASE_WIDTH // 2, BASE_HEIGHT // 2 - 100, 
                     "arial", 60, champion.color, center=True)
    
    # Champion trophies
    trophy_y = BASE_HEIGHT // 2 + 100
    for j in range(champion.trophies):
        trophy_x = BASE_WIDTH // 2 - 100 + j * 30
        backend.draw_rect(trophy_x, trophy_y, 24, 24, (212, 175, 55))
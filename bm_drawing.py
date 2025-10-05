import pygame
import numpy as np
import time
import math
from bm_params import *
from input_abstraction import get_key_name
from timing_abstraction import get_ticks
from lib_collisions import circle_rect_collision

def _format_controls(controls):
    """Convert pygame key constants to readable control names"""
    def key_to_name(key):
        # Common key mappings
        key_names = {
            pygame.K_w: 'W', pygame.K_a: 'A', pygame.K_s: 'S', pygame.K_d: 'D',
            pygame.K_i: 'I', pygame.K_j: 'J', pygame.K_k: 'K', pygame.K_l: 'L',
            pygame.K_f: 'F', pygame.K_c: 'C', pygame.K_v: 'V', pygame.K_b: 'B',
            pygame.K_SPACE: 'Space', pygame.K_LSHIFT: 'Shift', pygame.K_RSHIFT: 'RShift',
            pygame.K_LCTRL: 'Ctrl', pygame.K_RCTRL: 'RCtrl',
            pygame.K_UP: '↑', pygame.K_DOWN: '↓', pygame.K_LEFT: '←', pygame.K_RIGHT: '→',
            pygame.K_HOME: 'Home', pygame.K_END: 'End', pygame.K_DELETE: 'Del', pygame.K_PAGEDOWN: 'PgDn',
            pygame.K_BACKSPACE: 'Backspace',
            pygame.K_KP0: 'KP0', pygame.K_KP1: 'KP1', pygame.K_KP2: 'KP2', pygame.K_KP3: 'KP3',
            pygame.K_KP5: 'KP5', pygame.K_KP7: 'KP7', pygame.K_KP8: 'KP8', pygame.K_KP9: 'KP9',
            pygame.K_KP_DIVIDE: 'KP/',
        }
        return key_names.get(key, f'K{key}')
    
    up = key_to_name(controls['up'])
    down = key_to_name(controls['down'])
    left = key_to_name(controls['left'])
    right = key_to_name(controls['right'])
    bomb = key_to_name(controls['bomb'])
    
    return f"{up}{down}{left}{right} + {bomb}"

def _ensure_fonts_initialized():
    """Ensure fonts are initialized before use"""
    global arcade_font, font_small
    if arcade_font is None:
        arcade_font = pygame.font.SysFont('Comic Sans MS', 90)
    if font_small is None:
        font_small = pygame.font.SysFont("arial", 32)

def draw_brick_pattern(rect, surface):
    brick_height = rect[3] // 4
    brick_width = rect[2] // 3
    mortar_color = (80, 80, 80)
    rows = 2
    for row in range(rows):
        offset = brick_width // 2 if row % 2 == 1 else 0
        y = rect[1] + row * (rect[3] // rows)
        x = rect[0] + offset
        # Prevent infinite loop: ensure x always increases
        while x < rect[0] + rect[2]:
            brick_rect = np.array([x, y, brick_width, rect[3] // rows], dtype=np.float64)
            pygame.draw.rect(surface, mortar_color, brick_rect, 1)
            x += brick_width  # <-- increment x to avoid infinite loop
            
            
def draw_title_page(surface, alpha=255):
    # Ensure fonts are initialized
    _ensure_fonts_initialized()
    
    surface.fill(COLOR_BG) 
    
    # Get the original dimensions of the logo
    logo_width, logo_height = logo_image.get_size()
    
    # Calculate the scaling factor to fit the logo within the desired width and height
    max_width = BASE_WIDTH // 2
    max_height = BASE_HEIGHT // 4
    scale_factor = min(max_width / logo_width, max_height / logo_height)
    
    # Calculate the new dimensions while maintaining the aspect ratio
    new_width = int(logo_width * scale_factor)
    new_height = int(logo_height * scale_factor)
    
    # Scale the logo image to the new dimensions
    logo_scaled = pygame.transform.smoothscale(logo_image, (new_width, new_height))
    logo_scaled.set_alpha(alpha)
    
    # Get the rectangle for the scaled logo and center it
    rect = logo_scaled.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT // 4))
    
    # Blit the scaled logo onto the surface
    surface.blit(logo_scaled, rect)
    
    # Render the game name in big arcade font
    game_name_text = arcade_font.render("BomberMarv", True, (255, 255, 255))
    game_name_rect = game_name_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT // 2))
    surface.blit(game_name_text, game_name_rect)
    
    # Render the version tag
    version_font = pygame.font.SysFont("arial", 24)
    version_text = version_font.render(VERSION, True, (255, 255, 255))
    version_rect = version_text.get_rect(bottomright=(BASE_WIDTH - 10, BASE_HEIGHT - 10))
    surface.blit(version_text, version_rect)
    
    
    


def draw_trophy_icon(surface, pos, size):
    trophy_color = (212, 175, 55)
    x, y = pos
    width = size
    height = size
    # Draw a dome (ellipse) for the top of the trophy
    dome_rect = np.array([x, y, width, int(height * 0.6)], dtype=np.float64)
    pygame.draw.ellipse(surface, trophy_color, dome_rect)
    # Draw the cup
    cup_rect = np.array([x + int(width * 0.2), y + int(height * 0.5), int(width * 0.6), int(height * 0.3)], dtype=np.float64)
    pygame.draw.rect(surface, trophy_color, cup_rect)
    # Draw a base
    base_rect = np.array([x + int(width * 0.3), y + int(height * 0.85), int(width * 0.4), int(height * 0.15)], dtype=np.float64)
    pygame.draw.rect(surface, trophy_color, base_rect)
    
def draw_board(surface,theGame):
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            rect = np.array([x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
            if theGame.board[y][x] == EMPTY:
                pygame.gfxdraw.box(surface, rect, COLOR_BG)
            elif theGame.board[y][x] == INDESTRUCTIBLE:
                pygame.gfxdraw.box(surface, rect, COLOR_INDESTRUCTIBLE)
                pygame.draw.rect(surface, (80,80,80), rect, 1)
            elif theGame.board[y][x] == DESTRUCTIBLE:
                pygame.gfxdraw.box(surface, rect, COLOR_DESTRUCTIBLE)
                draw_brick_pattern(rect, surface)
                pygame.draw.rect(surface, (80,80,80), rect, 1)
                
                

def draw_powerups(surface, theGame):
    for p in theGame.powerups:
        center = (p.x * CELL_SIZE + CELL_SIZE//2, p.y * CELL_SIZE + CELL_SIZE//2)
        size = CELL_SIZE - 20
        draw_powerup_icon(surface, center, size, p.type)

def draw_powerup_icon(surface, center, size, powerup_type):
    if powerup_type == "bomb":
        draw_bomb_powerup_icon(surface, center, size)
    elif powerup_type == "fire":
        draw_fire_powerup_icon(surface, center, size)
    elif powerup_type == "quad_damage":
        draw_quad_damage_powerup_icon(surface, center, size)
    elif powerup_type == "death_bonus":
        draw_death_bonus_powerup_icon(surface, center, size)

def draw_bomb_powerup_icon(surface, center, size):
    size = int(size * 1.3)
    rect = np.array([center[0] - size//2, center[1] - size//2, size, size], dtype=np.float64)
    blue_border = (0, 255, 255)
    pygame.draw.rect(surface, blue_border, rect, 4)
    bomb_r = size // 3
    cell_center = center
    bomb_radius = bomb_r
    pygame.gfxdraw.filled_circle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_FILL)
    pygame.gfxdraw.aacircle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_OUTLINE)
    fuse_radius = max(2, bomb_radius // 3)
    fuse_offset = int(bomb_radius * 0.6)
    fuse_center = (cell_center[0], cell_center[1] - fuse_offset)
    pygame.gfxdraw.filled_circle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)
    pygame.gfxdraw.aacircle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)   

def draw_fire_powerup_icon(surface, center, size):
    size2 = int(size * 1.3)
    rect = np.array([center[0] - size2//2, center[1] - size2//2, size2, size2], dtype=np.float64)
    blue_border = (0, 255, 255)
    pygame.draw.rect(surface, blue_border, rect, 4)
    
    # Scale the fire powerup image to fit the size
    scaled_image = pygame.transform.smoothscale(fire_powerup_image, (size, size))
    
    # Get the rectangle for the scaled image and center it
    image_rect = scaled_image.get_rect(center=center)
    
    # Blit the scaled image onto the surface
    surface.blit(scaled_image, image_rect)

def draw_quad_damage_powerup_icon(surface, center, size):
    # Scale the quad damage image to fit the size
    scaled_image = pygame.transform.smoothscale(quad_damage_image, (size, size))
    
    # Get the rectangle for the scaled image and center it
    image_rect = scaled_image.get_rect(center=center)
    
    # Blit the scaled image onto the surface
    surface.blit(scaled_image, image_rect)

def draw_death_bonus_powerup_icon(surface, center, size):
    # Draw a distinctive icon: a skull-like simple icon inside a bordered square
    size2 = int(size * 1.3)
    rect = np.array([center[0] - size2//2, center[1] - size2//2, size2, size2], dtype=np.float64)
    border_color = (255, 255, 0)
    pygame.draw.rect(surface, border_color, rect, 4)
    # Simple skull: circle + two eyes + small jaw rectangle
    skull_radius = size // 3
    pygame.gfxdraw.filled_circle(surface, center[0], center[1], skull_radius, (230, 230, 230))
    pygame.gfxdraw.aacircle(surface, center[0], center[1], skull_radius, (0, 0, 0))
    eye_r = max(2, skull_radius // 5)
    eye_offset = skull_radius // 2
    pygame.gfxdraw.filled_circle(surface, center[0] - eye_offset//2, center[1] - eye_offset//3, eye_r, (0,0,0))
    pygame.gfxdraw.filled_circle(surface, center[0] + eye_offset//2, center[1] - eye_offset//3, eye_r, (0,0,0))
    jaw_rect = np.array([center[0] - skull_radius//2, center[1] + skull_radius//3, skull_radius, skull_radius//3], dtype=np.float64)
    pygame.draw.rect(surface, (230, 230, 230), jaw_rect)


def draw_trophy_icon(surface, pos, size):
    trophy_color = (212, 175, 55)
    x, y = pos
    width = size
    height = size
    dome_rect = np.array([x, y, width, int(height * 0.6)], dtype=np.float64)
    pygame.draw.ellipse(surface, trophy_color, dome_rect)
    cup_rect = np.array([x + int(width * 0.2), y + int(height * 0.5), int(width * 0.6), int(height * 0.3)], dtype=np.float64)
    pygame.draw.rect(surface, trophy_color, cup_rect)
    base_rect = np.array([x + int(width * 0.3), y + int(height * 0.85), int(width * 0.4), int(height * 0.15)], dtype=np.float64)
    pygame.draw.rect(surface, trophy_color, base_rect)

def draw_players(surface, players):
    _ensure_fonts_initialized()
    for player in players:
        if not player.alive and player.death_animation_time <= 0:
            continue
        pos = (int(player.pos[0]), int(player.pos[1]))
        r = player.draw_radius
        if player.alive:
            pygame.gfxdraw.filled_circle(surface, pos[0], pos[1], r, player.color)
            pygame.gfxdraw.aacircle(surface, pos[0], pos[1], r, player.color)
            helmet_color = (min(player.color[0]+30,255), min(player.color[1]+30,255), min(player.color[2]+30,255))
            rect_head = np.array([pos[0]-r, pos[1]-r, 2*r, 2*r], dtype=np.float64)
            pygame.draw.arc(surface, helmet_color, rect_head, math.pi, 2*math.pi, 3)
            eye_r = max(1, r//8)
            eye_offset_x = r//3
            eye_offset_y = r//3
            pygame.gfxdraw.filled_circle(surface, pos[0]-eye_offset_x, pos[1]-eye_offset_y, eye_r, (0,0,0))
            pygame.gfxdraw.filled_circle(surface, pos[0]+eye_offset_x, pos[1]-eye_offset_y, eye_r, (0,0,0))
            leg_width = r//3
            leg_height = r//4
            leg_offset = int(6 * math.sin(player.animation_time / 150.0))
            left_leg = np.array([pos[0] - r//2 - leg_width//2, pos[1] + r - 2 + leg_offset, leg_width, leg_height], dtype=np.float64)
            right_leg = np.array([pos[0] + r//2 - leg_width//2, pos[1] + r - 2 - leg_offset, leg_width, leg_height], dtype=np.float64)
            leg_color = (player.color[0]//2, player.color[1]//2, player.color[2]//2)
            pygame.draw.rect(surface, leg_color, left_leg)
            pygame.draw.rect(surface, leg_color, right_leg)
        
            if player.quad_damage:
                elapsed = get_ticks() - player.quad_damage_start_time
                pulse = 1 + 0.1 * math.sin(2 * math.pi * (elapsed / 500.0))
                rect_size = int((2 * r + 10) * pulse)
                rect = np.array([pos[0] - rect_size // 2, pos[1] - rect_size // 2, rect_size, rect_size], dtype=np.float64)
                pygame.draw.rect(surface, (0, 255, 255), rect, 4)
            
            # Draw player name
            name_text = font_small.render(player.name, True, (255, 255, 255))
            name_rect = name_text.get_rect(center=(pos[0], pos[1] - r - 10))
            surface.blit(name_text, name_rect)
            # Draw pickup message if active
            if getattr(player, 'pickup_message_end_time', 0) and get_ticks() < player.pickup_message_end_time:
                msg_text = font_small.render(player.pickup_message, True, (255, 255, 0))
                msg_rect = msg_text.get_rect(center=(pos[0], pos[1] - r - 40))
                # Draw a semi-transparent dark background for readability
                bg_rect = msg_rect.inflate(10, 6)
                bg_surface = pygame.Surface((bg_rect[2], bg_rect[3]), pygame.SRCALPHA)
                bg_surface.fill((0, 0, 0, 140))
                surface.blit(bg_surface, (bg_rect[0], bg_rect[1]))
                surface.blit(msg_text, msg_rect)
        else:
            # Draw death animation
            alpha = int(255 * (player.death_animation_time / 1000.0))
            death_color = (255, 0, 0, alpha)
            pygame.gfxdraw.filled_circle(surface, pos[0], pos[1], r, death_color)
            pygame.gfxdraw.aacircle(surface, pos[0], pos[1], r, death_color)

def draw_bombs(surface, current_time, bombs):
    for bomb in bombs:
        cell_center = (bomb.x * CELL_SIZE + CELL_SIZE//2, bomb.y * CELL_SIZE + CELL_SIZE//2)
        elapsed = current_time - bomb.start_time
        pulse = 1 + BOMB_PULSE_AMPLITUDE * math.sin(2 * math.pi * (elapsed / BOMB_PULSE_SPEED))
        bomb_radius = int(BOMB_BASE_RADIUS * pulse)
        pygame.gfxdraw.filled_circle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_FILL)
        pygame.gfxdraw.aacircle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_OUTLINE)
        fuse_radius = max(2, bomb_radius // 3)
        fuse_offset = int(bomb_radius * 0.6)
        fuse_center = (cell_center[0], cell_center[1] - fuse_offset)
        pygame.gfxdraw.filled_circle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)
        pygame.gfxdraw.aacircle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)

def draw_explosions(surface, current_time, explosions):
    for explosion in explosions:
        norm = (current_time - explosion.start_time) / EXPLOSION_DURATION
        norm = min(norm, 1)
        if norm < 0.2:
            arm_factor = norm / 0.2
        elif norm <= 0.7:
            arm_factor = 1
        else:
            arm_factor = (1 - (norm - 0.7) / 0.3)
        
        cx, cy = explosion.cells[0]
        center_pixel = (cx * CELL_SIZE + CELL_SIZE // 2, cy * CELL_SIZE + CELL_SIZE // 2)
        
        up_max = max([cy - cell[1] for cell in explosion.cells if cell[0] == cx and cell[1] < cy] or [0])
        down_max = max([cell[1] - cy for cell in explosion.cells if cell[0] == cx and cell[1] > cy] or [0])
        left_max = max([cx - cell[0] for cell in explosion.cells if cell[1] == cy and cell[0] < cx] or [0])
        right_max = max([cell[0] - cx for cell in explosion.cells if cell[1] == cy and cell[0] > cx] or [0])
        
        up_length = arm_factor * up_max * CELL_SIZE
        down_length = arm_factor * down_max * CELL_SIZE
        left_length = arm_factor * left_max * CELL_SIZE
        right_length = arm_factor * right_max * CELL_SIZE
        
        if explosion.quad_damage:
            img = blast_image_qd
            center_img = blast_centre_image_qd
        else:
            img = blast_image
            center_img = blast_centre_image
        
        # Draw the center of the explosion using the center image
        scaled_center_img = pygame.transform.smoothscale(center_img, (CELL_SIZE * FLAME_ARM_THICKNESS_RATIO, CELL_SIZE * FLAME_ARM_THICKNESS_RATIO))
        center_rect = scaled_center_img.get_rect(center=center_pixel)
        surface.blit(scaled_center_img, center_rect)
        
        # Draw the arms of the explosion using the blast image
        if up_length > 0:
            draw_blast_arm(surface, center_pixel, (0, -up_length), img)
        
        if down_length > 0:
            draw_blast_arm(surface, center_pixel, (0, down_length), img)
        
        if left_length > 0:
            draw_blast_arm(surface, center_pixel, (-left_length, 0), img)
        
        if right_length > 0:
            draw_blast_arm(surface, center_pixel, (right_length, 0), img)

def draw_explosion_collision_debug(surface, current_time, explosions, players=None):
    """Draw red rectangles showing the collision boxes of explosion arms for debugging"""
    for explosion in explosions:
        # Calculate animation timing (same as in handle_explosions and draw_explosions)
        norm = (current_time - explosion.start_time) / EXPLOSION_DURATION
        norm = min(norm, 1)
        if norm < 0.2:
            arm_factor = norm / 0.2
        elif norm <= 0.7:
            arm_factor = 1
        else:
            arm_factor = (1 - (norm - 0.7) / 0.3)
        
        # Only draw collision boxes when explosion arms are active (arm_factor > 0)
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
            
            # Draw collision boxes only for currently active cells
            for cell in active_cells:
                x, y = cell
                # Calculate the reduced collision rectangle (same as handle_explosions)
                scale = EXPLOSION_COLLISION_SCALE
                margin = CELL_SIZE * (1.0 - scale) / 2.0
                hitbox_size = CELL_SIZE * scale
                collision_rect = np.array([x * CELL_SIZE + margin, y * CELL_SIZE + margin, hitbox_size, hitbox_size], dtype=np.float64)
                
                # Draw filled semi-transparent rect and border for clarity
                border_width = max(2, int(4 * arm_factor))
                border_color = (255, 60, 60) if arm_factor > 0.5 else (200, 80, 80)
                fill_surface = pygame.Surface((int(hitbox_size), int(hitbox_size)), pygame.SRCALPHA)
                fill_surface.fill((255, 0, 0, 60))
                surface.blit(fill_surface, (collision_rect[0], collision_rect[1]))
                pygame.draw.rect(surface, border_color, (collision_rect[0], collision_rect[1], hitbox_size, hitbox_size), border_width)
                
                # Draw cell coordinates for debugging
                if arm_factor > 0.5:
                    coord_text = f"{x},{y}"
                    coord_surface = font_small.render(coord_text, True, (255, 255, 255))
                    coord_rect = coord_surface.get_rect(center=(x * CELL_SIZE + CELL_SIZE//2, y * CELL_SIZE + CELL_SIZE//2))
                    pygame.draw.rect(surface, (0, 0, 0, 128), coord_rect.inflate(4, 2))
                    surface.blit(coord_surface, coord_rect)
                
                # Show collision info for players in this cell
                if players and arm_factor > 0.5:
                    for player in players:
                        if player.alive:
                            if circle_rect_collision((player.pos[0], player.pos[1]), player.collision_radius, collision_rect):
                                pygame.draw.circle(surface, (255, 255, 0), (int(player.pos[0]), int(player.pos[1])), int(player.collision_radius), 2)

def draw_blast_arm(surface, start_pos, end_offset, image):
    x1, y1 = start_pos
    x2, y2 = x1 + end_offset[0], y1 + end_offset[1]
    length = math.hypot(x2 - x1, y2 - y1)
    
    # Calculate the angle for rotation
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    
    # Scale the image to the length of the arm
    scaled_image = pygame.transform.smoothscale(image, (int(length), int(CELL_SIZE * FLAME_ARM_THICKNESS_RATIO)))
    
    # Rotate the image
    if angle == 0:
        rotated_image = pygame.transform.rotate(scaled_image, 180)
    elif angle == 180:
        rotated_image = scaled_image
    else:
        rotated_image = pygame.transform.rotate(scaled_image, angle)
    
     # Get the rectangle for the rotated image and place its right edge at the center of the starting cell
    image_rect = rotated_image.get_rect()
    image_rect.center = (x1, y1)
    if angle == -90:
        image_rect.bottom = y1
    elif angle == 0:
        image_rect.left = x1
    elif angle == 90:
        image_rect.top = y1
    else:
        image_rect.right = x1
    
    # Blit the rotated image onto the surface
    surface.blit(rotated_image, image_rect)

def draw_controls(surface, players):
    font = pygame.font.SysFont("arial", 40)
    y_offset = BASE_HEIGHT - BASE_HEIGHT // 3
    control_text = "Controls: Up -  Down - Left - Right - Bomb"
    text = font.render(control_text, True, (255, 255, 255))
    rect = text.get_rect(center=(BASE_WIDTH // 2, y_offset))
    surface.blit(text, rect)
    y_offset += 50
    for i, player in enumerate(players):
        controls = player.controls
        control_text = f"{player.name}: {get_key_name(controls['up'])} - {get_key_name(controls['down'])} - {get_key_name(controls['left'])} - {get_key_name(controls['right'])} - {get_key_name(controls['bomb'])}"
        text = font.render(control_text, True, player.color)
        rect = text.get_rect(center=(BASE_WIDTH // 2, y_offset))
        surface.blit(text, rect)
        y_offset += 50

def draw_stat_screen(surface, winner, players):
    _ensure_fonts_initialized()
    font = pygame.font.SysFont("arial", 48, bold=True)
    draw_title_page(surface, alpha=255)
    if winner:
        x_start = BASE_WIDTH//2 + 150
        icon_size = 24
        for i in range(winner.trophies):
            trophy_pos = (x_start + i * (icon_size + 5), BASE_HEIGHT//2 + 70)
            draw_trophy_icon(surface, trophy_pos, icon_size)
        text = font.render(f"{winner.name} wins!", True, winner.color)
    else:
        text = font.render("No one wins!", True, (255,255,255))
    rect = text.get_rect(center=(BASE_WIDTH//2, BASE_HEIGHT//2 + 80))
    surface.blit(text, rect)
    font_small = pygame.font.SysFont("arial", 32)
    y_offset = BASE_HEIGHT//2 + 110
    # Columns: Name | Trophies | Death (s) | Flames | Bombs
    name_x = 50
    trophies_x = 260
    death_x = 450
    flames_x = 590
    bombs_x = 680
    header_color = (200, 200, 200)
    surface.blit(font_small.render("Player", True, header_color), (name_x, y_offset))
    surface.blit(font_small.render("Trophies", True, header_color), (trophies_x, y_offset))
    surface.blit(font_small.render("Death (s)", True, header_color), (death_x, y_offset))
    surface.blit(font_small.render("Flames", True, header_color), (flames_x, y_offset))
    surface.blit(font_small.render("Bombs", True, header_color), (bombs_x, y_offset))
    y_offset += 34
    for i, player in enumerate(players):
        # Name
        name_text = font_small.render(f"{player.name}", True, player.color)
        surface.blit(name_text, (name_x, y_offset))

        # Trophies icons
        trophy_surface = pygame.Surface((160, 36), pygame.SRCALPHA)
        for j in range(player.trophies):
            draw_trophy_icon(trophy_surface, (j * 28, 6), 24)
        surface.blit(trophy_surface, (trophies_x, y_offset - 6))

        # Death time relative to round start; alive players show "—"
        if hasattr(player, 'death_time_rel_ms') and player.death_time_rel_ms is not None:
            secs = player.death_time_rel_ms / 1000.0
            secs_rounded = int(round(secs))
            death_text_str = f"{secs_rounded}"
            death_color = (255, 160, 160)
        else:
            death_text_str = "—"
            death_color = (160, 255, 160)
        death_text = font_small.render(death_text_str, True, death_color)
        surface.blit(death_text, (death_x, y_offset))

        # Flames and Bombs snapshot (alive players show current values)
        flames_val = None
        bombs_val = None
        if hasattr(player, 'fire_power_at_death') and player.fire_power_at_death is not None:
            flames_val = player.fire_power_at_death
        else:
            flames_val = getattr(player, 'fire_power', 0)
        if hasattr(player, 'bomb_capacity_at_death') and player.bomb_capacity_at_death is not None:
            bombs_val = player.bomb_capacity_at_death
        else:
            bombs_val = getattr(player, 'bomb_capacity', 0)

        flames_text = font_small.render(str(flames_val), True, (255, 220, 160))
        bombs_text = font_small.render(str(bombs_val), True, (160, 220, 255))
        surface.blit(flames_text, (flames_x, y_offset))
        surface.blit(bombs_text, (bombs_x, y_offset))
        y_offset += 36
        
    #draw_controls(surface)

def draw_champion_screen(surface, champion):
    surface.fill(COLOR_BG) # move inside drawing fcns
    font = pygame.font.SysFont("arial", 60, bold=True)
    draw_title_page(surface, alpha=255)
    trophy_surface = pygame.Surface((200, 40), pygame.SRCALPHA)
    for j in range(champion.trophies):
        draw_trophy_icon(trophy_surface, (j * 30, 0), 24)
    text = font.render(f"Champion: {champion.name}", True, champion.color)
    rect = text.get_rect(center=(BASE_WIDTH//2, BASE_HEIGHT//2 - 100))
    surface.blit(text, rect)
    surface.blit(trophy_surface, (BASE_WIDTH//2 - 100, BASE_HEIGHT//2 + 100))
    

def draw_game_screen(surface, theGame):
    surface.fill(COLOR_BG)
    draw_board(surface, theGame)
    draw_powerups(surface, theGame)
    draw_bombs(surface, theGame.current_time, theGame.bombs)
    draw_explosions(surface, theGame.current_time, theGame.explosions)
    if SHOW_EXPLOSION_COLLISION_DEBUG:
        draw_explosion_collision_debug(surface, theGame.current_time, theGame.explosions, theGame.players)
    draw_players(surface, theGame.players)
    if SHOW_PLAYER_DIRECTIONS:
        draw_player_directions(surface, theGame.players, theGame)
        
        
# Draw player direction vectors and highlight the cell the player is pointing at
# (call this from draw_game_screen)
def draw_player_directions(surface, players, theGame):
    for player in players:
        if not player.alive:
            continue
        if hasattr(player, 'direction') and np.dot(player.direction, player.direction) > 0:
            start = (int(player.pos[0]), int(player.pos[1]))
            end = (int(player.pos[0] + player.direction[0] * CELL_SIZE), int(player.pos[1] + player.direction[1] * CELL_SIZE))
            pygame.draw.line(surface, (255, 0, 0), start, end, 4)
            pygame.draw.circle(surface, (255, 0, 0), end, 7)
            # Highlight the cell the player is pointing at
            cell_x = int((player.pos[0] + player.direction[0] * CELL_SIZE) // CELL_SIZE)
            cell_y = int((player.pos[1] + player.direction[1] * CELL_SIZE) // CELL_SIZE)
            # Defensive: check bounds
            if 0 <= cell_y < len(theGame.board) and 0 <= cell_x < len(theGame.board[0]):
                cell_empty = theGame.board[cell_y][cell_x] == EMPTY
            else:
                cell_empty = False
            if cell_empty:
                highlight_color = (0, 255, 0, 120)  # semi-transparent green
                dx, dy = int(player.direction[0]), int(player.direction[1])
                if (dx == 1 and dy == 0) or (dx == -1 and dy == 0) or (dx == 0 and dy == 1) or (dx == 0 and dy == -1):
                    cell_center = (cell_x * CELL_SIZE + CELL_SIZE // 2, cell_y * CELL_SIZE + CELL_SIZE // 2)
                    pygame.draw.line(surface, (0, 200, 0), start, cell_center, 4)
                    pygame.draw.circle(surface, (0, 200, 0), cell_center, 7)
            else:
                highlight_color = (255, 0, 0, 120)  # semi-transparent red
            highlight_rect = np.array([cell_x * CELL_SIZE, cell_y * CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
            highlight_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
            highlight_surface.fill(highlight_color)
            surface.blit(highlight_surface, (highlight_rect[0], highlight_rect[1]))
    
def draw_adjust_screen_size(screen):
    factor = min(screen.window_size[0] / BASE_WIDTH, screen.window_size[1] / BASE_HEIGHT)
    new_width = int(BASE_WIDTH * factor)
    new_height = int(BASE_HEIGHT * factor)
    scaled_surface = pygame.transform.smoothscale(screen.surface, (new_width, new_height))
    screen.window.fill((0,0,0))
    x_offset = (screen.window_size[0] - new_width) // 2
    y_offset = (screen.window_size[1] - new_height) // 2
    screen.window.blit(scaled_surface, (x_offset, y_offset))
    pygame.display.flip()
    
def draw_get_ready(surface):
    _ensure_fonts_initialized()
    start_text = arcade_font.render("Get Ready!", True, (180, 60, 120))
    start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT- 500))
    surface.blit(start_text, start_rect)

def draw_game_prep(surface, Game):
    """Draw the game lobby screen"""
    _ensure_fonts_initialized()
    surface.fill(COLOR_BG)

    # Title
    title_font = pygame.font.SysFont("arial", 36, bold=True)
    surface.blit(title_font.render("GAME LOBBY", True, (255, 255, 255)), (40, 20))

    # Two main panels: Local Players and Connected Clients
    panel_width = (BASE_WIDTH - 80) // 2
    left_panel = np.array([40, 80, panel_width, BASE_HEIGHT - 200], dtype=np.float64)
    right_panel = np.array([40 + panel_width + 20, 80, panel_width, BASE_HEIGHT - 200], dtype=np.float64)
    
    pygame.draw.rect(surface, (70, 70, 70), left_panel)
    pygame.draw.rect(surface, (70, 70, 70), right_panel)
    pygame.draw.rect(surface, (120, 120, 120), left_panel, 2)
    pygame.draw.rect(surface, (120, 120, 120), right_panel, 2)

    # Panel titles
    panel_title_font = pygame.font.SysFont("arial", 24, bold=True)
    surface.blit(panel_title_font.render("LOCAL PLAYERS", True, (255, 255, 255)), (left_panel[0] + 15, left_panel[1] - 35))
    surface.blit(panel_title_font.render("CONNECTED CLIENTS", True, (255, 255, 255)), (right_panel[0] + 15, right_panel[1] - 35))

    # Left panel: Local Players
    y = left_panel[1] + 20
    line_height = 35
    
    # Local player count selector
    surface.blit(font_small.render("Local Players:", True, (200, 255, 200)), (left_panel[0] + 20, y))
    y += line_height
    
    # Player count buttons (1-6)
    button_width = 60
    button_height = 30
    button_spacing = 10
    start_x = left_panel[0] + 20
    
    for i in range(1, 7):  # Changed from range(1, 5) to range(1, 7)
        button_x = start_x + (i-1) * (button_width + button_spacing)
        button_y = y
        button_rect = np.array([button_x, button_y, button_width, button_height], dtype=np.float64)
        
        # Highlight selected count
        is_selected = (Game.prep_section == 'local_players' and Game.prep_cursor_row == 0 and Game.prep_cursor_col == i-1)
        button_color = (255, 255, 0) if is_selected else (100, 100, 100)  # Bright yellow for selected
        
        pygame.draw.rect(surface, button_color, button_rect)
        pygame.draw.rect(surface, (255, 255, 255), button_rect, 1)
        
        # Button text
        text_surface = font_small.render(str(i), True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(button_x + button_width//2, button_y + button_height//2))
        surface.blit(text_surface, text_rect)
    
    y += button_height + 20
    
    # Initialize status cache if needed
    if not hasattr(Game, '_last_status_check'):
        Game._last_status_check = 0
        Game._cached_status = None
    
    current_time = time.time()
    if current_time - Game._last_status_check > 1.0:  # Update every 1 second instead of every frame
        try:
            import requests
            response = requests.get('http://localhost:8080/status', timeout=0.5)
            if response.status_code == 200:
                Game._cached_status = response.json()
            Game._last_status_check = current_time
        except Exception as e:
            Game._cached_status = None
            Game._last_status_check = current_time
    
    # All players list (local + client)
    surface.blit(font_small.render("Players:", True, (200, 255, 200)), (left_panel[0] + 20, y))
    y += line_height
    
    # Collect all players (local + client) with global IDs
    all_players = []
    global_player_id = 1
    
    # Add local players first
    for i in range(Game.prep_num_players):
        player_name = Game.prep_player_names[i % len(Game.prep_player_names)]
        color_idx = Game.prep_player_colors[i % len(Game.prep_player_colors)]
        all_players.append({
            'id': global_player_id,
            'name': player_name,
            'color': color_idx,
            'type': 'local',
            'source': i,  # Index for local player data
            'real_time_status': ''  # No real-time status for local players
        })
        global_player_id += 1
    
    # Add client players
    if Game._cached_status:
        status_data = Game._cached_status
        clients = status_data.get('clients', {})
        players = status_data.get('players', {})
        
        for client_id, client_info in clients.items():
            if client_info.get('registered', False):
                client_players = client_info.get('players', [])
                for player_id in client_players:
                    player_info = players.get(str(player_id), {})
                    keys = player_info.get('keys', {})

                    # Show pressed keys as directiveal indicators
                    pressed_keys = []
                    if keys.get('up'): pressed_keys.append('↑')
                    if keys.get('down'): pressed_keys.append('↓')
                    if keys.get('left'): pressed_keys.append('←')
                    if keys.get('right'): pressed_keys.append('→')
                    if keys.get('bomb'): pressed_keys.append('💣')
                    
                    real_time_status = ''.join(pressed_keys) if pressed_keys else '---'
                    
                    all_players.append({
                        'id': global_player_id,
                        'name': f"Client {client_id} P{player_id}",
                        'color': global_player_id % len(colors),  # Assign color based on global ID
                        'type': 'client',
                        'source': (client_id, player_id),  # Client and player ID
                        'real_time_status': real_time_status
                    })
                    global_player_id += 1
    
    # Display all players with integrated name and color editing
    for i, player in enumerate(all_players):
        # Check if this player is selected for editing
        is_selected = (Game.prep_section == 'local_players' and Game.prep_cursor_row == i + 1)  # +1 because row 0 is player count buttons
        is_editing_name = (Game.prep_editing_name and Game.prep_name_edit_index == i)
        
        # Player name with editing support
        if is_editing_name:
            name_text = f"Player {player['id']}: {player['name']}_"
            name_color = (255, 255, 0)  # Yellow for editing
        elif is_selected:
            name_text = f"Player {player['id']}: {player['name']}"
            name_color = (255, 255, 0)  # Yellow for selected
        else:
            name_text = f"Player {player['id']}: {player['name']}"
            name_color = (255, 255, 255)  # White for normal
        
        surface.blit(font_small.render(name_text, True, name_color), (left_panel[0] + 20, y))
        
        # Color indicator (clickable)
        color_rect = np.array([left_panel[0] + 200, y + 5, 20, 20], dtype=np.float64)
        color_border_color = (255, 255, 0) if is_selected else (255, 255, 255)
        pygame.draw.rect(surface, colors[player['color'] % len(colors)], color_rect)
        pygame.draw.rect(surface, color_border_color, color_rect, 2)
        
        # Status info - show controls for local, real-time movement for client
        if player['type'] == 'local':
            # Show controls for local players
            controls = Game.prep_controls[player['source'] % len(Game.prep_controls)]
            status_text = _format_controls(controls)
            status_color = (180, 180, 180)
        else:
            # Show real-time movement for client players
            # Get current key state from web_keys_by_player if available
            current_keys = '---'
            if hasattr(Game, 'web_keys_by_player'):
                # Find the player object for this web player
                for game_player in Game.players:
                    if (not game_player.is_local and 
                        game_player.client_id == player['source'][0] and 
                        game_player.client_player_id == player['source'][1]):
                        if game_player in Game.web_keys_by_player:
                            pressed_keys = []
                            web_keys = Game.web_keys_by_player[game_player]
                            if 'up' in web_keys: pressed_keys.append('↑')
                            if 'down' in web_keys: pressed_keys.append('↓')
                            if 'left' in web_keys: pressed_keys.append('←')
                            if 'right' in web_keys: pressed_keys.append('→')
                            if 'bomb' in web_keys: pressed_keys.append('💣')
                            current_keys = ''.join(pressed_keys) if pressed_keys else '---'
                        break
            
            status_text = current_keys
            status_color = (120, 255, 120) if current_keys != '---' else (180, 180, 180)
        
        surface.blit(font_small.render(status_text, True, status_color), (left_panel[0] + 240, y))
        
        y += line_height
    
    # Right panel: Connected Clients
    y = right_panel[1] + 20
    
    # Use cached status data
    if Game._cached_status:
        status_data = Game._cached_status
        clients = status_data.get('clients', {})
        players = status_data.get('players', {})
        
        if clients:
            for client_id, client_info in clients.items():
                # Client header
                last_seen = client_info.get('last_seen', 0)
                time_since = time.time() - last_seen
                status_color = (120, 255, 120) if time_since < 5 else (255, 200, 120) if time_since < 30 else (255, 120, 120)
                
                registered = client_info.get('registered', False)
                reg_status = "REG" if registered else "UNREG"
                
                avg_latency = client_info.get('avg_latency', 0)
                latency_samples = client_info.get('latency_samples', 0)
                latency_text = f" (avg: {avg_latency}ms)" if latency_samples > 0 else " (no data)"
                
                client_text = f"Client {client_id} [{reg_status}]{latency_text}"
                surface.blit(font_small.render(client_text, True, status_color), (right_panel[0] + 20, y))
                y += line_height
                
                # Players for this client
                client_players = client_info.get('players', [])
                for player_id in client_players:
                    player_info = players.get(str(player_id), {})
                    keys = player_info.get('keys', {})

                    # Show pressed keys as directional indicators
                    pressed_keys = []
                    if keys.get('up'): pressed_keys.append('↑')
                    if keys.get('down'): pressed_keys.append('↓')
                    if keys.get('left'): pressed_keys.append('←')
                    if keys.get('right'): pressed_keys.append('→')
                    if keys.get('bomb'): pressed_keys.append('💣')
                    
                    keys_display = ''.join(pressed_keys) if pressed_keys else '---'
                    
                    # Player info
                    player_text = f"  Player {player_id}: {keys_display}"
                    surface.blit(font_small.render(player_text, True, (255, 255, 255)), (right_panel[0] + 20, y))
                    y += line_height - 5
                
                # Separator line
                pygame.draw.line(surface, (110, 110, 110), (right_panel[0] + 15, y - 3), (right_panel[0] + right_panel[2] - 15, y - 3), 1)
                y += 10
        else:
            surface.blit(font_small.render("No clients connected", True, (180, 180, 180)), (right_panel[0] + 20, y))
    else:
        surface.blit(font_small.render("No server connection", True, (255, 120, 120)), (right_panel[0] + 20, y))
    
    # Total players count
    total_players = len(all_players)
    
    # Game start section
    start_y = BASE_HEIGHT - 120
    start_panel = np.array([40, start_y, BASE_WIDTH - 80, 80], dtype=np.float64)
    pygame.draw.rect(surface, (50, 50, 50), start_panel)
    pygame.draw.rect(surface, (120, 120, 120), start_panel, 2)
    
    # Total players display
    total_text = f"Total Players: {total_players}"
    surface.blit(font_small.render(total_text, True, (255, 255, 255)), (60, start_y + 15))
    
    # Start game button
    start_button_x = BASE_WIDTH - 200
    start_button_y = start_y + 10
    start_button_rect = np.array([start_button_x, start_button_y, 150, 40], dtype=np.float64)
    
    is_start_selected = (Game.prep_section == 'start_game')
    start_color = (120, 255, 120) if is_start_selected else (100, 100, 100)
    
    pygame.draw.rect(surface, start_color, start_button_rect)
    pygame.draw.rect(surface, (255, 255, 255), start_button_rect, 2)
    
    start_text = "START GAME"
    start_text_surface = font_small.render(start_text, True, (255, 255, 255))
    start_text_rect = start_text_surface.get_rect(center=(start_button_x + 75, start_button_y + 20))
    surface.blit(start_text_surface, start_text_rect)
    
    # Controls help
    controls_text = "ARROWS: Navigate   TAB: Switch sections   ENTER: Select/Edit   LEFT/RIGHT: Change color   ESC: Back"
    surface.blit(font_small.render(controls_text, True, (180, 180, 180)), (60, start_y + 50))
    
    # Debug info
    debug_text = f"DEBUG: Section={Game.prep_section}, Row={Game.prep_cursor_row}, Col={Game.prep_cursor_col}, Players={Game.prep_num_players}"
    surface.blit(font_small.render(debug_text, True, (255, 255, 0)), (60, start_y + 70))
    
    # Server status debug
    if Game._cached_status:
        clients_count = len(Game._cached_status.get('clients', {}))
        players_count = len(Game._cached_status.get('players', {}))
        server_debug = f"SERVER: {clients_count} clients, {players_count} players"
        surface.blit(font_small.render(server_debug, True, (255, 255, 0)), (60, start_y + 90))
    else:
        surface.blit(font_small.render("SERVER: No connection", True, (255, 0, 0)), (60, start_y + 90))

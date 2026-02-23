import pygame
import numpy as np
import time
import math
import os
import bm_params as bmp
from bm_params import *
from input_abstraction import get_key_name
from timing_abstraction import get_ticks
from lib_collisions import circle_rect_collision

_AVATAR_CACHE = {}


def _get_image_asset(name):
    """Resolve image assets lazily from bm_params at runtime."""
    bmp.init_assets()
    return getattr(bmp, name, None)


def _load_avatar_by_name(name, size):
    if not name:
        return None
    key = (name.lower(), int(size))
    if key in _AVATAR_CACHE:
        return _AVATAR_CACHE[key]
    avatar_path = os.path.join('img', 'avatars', f'{name}.png')
    if not os.path.exists(avatar_path):
        _AVATAR_CACHE[key] = None
        return None
    try:
        img = pygame.image.load(avatar_path).convert_alpha()
        scaled = pygame.transform.smoothscale(img, (int(size), int(size)))
        mask = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (int(size // 2), int(size // 2)), int(size // 2))
        avatar = scaled.copy()
        avatar.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        _AVATAR_CACHE[key] = avatar
        return avatar
    except Exception:
        _AVATAR_CACHE[key] = None
        return None

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
    
    logo_image = _get_image_asset("logo_image")
    if logo_image is None:
        return
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
    
    fire_powerup_image = _get_image_asset("fire_powerup_image")
    if fire_powerup_image is None:
        return
    # Scale the fire powerup image to fit the size
    scaled_image = pygame.transform.smoothscale(fire_powerup_image, (size, size))
    
    # Get the rectangle for the scaled image and center it
    image_rect = scaled_image.get_rect(center=center)
    
    # Blit the scaled image onto the surface
    surface.blit(scaled_image, image_rect)

def draw_quad_damage_powerup_icon(surface, center, size):
    quad_damage_image = _get_image_asset("quad_damage_image")
    if quad_damage_image is None:
        return
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
            avatar = _load_avatar_by_name(getattr(player, 'name', ''), 2 * r)
            if avatar is not None:
                avatar_rect = avatar.get_rect(center=(pos[0], pos[1]))
                surface.blit(avatar, avatar_rect)
                pygame.gfxdraw.aacircle(surface, pos[0], pos[1], r, (255, 255, 255))
            else:
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
            img = _get_image_asset("blast_image_qd")
            center_img = _get_image_asset("blast_centre_image_qd")
        else:
            img = _get_image_asset("blast_image")
            center_img = _get_image_asset("blast_centre_image")
        if img is None or center_img is None:
            continue
        
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

def draw_stat_screen(surface, winner, players, game=None):
    _ensure_fonts_initialized()
    font = pygame.font.SysFont("arial", 48, bold=True)
    big_winner_font = pygame.font.SysFont("arial", 96, bold=True)
    draw_title_page(surface, alpha=255)
    if winner:
        x_start = BASE_WIDTH//2 + 150
        icon_size = 24
        for i in range(winner.trophies):
            trophy_pos = (x_start + i * (icon_size + 5), BASE_HEIGHT//2 + 70)
            draw_trophy_icon(surface, trophy_pos, icon_size)
        text = big_winner_font.render(f"{winner.name} wins!", True, winner.color)
    else:
        text = font.render("No one wins!", True, (255,255,255))
    rect = text.get_rect(center=(BASE_WIDTH//2, BASE_HEIGHT//2 + 80))
    surface.blit(text, rect)
    font_small = pygame.font.SysFont("arial", 32)
    y_offset = BASE_HEIGHT//2 + 110
    # Columns: Name | Trophies | Death (s) | Flames | Bombs | Kills | Walls | PU | Cells
    name_x = 50
    trophies_x = 260
    death_x = 450
    flames_x = 590
    bombs_x = 680
    kills_x = 760
    walls_x = 840
    pups_x = 920
    walked_x = 1000
    header_color = (200, 200, 200)
    surface.blit(font_small.render("Player", True, header_color), (name_x, y_offset))
    surface.blit(font_small.render("Trophies", True, header_color), (trophies_x, y_offset))
    surface.blit(font_small.render("Death (s)", True, header_color), (death_x, y_offset))
    surface.blit(font_small.render("Flames", True, header_color), (flames_x, y_offset))
    surface.blit(font_small.render("Bombs", True, header_color), (bombs_x, y_offset))
    surface.blit(font_small.render("Kills", True, header_color), (kills_x, y_offset))
    surface.blit(font_small.render("Walls", True, header_color), (walls_x, y_offset))
    surface.blit(font_small.render("PU", True, header_color), (pups_x, y_offset))
    surface.blit(font_small.render("Cells", True, header_color), (walked_x, y_offset))
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
        kills_text = font_small.render(str(getattr(player, 'players_killed', 0)), True, (255, 180, 180))
        walls_text = font_small.render(str(getattr(player, 'walls_destroyed', 0)), True, (220, 200, 170))
        pups_text = font_small.render(str(getattr(player, 'powerups_collected', 0)), True, (180, 255, 180))
        walked_text = font_small.render(str(getattr(player, 'cells_walked', 0)), True, (180, 220, 255))
        surface.blit(flames_text, (flames_x, y_offset))
        surface.blit(bombs_text, (bombs_x, y_offset))
        surface.blit(kills_text, (kills_x, y_offset))
        surface.blit(walls_text, (walls_x, y_offset))
        surface.blit(pups_text, (pups_x, y_offset))
        surface.blit(walked_text, (walked_x, y_offset))
        y_offset += 36

    # Draw replay panel on the right side (if replay data is available)
    has_replay_segment = game is not None and hasattr(game, 'replay_segment') and bool(game.replay_segment)
    has_replay_buffer = game is not None and hasattr(game, 'replay_buffer') and bool(game.replay_buffer)
    if game is not None and (has_replay_segment or has_replay_buffer):
        panel_w = int(BASE_WIDTH * REPLAY_PANEL_WIDTH_RATIO)
        panel_h = BASE_HEIGHT - 2 * REPLAY_PANEL_PADDING
        panel_x = BASE_WIDTH - panel_w - REPLAY_PANEL_PADDING
        panel_y = REPLAY_PANEL_PADDING
        pygame.draw.rect(surface, (30, 30, 30), (panel_x, panel_y, panel_w, panel_h))
        pygame.draw.rect(surface, (120, 120, 120), (panel_x, panel_y, panel_w, panel_h), 2)

        # Title
        title = font_small.render("Replay", True, (255, 255, 255))
        surface.blit(title, (panel_x + 10, panel_y + 8))

        # Choose a frame to render: if a frozen replay segment exists, animate it in a loop
        focus_name = getattr(game, 'replay_focus_player', None)
        chosen_frame = None
        if hasattr(game, 'replay_segment') and game.replay_segment:
            seg = game.replay_segment
            # Derive target time within segment loop
            seg_start = getattr(game, 'replay_segment_start_time', 0) or 0
            seg_end = getattr(game, 'replay_segment_end_time', seg_start)
            duration = max(1, int(seg_end - seg_start))
            # Anchor loop timing at first stat-screen render so replay always starts from the beginning.
            if not hasattr(game, 'replay_loop_anchor_time') or game.replay_loop_anchor_time is None:
                game.replay_loop_anchor_time = game.current_time
            loop_elapsed = max(0, int(game.current_time - game.replay_loop_anchor_time))
            loop_offset = loop_elapsed % duration
            target_t = seg_start + loop_offset
            # Find the most recent snapshot at or before target_t
            last_idx = 0
            for idx, (t, snap) in enumerate(seg):
                if t <= target_t:
                    last_idx = idx
                else:
                    break
            chosen_frame = seg[last_idx][1]
        else:
            # Fallback: still preview from the captured window (may disappear as buffer trims)
            end_t = getattr(game, 'replay_end_time', game.current_time)
            start_t = getattr(game, 'replay_start_time', max(0, end_t - REPLAY_BUFFER_MS))
            frames = [snap for (t, snap) in game.replay_buffer if start_t <= t <= end_t]
            if frames:
                chosen_frame = frames[-1]
        if chosen_frame:
            players_state = chosen_frame['players']
            # Determine camera center
            cam_x_px, cam_y_px = BASE_WIDTH // 2, BASE_HEIGHT // 2
            if focus_name:
                for ps in players_state:
                    if ps['name'] == focus_name:
                        cam_x_px, cam_y_px = int(ps['pos'][0]), int(ps['pos'][1])
                        break
            # Compute viewport in pixels based on cell radius
            cells_radius = REPLAY_CAMERA_RADIUS_CELLS
            view_w = (2 * cells_radius + 1) * CELL_SIZE
            view_h = (2 * cells_radius + 1) * CELL_SIZE
            view_rect = pygame.Rect(cam_x_px - view_w // 2, cam_y_px - view_h // 2, view_w, view_h)

            # Create a surface for the world snapshot
            world_surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
            # Draw board cells
            for y in range(GRID_HEIGHT):
                for x in range(GRID_WIDTH):
                    r = np.array([x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
                    if game.board[y][x] == EMPTY:
                        pygame.gfxdraw.box(world_surface, r, COLOR_BG)
                    elif game.board[y][x] == INDESTRUCTIBLE:
                        pygame.gfxdraw.box(world_surface, r, COLOR_INDESTRUCTIBLE)
                        pygame.draw.rect(world_surface, (80,80,80), r, 1)
                    elif game.board[y][x] == DESTRUCTIBLE:
                        pygame.gfxdraw.box(world_surface, r, COLOR_DESTRUCTIBLE)
                        draw_brick_pattern(r, world_surface)
                        pygame.draw.rect(world_surface, (80,80,80), r, 1)

            # Draw bombs
            for b in chosen_frame['bombs']:
                cx = b['x'] * CELL_SIZE + CELL_SIZE//2
                cy = b['y'] * CELL_SIZE + CELL_SIZE//2
                pygame.gfxdraw.filled_circle(world_surface, cx, cy, BOMB_BASE_RADIUS, COLOR_BOMB_FILL)
                pygame.gfxdraw.aacircle(world_surface, cx, cy, BOMB_BASE_RADIUS, COLOR_BOMB_OUTLINE)

            # Draw powerups
            for pu in chosen_frame['powerups']:
                center = (pu['x'] * CELL_SIZE + CELL_SIZE//2, pu['y'] * CELL_SIZE + CELL_SIZE//2)
                size = CELL_SIZE - 20
                draw_powerup_icon(world_surface, center, size, pu['type'])

            # Draw players
            for ps in players_state:
                if not ps['alive']:
                    continue
                pos = (int(ps['pos'][0]), int(ps['pos'][1]))
                r = ps['draw_radius']
                col = ps['color']
                pygame.gfxdraw.filled_circle(world_surface, pos[0], pos[1], r, col)
                pygame.gfxdraw.aacircle(world_surface, pos[0], pos[1], r, col)

            # Crop and scale to panel; guard against empty clip rects.
            clip_rect = view_rect.clip(world_surface.get_rect())
            if clip_rect.width > 0 and clip_rect.height > 0:
                sub_surface = world_surface.subsurface(clip_rect)
                scaled = pygame.transform.smoothscale(sub_surface, (panel_w - 2 * REPLAY_PANEL_PADDING, panel_h - 40))
                surface.blit(scaled, (panel_x + REPLAY_PANEL_PADDING, panel_y + 30))
        
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
    """Draw the host lobby screen with a clean split layout."""
    _ensure_fonts_initialized()
    surface.fill((24, 28, 34))
    pulse = 0.5 + 0.5 * math.sin(time.time() * 8.0)

    # Header
    title_font = pygame.font.SysFont("arial", 54, bold=True)
    subtitle_font = pygame.font.SysFont("arial", 28)
    title = title_font.render("BomberMarv Lobby", True, (238, 244, 255))
    subtitle = subtitle_font.render("Host setup and connected clients", True, (160, 176, 200))
    surface.blit(title, (40, 22))
    surface.blit(subtitle, (42, 72))
    # Game._cached_status is refreshed by the main loop; do not block drawing here.
    if not hasattr(Game, '_cached_status'):
        Game._cached_status = None

    # Build player list used by the left panel.
    all_players = []
    global_player_id = 1
    for i in range(Game.prep_num_players):
        all_players.append({
            'id': global_player_id,
            'name': Game.prep_player_names[i % len(Game.prep_player_names)],
            'color': Game.prep_player_colors[i % len(Game.prep_player_colors)],
            'team': Game.prep_player_teams[i % len(Game.prep_player_teams)],
            'type': 'local',
            'source': i,
            'status': _format_controls(Game.prep_controls[i % len(Game.prep_controls)]),
        })
        global_player_id += 1

    cached_clients = {}
    cached_players = {}
    if Game._cached_status:
        cached_clients = Game._cached_status.get('clients', {})
        cached_players = Game._cached_status.get('players', {})

    for client_id, client_info in cached_clients.items():
        if not client_info.get('registered', False):
            continue
        display_name = str(client_info.get('display_name', '') or '').strip()
        client_latency_5s = float(client_info.get('avg_latency_5s', client_info.get('avg_latency', 0)) or 0)
        for player_id in client_info.get('players', []):
            pinfo = cached_players.get(str(player_id), {})
            keys = pinfo.get('keys', {})
            pressed = []
            if keys.get('up'): pressed.append('UP')
            if keys.get('down'): pressed.append('DOWN')
            if keys.get('left'): pressed.append('LEFT')
            if keys.get('right'): pressed.append('RIGHT')
            if keys.get('bomb'): pressed.append('BOMB')
            live_status = ' + '.join(pressed) if pressed else 'IDLE'
            resolved_name = display_name if display_name else f"Client {client_id} P{player_id}"
            all_players.append({
                'id': global_player_id,
                'name': resolved_name,
                'color': global_player_id % len(colors),
                'team': (global_player_id - 1) % 2,
                'type': 'client',
                'source': (client_id, player_id),
                'status': live_status,
                'latency_5s': client_latency_5s,
            })
            global_player_id += 1

    # Panels
    top_y = 120
    panel_h = BASE_HEIGHT - 250
    left_panel = pygame.Rect(34, top_y, int(BASE_WIDTH * 0.62), panel_h)
    right_panel = pygame.Rect(left_panel.right + 14, top_y, BASE_WIDTH - left_panel.right - 48, panel_h)

    pygame.draw.rect(surface, (34, 41, 52), left_panel, border_radius=14)
    pygame.draw.rect(surface, (69, 87, 112), left_panel, 2, border_radius=14)
    pygame.draw.rect(surface, (30, 37, 48), right_panel, border_radius=14)
    pygame.draw.rect(surface, (64, 80, 104), right_panel, 2, border_radius=14)

    section_font = pygame.font.SysFont("arial", 32, bold=True)
    surface.blit(section_font.render("Players", True, (235, 242, 255)), (left_panel.x + 18, left_panel.y + 12))
    surface.blit(section_font.render("Remote Clients", True, (235, 242, 255)), (right_panel.x + 18, right_panel.y + 12))

    # Local player count controls
    label_font = pygame.font.SysFont("arial", 26, bold=True)
    surface.blit(label_font.render("Local player count", True, (185, 214, 180)), (left_panel.x + 20, left_panel.y + 56))

    button_y = left_panel.y + 88
    button_w = 52
    button_h = 34
    for idx in range(6):
        rect = pygame.Rect(left_panel.x + 20 + idx * (button_w + 8), button_y, button_w, button_h)
        selected = (Game.prep_section == 'local_players' and Game.prep_cursor_row == 0 and Game.prep_cursor_col == idx)
        if selected:
            glow = int(180 + 60 * pulse)
            fill = (glow, 180, 62)
            text_col = (20, 24, 28)
        else:
            fill = (74, 90, 112) if idx + 1 != Game.prep_num_players else (106, 144, 216)
            text_col = (236, 241, 248)
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, (196, 209, 228), rect, 1, border_radius=8)
        txt = label_font.render(str(idx + 1), True, text_col)
        surface.blit(txt, txt.get_rect(center=rect.center))

    # Player rows
    row_y = button_y + button_h + 22
    row_h = 44
    max_rows = max(1, (left_panel.bottom - row_y - 10) // row_h)
    shown_players = all_players[:max_rows]
    for i, p in enumerate(shown_players):
        rect = pygame.Rect(left_panel.x + 14, row_y + i * row_h, left_panel.width - 28, row_h - 4)
        selected = (Game.prep_section == 'local_players' and Game.prep_cursor_row == i + 1)
        editing = (Game.prep_editing_name and Game.prep_name_edit_index == i)
        if selected:
            glow = int(76 + 36 * pulse)
            row_bg = (glow, glow + 10, 110)
        else:
            row_bg = (43, 52, 66)
        pygame.draw.rect(surface, row_bg, rect, border_radius=8)
        pygame.draw.rect(surface, (102, 122, 148), rect, 1, border_radius=8)

        # color chip
        chip_rect = pygame.Rect(rect.x + 8, rect.y + 8, 18, 18)
        pygame.draw.rect(surface, colors[p['color'] % len(colors)], chip_rect, border_radius=4)
        pygame.draw.rect(surface, (220, 232, 248), chip_rect, 1, border_radius=4)

        name = p['name'] + "_" if editing else p['name']
        if p['type'] == 'local':
            name = f"L{p['id']}: {name}"
        else:
            name = f"R{p['id']}: {name}"
        name_color = (250, 234, 130) if (selected or editing) else (234, 242, 255)
        status_color = (142, 246, 160) if p['type'] == 'client' and p['status'] != 'IDLE' else (164, 181, 203)
        status_text = p['status']
        team_text = f"T{int(p.get('team', 0)) + 1}"
        if p['type'] == 'client':
            status_text = f"{p['status']} | {int(round(float(p.get('latency_5s', 0))))} ms"
        status_text = f"{team_text} | {status_text}"

        line_font = pygame.font.SysFont("arial", 34, bold=True)
        status_font = pygame.font.SysFont("arial", 28, bold=True)
        surface.blit(line_font.render(name, True, name_color), (chip_rect.right + 10, rect.y + 1))
        surface.blit(status_font.render(status_text, True, status_color), (rect.x + int(rect.width * 0.60), rect.y + 4))

    if len(all_players) > max_rows:
        more = len(all_players) - max_rows
        surface.blit(font_small.render(f"... and {more} more", True, (180, 188, 200)), (left_panel.x + 20, left_panel.bottom - 28))

    # Right panel client cards
    client_card_y = right_panel.y + 52
    if cached_clients:
        for client_id, info in cached_clients.items():
            if client_card_y > right_panel.bottom - 70:
                break
            last_seen = info.get('last_seen', 0)
            age = time.time() - last_seen
            online_col = (132, 233, 146) if age < 5 else (236, 200, 117) if age < 30 else (227, 123, 123)
            reg = "READY" if info.get('registered', False) else "WAITING"
            display_name = str(info.get('display_name', '') or '').strip()
            latency = info.get('avg_latency_5s', info.get('avg_latency', 0))
            samples = info.get('latency_samples_5s', info.get('latency_samples', 0))
            card = pygame.Rect(right_panel.x + 12, client_card_y, right_panel.width - 24, 62)
            pygame.draw.rect(surface, (43, 52, 66), card, border_radius=8)
            pygame.draw.rect(surface, (95, 116, 140), card, 1, border_radius=8)
            line1 = f"Client {client_id} - {reg}"
            if display_name:
                line1 += f" ({display_name})"
            line2 = f"Players: {len(info.get('players', []))}   Latency(5s): {latency}ms ({samples})"
            surface.blit(font_small.render(line1, True, online_col), (card.x + 10, card.y + 4))
            surface.blit(font_small.render(line2, True, (188, 204, 224)), (card.x + 10, card.y + 30))
            client_card_y += 70
    else:
        surface.blit(font_small.render("No remote clients connected.", True, (172, 184, 204)), (right_panel.x + 14, right_panel.y + 58))

    # Footer panel and start action
    footer = pygame.Rect(34, BASE_HEIGHT - 112, BASE_WIDTH - 68, 78)
    pygame.draw.rect(surface, (28, 34, 43), footer, border_radius=12)
    pygame.draw.rect(surface, (80, 97, 121), footer, 2, border_radius=12)

    total_players = len(all_players)
    totals = label_font.render(f"Total players: {total_players} (Local {Game.prep_num_players})", True, (232, 239, 250))
    surface.blit(totals, (footer.x + 18, footer.y + 14))

    start_rect = pygame.Rect(footer.right - 208, footer.y + 14, 188, 48)
    start_selected = (Game.prep_section == 'start_game')
    if start_selected:
        glow = int(132 + 50 * pulse)
        start_fill = (86, glow, 128)
    else:
        start_fill = (68, 98, 76)
    start_text_col = (22, 36, 24) if start_selected else (233, 246, 236)
    pygame.draw.rect(surface, start_fill, start_rect, border_radius=10)
    pygame.draw.rect(surface, (210, 235, 214), start_rect, 1, border_radius=10)
    start_text = label_font.render("START GAME", True, start_text_col)
    surface.blit(start_text, start_text.get_rect(center=start_rect.center))

    help_text = "ARROWS navigate | ENTER select/edit | LEFT/RIGHT color | T team | TAB switch | ESC back"
    surface.blit(font_small.render(help_text, True, (160, 176, 198)), (footer.x + 18, footer.y + 44))

import pygame
import numpy as np
import time
import math
import os
import types
import bm_params as bmp
from bm_params import *
from timing_abstraction import get_ticks
from lib_collisions import circle_rect_collision
from explosions import (
    explosion_arm_pixel_length,
    explosion_cell_rect,
    explosion_player_radius,
    explosion_tip_clip,
    is_player_in_planned_blast,
)
from bm_paths import lan_join_label
from lightning import draw_lightning_cross
from replay import frame_at_time, hydrate_replay_snapshot, letterbox_dest, pick_kill_cam, replay_view_rect

_AVATAR_CACHE = {}
_ASSETS_READY = False
_SCALED_IMAGE_CACHE = {}
_BOARD_LAYER_CACHE = {"signature": None, "surface": None}
_BLAST_ARM_CACHE = {}
_TEXT_CACHE = {}
_UI_FONT_CACHE = {}
_NAME_FONT_CACHE = {}
_LOBBY_BG_CACHE = {"key": None, "surf": None}

_WIN_STAT_COLUMNS = (
    ("name", "Player"),
    ("wins", "WINS"),
    ("death", "Death Time (s)"),
    ("flames", "Flames"),
    ("bombs", "Bombs"),
    ("kills", "Kills"),
    ("walls", "Walls Exploded"),
    ("pups", "Pickups"),
    ("qds", "QDs"),
    ("walked", "Cells Walked"),
)

_WIN_HEADER_LINES = {
    "Death Time (s)": ("Death", "Time (s)"),
    "Walls Exploded": ("Walls", "Exploded"),
    "Cells Walked": ("Cells", "Walked"),
}


def _get_image_asset(name):
    """Resolve image assets lazily from bm_params at runtime."""
    global _ASSETS_READY
    if not _ASSETS_READY:
        bmp.init_assets()
        _ASSETS_READY = True
    return getattr(bmp, name, None)


def _get_scaled_image(name, width, height):
    key = (name, int(width), int(height))
    cached = _SCALED_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    image = _get_image_asset(name)
    if image is None:
        return None
    scaled = pygame.transform.smoothscale(image, (int(width), int(height)))
    _SCALED_IMAGE_CACHE[key] = scaled
    return scaled


def _board_signature(theGame):
    return tuple(tuple(int(cell) for cell in row) for row in theGame.board)


def _build_board_layer(theGame):
    gw = getattr(theGame, 'grid_width', len(theGame.board[0]))
    gh = getattr(theGame, 'grid_height', len(theGame.board))
    layer = pygame.Surface((gw * CELL_SIZE, gh * CELL_SIZE))
    layer.fill(COLOR_BG)
    for y in range(gh):
        for x in range(gw):
            rect = np.array([x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
            if theGame.board[y][x] == EMPTY:
                pygame.gfxdraw.box(layer, rect, COLOR_BG)
            elif theGame.board[y][x] == INDESTRUCTIBLE:
                pygame.gfxdraw.box(layer, rect, COLOR_INDESTRUCTIBLE)
                pygame.draw.rect(layer, (80, 80, 80), rect, 1)
            elif theGame.board[y][x] == DESTRUCTIBLE:
                pygame.gfxdraw.box(layer, rect, COLOR_DESTRUCTIBLE)
                draw_brick_pattern(rect, layer)
                pygame.draw.rect(layer, (80, 80, 80), rect, 1)
    return layer


def _get_board_layer(theGame):
    signature = _board_signature(theGame)
    if _BOARD_LAYER_CACHE["signature"] != signature or _BOARD_LAYER_CACHE["surface"] is None:
        _BOARD_LAYER_CACHE["signature"] = signature
        _BOARD_LAYER_CACHE["surface"] = _build_board_layer(theGame)
    return _BOARD_LAYER_CACHE["surface"]


def _get_blast_arm_surface(image, length, thickness, direction):
    """Create a blast arm surface extending in the given direction.
    The source image is a horizontal flame strip; we scale to (length, thickness)
    and rotate so the arm extends correctly in each direction."""
    cache_key = (id(image), int(length), int(thickness), direction)
    cached = _BLAST_ARM_CACHE.get(cache_key)
    if cached is not None:
        return cached
    # Scale to (length, thickness) for all directions - length is along the arm
    # Flip along length so bulky base is at explosion center, pointy tip at outer end
    scaled = pygame.transform.smoothscale(image, (int(length), int(thickness)))
    if direction == "right":
        out = pygame.transform.flip(scaled, True, False)
    elif direction == "left":
        out = scaled
    elif direction == "up":
        out = pygame.transform.rotate(scaled, 90)
        out = pygame.transform.flip(out, False, True)
    elif direction == "down":
        out = pygame.transform.rotate(scaled, -90)
        out = pygame.transform.flip(out, False, True)
    else:
        out = scaled
    _BLAST_ARM_CACHE[cache_key] = out
    return out


def _get_cached_text(font_obj, text, color):
    key = (id(font_obj), str(text), tuple(color))
    cached = _TEXT_CACHE.get(key)
    if cached is not None:
        return cached
    rendered = font_obj.render(str(text), True, color)
    _TEXT_CACHE[key] = rendered
    return rendered


def _ui_font(size, bold=False):
    size = max(12, int(size))
    key = (size, bool(bold))
    font = _UI_FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("arial", size, bold=bold)
        _UI_FONT_CACHE[key] = font
    return font


def _fit_text_to_width(font, text, max_width):
    text = "" if text is None else str(text)
    if max_width <= 0:
        return ""
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = "…"
    if font.size(ellipsis)[0] > max_width:
        return ""
    lo, hi = 0, len(text)
    best = ellipsis
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid] + ellipsis
        if font.size(candidate)[0] <= max_width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _blit_clipped(surface, src, x, y, width, height):
    if src is None or width <= 0 or height <= 0:
        return
    old_clip = surface.get_clip()
    clip_rect = pygame.Rect(int(x), int(y), int(width), int(height))
    if old_clip:
        clip_rect = clip_rect.clip(old_clip)
    surface.set_clip(clip_rect)
    surface.blit(src, (int(x), int(y)))
    surface.set_clip(old_clip)


def _blit_label(surface, font, text, color, x, y, width, height, vcenter=True):
    fitted = _fit_text_to_width(font, text, max(0, int(width) - 2))
    src = font.render(fitted, True, color)
    text_y = y + max(0, (int(height) - src.get_height()) // 2) if vcenter else y
    _blit_clipped(surface, src, x, text_y, width, height)


def _series_count(player, total_attr, round_attr):
    return int(getattr(player, total_attr, 0) or 0) + int(getattr(player, round_attr, 0) or 0)


def _win_header_lines(label):
    return _WIN_HEADER_LINES.get(label, (label,))


def _measure_win_stat_columns(font, rows, available_w, trophy_size, force=False):
    """Return column x/width list that fits in available_w, or None."""
    n_cols = len(_WIN_STAT_COLUMNS)
    if available_w <= 0 or n_cols <= 0:
        return None
    inner_pad = max(8, font.get_height() // 4)
    name_cap = max(int(available_w * 0.22), font.size("Player")[0] + inner_pad)
    min_name_w = font.size("Mmmmmmmmmm")[0] + inner_pad
    min_widths = []
    for key, label in _WIN_STAT_COLUMNS:
        header_w = max(font.size(line)[0] for line in _win_header_lines(label))
        if key == "name":
            content_w = 0
            for row in rows:
                content_w = max(content_w, font.size(row["name"])[0])
            content_w = min(content_w, name_cap)
        elif key == "wins":
            max_trophies = max((row["trophies"] for row in rows), default=0)
            content_w = max_trophies * (trophy_size + 4) if max_trophies else trophy_size
        else:
            content_w = 0
            for row in rows:
                content_w = max(content_w, font.size(row[key])[0])
        min_widths.append(max(header_w, content_w) + inner_pad)

    min_gap = max(16, font.get_height() // 3)
    reserved_gaps = min_gap * (n_cols - 1)
    overflow = sum(min_widths) + reserved_gaps - available_w
    if overflow > 0:
        reducible = max(0, min_widths[0] - min_name_w)
        shrink = min(overflow, reducible)
        min_widths[0] -= shrink
        overflow -= shrink
        if overflow > 0:
            if not force:
                return None
            interior = max(1, available_w - reserved_gaps)
            scale = interior / max(1, sum(min_widths))
            min_widths = [max(16, w * scale) for w in min_widths]

    extra = available_w - sum(min_widths) - reserved_gaps
    if extra > 0:
        name_bonus = extra * 0.35
        min_widths[0] += name_bonus
        extra -= name_bonus
    gap_extra = extra / (n_cols - 1) if n_cols > 1 and extra > 0 else 0
    columns = []
    x = 0
    for i, (key, label) in enumerate(_WIN_STAT_COLUMNS):
        width = min_widths[i]
        columns.append({
            "key": key,
            "label": label,
            "lines": _win_header_lines(label),
            "x": int(round(x)),
            "width": int(width),
        })
        x += width
        if i < n_cols - 1:
            x += min_gap + gap_extra
    return columns


def _fit_win_stats_layout(rows, available_w, available_h, n_players):
    n_players = max(1, int(n_players))
    fallback = None
    for font_size in range(48, 17, -2):
        font = _ui_font(font_size)
        font_bold = _ui_font(font_size, bold=True)
        trophy_size = max(14, min(28, int(font_size * 0.7)))
        columns = _measure_win_stat_columns(font, rows, available_w, trophy_size)
        if columns is None:
            continue
        max_lines = max(len(col["lines"]) for col in columns)
        header_h = int(font_size * 1.12) * max_lines + 10
        row_h = max(int(font_size * 1.55), trophy_size + 12)
        candidate = {
            "font_size": font_size,
            "font": font,
            "font_bold": font_bold,
            "header_h": header_h,
            "row_h": row_h,
            "trophy_size": trophy_size,
            "columns": columns,
        }
        fallback = candidate
        if header_h + n_players * row_h <= available_h:
            return candidate
    if fallback is None:
        font = _ui_font(18)
        font_bold = _ui_font(18, bold=True)
        trophy_size = 14
        columns = _measure_win_stat_columns(font, rows, available_w, trophy_size, force=True)
        max_lines = max((len(col["lines"]) for col in columns), default=1)
        fallback = {
            "font_size": 18,
            "font": font,
            "font_bold": font_bold,
            "header_h": int(18 * 1.12) * max_lines + 8,
            "row_h": max(22, trophy_size + 8),
            "trophy_size": trophy_size,
            "columns": columns or [],
        }
    needed = fallback["header_h"] + n_players * fallback["row_h"]
    if needed > available_h and available_h > 0:
        fallback["row_h"] = max(20, (available_h - fallback["header_h"]) // n_players)
    return fallback


def _load_avatar_by_name(name, size):
    if not name:
        return None
    key = (name.lower(), int(size))
    if key in _AVATAR_CACHE:
        return _AVATAR_CACHE[key]
    from bm_paths import resource_path

    avatar_path = resource_path("img", "avatars", f"{name}.png")
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

def _key_label(key):
    key_names = {
        pygame.K_w: "W", pygame.K_a: "A", pygame.K_s: "S", pygame.K_d: "D",
        pygame.K_i: "I", pygame.K_j: "J", pygame.K_k: "K", pygame.K_l: "L",
        pygame.K_f: "F", pygame.K_c: "C", pygame.K_v: "V", pygame.K_b: "B",
        pygame.K_h: "H",
        pygame.K_SPACE: "Space", pygame.K_LSHIFT: "Shift", pygame.K_RSHIFT: "RShift",
        pygame.K_LCTRL: "Left Ctrl", pygame.K_RCTRL: "Right Ctrl",
        pygame.K_UP: "↑", pygame.K_DOWN: "↓", pygame.K_LEFT: "←", pygame.K_RIGHT: "→",
        pygame.K_HOME: "Home", pygame.K_END: "End", pygame.K_DELETE: "Del", pygame.K_PAGEDOWN: "PgDn",
        pygame.K_BACKSPACE: "Backspace",
        pygame.K_KP0: "Num 0", pygame.K_KP1: "Num 1", pygame.K_KP2: "Num 2", pygame.K_KP3: "Num 3",
        pygame.K_KP5: "Num 5", pygame.K_KP7: "Num 7", pygame.K_KP8: "Num 8", pygame.K_KP9: "Num 9",
        pygame.K_KP_DIVIDE: "Num /",
    }
    return key_names.get(key, "K%s" % key)


def _format_controls(controls):
    """Convert pygame key constants to readable control names."""
    move = " ".join(_key_label(controls[name]) for name in ("up", "left", "down", "right"))
    return "%s + %s" % (move, _key_label(controls["bomb"]))


READY_KEY_LINES = (
    "Local   W A S D move   ·   Space bomb",
    "Browser   Arrow keys move   ·   Space bomb",
)


def control_guide_rows():
    """Seat, move keys, bomb key. Extra rows use the middle column as the action."""
    from bm_params import controls_list
    rows = []
    for index, controls in enumerate(controls_list):
        move = " ".join(_key_label(controls[name]) for name in ("up", "left", "down", "right"))
        rows.append(("Player %d" % (index + 1), move, _key_label(controls["bomb"])))
    rows.append(("Browser", "Arrow keys or W A S D", "Space or Enter"))
    rows.append(("F11", "Fullscreen", ""))
    rows.append(("Esc", "Pause a round. On the lobby, asks before quitting.", ""))
    rows.append(("Enter", "Start the match and continue after a round", ""))
    return rows

def player_label_font_size(draw_radius):
    """Name labels scale with the avatar so they do not cover neighboring tiles."""
    return max(13, min(26, int(max(8, draw_radius) * 0.52)))


def _player_label_font(draw_radius, bold=False):
    size = player_label_font_size(draw_radius)
    key = (size, bool(bold))
    cached = _NAME_FONT_CACHE.get(key)
    if cached is not None:
        return cached
    font = pygame.font.SysFont("arial", size, bold=bold)
    _NAME_FONT_CACHE[key] = font
    return font


def _ensure_fonts_initialized():
    """Ensure fonts are initialized before use"""
    global arcade_font, font_small
    if arcade_font is None:
        arcade_font = pygame.font.SysFont('Comic Sans MS', 180)
    if font_small is None:
        font_small = pygame.font.SysFont("arial", 64)

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
            
            
def draw_title_page(surface, alpha=255, show_game_name=True, players=None, show_start_hint=False):
    # Ensure fonts are initialized
    _ensure_fonts_initialized()
    
    sw, sh = surface.get_size()
    
    surface.fill(COLOR_BG) 
    
    logo_image = _get_image_asset("logo_image")
    if logo_image is not None:
        logo_width, logo_height = logo_image.get_size()
        max_width = sw // 2
        max_height = sh // 5 if show_start_hint else sh // 4
        scale_factor = min(max_width / logo_width, max_height / logo_height)
        new_width = int(logo_width * scale_factor)
        new_height = int(logo_height * scale_factor)
        logo_scaled = pygame.transform.smoothscale(logo_image, (new_width, new_height))
        logo_scaled.set_alpha(alpha)
        rect = logo_scaled.get_rect(center=(sw // 2, max(new_height // 2 + 16, sh // 5)))
        surface.blit(logo_scaled, rect)
    elif show_game_name:
        game_name_text = arcade_font.render("BomberMarv", True, (255, 255, 255))
        game_name_rect = game_name_text.get_rect(center=(sw // 2, sh // 2))
        surface.blit(game_name_text, game_name_rect)
    
    if show_game_name and logo_image is not None:
        name_size = max(42, min(140, sh // 8)) if show_start_hint else min(180, max(48, sh // 6))
        name_font = pygame.font.SysFont("Comic Sans MS", name_size)
        game_name_text = name_font.render("BomberMarv", True, (255, 255, 255))
        name_y = sh // 2 - (sh // 14 if show_start_hint else 0)
        game_name_rect = game_name_text.get_rect(center=(sw // 2, name_y))
        surface.blit(game_name_text, game_name_rect)

    if show_start_hint:
        draw_controls(surface, players)
        hint_size = max(20, min(36, sh // 24))
        hint_font = pygame.font.SysFont("arial", hint_size)
        start_text = hint_font.render("Press Enter to start the game", True, (255, 255, 255))
        start_rect = start_text.get_rect(center=(sw // 2, sh - max(28, hint_size + 10)))
        surface.blit(start_text, start_rect)
    
    version_font = pygame.font.SysFont("arial", max(18, min(48, sh // 20)))
    version_text = version_font.render(VERSION, True, (255, 255, 255))
    version_rect = version_text.get_rect(bottomright=(sw - 10, sh - 10))
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
    surface.blit(_get_board_layer(theGame), (0, 0))
                
                

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
    
    scaled_image = _get_scaled_image("fire_powerup_image", size, size)
    if scaled_image is None:
        return
    
    # Get the rectangle for the scaled image and center it
    image_rect = scaled_image.get_rect(center=center)
    
    # Blit the scaled image onto the surface
    surface.blit(scaled_image, image_rect)

def draw_quad_damage_powerup_icon(surface, center, size):
    scaled_image = _get_scaled_image("quad_damage_image", size, size)
    if scaled_image is None:
        return
    
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

def _draw_brabi_glow(surface, pos, radius, now):
    """A green pulse that appears, swells, and goes out."""
    period = max(1, int(UBER_BOSS_GLOW_PERIOD_MS))
    phase = (int(now) % period) / period
    if phase > 0.42:
        return
    strength = math.sin(phase / 0.42 * math.pi)
    glow_r = int(radius * (1.2 + 0.9 * strength))
    alpha = int(50 + 150 * strength)
    layer = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
    center = (glow_r + 2, glow_r + 2)
    pygame.draw.circle(layer, (40, 255, 110, alpha), center, glow_r)
    pygame.draw.circle(layer, (210, 255, 220, int(alpha * 0.85)), center, max(2, int(glow_r * 0.55)), 3)
    surface.blit(layer, (pos[0] - glow_r - 2, pos[1] - glow_r - 2))


def _draw_cleaver(surface, pos, radius, player, now):
    """Bloody cleaver in BomberMarv's left hand, sticking out past the icon."""
    direction = getattr(player, "direction", None)
    if direction is None:
        dx, dy = 0.0, 0.0
    else:
        dx, dy = float(direction[0]), float(direction[1])
    moving = abs(dx) + abs(dy) > 0.25
    swinging = int(getattr(player, "cleaver_swing_until", 0) or 0) > int(now or 0)
    # Face stays upright. His left hand is on the viewer's right, on the rim.
    hand = (pos[0] + radius * 0.88, pos[1] + radius * 0.02)
    base = 0.18
    if moving:
        swing = math.sin(float(getattr(player, "animation_time", 0) or 0) / 80.0) * 0.38
    elif swinging:
        swing = math.sin(int(now) / 70.0) * 0.5
    else:
        swing = 0.16
    angle = base + swing
    handle_len = radius * 0.42
    blade_w = radius * 1.28
    blade_h = radius * 0.86
    grip = max(2.2, radius * 0.07)

    def rot(px, py):
        ca, sa = math.cos(angle), math.sin(angle)
        return (hand[0] + px * ca - py * sa, hand[1] + px * sa + py * ca)

    fist_r = max(3, int(radius * 0.18))
    pygame.draw.circle(surface, (48, 48, 54), (int(hand[0]), int(hand[1])), fist_r)
    pygame.draw.circle(surface, (24, 24, 28), (int(hand[0]), int(hand[1])), fist_r, 1)
    handle = [rot(0, -grip * 0.42), rot(handle_len, -grip * 0.42), rot(handle_len, grip * 0.42), rot(0, grip * 0.42)]
    pygame.draw.polygon(surface, (110, 68, 36), handle)
    pygame.draw.polygon(surface, (62, 36, 18), handle, 1)
    bx0 = handle_len * 0.78
    blade = [
        rot(bx0, -blade_h * 0.26),
        rot(bx0 + blade_w * 0.18, -blade_h * 0.58),
        rot(bx0 + blade_w, -blade_h * 0.46),
        rot(bx0 + blade_w, blade_h * 0.36),
        rot(bx0 + blade_w * 0.08, blade_h * 0.16),
    ]
    pygame.draw.polygon(surface, (176, 184, 192), blade)
    pygame.draw.polygon(surface, (52, 56, 64), blade, max(1, int(radius * 0.045)))
    pygame.draw.line(
        surface, (226, 230, 236),
        rot(bx0 + blade_w * 0.16, -blade_h * 0.34),
        rot(bx0 + blade_w * 0.78, -blade_h * 0.42),
        max(1, int(radius * 0.04)),
    )
    blood = (132, 16, 20)
    blood_dark = (78, 8, 12)
    pygame.draw.polygon(surface, blood, [
        rot(bx0 + blade_w * 0.22, -blade_h * 0.08),
        rot(bx0 + blade_w * 0.58, -blade_h * 0.30),
        rot(bx0 + blade_w * 0.84, -blade_h * 0.06),
        rot(bx0 + blade_w * 0.70, blade_h * 0.18),
        rot(bx0 + blade_w * 0.34, blade_h * 0.10),
    ])
    pygame.draw.polygon(surface, blood_dark, [
        rot(bx0 + blade_w * 0.48, -blade_h * 0.02),
        rot(bx0 + blade_w * 0.76, blade_h * 0.08),
        rot(bx0 + blade_w * 0.62, blade_h * 0.22),
        rot(bx0 + blade_w * 0.40, blade_h * 0.06),
    ])
    for ox, oy, scale in (
        (bx0 + blade_w * 0.70, blade_h * 0.42, 0.11),
        (bx0 + blade_w * 0.92, blade_h * 0.34, 0.08),
        (bx0 + blade_w * 0.48, blade_h * 0.30, 0.07),
    ):
        drop = rot(ox, oy)
        tail = rot(ox - blade_w * 0.02, oy - blade_h * 0.16)
        pygame.draw.polygon(surface, blood, [
            tail,
            rot(ox - radius * 0.06, oy),
            (drop[0], drop[1]),
            rot(ox + radius * 0.05, oy - blade_h * 0.02),
        ])
        pygame.draw.circle(surface, blood, (int(drop[0]), int(drop[1])), max(2, int(radius * scale)))


def draw_players(surface, players, explosions=None, current_time=None, bombs=None, board=None, grid_width=None, grid_height=None):
    _ensure_fonts_initialized()
    for player in players:
        if not player.alive and player.death_animation_time <= 0:
            continue
        pos = (int(player.pos[0]), int(player.pos[1]))
        r = player.draw_radius
        clock = current_time if current_time is not None else get_ticks()
        if player.alive and getattr(player, "sprite", "") == "brabi":
            _draw_brabi_glow(surface, pos, r, clock)
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
            # Scared only while standing on a live bomb's planned blast (max 5 cells).
            scared = False
            if bombs and board:
                px, py = player.get_grid_pos()
                gw = grid_width if grid_width is not None else len(board[0])
                gh = grid_height if grid_height is not None else len(board)
                scared = is_player_in_planned_blast(
                    px, py, bombs, board, gw, gh, SCARED_BLAST_MAX_CELLS
                )
            # Eyes: static white circles with black pupils that turn in direction of movement
            dx = float(getattr(player, 'direction', [0, 0])[0])
            dy = float(getattr(player, 'direction', [0, 0])[1])
            size = 2 * r
            eye_radius = max(4, int(size * 0.12))
            if scared:
                eye_radius = int(eye_radius * 1.5)
            pupil_radius = max(1, int(size * 0.05))
            eye_gap = size * 0.18
            eye_offset_y = eye_gap * 0.7
            # Static eye centers
            left_cx = pos[0] - eye_gap
            right_cx = pos[0] + eye_gap
            eye_cy = pos[1] - eye_offset_y
            # White eyes (static)
            pygame.gfxdraw.filled_circle(surface, int(left_cx), int(eye_cy), eye_radius, (255, 255, 255))
            pygame.gfxdraw.filled_circle(surface, int(right_cx), int(eye_cy), eye_radius, (255, 255, 255))
            pygame.gfxdraw.aacircle(surface, int(left_cx), int(eye_cy), eye_radius, (255, 255, 255))
            pygame.gfxdraw.aacircle(surface, int(right_cx), int(eye_cy), eye_radius, (255, 255, 255))
            # Black pupils (move within eye as if turning to look in direction)
            pupil_off = min(4, eye_radius - pupil_radius - 1)  # stay within eye
            left_px = left_cx + dx * pupil_off
            left_py = eye_cy + dy * pupil_off
            right_px = right_cx + dx * pupil_off
            right_py = eye_cy + dy * pupil_off
            pygame.gfxdraw.filled_circle(surface, int(left_px), int(left_py), pupil_radius, (0, 0, 0))
            pygame.gfxdraw.filled_circle(surface, int(right_px), int(right_py), pupil_radius, (0, 0, 0))
            pygame.gfxdraw.aacircle(surface, int(left_px), int(left_py), pupil_radius, (0, 0, 0))
            pygame.gfxdraw.aacircle(surface, int(right_px), int(right_py), pupil_radius, (0, 0, 0))
            # Glasses when quad damage is active
            if player.quad_damage:
                glasses_color = (0, 255, 255)
                lens_r = max(8, int(eye_radius * 1.8))
                frame_w = max(2, lens_r // 4)
                pygame.draw.circle(surface, glasses_color, (int(left_cx), int(eye_cy)), lens_r, frame_w)
                pygame.draw.circle(surface, glasses_color, (int(right_cx), int(eye_cy)), lens_r, frame_w)
                pygame.draw.line(surface, glasses_color, (int(left_cx + lens_r), int(eye_cy)), (int(right_cx - lens_r), int(eye_cy)), frame_w)
            # Mouth: line by default, circle when scared
            mouth_y = pos[1] + eye_gap * 0.8
            mouth_color = (40, 40, 40)
            if scared:
                mouth_r = max(2, int(size * 0.06))
                pygame.gfxdraw.filled_circle(surface, int(pos[0]), int(mouth_y), mouth_r, mouth_color)
                pygame.gfxdraw.aacircle(surface, int(pos[0]), int(mouth_y), mouth_r, mouth_color)
            else:
                mouth_w = int(size * 0.25)
                pygame.draw.line(surface, mouth_color, (int(pos[0] - mouth_w), int(mouth_y)), (int(pos[0] + mouth_w), int(mouth_y)), 2)
            leg_width = r//3
            leg_height = r//4
            leg_offset = int(6 * math.sin(player.animation_time / 150.0))
            left_leg = np.array([pos[0] - r//2 - leg_width//2, pos[1] + r - 2 + leg_offset, leg_width, leg_height], dtype=np.float64)
            right_leg = np.array([pos[0] + r//2 - leg_width//2, pos[1] + r - 2 - leg_offset, leg_width, leg_height], dtype=np.float64)
            leg_color = (player.color[0]//2, player.color[1]//2, player.color[2]//2)
            pygame.draw.rect(surface, leg_color, left_leg)
            pygame.draw.rect(surface, leg_color, right_leg)
            if getattr(player, "sprite", "") == "cleaver":
                _draw_cleaver(surface, pos, r, player, clock)

            if player.quad_damage:
                clock = current_time if current_time is not None else get_ticks()
                elapsed = clock - player.quad_damage_start_time
                pulse = 1 + 0.1 * math.sin(2 * math.pi * (elapsed / 500.0))
                rect_size = int((2 * r + 10) * pulse)
                rect = np.array([pos[0] - rect_size // 2, pos[1] - rect_size // 2, rect_size, rect_size], dtype=np.float64)
                pygame.draw.rect(surface, (0, 255, 255), rect, 4)

            shield_until = getattr(player, 'boss_shield_until', 0)
            if current_time is not None and shield_until > current_time:
                pulse = 1 + 0.08 * math.sin(2 * math.pi * (current_time / 280.0))
                shield_r = int((r + 10) * pulse)
                pygame.draw.circle(surface, (210, 230, 255), pos, shield_r, 4)
                pygame.draw.circle(surface, (130, 180, 255), pos, max(1, shield_r - 6), 2)
            
            if player.name:
                name_font = _player_label_font(r)
                name_text = _get_cached_text(name_font, player.name, (255, 255, 255))
                name_rect = name_text.get_rect(center=(pos[0], pos[1] - r - max(8, name_font.get_height() // 2)))
                surface.blit(name_text, name_rect)
            clock = current_time if current_time is not None else get_ticks()
            if getattr(player, 'pickup_message_end_time', 0) and clock < player.pickup_message_end_time:
                msg_font = _player_label_font(r + 8, bold=True)
                msg_text = msg_font.render(player.pickup_message, True, (255, 255, 0))
                msg_rect = msg_text.get_rect(center=(pos[0], pos[1] - r - msg_font.get_height() - 18))
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
    import bm_settings
    for explosion in explosions:
        norm = (current_time - explosion.start_time) / max(1, bm_settings.explosion_duration_ms())
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
        
        up_length = explosion_arm_pixel_length(arm_factor, up_max, CELL_SIZE)
        down_length = explosion_arm_pixel_length(arm_factor, down_max, CELL_SIZE)
        left_length = explosion_arm_pixel_length(arm_factor, left_max, CELL_SIZE)
        right_length = explosion_arm_pixel_length(arm_factor, right_max, CELL_SIZE)

        if getattr(explosion, "lightning", False):
            draw_lightning_cross(
                surface,
                center_pixel,
                ((0, -1, up_length), (0, 1, down_length), (-1, 0, left_length), (1, 0, right_length)),
                CELL_SIZE,
                current_time,
                seed=int(explosion.start_time) + cx * 17 + cy * 31,
                alpha_scale=max(0.35, arm_factor),
                style=getattr(explosion, "lightning_style", "") or "marv",
            )
            continue

        if explosion.quad_damage:
            img = _get_image_asset("blast_image_qd")
            center_img = _get_image_asset("blast_centre_image_qd")
        else:
            img = _get_image_asset("blast_image")
            center_img = _get_image_asset("blast_centre_image")
        if img is None or center_img is None:
            continue
        
        # Draw the center of the explosion using the center image
        center_size = int(CELL_SIZE * FLAME_ARM_THICKNESS_RATIO)
        center_key = "blast_centre_image_qd" if explosion.quad_damage else "blast_centre_image"
        scaled_center_img = _get_scaled_image(center_key, center_size, center_size)
        if scaled_center_img is None:
            continue
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
    import bm_settings
    for explosion in explosions:
        # Calculate animation timing (same as in handle_explosions and draw_explosions)
        norm = (current_time - explosion.start_time) / max(1, bm_settings.explosion_duration_ms())
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
            hit_radius = explosion_player_radius(CELL_SIZE, EXPLOSION_PLAYER_HIT_SCALE)
            for cell in active_cells:
                x, y = cell
                rx, ry, rw, rh = explosion_cell_rect(
                    x, y, CELL_SIZE, EXPLOSION_COLLISION_SCALE,
                    clip_outward=explosion_tip_clip(cx, cy, x, y, active_cells),
                )
                border_width = max(2, int(4 * arm_factor))
                border_color = (255, 60, 60) if arm_factor > 0.5 else (200, 80, 80)
                fill_surface = pygame.Surface((max(1, int(rw)), max(1, int(rh))), pygame.SRCALPHA)
                fill_surface.fill((255, 0, 0, 60))
                surface.blit(fill_surface, (rx, ry))
                pygame.draw.rect(surface, border_color, (rx, ry, rw, rh), border_width)
                
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
                            if circle_rect_collision((player.pos[0], player.pos[1]), hit_radius, (rx, ry, rw, rh)):
                                pygame.draw.circle(surface, (255, 255, 0), (int(player.pos[0]), int(player.pos[1])), int(hit_radius), 2)

def draw_blast_arm(surface, start_pos, end_offset, image):
    x1, y1 = start_pos
    x2, y2 = x1 + end_offset[0], y1 + end_offset[1]
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 0:
        return
    thickness = int(CELL_SIZE * FLAME_ARM_THICKNESS_RATIO)
    if abs(end_offset[0]) >= abs(end_offset[1]):
        direction = "right" if end_offset[0] > 0 else "left"
    else:
        direction = "down" if end_offset[1] > 0 else "up"
    arm_surface = _get_blast_arm_surface(image, int(length), thickness, direction)
    image_rect = arm_surface.get_rect(center=(x1, y1))
    if direction == "up":
        image_rect.bottom = y1
    elif direction == "down":
        image_rect.top = y1
    elif direction == "left":
        image_rect.right = x1
    else:
        image_rect.left = x1
    surface.blit(arm_surface, image_rect)

def draw_controls(surface, players):
    """Compact keyboard cheat-sheet for the title screen."""
    sw, sh = surface.get_size()
    roster = [p for p in (players or []) if getattr(p, "controls", None)]
    title_size = max(16, min(28, sh // 36))
    row_size = max(14, min(22, sh // 42))
    title_font = pygame.font.SysFont("arial", title_size, bold=True)
    row_font = pygame.font.SysFont("arial", row_size)
    y = int(sh * 0.62)
    header = title_font.render("Controls  ·  Move  +  Bomb", True, (220, 226, 236))
    surface.blit(header, header.get_rect(center=(sw // 2, y)))
    y += title_font.get_height() + 8
    if not roster:
        line = row_font.render("P1  WASD  +  Space", True, (200, 210, 224))
        surface.blit(line, line.get_rect(center=(sw // 2, y)))
        return
    gap = row_font.get_height() + 6
    for player in roster[:6]:
        label = f"{player.name}:  {_format_controls(player.controls)}"
        text = row_font.render(label, True, getattr(player, "color", (255, 255, 255)))
        surface.blit(text, text.get_rect(center=(sw // 2, y)))
        y += gap
        if y > sh - 56:
            break


def result_content_top(sh):
    """Y where the result heading starts. Corner cards stay above this line."""
    return int(sh * 0.34)


def _win_screen_regions(sw, sh, has_replay):
    """Stats on top; replay is a near-square panel under the table when present."""
    padding = max(16, int(sw * 0.012))
    gap = 14
    table_top_min = result_content_top(sh)
    table_w = sw - 2 * padding
    replay_w = 0
    replay_h = 0
    if has_replay:
        replay_h = int(sh * REPLAY_PANEL_HEIGHT_RATIO)
        max_replay_h = max(160, sh - table_top_min - 160 - padding)
        replay_h = min(replay_h, max_replay_h)
        replay_h = max(int(sh * 0.32), replay_h)
        replay_w = min(int(sw * REPLAY_PANEL_WIDTH_RATIO), int(replay_h * 1.25), sw - 2 * padding)
        replay_w = max(replay_w, min(sw - 2 * padding, int(replay_h * 0.92)))
    available_h = max(120, sh - table_top_min - padding - (replay_h + gap if has_replay else 0))
    return {
        "padding": padding,
        "gap": gap,
        "table_top_min": table_top_min,
        "table_w": table_w,
        "available_h": available_h,
        "replay_w": replay_w,
        "replay_h": replay_h,
    }


def draw_stat_screen(surface, winner, players, game=None, heading=None, heading_color=None, caption=None):
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    draw_title_page(surface, alpha=255, show_game_name=False)
    players = list(players or [])
    n_players = max(1, len(players))

    death_vals = []
    flames_vals = []
    bombs_vals = []
    for p in players:
        if hasattr(p, 'death_time_rel_ms') and p.death_time_rel_ms is not None:
            death_vals.append(int(round(p.death_time_rel_ms / 1000.0)))
        else:
            death_vals.append(999999)
        fp = p.fire_power_at_death if hasattr(p, 'fire_power_at_death') and p.fire_power_at_death is not None else getattr(p, 'fire_power', 0)
        bp = p.bomb_capacity_at_death if hasattr(p, 'bomb_capacity_at_death') and p.bomb_capacity_at_death is not None else getattr(p, 'bomb_capacity', 0)
        flames_vals.append(fp)
        bombs_vals.append(bp)
    max_death = max(death_vals) if death_vals else 0
    max_flames = max(flames_vals) if flames_vals else 0
    max_bombs = max(bombs_vals) if bombs_vals else 0
    max_kills = max((_series_count(p, 'total_players_killed', 'players_killed') for p in players), default=0)
    max_walls = max((_series_count(p, 'total_walls_destroyed', 'walls_destroyed') for p in players), default=0)
    max_pups = max((_series_count(p, 'total_powerups_collected', 'powerups_collected') for p in players), default=0)
    max_qd = max((_series_count(p, 'total_quad_damage_collected', 'quad_damage_collected') for p in players), default=0)
    max_walked = max((_series_count(p, 'total_cells_walked', 'cells_walked') for p in players), default=0)

    rows = []
    for i, player in enumerate(players):
        if hasattr(player, 'death_time_rel_ms') and player.death_time_rel_ms is not None:
            death_text_str = str(int(round(player.death_time_rel_ms / 1000.0)))
            death_color = (255, 160, 160)
        else:
            death_text_str = "—"
            death_color = (160, 255, 160)
        kills_val = _series_count(player, 'total_players_killed', 'players_killed')
        walls_val = _series_count(player, 'total_walls_destroyed', 'walls_destroyed')
        pups_val = _series_count(player, 'total_powerups_collected', 'powerups_collected')
        qd_val = _series_count(player, 'total_quad_damage_collected', 'quad_damage_collected')
        walked_val = _series_count(player, 'total_cells_walked', 'cells_walked')
        rows.append({
            "name": str(getattr(player, "name", "") or f"P{i + 1}"),
            "color": getattr(player, "color", (255, 255, 255)),
            "trophies": int(getattr(player, "trophies", 0) or 0),
            "death": death_text_str,
            "death_color": death_color,
            "flames": str(flames_vals[i]),
            "bombs": str(bombs_vals[i]),
            "kills": str(kills_val),
            "walls": str(walls_val),
            "pups": str(pups_val),
            "qds": str(qd_val),
            "walked": str(walked_val),
            "bold": {
                "death": death_vals[i] == max_death and max_death > 0,
                "flames": flames_vals[i] == max_flames and max_flames > 0,
                "bombs": bombs_vals[i] == max_bombs and max_bombs > 0,
                "kills": kills_val == max_kills and max_kills > 0,
                "walls": walls_val == max_walls and max_walls > 0,
                "pups": pups_val == max_pups and max_pups > 0,
                "qds": qd_val == max_qd and max_qd > 0,
                "walked": walked_val == max_walked and max_walked > 0,
            },
        })

    cell_colors = {
        "flames": (255, 220, 160),
        "bombs": (160, 220, 255),
        "kills": (255, 180, 180),
        "walls": (220, 200, 170),
        "pups": (180, 255, 180),
        "qds": (100, 220, 255),
        "walked": (180, 220, 255),
    }

    has_kill_cams = game is not None and bool(getattr(game, "kill_cam_clips", None))
    has_replay_segment = game is not None and hasattr(game, 'replay_segment') and bool(game.replay_segment)
    has_replay = has_kill_cams or has_replay_segment
    regions = _win_screen_regions(sw, sh, has_replay)
    padding = regions["padding"]
    gap = regions["gap"]
    table_top_min = regions["table_top_min"]
    table_w = regions["table_w"]
    available_h = regions["available_h"]
    replay_w = regions["replay_w"]
    replay_h = regions["replay_h"]
    layout = _fit_win_stats_layout(rows, table_w, available_h, n_players)

    table_left = padding
    font = layout["font"]
    font_bold = layout["font_bold"]
    header_h = layout["header_h"]
    row_h = layout["row_h"]
    trophy_size = layout["trophy_size"]
    columns = layout["columns"]

    if heading:
        winner_label = heading
        winner_color = heading_color or (winner.color if winner else (255, 255, 255))
    elif winner:
        winner_label = f"{winner.name} wins!"
        winner_color = winner.color
    else:
        winner_label = "No one wins!"
        winner_color = (255, 255, 255)
    winner_max_size = min(120, int(sh * 0.08))
    winner_font = _ui_font(36, bold=True)
    for size in range(winner_max_size, 27, -4):
        trial = _ui_font(size, bold=True)
        if trial.size(winner_label)[0] <= table_w:
            winner_font = trial
            break
    winner_label = _fit_text_to_width(winner_font, winner_label, table_w)
    winner_surf = winner_font.render(winner_label, True, winner_color)
    winner_h = winner_surf.get_height()
    trophy_icon = max(16, min(28, winner_h // 3))
    winner_trophies = int(getattr(winner, "trophies", 0) or 0) if winner else 0
    trophy_strip_w = winner_trophies * (trophy_icon + 4) if winner_trophies else 0

    table_h = header_h + n_players * row_h
    table_bottom = sh - padding
    caption_font = _ui_font(max(18, min(28, layout["font_size"])))
    trophy_goal = TROPHY_WIN_THRESHOLD
    if game is not None and hasattr(game, "trophy_threshold"):
        trophy_goal = int(game.trophy_threshold())
    caption_text = caption if caption is not None else f"Match totals until {trophy_goal} trophies"
    if caption is None and game is not None:
        extra = game.result_prompt() if hasattr(game, "result_prompt") else ""
        if extra:
            caption_text = f"{caption_text}   ·   {extra}"
    caption_h = caption_font.get_height() + 10
    # The heading stays on the content line, clear of the corner card above it.
    winner_top = table_top_min
    table_top = winner_top + winner_h + caption_h + 16
    if table_top + table_h > table_bottom:
        table_top = winner_top + winner_h + caption_h + 8

    winner_x = table_left + max(0, (table_w - winner_surf.get_width() - trophy_strip_w - 12) // 2)
    surface.blit(winner_surf, (winner_x, winner_top))
    if winner_trophies:
        trophy_x = winner_x + winner_surf.get_width() + 12
        trophy_y = winner_top + max(0, (winner_h - trophy_icon) // 2)
        for i in range(winner_trophies):
            draw_trophy_icon(surface, (trophy_x + i * (trophy_icon + 4), trophy_y), trophy_icon)
    caption_surf = caption_font.render(caption_text, True, (186, 196, 210))
    caption_rect = caption_surf.get_rect(midtop=(table_left + table_w // 2, winner_top + winner_h + 4))
    surface.blit(caption_surf, caption_rect)

    header_color = (200, 200, 200)
    line_h = int(layout["font_size"] * 1.12)
    for col in columns:
        line_y = table_top
        for line in col["lines"]:
            text_surf = font.render(line, True, header_color)
            _blit_clipped(surface, text_surf, table_left + col["x"], line_y, col["width"], line_h)
            line_y += line_h
    pygame.draw.line(
        surface,
        (140, 150, 165),
        (table_left, table_top + header_h - 4),
        (table_left + table_w, table_top + header_h - 4),
        1,
    )

    for i, row in enumerate(rows):
        row_y = table_top + header_h + i * row_h
        text_y = row_y + max(0, (row_h - font.get_height()) // 2)
        for col in columns:
            key = col["key"]
            x = table_left + col["x"]
            if key == "wins":
                icon_y = row_y + max(0, (row_h - trophy_size) // 2)
                for j in range(row["trophies"]):
                    icon_x = x + j * (trophy_size + 4)
                    if icon_x + trophy_size > x + col["width"]:
                        break
                    draw_trophy_icon(surface, (icon_x, icon_y), trophy_size)
                continue
            if key == "name":
                value = _fit_text_to_width(font, row["name"], max(12, col["width"] - 4))
                color = row["color"]
                use_font = font_bold
            else:
                value = row[key]
                color = row["death_color"] if key == "death" else cell_colors.get(key, (255, 255, 255))
                use_font = font_bold if row["bold"].get(key) else font
            text_surf = use_font.render(value, True, color)
            _blit_clipped(surface, text_surf, x, text_y, col["width"], row_h)

    # Draw replay under the stats table (if replay data is available)
    if has_replay and replay_w > 0 and replay_h > 0:
        panel_w = replay_w
        panel_h = replay_h
        panel_x = max(padding, (sw - panel_w) // 2)
        panel_y = table_top + table_h + gap
        if panel_y + panel_h > sh - padding:
            panel_h = max(140, sh - padding - panel_y)
        if panel_y + panel_h > sh - 4:
            panel_y = max(table_top + table_h + 8, sh - padding - panel_h)
        pygame.draw.rect(surface, (30, 30, 30), (panel_x, panel_y, panel_w, panel_h))
        pygame.draw.rect(surface, (120, 120, 120), (panel_x, panel_y, panel_w, panel_h), 2)

        # Title
        replay_font = _ui_font(min(36, max(18, panel_w // 10)))
        title = replay_font.render("Replay", True, (255, 255, 255))
        _blit_clipped(surface, title, panel_x + 10, panel_y + 8, panel_w - 20, title.get_height())

        focus_name = getattr(game, 'replay_focus_player', None)
        chosen_frame = None
        clips = list(getattr(game, "kill_cam_clips", None) or [])
        if clips:
            if not getattr(game, "replay_loop_anchor_time", None):
                game.replay_loop_anchor_time = game.current_time
            loop_elapsed = max(0, int(game.current_time - game.replay_loop_anchor_time))
            clip, target_t = pick_kill_cam(clips, loop_elapsed)
            if clip is not None:
                focus_name = clip.get("name") or focus_name
                chosen_frame = frame_at_time(clip.get("frames") or [], target_t)
                cam_label = _ui_font(min(22, max(14, panel_w // 16)))
                label = cam_label.render(f"Kill cam: {focus_name}", True, (220, 220, 220))
                _blit_clipped(
                    surface, label, panel_x + 10, panel_y + 8 + title.get_height(),
                    panel_w - 20, label.get_height(),
                )
        elif hasattr(game, 'replay_segment') and game.replay_segment:
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
            chosen_frame = frame_at_time(seg, target_t)
        else:
            # Fallback: still preview from the captured window (may disappear as buffer trims)
            end_t = getattr(game, 'replay_end_time', game.current_time)
            start_t = getattr(game, 'replay_start_time', max(0, end_t - REPLAY_BUFFER_MS))
            frames = [(t, snap) for (t, snap) in game.replay_buffer if start_t <= t <= end_t]
            if frames:
                chosen_frame = frames[-1][1] if isinstance(frames[-1], tuple) else frames[-1]
        if chosen_frame:
            players_state = chosen_frame['players']
            # Determine camera center
            cam_x_px, cam_y_px = sw // 2, sh // 2
            if focus_name:
                for ps in players_state:
                    if ps['name'] == focus_name:
                        cam_x_px, cam_y_px = int(ps['pos'][0]), int(ps['pos'][1])
                        break
            frame = hydrate_replay_snapshot(chosen_frame)
            board = frame["board"] if frame["board"] is not None else game.board
            gw = int(frame["grid_width"] or getattr(game, "grid_width", len(board[0])))
            gh = int(frame["grid_height"] or getattr(game, "grid_height", len(board)))
            world_w = gw * CELL_SIZE
            world_h = gh * CELL_SIZE
            vx, vy, view_w, view_h = replay_view_rect(
                cam_x_px, cam_y_px, world_w, world_h, CELL_SIZE, REPLAY_CAMERA_RADIUS_CELLS
            )
            view_rect = pygame.Rect(vx, vy, view_w, view_h)
            world_surface = pygame.Surface((world_w, world_h))
            world_game = types.SimpleNamespace(
                board=board,
                grid_width=gw,
                grid_height=gh,
                powerups=frame["powerups"],
            )
            draw_board(world_surface, world_game)
            draw_powerups(world_surface, world_game)
            draw_bombs(world_surface, frame["t"], frame["bombs"])
            if frame["explosions"]:
                draw_explosions(world_surface, frame["t"], frame["explosions"])
            draw_players(
                world_surface,
                frame["players"],
                frame["explosions"],
                frame["t"],
                frame["bombs"],
                board,
                gw,
                gh,
            )

            # Keep a square crop even at map edges, then letterbox into the panel.
            crop = pygame.Surface((view_w, view_h))
            crop.fill(COLOR_BG)
            crop.blit(world_surface, (-view_rect.x, -view_rect.y))
            title_h = 52 if clips else 30
            avail_w = max(1, panel_w - 2 * REPLAY_PANEL_PADDING)
            avail_h = max(1, panel_h - title_h - REPLAY_PANEL_PADDING)
            dest_w, dest_h, ox, oy = letterbox_dest(view_w, view_h, avail_w, avail_h)
            if dest_w > 0 and dest_h > 0:
                scaled = pygame.transform.scale(crop, (dest_w, dest_h))
                surface.blit(
                    scaled,
                    (panel_x + REPLAY_PANEL_PADDING + ox, panel_y + title_h + oy),
                )
        
    #draw_controls(surface)

def _result_logo_rect(sw, sh):
    """Square logo box from the result background, so the invite card can sit beside it."""
    side = min(sw // 2, sh // 4)
    cx = sw // 2
    cy = max(side // 2 + 16, sh // 5)
    return pygame.Rect(cx - side // 2, cy - side // 2, side, side)


def champion_boss_card_rect(sw, sh):
    """Top-right invite card. Wider than the logo gap, still above the heading."""
    margin = max(12, int(min(sw, sh) * 0.018))
    logo = _result_logo_rect(sw, sh)
    card_h = max(1, min(300, result_content_top(sh) - margin - 10))
    room = sw - margin - logo.right - 18
    if room >= 280:
        card_w = min(540, room)
    else:
        card_w = min(340, max(200, sw - 2 * margin))
    return pygame.Rect(sw - margin - card_w, margin, card_w, card_h)


def draw_champion_screen(surface, champion, players=None, game=None):
    """Stats, kill-cams, and a compact BomberMarv card in the top-right corner."""
    champ_name = champion.name if champion is not None else "Champion"
    roster = players if players is not None else ([champion] if champion else [])
    draw_stat_screen(surface, champion, roster, game, heading=f"Champion: {champ_name}")
    _draw_champion_boss_card(surface, game)


def _quote_beats(quote):
    """Break a boss line on its punches, then on a single comma."""
    import re
    text = str(quote).strip()
    beats = [part.strip() for part in re.split(r"(?<=\?!) |(?<=\?\?\?) ", text) if part.strip()]
    if len(beats) == 1 and ", " in text:
        left, right = text.split(", ", 1)
        beats = [f"{left},", right]
    return beats or [text]


def _wrap_words(text, font, width):
    words = str(text).split()
    if not words:
        return []
    lines = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if not current or font.size(trial)[0] <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _invite_quote_lines(quote, font=None, width=10**6):
    lines = []
    for beat in _quote_beats(quote):
        if font is None:
            lines.append(beat)
        else:
            lines.extend(_wrap_words(beat, font, width) or [beat])
    if not lines:
        return ['""']
    if len(lines) == 1:
        return [f'"{lines[0]}"']
    quoted = []
    for i, line in enumerate(lines):
        if i == 0:
            quoted.append(f'"{line}')
        elif i == len(lines) - 1:
            quoted.append(f'{line}"')
        else:
            quoted.append(line)
    return quoted


def _draw_boss_invite_card(surface, game, *, name, color, quote, stats, sprite, backdrop, ring, radius_scale=1.0):
    """Top-right portrait card. BomberMarv on the champion screen, BomberTom before his fight."""
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    card = champion_boss_card_rect(sw, sh)
    if card.width < 120 or card.height < 100:
        return

    pygame.draw.rect(surface, (24, 28, 38), card, border_radius=14)
    pygame.draw.rect(surface, (196, 209, 228), card, 2, border_radius=14)

    pulse = 0.5 + 0.5 * math.sin(time.time() * 3.0)
    boss_r = max(18, int(min(card.width, card.height) * 0.18 * radius_scale))
    boss_pos = (card.centerx, card.y + 10 + boss_r)
    now = getattr(game, "current_time", 0) if game is not None else int(time.time() * 1000)
    glow_r = int(boss_r * (1.18 + 0.06 * pulse))
    pygame.draw.circle(surface, backdrop, boss_pos, glow_r)
    pygame.draw.circle(surface, ring, boss_pos, glow_r, 2)

    boss_portrait = types.SimpleNamespace(
        name="",
        color=color,
        pos=boss_pos,
        alive=True,
        draw_radius=boss_r,
        direction=(0.0, 1.0),
        animation_time=float(now),
        quad_damage=False,
        quad_damage_start_time=0,
        death_animation_time=0,
        pickup_message="",
        pickup_message_end_time=0,
        global_id="boss-portrait",
        sprite=sprite,
        cleaver_swing_until=10**12,
        get_grid_pos=lambda: (0, 0),
    )
    draw_players(surface, [boss_portrait], current_time=now)

    name_font = _ui_font(min(34, max(22, card.height // 8)), bold=True)
    stat_font = _ui_font(min(20, max(15, card.height // 13)))
    inset = 14
    text_w = card.width - inset * 2
    name_y = boss_pos[1] + boss_r + 6
    _blit_label(surface, name_font, name, (236, 240, 248), card.x + inset, name_y, text_w, name_font.get_height() + 2)
    stats_h = stat_font.get_height() + 2
    quote_top = name_y + name_font.get_height() + 4
    quote_budget = max(12, card.bottom - 10 - stats_h - 8 - quote_top)
    quote_font = _ui_font(16)
    lines = _invite_quote_lines(quote, quote_font, text_w)
    line_h = quote_font.get_height() + 2
    for size in range(min(26, max(18, card.height // 10)), 15, -1):
        quote_font = _ui_font(size)
        lines = _invite_quote_lines(quote, quote_font, text_w)
        line_h = quote_font.get_height() + 2
        if len(lines) * line_h <= quote_budget:
            break
    for i, line in enumerate(lines):
        y = quote_top + i * line_h
        if y + line_h > card.bottom - stats_h - 12:
            break
        _blit_label(
            surface, quote_font, line, (210, 214, 230),
            card.x + inset, y, text_w, line_h, vcenter=False,
        )
    stats_y = min(card.bottom - stats_h - 10, quote_top + len(lines) * line_h + 8)
    _blit_label(
        surface, stat_font, stats, (186, 196, 210),
        card.x + inset, stats_y, text_w, stats_h,
    )


def _draw_champion_boss_card(surface, game=None):
    """Small BomberMarv portrait + quote, kept off the title and stats."""
    stats = f"x{BOSS_SPEED_MULTIPLIER:g}  ·  Fire {BOSS_START_FIRE_POWER}  ·  Bombs {BOSS_START_BOMB_CAPACITY}  ·  +{BOSS_EXTRA_LIVES} life"
    _draw_boss_invite_card(
        surface, game,
        name=BOSS_NAME, color=BOSS_COLOR, quote=BOSS_QUOTE, stats=stats,
        sprite="cleaver", backdrop=(28, 28, 34), ring=(90, 90, 104),
    )


def _draw_brabi_invite_card(surface, game=None):
    """Same corner card as the champion screen, for the fight after BomberMarv."""
    lives = int(UBER_BOSS_EXTRA_LIVES)
    life_word = "life" if lives == 1 else "lives"
    stats = (
        f"x{UBER_BOSS_SPEED_MULTIPLIER:g}  ·  Fire {UBER_BOSS_START_FIRE_POWER}"
        f"  ·  Bombs {UBER_BOSS_START_BOMB_CAPACITY}  ·  +{lives} {life_word}"
    )
    _draw_boss_invite_card(
        surface, game,
        name=UBER_BOSS_NAME, color=UBER_BOSS_COLOR, quote=UBER_BOSS_QUOTE, stats=stats,
        sprite="brabi", backdrop=(16, 42, 28), ring=UBER_BOSS_COLOR,
    )


def marv_killer_banner_rect(sw, sh):
    """Gold ceremony panel in the logo band, above the result heading."""
    margin_y = max(12, int(sh * 0.03))
    gap = 12
    card_w = min(760, max(420, int(sw * 0.52)))
    max_h = max(1, result_content_top(sh) - margin_y - gap)
    card_h = min(190, max_h)
    return pygame.Rect((sw - card_w) // 2, margin_y, card_w, card_h)


def _draw_marv_killer_banner(surface, name):
    """Title grant for beating BomberMarv and BomberTom."""
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    card = marv_killer_banner_rect(sw, sh)
    # Clear the logo band so the ceremony panel is the only thing above the heading.
    wipe_bottom = result_content_top(sh) - 6
    pygame.draw.rect(surface, COLOR_BG, pygame.Rect(0, 0, sw, max(0, wipe_bottom)))
    pygame.draw.rect(surface, (28, 20, 8), card, border_radius=18)
    pygame.draw.rect(surface, (232, 196, 74), card, 3, border_radius=18)
    trophy = max(26, min(44, card.height // 6))
    draw_trophy_icon(surface, (card.centerx - trophy // 2, card.y + 14), trophy)
    title_font = _ui_font(min(64, max(36, card.height // 4)), bold=True)
    name_font = _ui_font(min(34, max(22, card.height // 8)), bold=True)
    line_font = _ui_font(min(26, max(18, card.height // 10)))
    inset = 16
    title_y = card.y + 18 + trophy
    _blit_label(
        surface, title_font, MARV_KILLER_TITLE, (255, 214, 90),
        card.x + inset, title_y, card.width - inset * 2, title_font.get_height() + 4,
    )
    name_y = title_y + title_font.get_height() + 6
    _blit_label(
        surface, name_font, str(name or "Champion"), (248, 244, 230),
        card.x + inset, name_y, card.width - inset * 2, name_font.get_height() + 2,
    )
    _blit_label(
        surface, line_font, f"defeated {BOSS_NAME} and {UBER_BOSS_NAME}.", (232, 214, 170),
        card.x + inset, card.bottom - line_font.get_height() - 16, card.width - inset * 2, line_font.get_height() + 2,
    )


def draw_boss_result_screen(surface, winner, players=None, game=None):
    """Win or loss after a boss, with the Enter prompt for the next fight or the lobby."""
    killer = game is not None and hasattr(game, "marv_killer_result") and game.marv_killer_result()
    if game is not None and hasattr(game, "boss_result_copy"):
        heading, detail, color, prompt = game.boss_result_copy()
        caption = f"{detail}   ·   {prompt}"
    elif winner is not None and getattr(winner, "is_ai", False):
        heading, detail, color = "You lose", f"{getattr(winner, 'name', None) or BOSS_NAME} wins the fight.", (255, 96, 88)
        caption = f"{detail}   ·   Enter: back to the lobby"
    elif winner is not None:
        heading, color = "You win", (88, 220, 120)
        caption = "Enter: back to the lobby"
    else:
        heading, color = "Draw", (220, 224, 232)
        caption = "Enter: back to the lobby"
    roster = players if players is not None else ([winner] if winner else [])
    draw_stat_screen(surface, winner, roster, game, heading=heading, heading_color=color, caption=caption)
    if killer:
        shown = winner.name if winner is not None else ""
        if game is not None and getattr(game, "boss_fight_winner", None) is not None:
            shown = game.boss_fight_winner.name
        _draw_marv_killer_banner(surface, shown)
    elif game is not None and getattr(game, "boss_advance", "") == "brabi":
        _draw_brabi_invite_card(surface, game)

def draw_game_screen(surface, theGame):
    surface.fill(COLOR_BG)
    draw_board(surface, theGame)
    draw_powerups(surface, theGame)
    draw_bombs(surface, theGame.current_time, theGame.bombs)
    draw_explosions(surface, theGame.current_time, theGame.explosions)
    if SHOW_EXPLOSION_COLLISION_DEBUG:
        draw_explosion_collision_debug(surface, theGame.current_time, theGame.explosions, theGame.players)
    draw_players(
        surface,
        theGame.players,
        theGame.explosions,
        theGame.current_time,
        theGame.bombs,
        theGame.board,
        theGame.grid_width,
        theGame.grid_height,
    )
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
    from frontend import present_rect
    surf_w, surf_h = screen.surface.get_size()
    win_w, win_h = screen.window_size
    new_width, new_height, x_offset, y_offset = present_rect(
        surf_w, surf_h, win_w, win_h, cover=False,
    )
    scaled_surface = pygame.transform.smoothscale(screen.surface, (new_width, new_height))
    screen.window.fill((0, 0, 0))
    screen.window.blit(scaled_surface, (x_offset, y_offset))
    pygame.display.flip()
    
def get_ready_banner_rect(sw, sh):
    """Centered banner that stays off corner spawns and fits the key lines."""
    banner_h = max(108, min(240, int(sh * 0.20)))
    return pygame.Rect(0, (sh - banner_h) // 2, sw, banner_h)


def draw_get_ready(surface):
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    banner = get_ready_banner_rect(sw, sh)
    overlay = pygame.Surface((banner.width, banner.height), pygame.SRCALPHA)
    overlay.fill((12, 10, 18, 210))
    surface.blit(overlay, banner.topleft)
    pygame.draw.line(surface, (212, 175, 55), (0, banner.top), (sw, banner.top), 2)
    pygame.draw.line(surface, (212, 175, 55), (0, banner.bottom - 1), (sw, banner.bottom - 1), 2)
    title_size = max(26, min(52, int(banner.height * 0.28)))
    line_size = max(16, min(28, int(banner.height * 0.16)))
    title_font = pygame.font.SysFont("Comic Sans MS", title_size, bold=True)
    line_font = pygame.font.SysFont("arial", line_size, bold=True)
    title = title_font.render("Get Ready!", True, (236, 120, 168))
    title_rect = title.get_rect(midtop=(banner.centerx, banner.y + max(8, banner.height // 10)))
    surface.blit(title, title_rect)
    y = title_rect.bottom + max(6, banner.height // 18)
    for line in READY_KEY_LINES:
        text = line_font.render(line, True, (232, 238, 248))
        rect = text.get_rect(midtop=(banner.centerx, y))
        surface.blit(text, rect)
        y = rect.bottom + 4


def _get_lobby_backdrop(sw, sh):
    key = (int(sw), int(sh))
    if _LOBBY_BG_CACHE["key"] == key and _LOBBY_BG_CACHE["surf"] is not None:
        return _LOBBY_BG_CACHE["surf"]
    surf = pygame.Surface((sw, sh))
    surf.fill((16, 20, 28))
    cell = 56
    dark = (20, 25, 34)
    for y in range(0, sh, cell):
        for x in range(0, sw, cell):
            if ((x // cell) + (y // cell)) % 2 == 0:
                pygame.draw.rect(surf, dark, (x, y, cell, cell))
    pygame.draw.rect(surf, (212, 175, 55), pygame.Rect(0, 0, sw, 7))
    pygame.draw.rect(surf, (42, 32, 12), pygame.Rect(0, 7, sw, 3))
    _LOBBY_BG_CACHE["key"] = key
    _LOBBY_BG_CACHE["surf"] = surf
    return surf


def _draw_panel(surface, rect, fill, border, radius=16):
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    pygame.draw.rect(surface, border, rect, 2, border_radius=radius)


def _draw_pill(surface, font, text, fill, text_color, x, y, width, height, border=None):
    rect = pygame.Rect(int(x), int(y), int(width), int(height))
    pygame.draw.rect(surface, fill, rect, border_radius=8)
    if border is not None:
        pygame.draw.rect(surface, border, rect, 1, border_radius=8)
    _blit_label(surface, font, text, text_color, rect.x + 4, rect.y, rect.width - 8, rect.height)


def _draw_option_pills(surface, font, values, x, y, button_w, button_h, gap, selected_idx, current_idx, pulse):
    """Draw a row of numeric lobby option buttons. Returns the used height."""
    for idx, label in enumerate(values):
        rect = pygame.Rect(int(x + idx * (button_w + gap)), int(y), int(button_w), int(button_h))
        selected = idx == selected_idx
        current = idx == current_idx
        if selected:
            glow = int(180 + 60 * pulse)
            fill = (glow, 180, 62)
            text_col = (20, 24, 28)
        elif current:
            fill = (86, 122, 196)
            text_col = (236, 241, 248)
        else:
            fill = (62, 76, 96)
            text_col = (220, 228, 240)
        pygame.draw.rect(surface, fill, rect, border_radius=10)
        pygame.draw.rect(surface, (196, 209, 228) if selected or current else (90, 108, 132), rect, 1, border_radius=10)
        _blit_label(surface, font, str(label), text_col, rect.x, rect.y, rect.width, rect.height)
    return button_h


def draw_settings_screen(surface, game):
    """Full-page match rules. Values are saved as they change."""
    import bm_settings
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    surface.blit(_get_lobby_backdrop(sw, sh), (0, 0))
    margin = max(28, int(sw * 0.04))
    title_font = _ui_font(min(52, max(32, sh // 28)), bold=True)
    hint_font = _ui_font(min(22, max(16, sh // 52)))
    row_font = _ui_font(min(28, max(18, sh // 36)), bold=True)
    _blit_label(surface, title_font, "Match settings", (238, 244, 255), margin, 28, sw - margin * 2, title_font.get_height() + 4, vcenter=False)
    _blit_label(
        surface, hint_font,
        "Left / Right change  ·  Enter toggles  ·  changed values are marked  ·  R or Reset defaults  ·  Esc lobby",
        (176, 190, 210), margin, 36 + title_font.get_height(), sw - margin * 2, hint_font.get_height() + 4, vcenter=False,
    )
    top = 36 + title_font.get_height() + hint_font.get_height() + 28
    rows = list(bm_settings.RULES) + [("reset", "Reset defaults", None)]
    cursor = int(getattr(game, "settings_cursor", 0) or 0) % max(1, len(rows))
    row_h = min(48, max(30, (sh - top - 36) // max(1, len(rows))))
    visible = max(1, (sh - top - 36) // row_h)
    start = 0
    if len(rows) > visible:
        start = min(max(0, cursor - visible // 2), len(rows) - visible)
    for index, (key, label, *_rest) in enumerate(rows[start:start + visible], start=start):
        rect = pygame.Rect(margin, top + (index - start) * row_h, sw - margin * 2, row_h - 6)
        selected = index == cursor
        changed = key != "reset" and not bm_settings.is_default(key)
        fill = (58, 74, 102) if selected else (48, 42, 28) if changed else (36, 44, 58)
        border = (212, 196, 120) if selected else (214, 164, 72) if changed else (90, 108, 132)
        pygame.draw.rect(surface, fill, rect, border_radius=10)
        pygame.draw.rect(surface, border, rect, 2 if selected or changed else 1, border_radius=10)
        if key == "reset":
            _blit_label(surface, row_font, label, (236, 242, 252), rect.x + 18, rect.y, rect.width - 36, rect.height)
            continue
        value = bm_settings.format_value(key)
        mark = "●  " if changed else ""
        _blit_label(surface, row_font, mark + label, (255, 214, 120) if changed else (236, 242, 252), rect.x + 18, rect.y, rect.width * 0.68, rect.height)
        value_color = (255, 196, 90) if changed else (142, 230, 160) if value == "On" else (232, 214, 150) if value != "Off" else (210, 160, 150)
        _blit_label(surface, row_font, value, value_color, rect.x + int(rect.width * 0.68), rect.y, rect.width * 0.32 - 18, rect.height)


def draw_controls_screen(surface, game):
    """Full-page key assignments for local seats and browser players."""
    del game
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    surface.blit(_get_lobby_backdrop(sw, sh), (0, 0))
    margin = max(28, int(sw * 0.04))
    title_font = _ui_font(min(52, max(32, sh // 28)), bold=True)
    hint_font = _ui_font(min(22, max(16, sh // 52)))
    row_font = _ui_font(min(28, max(18, sh // 40)), bold=True)
    sub_font = _ui_font(min(22, max(15, sh // 52)))
    _blit_label(surface, title_font, "Keys", (238, 244, 255), margin, 28, sw - margin * 2, title_font.get_height() + 4, vcenter=False)
    _blit_label(
        surface, hint_font,
        "Hold bomb to plant as you walk.  ·  Esc returns to the lobby",
        (176, 190, 210), margin, 36 + title_font.get_height(), sw - margin * 2, hint_font.get_height() + 4, vcenter=False,
    )
    top = 36 + title_font.get_height() + hint_font.get_height() + 28
    rows = control_guide_rows()
    row_h = min(52, max(34, (sh - top - 28) // max(1, len(rows))))
    for index, (who, move, bomb) in enumerate(rows):
        rect = pygame.Rect(margin, top + index * row_h, sw - margin * 2, row_h - 6)
        pygame.draw.rect(surface, (36, 44, 58), rect, border_radius=10)
        pygame.draw.rect(surface, (90, 108, 132), rect, 1, border_radius=10)
        _blit_label(surface, row_font, who, (255, 214, 120), rect.x + 18, rect.y, rect.width * 0.24, rect.height)
        action = move if not bomb else "%s    ·    bomb %s" % (move, bomb)
        _blit_label(surface, sub_font, action, (232, 238, 248), rect.x + int(rect.width * 0.26), rect.y, rect.width * 0.72 - 18, rect.height)


def draw_quit_prompt(surface, game):
    """Ask before closing the app from the lobby."""
    if not getattr(game, "quit_prompt_open", False):
        return
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 180))
    surface.blit(dim, (0, 0))
    panel_w = min(720, max(420, int(sw * 0.52)))
    panel_h = min(280, max(200, int(sh * 0.28)))
    panel = pygame.Rect((sw - panel_w) // 2, (sh - panel_h) // 2, panel_w, panel_h)
    pygame.draw.rect(surface, (28, 34, 46), panel, border_radius=16)
    pygame.draw.rect(surface, (196, 209, 228), panel, 2, border_radius=16)
    title_font = _ui_font(min(36, max(24, panel_h // 7)), bold=True)
    hint_font = _ui_font(min(20, max(14, panel_h // 12)))
    btn_font = _ui_font(min(28, max(18, panel_h // 8)), bold=True)
    _blit_label(surface, title_font, "Exit BomberMarv?", (238, 244, 255), panel.x + 24, panel.y + 22, panel.width - 48, title_font.get_height() + 8)
    _blit_label(
        surface, hint_font, "Arrows select   ·   Enter confirm   ·   Esc stay",
        (164, 178, 198), panel.x + 24, panel.y + 28 + title_font.get_height(), panel.width - 48, hint_font.get_height() + 6,
    )
    choice = getattr(game, "quit_prompt_choice", "no")
    btn_w = min(160, max(110, int(panel_w * 0.28)))
    btn_h = min(56, max(40, int(panel_h * 0.22)))
    gap = 24
    pair_w = btn_w * 2 + gap
    btn_y = panel.bottom - btn_h - 28
    no_rect = pygame.Rect(panel.centerx - pair_w // 2, btn_y, btn_w, btn_h)
    yes_rect = pygame.Rect(no_rect.right + gap, btn_y, btn_w, btn_h)
    for label, rect, selected in (("NO", no_rect, choice != "yes"), ("YES", yes_rect, choice == "yes")):
        if selected:
            fill = (86, 168, 118) if label == "NO" else (176, 72, 78)
            text = (22, 32, 28) if label == "NO" else (255, 236, 236)
            border = (230, 240, 232)
        else:
            fill = (46, 56, 70)
            text = (210, 220, 232)
            border = (90, 108, 132)
        pygame.draw.rect(surface, fill, rect, border_radius=12)
        pygame.draw.rect(surface, border, rect, 2 if selected else 1, border_radius=12)
        _blit_label(surface, btn_font, label, text, rect.x, rect.y, rect.width, rect.height)


def draw_game_prep(surface, Game):
    """Draw the host lobby screen with a clean split layout."""
    if getattr(Game, "prep_section", "") == "settings":
        draw_settings_screen(surface, Game)
        return
    if getattr(Game, "prep_section", "") == "controls":
        draw_controls_screen(surface, Game)
        return
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    surface.blit(_get_lobby_backdrop(sw, sh), (0, 0))
    pulse = 0.5 + 0.5 * math.sin(time.time() * 8.0)

    # Game._cached_status is refreshed by the main loop; do not block drawing here.
    if not hasattr(Game, '_cached_status'):
        Game._cached_status = None

    cached_clients = {}
    cached_players = {}
    if Game._cached_status:
        cached_clients = Game._cached_status.get('clients', {})
        cached_players = Game._cached_status.get('players', {})

    all_players = Game.get_all_players_info()
    for p in all_players:
        if p.get('type') == 'local':
            controls = p.get('controls') or Game.prep_controls[p.get('source', 0) % len(Game.prep_controls)]
            p['status'] = _format_controls(controls)
        elif p.get('type') == 'ai':
            p['status'] = 'CPU'
        else:
            source = p.get('source') or (None, None)
            client_id, player_id = source if isinstance(source, tuple) else (source, None)
            client_info = cached_clients.get(client_id, {}) or cached_clients.get(str(client_id), {})
            pinfo = cached_players.get(str(player_id), {})
            keys = pinfo.get('keys', {})
            pressed = []
            if keys.get('up'): pressed.append('UP')
            if keys.get('down'): pressed.append('DOWN')
            if keys.get('left'): pressed.append('LEFT')
            if keys.get('right'): pressed.append('RIGHT')
            if keys.get('bomb'): pressed.append('BOMB')
            p['status'] = ' + '.join(pressed) if pressed else 'IDLE'
            p['latency_5s'] = float(client_info.get('avg_latency_5s', client_info.get('avg_latency', 0)) or 0)

    margin = max(28, int(sw * 0.02))
    title_font = _ui_font(min(58, max(36, sh // 32)), bold=True)
    subtitle_font = _ui_font(min(24, max(16, sh // 56)))
    badge_font = _ui_font(min(22, max(16, sh // 58)), bold=True)
    header_top = 22
    trophy_goal = int(Game.trophy_threshold()) if hasattr(Game, "trophy_threshold") else TROPHY_WIN_THRESHOLD
    badge_text = f"First to {trophy_goal} trophies"
    badge_w = badge_font.size(badge_text)[0] + 64
    badge_h = 40
    badge_rect = pygame.Rect(sw - margin - badge_w, header_top + 10, badge_w, badge_h)
    pygame.draw.rect(surface, (46, 38, 18), badge_rect, border_radius=12)
    pygame.draw.rect(surface, (212, 175, 55), badge_rect, 1, border_radius=12)
    trophy_size = 22
    draw_trophy_icon(surface, (badge_rect.x + 12, badge_rect.y + (badge_h - trophy_size) // 2), trophy_size)
    _blit_label(
        surface, badge_font, badge_text, (240, 214, 130),
        badge_rect.x + 40, badge_rect.y, badge_rect.width - 50, badge_h,
    )

    title_w = max(120, badge_rect.x - margin - 24)
    _blit_label(surface, title_font, "BomberMarv Lobby", (238, 244, 255), margin, header_top, title_w, title_font.get_height() + 4, vcenter=False)
    _blit_label(
        surface, subtitle_font, "Host setup  ·  local players, AI opponents, names, colors, teams",
        (186, 198, 214), margin, header_top + title_font.get_height() + 6, title_w, subtitle_font.get_height() + 4, vcenter=False,
    )

    footer_h = max(116, int(sh * 0.12))
    header_bottom = header_top + title_font.get_height() + subtitle_font.get_height() + 28
    gap = 20
    panel_h = max(240, sh - footer_h - header_bottom - 18)
    left_w = int((sw - margin * 2 - gap) * 0.64)
    left_panel = pygame.Rect(margin, header_bottom, left_w, panel_h)
    right_panel = pygame.Rect(left_panel.right + gap, header_bottom, sw - margin - left_panel.right - gap, panel_h)
    footer = pygame.Rect(margin, sh - footer_h - 10, sw - margin * 2, footer_h)

    _draw_panel(surface, left_panel, (32, 39, 51), (86, 104, 132))
    _draw_panel(surface, right_panel, (28, 35, 46), (74, 92, 118))
    _draw_panel(surface, footer, (26, 34, 44), (80, 97, 121), radius=14)

    inset = 20
    section_font = _ui_font(min(32, max(22, sh // 48)), bold=True)
    label_font = _ui_font(min(20, max(16, sh // 60)), bold=True)
    join_label = lan_join_label()
    _blit_label(surface, section_font, "Players", (235, 242, 255), left_panel.x + inset, left_panel.y + 14, left_panel.width - 40, section_font.get_height() + 2, vcenter=False)
    _blit_label(surface, section_font, "Remote players", (235, 242, 255), right_panel.x + inset, right_panel.y + 14, right_panel.width - 40, section_font.get_height() + 2, vcenter=False)
    join_font = _ui_font(min(20, max(14, sh // 62)), bold=True)
    _blit_label(
        surface, join_font, join_label, (240, 214, 130),
        right_panel.x + inset, right_panel.y + 16 + section_font.get_height(),
        right_panel.width - 40, join_font.get_height() + 2, vcenter=False,
    )

    count_label_y = left_panel.y + 14 + section_font.get_height() + 8
    _blit_label(surface, label_font, "Local player count", (185, 214, 180), left_panel.x + inset, count_label_y, 420, label_font.get_height() + 2, vcenter=False)

    button_y = count_label_y + label_font.get_height() + 8
    button_h = min(44, max(32, sh // 44))
    button_gap = 8
    button_w = min(52, max(32, (left_panel.width - inset * 2 - button_gap * (MAX_PLAYERS - 1)) // MAX_PLAYERS))
    button_font = _ui_font(min(26, button_h - 8), bold=True)
    local_selected = Game.prep_section == 'local_players' and Game.prep_cursor_row == PREP_ROW_LOCAL
    _draw_option_pills(
        surface, button_font, list(range(1, MAX_PLAYERS + 1)),
        left_panel.x + inset, button_y, button_w, button_h, button_gap,
        Game.prep_cursor_col if local_selected else -1,
        Game.prep_num_players - 1,
        pulse,
    )

    ai_label_y = button_y + button_h + 10
    _blit_label(surface, label_font, "AI opponents", (180, 200, 220), left_panel.x + inset, ai_label_y, 420, label_font.get_height() + 2, vcenter=False)
    ai_button_y = ai_label_y + label_font.get_height() + 6
    ai_selected = Game.prep_section == 'local_players' and Game.prep_cursor_row == PREP_ROW_AI
    _draw_option_pills(
        surface, button_font, list(range(MAX_PLAYERS)),
        left_panel.x + inset, ai_button_y, button_w, button_h, button_gap,
        Game.prep_cursor_col if ai_selected else -1,
        int(getattr(Game, "prep_ai_count", 0) or 0),
        pulse,
    )

    trophy_label_y = ai_button_y + button_h + 10
    _blit_label(surface, label_font, "Trophies to win (boss fight)", (212, 190, 140), left_panel.x + inset, trophy_label_y, 520, label_font.get_height() + 2, vcenter=False)
    trophy_button_y = trophy_label_y + label_font.get_height() + 6
    trophy_selected = Game.prep_section == 'local_players' and Game.prep_cursor_row == PREP_ROW_TROPHY
    _draw_option_pills(
        surface, button_font, list(range(MIN_TROPHY_WIN, MAX_TROPHY_WIN + 1)),
        left_panel.x + inset, trophy_button_y, button_w, button_h, button_gap,
        Game.prep_cursor_col if trophy_selected else -1,
        trophy_goal - 1,
        pulse,
    )

    roster_count = max(1, len(all_players))
    arena_choices = grid_size_choices(roster_count)
    arena_default = default_grid_size(roster_count)
    arena_offset = clamp_grid_offset(getattr(Game, "prep_grid_offset", 0))
    arena_current = clamp_odd_grid(arena_default + arena_offset)
    arena_label_y = trophy_button_y + button_h + 10
    _blit_label(
        surface, label_font,
        f"Arena size  ·  default {arena_default}  ·  ±2/4/6",
        (180, 210, 230), left_panel.x + inset, arena_label_y, 620, label_font.get_height() + 2, vcenter=False,
    )
    arena_button_y = arena_label_y + label_font.get_height() + 6
    arena_n = max(1, len(arena_choices))
    arena_w = min(56, max(32, (left_panel.width - inset * 2 - button_gap * (arena_n - 1)) // arena_n))
    arena_selected = Game.prep_section == 'local_players' and Game.prep_cursor_row == PREP_ROW_ARENA
    _draw_option_pills(
        surface, button_font, arena_choices,
        left_panel.x + inset, arena_button_y, arena_w, button_h, button_gap,
        Game.prep_cursor_col if arena_selected else -1,
        grid_offset_index(arena_offset),
        pulse,
    )

    row_y = arena_button_y + button_h + 14
    available_rows = max(1, left_panel.bottom - row_y - 16)
    n_show = max(1, len(all_players))
    row_h = min(88, max(64, available_rows // min(n_show, 8)))
    max_rows = max(1, available_rows // row_h)
    if len(all_players) > max_rows:
        max_rows = max(1, (available_rows - 26) // row_h)
    shown_players = all_players[:max_rows]
    name_font = _ui_font(min(30, max(18, row_h - 40)), bold=True)
    meta_font = _ui_font(min(18, max(14, row_h - 52)))
    chip = min(36, row_h - 22)
    team_w = 52
    role_w = 78

    for i, p in enumerate(shown_players):
        rect = pygame.Rect(left_panel.x + 14, row_y + i * row_h, left_panel.width - 28, row_h - 8)
        selected = (Game.prep_section == 'local_players' and Game.prep_cursor_row == i + PREP_ROW_PLAYERS)
        editing = (Game.prep_editing_name and Game.prep_name_edit_index == i)
        if selected:
            glow = int(70 + 36 * pulse)
            row_bg = (glow, glow + 12, 112)
        else:
            row_bg = (41, 50, 64)
        pygame.draw.rect(surface, row_bg, rect, border_radius=10)
        pygame.draw.rect(surface, (212, 175, 55) if selected else (102, 122, 148), rect, 2 if selected else 1, border_radius=10)
        player_color = colors[p['color'] % len(colors)]
        pygame.draw.rect(surface, player_color, pygame.Rect(rect.x, rect.y, 8, rect.height), border_top_left_radius=10, border_bottom_left_radius=10)

        chip_rect = pygame.Rect(rect.x + 18, rect.y + (rect.height - chip) // 2, chip, chip)
        pygame.draw.rect(surface, player_color, chip_rect, border_radius=8)
        pygame.draw.rect(surface, (220, 232, 248), chip_rect, 1, border_radius=8)

        name_h = name_font.get_height()
        meta_h = meta_font.get_height()
        block_h = name_h + 4 + meta_h
        block_y = rect.y + max(4, (rect.height - block_h) // 2)
        team_rect = pygame.Rect(chip_rect.right + 10, block_y + max(0, (name_h - 24) // 2), team_w, 24)
        _draw_pill(surface, meta_font, f"T{int(p.get('team', 0)) + 1}", (58, 72, 96), (210, 220, 235), team_rect.x, team_rect.y, team_rect.width, team_rect.height)

        if p['type'] == 'local':
            role = "LOCAL"
            role_fill = (52, 92, 74)
        elif p['type'] == 'ai':
            role = "AI"
            role_fill = (108, 72, 52)
        else:
            role = "REMOTE"
            role_fill = (52, 78, 108)
        role_rect = pygame.Rect(rect.right - 12 - role_w, block_y + max(0, (name_h - 24) // 2), role_w, 24)
        _draw_pill(surface, meta_font, role, role_fill, (220, 236, 230), role_rect.x, role_rect.y, role_rect.width, role_rect.height)

        style_fill = {
            "cautious": ((64, 104, 148), "Cautious"),
            "normal": ((58, 112, 82), "Normal"),
            "crazy": ((148, 74, 56), "Crazy"),
        }.get(p.get("personality") if p.get("type") == "ai" else None)
        name_limit = role_rect.x
        if style_fill:
            style_w = 96
            style_rect = pygame.Rect(role_rect.x - 8 - style_w, role_rect.y, style_w, role_rect.height)
            _draw_pill(
                surface, meta_font, style_fill[1], style_fill[0], (236, 242, 248),
                style_rect.x, style_rect.y, style_rect.width, style_rect.height,
            )
            name_limit = style_rect.x

        name = p['name'] + "_" if editing else p['name']
        prefix = f"L{p['id']}" if p['type'] == 'local' else (f"AI{p['id']}" if p['type'] == 'ai' else f"R{p['id']}")
        name = f"{prefix}  {name}"
        name_color = (250, 234, 130) if (selected or editing) else (234, 242, 255)
        name_x = team_rect.right + 10
        name_w = max(40, name_limit - 10 - name_x)
        _blit_label(surface, name_font, name, name_color, name_x, block_y, name_w, name_h, vcenter=False)

        status_text = p['status']
        if p['type'] == 'client':
            status_text = f"{p['status']}  ·  {int(round(float(p.get('latency_5s', 0))))} ms"
        status_color = (142, 246, 160) if p['type'] == 'client' and p['status'] != 'IDLE' else (164, 181, 203)
        if p.get('title'):
            status_text = f"{p['title']}  ·  {status_text}"
            status_color = (255, 214, 90)
        _blit_label(surface, meta_font, status_text, status_color, name_x, block_y + name_h + 4, name_w, meta_h, vcenter=False)

    if len(all_players) > max_rows:
        more = len(all_players) - max_rows
        _blit_label(surface, meta_font, f"... and {more} more", (180, 188, 200), left_panel.x + inset, left_panel.bottom - 26, 280, 22)

    card_font = _ui_font(min(24, max(16, sh // 58)), bold=True)
    card_sub = _ui_font(min(18, max(14, sh // 64)))
    client_card_y = right_panel.y + 18 + section_font.get_height() + join_font.get_height() + 12
    card_h = min(92, max(70, (right_panel.bottom - client_card_y - 20) // 4))
    if cached_clients:
        for client_id, info in cached_clients.items():
            if client_card_y + card_h > right_panel.bottom - 12:
                break
            last_seen = info.get('last_seen', 0)
            age = time.time() - last_seen
            online_col = (132, 233, 146) if age < 5 else (236, 200, 117) if age < 30 else (227, 123, 123)
            reg = "READY" if info.get('registered', False) else "WAITING"
            display_name = str(info.get('display_name', '') or '').strip()
            latency = info.get('avg_latency_5s', info.get('avg_latency', 0))
            samples = info.get('latency_samples_5s', info.get('latency_samples', 0))
            card = pygame.Rect(right_panel.x + 16, client_card_y, right_panel.width - 32, card_h - 10)
            pygame.draw.rect(surface, (40, 50, 64), card, border_radius=12)
            pygame.draw.rect(surface, (95, 116, 140), card, 1, border_radius=12)
            pygame.draw.circle(surface, online_col, (card.x + 22, card.y + card.height // 2), 7)
            line1 = f"Client {client_id}  ·  {reg}"
            if display_name:
                line1 += f"  ·  {display_name}"
            line2 = f"{len(info.get('players', []))} player(s)  ·  {latency} ms ({samples})"
            text_x = card.x + 40
            text_w = card.width - 52
            _blit_label(surface, card_font, line1, online_col, text_x, card.y + 8, text_w, card_font.get_height() + 2, vcenter=False)
            _blit_label(surface, card_sub, line2, (188, 204, 224), text_x, card.y + 10 + card_font.get_height(), text_w, card_sub.get_height() + 2, vcenter=False)
            client_card_y += card_h
    else:
        empty = pygame.Rect(right_panel.x + 16, client_card_y, right_panel.width - 32, min(168, max(110, right_panel.bottom - client_card_y - 16)))
        pygame.draw.rect(surface, (36, 44, 56), empty, border_radius=12)
        pygame.draw.rect(surface, (70, 88, 112), empty, 1, border_radius=12)
        _blit_label(
            surface, card_font, "Waiting for browsers", (210, 220, 236),
            empty.x + 16, empty.y + 16, empty.width - 32, card_font.get_height() + 4, vcenter=False,
        )
        _blit_label(
            surface, card_sub, f"Share {join_label} with guests on the same Wi-Fi.",
            (172, 184, 204), empty.x + 16, empty.y + 20 + card_font.get_height(), empty.width - 32, empty.height - card_font.get_height() - 28, vcenter=False,
        )

    footer_font = _ui_font(min(26, max(18, footer_h // 5)), bold=True)
    help_font = _ui_font(min(20, max(15, footer_h // 6)))
    total_players = len(all_players)
    totals_text = (
        f"{total_players} players   ·   {Game.prep_num_players} local   ·   "
        f"{int(getattr(Game, 'prep_ai_count', 0) or 0)} AI   ·   "
        f"{arena_current}×{arena_current}   ·   first to {trophy_goal}"
    )
    start_w = min(280, max(188, int(footer.width * 0.16)))
    start_h = min(58, footer.height - 24)
    settings_w = min(200, max(140, int(footer.width * 0.12)))
    keys_w = min(160, max(110, int(footer.width * 0.10)))
    start_rect = pygame.Rect(footer.right - 16 - start_w, footer.y + (footer.height - start_h) // 2, start_w, start_h)
    settings_rect = pygame.Rect(start_rect.x - 12 - settings_w, start_rect.y, settings_w, start_h)
    keys_rect = pygame.Rect(settings_rect.x - 12 - keys_w, start_rect.y, keys_w, start_h)
    text_w = max(80, keys_rect.x - footer.x - 36)
    _blit_label(surface, footer_font, totals_text, (232, 239, 250), footer.x + 22, footer.y + 16, text_w, footer_font.get_height() + 4, vcenter=False)

    settings_selected = (Game.prep_section == "settings_button")
    settings_fill = (86, 96, 132) if settings_selected else (48, 58, 76)
    pygame.draw.rect(surface, settings_fill, settings_rect, border_radius=12)
    pygame.draw.rect(surface, (210, 220, 240), settings_rect, 2 if settings_selected else 1, border_radius=12)
    _blit_label(surface, footer_font, "SETTINGS", (236, 242, 255), settings_rect.x + 8, settings_rect.y, settings_rect.width - 16, settings_rect.height)

    keys_selected = (Game.prep_section == "keys_button")
    keys_fill = (86, 96, 132) if keys_selected else (48, 58, 76)
    pygame.draw.rect(surface, keys_fill, keys_rect, border_radius=12)
    pygame.draw.rect(surface, (210, 220, 240), keys_rect, 2 if keys_selected else 1, border_radius=12)
    _blit_label(surface, footer_font, "KEYS", (236, 242, 255), keys_rect.x + 8, keys_rect.y, keys_rect.width - 16, keys_rect.height)

    start_selected = (Game.prep_section == 'start_game')
    if start_selected:
        glow = int(132 + 50 * pulse)
        start_fill = (86, glow, 128)
        start_text_col = (22, 36, 24)
    else:
        start_fill = (62, 108, 78)
        start_text_col = (233, 246, 236)
    pygame.draw.rect(surface, start_fill, start_rect, border_radius=12)
    pygame.draw.rect(surface, (210, 235, 214), start_rect, 1, border_radius=12)
    _blit_label(surface, footer_font, "START GAME", start_text_col, start_rect.x + 8, start_rect.y, start_rect.width - 16, start_rect.height)

    help_text = "Arrows navigate  ·  Enter select  ·  K keys  ·  S settings  ·  Esc quit"
    _blit_label(surface, help_font, help_text, (160, 176, 198), footer.x + 22, footer.y + 20 + footer_font.get_height(), text_w, help_font.get_height() + 6, vcenter=False)


def draw_leave_prompt(surface, game):
    """Dim the playfield and ask whether to cancel the session."""
    if not getattr(game, "leave_prompt_open", False):
        return
    _ensure_fonts_initialized()
    sw, sh = surface.get_size()
    dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 180))
    surface.blit(dim, (0, 0))

    panel_w = min(720, max(420, int(sw * 0.52)))
    panel_h = min(280, max(200, int(sh * 0.28)))
    panel = pygame.Rect((sw - panel_w) // 2, (sh - panel_h) // 2, panel_w, panel_h)
    pygame.draw.rect(surface, (28, 34, 46), panel, border_radius=16)
    pygame.draw.rect(surface, (196, 209, 228), panel, 2, border_radius=16)

    title = game.leave_prompt_title() if hasattr(game, "leave_prompt_title") else "Leave game?"
    title_font = _ui_font(min(36, max(24, panel_h // 7)), bold=True)
    hint_font = _ui_font(min(20, max(14, panel_h // 12)))
    btn_font = _ui_font(min(28, max(18, panel_h // 8)), bold=True)
    _blit_label(surface, title_font, title, (238, 244, 255), panel.x + 24, panel.y + 22, panel.width - 48, title_font.get_height() + 8)
    _blit_label(
        surface, hint_font, "Arrows select   ·   Enter confirm   ·   Esc resume",
        (164, 178, 198), panel.x + 24, panel.y + 28 + title_font.get_height(), panel.width - 48, hint_font.get_height() + 6,
    )

    choice = getattr(game, "leave_prompt_choice", "no")
    btn_w = min(160, max(110, int(panel_w * 0.28)))
    btn_h = min(56, max(40, int(panel_h * 0.22)))
    gap = 24
    pair_w = btn_w * 2 + gap
    btn_y = panel.bottom - btn_h - 28
    no_rect = pygame.Rect(panel.centerx - pair_w // 2, btn_y, btn_w, btn_h)
    yes_rect = pygame.Rect(no_rect.right + gap, btn_y, btn_w, btn_h)
    for label, rect, selected in (("NO", no_rect, choice != "yes"), ("YES", yes_rect, choice == "yes")):
        if selected:
            fill = (86, 168, 118) if label == "NO" else (176, 72, 78)
            text = (22, 32, 28) if label == "NO" else (255, 236, 236)
            border = (230, 240, 232)
        else:
            fill = (46, 56, 70)
            text = (210, 220, 232)
            border = (90, 108, 132)
        pygame.draw.rect(surface, fill, rect, border_radius=12)
        pygame.draw.rect(surface, border, rect, 2 if selected else 1, border_radius=12)
        _blit_label(surface, btn_font, label, text, rect.x, rect.y, rect.width, rect.height)

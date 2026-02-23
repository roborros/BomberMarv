"""Pure configuration/constants for BomberMarv (no image/sound loading)."""

import pygame

VERSION = "v1.2.0"

NUM_PLAYERS = 1
CELL_SIZE = 100
PLAYER_SPEED = int(CELL_SIZE * 2.5)
PLAYER_DRAW_SCALE = 0.85
PLAYER_COLLISION_SCALE = 0.7
BOMB_DRAW_SCALE = 0.9
BOMB_PULSE_AMPLITUDE = 0.1
BOMB_PULSE_SPEED = 300.0
FLAME_ARM_THICKNESS_RATIO = 0.9
POWERUP_PROBABILITY = 0.25
TROPHY_WIN_THRESHOLD = 5
QUAD_DAMAGE_PROBABILITY = 0.0005
QUAD_DAMAGE_TIME = 20
QUAD_DAMAGE_POWER = 10
QUAD_DAMAGE_DELAY = 40
QUAD_DAMAGE_SPEEDUP = 1.5
CRUSHING_WALLS_DELAY = 3
CRUSHING_WALLS_MIN_DESTROYABLE = 500
CRUSHING_WALLS_MAX_ALIVE = 2
CRUSHING_WALLS_GROWTH_INTERVAL_MS = 400
GRID_SIZE = 21
BOMB_TIMER = 3000
EXPLOSION_DURATION = 400
EXPLOSION_COLLISION_SCALE = 0.6
ENDGAME_POST_DELAY_MS = 2500
REPLAY_LOG_INTERVAL_MS = 100
REPLAY_BUFFER_MS = 5000
REPLAY_CAMERA_RADIUS_CELLS = 5
REPLAY_PANEL_WIDTH_RATIO = 0.42
REPLAY_PANEL_PADDING = 12
DEBUG_MODE = False
DEGUG = DEBUG_MODE

if DEBUG_MODE:
    SHOW_PLAYER_DIRECTIONS = True
    SHOW_EXPLOSION_COLLISION_DEBUG = True
    EXPLOSION_DURATION = 4000
else:
    SHOW_PLAYER_DIRECTIONS = False
    SHOW_EXPLOSION_COLLISION_DEBUG = False

KEY_SEND_FREQUENCY_LIMIT = 20
player_names = ["Tom", "Sobi", "Marv", "Zelda", "Ondra", "Sasa"]
colors = [
    (100, 150, 200),
    (200, 150, 100),
    (150, 200, 100),
    (200, 100, 150),
    (100, 200, 150),
    (150, 100, 200),
]
FPS = 60

controls_list = [
    {'up': pygame.K_i, 'down': pygame.K_k, 'left': pygame.K_j, 'right': pygame.K_l, 'bomb': pygame.K_h},
    {'up': pygame.K_w, 'down': pygame.K_s, 'left': pygame.K_a, 'right': pygame.K_d, 'bomb': pygame.K_LCTRL},
    {'up': pygame.K_f, 'down': pygame.K_v, 'left': pygame.K_c, 'right': pygame.K_b, 'bomb': pygame.K_SPACE},
    {'up': pygame.K_KP5, 'down': pygame.K_KP2, 'left': pygame.K_KP1, 'right': pygame.K_KP3, 'bomb': pygame.K_RCTRL},
    {'up': pygame.K_HOME, 'down': pygame.K_END, 'left': pygame.K_DELETE, 'right': pygame.K_PAGEDOWN, 'bomb': pygame.K_BACKSPACE},
    {'up': pygame.K_KP_DIVIDE, 'down': pygame.K_KP8, 'left': pygame.K_KP7, 'right': pygame.K_KP9, 'bomb': pygame.K_KP0},
]

COLOR_BG = (60, 60, 60)
COLOR_INDESTRUCTIBLE = (120, 120, 120)
COLOR_DESTRUCTIBLE = (200, 200, 200)
COLOR_BOMB_FILL = (120, 120, 120)
COLOR_BOMB_OUTLINE = (80, 80, 80)
COLOR_FUSE = (255, 200, 150)
EMPTY = 0
INDESTRUCTIBLE = 1
DESTRUCTIBLE = 2

if NUM_PLAYERS > 4:
    GRID_WIDTH = int(GRID_SIZE * 1.3)
else:
    GRID_WIDTH = GRID_SIZE
GRID_HEIGHT = GRID_WIDTH
BASE_WIDTH = CELL_SIZE * GRID_WIDTH
BASE_HEIGHT = CELL_SIZE * GRID_HEIGHT
BOMB_BASE_RADIUS = int((CELL_SIZE * BOMB_DRAW_SCALE) / 2)

SEND_ON_CHANGE = True
PERIODIC_SENDING = True
MIN_SEND_FREQUENCY = 1
MAX_SEND_FREQUENCY = 1000

import pygame
import pygame.gfxdraw
import random
import sys
import math



VERSION = "v1.2.0"

# --- Configurable Constants ---
NUM_PLAYERS = 1  # Default players (min 1, max 6)
#NUM_PLAYERS = max(2, min(NUM_PLAYERS, 6))

CELL_SIZE = 100  # Cell size (overall resolution)

PLAYER_SPEED = int(CELL_SIZE*2.5)  # Default player speed (pixels per second)

PLAYER_DRAW_SCALE = 0.85     # Drawn sprite diameter = 85% of cell edge
PLAYER_COLLISION_SCALE = 0.7 # Collision circle = 75% of cell edge

BOMB_DRAW_SCALE = 0.9         # Bomb drawn diameter = 90% of cell edge
BOMB_PULSE_AMPLITUDE = 0.1    # 10% pulse modulation
BOMB_PULSE_SPEED = 300.0      # Bomb pulse period (ms)

FLAME_ARM_THICKNESS_RATIO = 0.9

POWERUP_PROBABILITY = 0.25  # Chance to spawn a powerup when a block is destroyed

TROPHY_WIN_THRESHOLD = 5   # Number of trophies needed to become Champion

QUAD_DAMAGE_PROBABILITY = 0.0005 # Chance to spawn a Quad Damage powerup
QUAD_DAMAGE_TIME = 20 # Duration of Quad Damage effect (s)
QUAD_DAMAGE_POWER = 10    # Powerup bonus to bomb capacity and fire power
QUAD_DAMAGE_DELAY = 40  # Delay before Quad Damage powerup spawns (s)
QUAD_DAMAGE_SPEEDUP = 1.5  # Speedup

# Crushing walls feature (endgame walls)
CRUSHING_WALLS_DELAY = 3                # Delay before crushing walls activate (seconds)
CRUSHING_WALLS_MIN_DESTROYABLE = 500      # Minimum destroyable cells before activation
CRUSHING_WALLS_MAX_ALIVE = 2              # Max alive players to allow activation (<= triggers)
CRUSHING_WALLS_GROWTH_INTERVAL_MS = 400  # Interval between new walls once active (ms)

GRID_SIZE = 21

BOMB_TIMER = 3000
EXPLOSION_DURATION = 400

# Explosion collision area scale (portion of cell covered by hitbox)
# 0.85 => 85% of cell size with equal margins on all sides
EXPLOSION_COLLISION_SCALE = 0.6

# Post-win delay (ms): keep game running briefly after a win before showing screen
ENDGAME_POST_DELAY_MS = 2500

# --- Replay settings ---
# How often to log snapshots for replay (ms)
REPLAY_LOG_INTERVAL_MS = 100
# How much history to keep/play back on win (ms)
REPLAY_BUFFER_MS = 5000
# Camera radius in cells (viewport will be (2*r+1) cells in width/height)
REPLAY_CAMERA_RADIUS_CELLS = 5
# Replay panel width as a fraction of base width on the win screen
REPLAY_PANEL_WIDTH_RATIO = 0.42
REPLAY_PANEL_PADDING = 12

DEBUG_MODE = False
# Backward-compatible alias used in existing modules.
DEGUG = DEBUG_MODE

if DEBUG_MODE:
    SHOW_PLAYER_DIRECTIONS = True  # Set to False to disable direction arrows
    SHOW_EXPLOSION_COLLISION_DEBUG = True  # Set to False to disable red collision boxes
    EXPLOSION_DURATION = 4000
else:
    SHOW_PLAYER_DIRECTIONS = False  # Set to False to disable direction arrows
    SHOW_EXPLOSION_COLLISION_DEBUG = False  # Set to False to disable red collision boxes

# Web client input throttling
KEY_SEND_FREQUENCY_LIMIT = 20  # Minimum milliseconds between key events (20ms = 50Hz max)
# Lower values = more responsive but higher server load
# Higher values = less responsive but lower server load
# Recommended range: 10-50ms (100Hz-20Hz)

player_names = ["Tom", "Sobi", "Marv", "Zelda", "Ondra", "Sasa"]
#players = []
colors = [
    (100, 150, 200),  # Light Blue
    (200, 150, 100),  # Light Brown
    (150, 200, 100),  # Light Green
    (200, 100, 150),  # Light Pink
    (100, 200, 150),  # Light Teal
    (150, 100, 200)   # Light Purple
]

FPS = 60

controls_list = [
    {'up': pygame.K_i, 'down': pygame.K_k, 'left': pygame.K_j, 'right': pygame.K_l, 'bomb': pygame.K_h},
    {'up': pygame.K_w, 'down': pygame.K_s, 'left': pygame.K_a, 'right': pygame.K_d, 'bomb': pygame.K_LCTRL},
    {'up': pygame.K_f , 'down': pygame.K_v, 'left': pygame.K_c, 'right': pygame.K_b, 'bomb': pygame.K_SPACE},
    {'up': pygame.K_KP5, 'down': pygame.K_KP2, 'left': pygame.K_KP1, 'right': pygame.K_KP3, 'bomb': pygame.K_RCTRL},
    {'up': pygame.K_HOME, 'down': pygame.K_END, 'left': pygame.K_DELETE, 'right': pygame.K_PAGEDOWN, 'bomb': pygame.K_BACKSPACE},
    {'up': pygame.K_KP_DIVIDE, 'down': pygame.K_KP8, 'left': pygame.K_KP7, 'right': pygame.K_KP9, 'bomb': pygame.K_KP0},
    
]
# https://www.pygame.org/docs/ref/key.html


# --- Colors ---
COLOR_BG = (60, 60, 60)
COLOR_INDESTRUCTIBLE = (120, 120, 120)
COLOR_DESTRUCTIBLE = (200, 200, 200)

COLOR_BOMB_FILL = (120, 120, 120)
COLOR_BOMB_OUTLINE = (80, 80, 80)
COLOR_FUSE = (255, 200, 150)

# --- Board Cell Types ---
EMPTY = 0
INDESTRUCTIBLE = 1
DESTRUCTIBLE = 2


# --- IMGS ---
quad_damage_image = pygame.image.load('img\\qd.png')
fire_powerup_image = pygame.image.load('img\\fireup.png')
blast_image = pygame.image.load('img\\blast.png')
blast_image_qd = pygame.image.load('img\\blast_qd.png')
blast_centre_image = pygame.image.load('img\\blast_centre.png')
blast_centre_image_qd = pygame.image.load('img\\blast_centre_qd.png')
logo_image = pygame.image.load('img\\logo.png')


# Internal constants and pre-calculation

if NUM_PLAYERS > 4:
    GRID_WIDTH = int(GRID_SIZE * 1.3)
else:
    GRID_WIDTH = GRID_SIZE
GRID_HEIGHT = GRID_WIDTH

BASE_WIDTH = CELL_SIZE * GRID_WIDTH
BASE_HEIGHT = CELL_SIZE * GRID_HEIGHT

BOMB_BASE_RADIUS = int((CELL_SIZE * BOMB_DRAW_SCALE) / 2)




# Font initialization moved to frontend
arcade_font = None  # Will be initialized in frontend
font_small = None   # Will be initialized in frontend

# Window initialization moved to frontend
INITIAL_WINDOW_SIZE = (1200, 800)  # Default size, will be updated by frontend
window = None  # Will be set by frontend
game_surface = None  # Will be set by frontend

# Input sending configuration
SEND_ON_CHANGE = True  # Send input immediately when it changes
PERIODIC_SENDING = True  # Send input periodically even without changes
MIN_SEND_FREQUENCY = 1  # Minimum allowed frequency (ms)
MAX_SEND_FREQUENCY = 1000  # Maximum allowed frequency (ms)


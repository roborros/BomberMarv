import pygame
import pygame.gfxdraw
import random
import sys
import math



VERSION = "v1.1.0"

# --- Configurable Constants ---
NUM_PLAYERS = 6  # Default players (min 2, max 6)
NUM_PLAYERS = max(2, min(NUM_PLAYERS, 2))

CELL_SIZE = 100  # Cell size (overall resolution)

PLAYER_SPEED = int(CELL_SIZE*2.5)  # Default player speed (pixels per second)

PLAYER_DRAW_SCALE = 0.85     # Drawn sprite diameter = 85% of cell edge
PLAYER_COLLISION_SCALE = 0.7 # Collision circle = 75% of cell edge

BOMB_DRAW_SCALE = 0.9         # Bomb drawn diameter = 90% of cell edge
BOMB_PULSE_AMPLITUDE = 0.1    # 10% pulse modulation
BOMB_PULSE_SPEED = 300.0      # Bomb pulse period (ms)

FLAME_ARM_THICKNESS_RATIO = 0.9

POWERUP_PROBABILITY = 0.25  # Chance to spawn a powerup when a block is destroyed

TROPHY_WIN_THRESHOLD = 3   # Number of trophies needed to become Champion

QUAD_DAMAGE_PROBABILITY = 0.0005 # Chance to spawn a Quad Damage powerup
QUAD_DAMAGE_TIME = 20 # Duration of Quad Damage effect (s)
QUAD_DAMAGE_POWER = 10    # Powerup bonus to bomb capacity and fire power
QUAD_DAMAGE_DELAY = 40  # Delay before Quad Damage powerup spawns (s)
QUAD_DAMAGE_SPEEDUP = 1.5  # Speedup

GRID_SIZE = 15

BOMB_TIMER = 3000
EXPLOSION_DURATION = 400

player_names = ["Tom", "Marv", "Dan", "Ondra", "Sobi", "Sasa"]
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
    {'up': pygame.K_HOME, 'down': pygame.K_END, 'left': pygame.K_DELETE, 'right': pygame.K_PAGEDOWN, 'bomb': pygame.K_BACKSPACE},
    {'up': pygame.K_w, 'down': pygame.K_s, 'left': pygame.K_a, 'right': pygame.K_d, 'bomb': pygame.K_LCTRL},
    {'up': pygame.K_f , 'down': pygame.K_v, 'left': pygame.K_c, 'right': pygame.K_b, 'bomb': pygame.K_LSHIFT},
    {'up': pygame.K_i, 'down': pygame.K_k, 'left': pygame.K_j, 'right': pygame.K_l, 'bomb': pygame.K_SPACE},
    {'up': pygame.K_KP_DIVIDE, 'down': pygame.K_KP8, 'left': pygame.K_KP7, 'right': pygame.K_KP9, 'bomb': pygame.K_RCTRL},
    {'up': pygame.K_KP5, 'down': pygame.K_KP2, 'left': pygame.K_KP1, 'right': pygame.K_KP3, 'bomb': pygame.K_KP0},
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




pygame.init()
arcade_font = pygame.font.SysFont('Comic Sans MS', 90)  # Using a common font
font_small = pygame.font.SysFont("arial", 32)

display_info = pygame.display.Info()
INITIAL_WINDOW_SIZE = (int(display_info.current_w * 0.7), int(display_info.current_h * 0.7))
pygame.display.set_icon(logo_image)

is_fullscreen = False

window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
pygame.display.set_caption("BomberMarv")
clock = pygame.time.Clock()
game_surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
window_size = INITIAL_WINDOW_SIZE


import pygame
import pygame.gfxdraw
import random
import sys
import math



VERSION = "v1.2.8"

# --- Configurable Constants ---
NUM_PLAYERS = 1  # Default players (min 1, max 8)
#NUM_PLAYERS = max(2, min(NUM_PLAYERS, 8))

CELL_SIZE = 100  # Cell size (overall resolution)

PLAYER_SPEED_MULTIPLIER = 1.15  # Configurable: 1.0 = default, 1.15 = 15% faster
PLAYER_SPEED = int(CELL_SIZE * 2.5 * PLAYER_SPEED_MULTIPLIER)  # Default player speed (pixels per second)

PLAYER_DRAW_SCALE = 0.85     # Drawn sprite diameter = 85% of cell edge
PLAYER_COLLISION_SCALE = 0.7 # Collision circle diameter = 70% of cell edge

BOMB_DRAW_SCALE = 0.9         # Bomb drawn diameter = 90% of cell edge
BOMB_PULSE_AMPLITUDE = 0.1    # 10% pulse modulation
BOMB_PULSE_SPEED = 300.0      # Bomb pulse period (ms)

FLAME_ARM_THICKNESS_RATIO = 0.9

POWERUP_PROBABILITY = 0.25  # Chance to spawn a powerup when a block is destroyed

TROPHY_WIN_THRESHOLD = 3   # Default trophies needed to become Champion
MIN_TROPHY_WIN = 1
MAX_TROPHY_WIN = 5
MAX_PLAYERS = 8
DEFAULT_AI_COUNT = 1

# Boss fight (AI) parameters
BOSS_SPEED_MULTIPLIER = 1.4
BOSS_EXTRA_LIVES = 1
BOSS_START_FIRE_POWER = 2
BOSS_START_BOMB_CAPACITY = 2
BOSS_NAME = "BomberMarv"
BOSS_COLOR = (56, 56, 62)
BOSS_QUOTE = "Finally a worthy challenger, come and fight me!"
BOSS_TAUNT = "Fresh meat!"
BOSS_TAUNT_INTERVAL_MS = 15000
# Uberboss after BomberMarv falls. Extra lives are revives, so 2 means 3 lives total.
UBER_BOSS_NAME = "BomberTom"
MARV_KILLER_TITLE = "MarvKiller"
UBER_BOSS_QUOTE = "Oh you got BomberMarv?! You thought this is the end??? You you will pay for this!"
UBER_BOSS_COLOR = (36, 200, 84)
UBER_BOSS_SPEED_MULTIPLIER = 2.0
UBER_BOSS_EXTRA_LIVES = 2
UBER_BOSS_START_FIRE_POWER = 5
UBER_BOSS_START_BOMB_CAPACITY = 5
UBER_BOSS_DRAW_SCALE = 1.5
UBER_BOSS_GLOW_PERIOD_MS = 1400
BOSS_CRUSHING_WALLS_DELAY = 120      # Same start as every other game
BOSS_CRUSHING_WALLS_GROWTH_INTERVAL_MS = 1200  # 1.5x the old squeeze, still slower than a normal round

QUAD_DAMAGE_PROBABILITY = 0.000675  # Chance per tick; 35% above the previous 0.0005 default
QUAD_DAMAGE_TIME = 20 # Duration of Quad Damage effect (s)
QUAD_DAMAGE_POWER = 10    # Powerup bonus to bomb capacity and fire power
QUAD_DAMAGE_DELAY = 60  # Earliest Quad Damage can appear (s); probability is unchanged
QUAD_DAMAGE_SPEEDUP = 1.5  # Speedup

# Crushing walls feature (endgame walls)
CRUSHING_WALLS_MIN_START_S = 120        # Never start sooner than this after game_start_time
CRUSHING_WALLS_DELAY = 120              # Shared start for every player count and the boss fight
CRUSHING_WALLS_2P_DELAY = 120           # Same start; player count does not change it
CRUSHING_WALLS_MIN_DESTROYABLE = 500      # Start once fewer than this many soft walls remain
CRUSHING_WALLS_MAX_ALIVE = 2              # Max alive players to allow activation (<= triggers)
CRUSHING_WALLS_GROWTH_INTERVAL_MS = 800  # 1.5x faster than the previous 1200ms step
# More than two players still alive, and fewer than 15% of the soft walls remain.
CRUSHING_WALLS_STALE_WALL_FRACTION = 0.15
CRUSHING_WALLS_CROWDED_TIME_MULTIPLIER = 1.5
# After twice the wait, the walls start even if the soft walls are still up.
CRUSHING_WALLS_STALE_TIME_MULTIPLIER = 2

# Lobby rows (local players section)
PREP_ROW_LOCAL = 0
PREP_ROW_AI = 1
PREP_ROW_TROPHY = 2
PREP_ROW_ARENA = 3
PREP_ROW_PLAYERS = 4

# Grid size (odd). Lobby can shift the default by ±2/4/6 tiles.
GRID_SIZE_1_2 = 15          # 1-2 players
GRID_SIZE_2_PLAYERS = GRID_SIZE_1_2
GRID_SIZE_3_4 = 17          # 3-4 players
GRID_SIZE_DEFAULT = GRID_SIZE_1_2
GRID_SIZE_5_6 = 19          # 5-6 players
GRID_SIZE_7_8 = 21          # 7-8 players
GRID_SIZE_BOSS = 15         # Boss fight (1v1, same as a small match)
GRID_SIZE_OFFSETS = (-6, -4, -2, 0, 2, 4, 6)
GRID_SIZE_MIN = 9
GRID_SIZE_MAX = 27


def _as_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def clamp_odd_grid(size):
    """Keep arenas odd and inside the playable tile range."""
    size = _as_int(size, GRID_SIZE_DEFAULT)
    if size % 2 == 0:
        size += 1
    return max(GRID_SIZE_MIN, min(GRID_SIZE_MAX, size))


def default_grid_size(player_count=None, is_boss_fight=False):
    """Default odd tile count for a roster size. Boss fights stay on 15."""
    if is_boss_fight:
        return GRID_SIZE_BOSS
    if player_count is None:
        return GRID_SIZE_DEFAULT
    count = _as_int(player_count, 0)
    if count <= 2:
        return GRID_SIZE_1_2
    if count <= 4:
        return GRID_SIZE_3_4
    if count <= 6:
        return GRID_SIZE_5_6
    return GRID_SIZE_7_8


def clamp_grid_offset(offset=0):
    off = _as_int(offset, 0)
    if off % 2:
        off -= 1 if off > 0 else -1
    return max(GRID_SIZE_OFFSETS[0], min(GRID_SIZE_OFFSETS[-1], off))


def grid_offset_index(offset=0):
    off = clamp_grid_offset(offset)
    if off in GRID_SIZE_OFFSETS:
        return GRID_SIZE_OFFSETS.index(off)
    return GRID_SIZE_OFFSETS.index(0)


def grid_size_choices(player_count=None):
    base = default_grid_size(player_count)
    return [clamp_odd_grid(base + off) for off in GRID_SIZE_OFFSETS]


def get_grid_size(player_count=None, is_boss_fight=False, offset=0):
    """Return grid size (odd) for the given context.

    Boss fights are always 1v1 on the 15-tile arena, regardless of how
    many players were in the preceding free-for-all. FFA size is the
    roster default plus an optional even lobby offset (±2/4/6).
    """
    if is_boss_fight:
        return GRID_SIZE_BOSS
    return clamp_odd_grid(default_grid_size(player_count) + clamp_grid_offset(offset))


BOMB_TIMER = 3000
EXPLOSION_DURATION = 400
BOSS_SHIELD_DURATION_MS = EXPLOSION_DURATION + 200  # i-frames after spending an extra life

# Play one of the mocny_stral variants once unique tiles in this window reach the threshold.
BIG_EXPLOSION_TILE_THRESHOLD = 125  # 2.5x the previous 50-tile loud hit
BIG_EXPLOSION_WINDOW_MS = 700
BIG_EXPLOSION_SOUND_DELAY_MS = 300
BIG_EXPLOSION_VOLUME = 1.0
BIG_EXPLOSION_COOLDOWN_MS = 5000
MOCNY_STRAL_VARIANTS = 5


def format_match_clock(elapsed_ms) -> str:
    """Elapsed round time in whole seconds."""
    return str(max(0, int(elapsed_ms) // 1000))


def format_crushing_wall_start(early_s, late_s) -> str:
    """XX is few players and few soft walls left; YY is the start with no other condition."""
    return f"(cw start: {int(early_s)}s/{int(late_s)}s)"

# Explosion collision: inner 70% of a flaming cell. Flame art stops at the
# last cell's center; the hit rect is that same inner 70% square.
EXPLOSION_COLLISION_SCALE = 0.7
EXPLOSION_PLAYER_HIT_SCALE = 0.30  # radius = 30% of half-cell (~15px)
SCARED_BLAST_MAX_CELLS = 5

# Post-win delay (ms): keep game running briefly after a win before showing screen
ENDGAME_POST_DELAY_MS = 2500

# --- Replay settings ---
# How often to log snapshots for replay (ms). 16ms matches the 60 Hz sim.
REPLAY_LOG_INTERVAL_MS = 16
# How much history to keep so a kill-cam can reach back before a death
REPLAY_BUFFER_MS = 6500
# Camera radius in cells (viewport will be (2*r+1) cells in width/height)
REPLAY_CAMERA_RADIUS_CELLS = 5
# Replay panel on the win screen sits below the stats table
REPLAY_PANEL_WIDTH_RATIO = 0.80
REPLAY_PANEL_HEIGHT_RATIO = 0.44
REPLAY_PANEL_PADDING = 12
# Kill-cam window around each death, played in death order then looped
REPLAY_KILLCAM_PRE_MS = 3500
REPLAY_KILLCAM_POST_MS = 1500

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

player_names = ["Marv", "Sobi", "Tom", "Zelda", "Ondra", "Sasa", "Luna", "Kai"]
AI_NAME_LEFT = (
    "Zesty", "Nitro", "Pixel", "Cosmic", "Spicy", "Fuzzy", "Neon", "Dusty",
    "Turbo", "Lucky", "Giga", "Tiny", "Sneaky", "Bouncy", "Rusty",
)
AI_NAME_RIGHT = (
    "Badger", "Noodle", "Comet", "Pickle", "Waffle", "Gremlin", "Rocket",
    "Muffin", "Penguin", "Cactus", "Otter", "Falcon", "Bean", "Goblin", "Yeti",
)
#players = []
colors = [
    (100, 150, 200),  # Light Blue
    (200, 150, 100),  # Light Brown
    (150, 200, 100),  # Light Green
    (200, 100, 150),  # Light Pink
    (100, 200, 150),  # Light Teal
    (150, 100, 200),  # Light Purple
    (220, 90, 70),    # Coral
    (80, 160, 220),   # Sky
]

FPS = 60

controls_list = [
    {
        'up': pygame.K_w, 'down': pygame.K_s, 'left': pygame.K_a, 'right': pygame.K_d, 'bomb': pygame.K_SPACE,
        'also': {'up': pygame.K_UP, 'down': pygame.K_DOWN, 'left': pygame.K_LEFT, 'right': pygame.K_RIGHT},
    },
    {'up': pygame.K_i, 'down': pygame.K_k, 'left': pygame.K_j, 'right': pygame.K_l, 'bomb': pygame.K_LCTRL},
    {'up': pygame.K_f , 'down': pygame.K_v, 'left': pygame.K_c, 'right': pygame.K_b, 'bomb': pygame.K_h},
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


# --- IMGS (loaded lazily after pygame init) ---
quad_damage_image = None
fire_powerup_image = None
blast_image = None
blast_image_qd = None
blast_centre_image = None
blast_centre_image_qd = None
logo_image = None


def init_assets():
    """Load pygame image assets after pygame has been initialized."""
    global quad_damage_image, fire_powerup_image, blast_image, blast_image_qd, blast_centre_image, blast_centre_image_qd, logo_image
    if logo_image is not None:
        return
    from bm_assets import load_images

    images = load_images()
    quad_damage_image = images["quad_damage_image"]
    fire_powerup_image = images["fire_powerup_image"]
    blast_image = images["blast_image"]
    blast_image_qd = images["blast_image_qd"]
    blast_centre_image = images["blast_centre_image"]
    blast_centre_image_qd = images["blast_centre_image_qd"]
    logo_image = images["logo_image"]


# Internal constants and pre-calculation
# Default for prep/startup (no game running)
GRID_WIDTH = GRID_SIZE_DEFAULT
GRID_HEIGHT = GRID_SIZE_DEFAULT

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


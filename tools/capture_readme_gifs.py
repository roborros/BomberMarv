#!/usr/bin/env python3
"""Render short gameplay GIFs for the public README.

Pieces are only placed on EMPTY tiles. Run from repo root:

    python tools/capture_readme_gifs.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from helpers import silence_sounds  # noqa: E402

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from bm_classes import Bomb, Game, Player, PowerUp  # noqa: E402
from bm_drawing import (  # noqa: E402
    draw_explosion_collision_debug,
    draw_game_prep,
    draw_game_screen,
    draw_get_ready,
    draw_leave_prompt,
    draw_stat_screen,
    draw_title_page,
)
import bm_drawing  # noqa: E402
from lib_collisions import circle_rect_collision  # noqa: E402
from bm_params import (  # noqa: E402
    BASE_HEIGHT,
    BASE_WIDTH,
    BOMB_BASE_RADIUS,
    BOMB_PULSE_AMPLITUDE,
    BOMB_TIMER,
    CELL_SIZE,
    DESTRUCTIBLE,
    EMPTY,
    EXPLOSION_DURATION,
    INDESTRUCTIBLE,
    PLAYER_DRAW_SCALE,
    colors,
    init_assets,
)
from input_abstraction import Keys  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "media")
STILL_DIR = os.path.join(ROOT, "tools", ".frames")
MAX_WIDTH = 900
GIF_FPS = 16
GIF_COLORS = 256


def _surface_to_image(surface: pygame.Surface, max_width: int | None = MAX_WIDTH) -> Image.Image:
    raw = pygame.image.tobytes(surface, "RGB")
    image = Image.frombytes("RGB", surface.get_size(), raw)
    if max_width and image.width > max_width:
        height = max(1, int(image.height * (max_width / image.width)))
        image = image.resize((max_width, height), Image.Resampling.LANCZOS)
    return image


def _quantize_frames(frames: list[Image.Image], colors: int = GIF_COLORS) -> list[Image.Image]:
    picks = sorted({
        min(len(frames) - 1, max(0, i))
        for i in (0, len(frames) // 4, len(frames) // 2, (3 * len(frames)) // 4, len(frames) - 1)
    })
    samples = [frames[i] for i in picks]
    width, height = samples[0].size
    sheet = Image.new("RGB", (width * len(samples), height))
    for i, sample in enumerate(samples):
        sheet.paste(sample, (i * width, 0))
    # Keep caption gold, flame, and kill-box cyan in the 256-color palette.
    anchors = (
        (0, 255, 255), (16, 18, 24), (255, 70, 40), (255, 190, 50),
        (212, 175, 55), (245, 248, 252), (80, 255, 255), (40, 40, 48),
    )
    px = sheet.load()
    for i, color in enumerate(anchors):
        for y in range(10):
            for x in range(10):
                px[i * 10 + x, y] = color
    palette = sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    return [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]


def _save_gif_ffmpeg(path: str, frames: list[Image.Image], fps: int) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    work = os.path.join(STILL_DIR, "_gifwork", os.path.splitext(os.path.basename(path))[0])
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)
    try:
        for i, frame in enumerate(frames):
            frame.save(os.path.join(work, f"{i:04d}.png"))
        pattern = os.path.join(work, "%04d.png")
        palette = os.path.join(work, "palette.png")
        gen = subprocess.run(
            [
                ffmpeg, "-y", "-framerate", str(fps), "-i", pattern,
                "-vf", f"palettegen=max_colors={GIF_COLORS}:reserve_transparent=0:stats_mode=full",
                palette,
            ],
            capture_output=True,
            text=True,
        )
        if gen.returncode != 0:
            return False
        use = subprocess.run(
            [
                ffmpeg, "-y", "-framerate", str(fps), "-i", pattern, "-i", palette,
                "-lavfi", "paletteuse=dither=sierra2_4a:diff_mode=rectangle",
                "-loop", "0", path,
            ],
            capture_output=True,
            text=True,
        )
        return use.returncode == 0 and os.path.isfile(path)
    except OSError:
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def save_gif(name: str, frames: list[Image.Image], fps: int = GIF_FPS) -> str:
    if not frames:
        raise RuntimeError(f"no frames for {name}")
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    if not _save_gif_ffmpeg(path, frames, fps):
        quantized = _quantize_frames(frames)
        quantized[0].save(
            path,
            save_all=True,
            append_images=quantized[1:],
            duration=int(round(1000 / fps)),
            loop=0,
            optimize=False,
            disposal=2,
        )
    size_kb = os.path.getsize(path) / 1024
    print(f"wrote {path} ({len(frames)} frames, {size_kb:.0f} KB)", flush=True)
    return path


def save_still(name: str, image: Image.Image) -> None:
    os.makedirs(STILL_DIR, exist_ok=True)
    path = os.path.join(STILL_DIR, name)
    image.save(path)
    print(f"still {path}", flush=True)


def _init_pygame() -> None:
    pygame.init()
    pygame.font.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    init_assets()
    silence_sounds()
    bm_drawing._ensure_fonts_initialized()


def empty_arena(size: int, extra_destructible=(), extra_pillars=()) -> list[list[int]]:
    board = [
        [
            INDESTRUCTIBLE if x == 0 or y == 0 or x == size - 1 or y == size - 1 else EMPTY
            for x in range(size)
        ]
        for y in range(size)
    ]
    for x, y in extra_pillars:
        board[y][x] = INDESTRUCTIBLE
    for x, y in extra_destructible:
        board[y][x] = DESTRUCTIBLE
    return board


def classic_pillars(size: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(2, size - 1, 2) for x in range(2, size - 1, 2)]


def require_empty(board, cells, label: str) -> None:
    for x, y in cells:
        tile = board[y][x]
        if tile != EMPTY:
            kind = "indestructible" if tile == INDESTRUCTIBLE else "destructible"
            raise RuntimeError(f"{label} at {(x, y)} sits on a {kind} wall")


def require_open_neighborhood(board, cells, label: str) -> None:
    """Bombs/powerups must not sit against a wall; 90% sprites look glued on."""
    height = len(board)
    width = len(board[0])
    for x, y in cells:
        require_empty(board, [(x, y)], label)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height) or board[ny][nx] != EMPTY:
                raise RuntimeError(f"{label} at {(x, y)} is against a wall at {(nx, ny)}")


def _sprite_hits_walls(game, cx, cy, radius, ignore) -> list[tuple[int, int]]:
    hits = []
    for y, row in enumerate(game.board):
        for x, tile in enumerate(row):
            if tile == EMPTY or (x, y) in ignore:
                continue
            rect = (x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            if circle_rect_collision((cx, cy), radius, rect):
                hits.append((x, y))
    return hits


def assert_sprites_clear_of_walls(game, label: str, ignore_cells=()) -> None:
    """Drawn circles must not cover wall tiles. Grid-empty is not enough: AI hugs walls."""
    ignore = set(ignore_cells)
    player_r = int(CELL_SIZE * PLAYER_DRAW_SCALE / 2)
    bomb_r = int(BOMB_BASE_RADIUS * (1 + BOMB_PULSE_AMPLITUDE)) + 6
    pup_r = (CELL_SIZE - 20) / 2
    problems = []
    for player in game.players:
        if not player.alive:
            continue
        radius = getattr(player, "draw_radius", player_r)
        hits = _sprite_hits_walls(game, float(player.pos[0]), float(player.pos[1]), radius, ignore)
        if hits:
            problems.append(f"player {player.name} overlaps walls {hits[:4]}")
    for bomb in game.bombs:
        cx = bomb.x * CELL_SIZE + CELL_SIZE // 2
        cy = bomb.y * CELL_SIZE + CELL_SIZE // 2
        hits = _sprite_hits_walls(game, cx, cy, bomb_r, ignore)
        if hits:
            problems.append(f"bomb at {(bomb.x, bomb.y)} overlaps walls {hits[:4]}")
    for pup in game.powerups:
        cx = pup.x * CELL_SIZE + CELL_SIZE // 2
        cy = pup.y * CELL_SIZE + CELL_SIZE // 2
        hits = _sprite_hits_walls(game, cx, cy, pup_r, ignore)
        if hits:
            problems.append(f"powerup at {(pup.x, pup.y)} overlaps walls {hits[:4]}")
    if problems:
        raise RuntimeError(f"{label}: " + "; ".join(problems))


def assert_pieces_on_empty(game, label: str) -> None:
    cells = []
    for player in game.players:
        if player.alive:
            cells.append(player.get_grid_pos())
    cells.extend((bomb.x, bomb.y) for bomb in game.bombs)
    cells.extend((pup.x, pup.y) for pup in game.powerups)
    require_empty(game.board, cells, label)
    assert_sprites_clear_of_walls(game, label)


def _local_player(x: int, y: int, name: str, color, controls=None) -> Player:
    controls = controls or {
        "up": Keys.W,
        "down": Keys.S,
        "left": Keys.A,
        "right": Keys.D,
        "bomb": Keys.SPACE,
    }
    player = Player(x, y, color, controls, name)
    player.is_local = True
    player.is_ai = False
    player.global_id = 1
    player.pos[0] = x * CELL_SIZE + CELL_SIZE / 2
    player.pos[1] = y * CELL_SIZE + CELL_SIZE / 2
    return player


def _ai_player(x: int, y: int, name: str, color, slot: int = 0) -> Player:
    player = Player(x, y, color, None, name)
    player.is_local = False
    player.is_ai = True
    player.ai_role = "cpu"
    player.ai_slot = slot
    player.global_id = slot + 2
    player.pos[0] = x * CELL_SIZE + CELL_SIZE / 2
    player.pos[1] = y * CELL_SIZE + CELL_SIZE / 2
    return player


def _playing_game(board) -> Game:
    size = len(board)
    game = Game()
    game.board = board
    game._set_arena_size(size)
    game.bombs = []
    game.explosions = []
    game.powerups = []
    game.replay_buffer = []
    game.kill_cam_clips = []
    game._pending_kill_cams = []
    game.game_state = "playing"
    game.game_start_time = 0
    game.round_start_time = 0
    game.current_time = 0
    game.dt = 16
    game.crushing_walls_active = False
    game.starting_player_count = 4
    game.leave_prompt_open = False
    return game


def _surface_for(game: Game) -> pygame.Surface:
    return pygame.Surface((game.grid_width * CELL_SIZE, game.grid_height * CELL_SIZE))


def _plant(game: Game, owner: Player, x: int, y: int, fuse_left_ms: int) -> Bomb:
    require_open_neighborhood(game.board, [(x, y)], "bomb")
    bomb = Bomb(x, y, game.current_time - BOMB_TIMER + fuse_left_ms, owner.fire_power, owner)
    owner.active_bombs += 1
    game.bombs.append(bomb)
    return bomb


def _draw_caption(surface, text: str) -> None:
    if not text:
        return
    sw, sh = surface.get_size()
    font = pygame.font.SysFont("arial", max(18, min(30, sh // 26)), bold=True)
    pad_x, pad_y = 16, 10
    label = font.render(text, True, (245, 248, 252))
    bg_h = label.get_height() + pad_y * 2
    banner = pygame.Surface((sw, bg_h), pygame.SRCALPHA)
    banner.fill((12, 14, 22, 220))
    surface.blit(banner, (0, sh - bg_h))
    pygame.draw.line(surface, (212, 175, 55), (0, sh - bg_h), (sw, sh - bg_h), 2)
    rect = label.get_rect(midleft=(pad_x, sh - bg_h // 2))
    if rect.right > sw - pad_x:
        rect.centerx = sw // 2
    surface.blit(label, rect)


def _letterbox(src, size=(1280, 720), fill=(16, 20, 28)) -> pygame.Surface:
    out = pygame.Surface(size)
    out.fill(fill)
    bw, bh = src.get_size()
    scale = min(size[0] / float(bw), size[1] / float(bh))
    nw, nh = max(1, int(bw * scale)), max(1, int(bh * scale))
    out.blit(
        pygame.transform.smoothscale(src, (nw, nh)),
        ((size[0] - nw) // 2, (size[1] - nh) // 2),
    )
    return out


def _hold_frames(game, surface, duration_ms, **kwargs):
    kwargs.setdefault("pressed", {})
    return _simulate_frames(game, surface, duration_ms, **kwargs)


def _place(player: Player, x: int, y: int) -> None:
    player.pos[0] = x * CELL_SIZE + CELL_SIZE / 2
    player.pos[1] = y * CELL_SIZE + CELL_SIZE / 2


def _simulate_frames(
    game,
    surface,
    duration_ms,
    start_ms=None,
    every_ms=32,
    pressed=None,
    clear_label=None,
    ignore_cells=(),
    caption=None,
    extra_draw=None,
):
    frames = []
    keys = pressed or {}
    if start_ms is None:
        start_ms = int(getattr(game, "current_time", 0) or 0)

    def _is_pressed(key):
        return bool(keys.get(key, False))

    with patch("bm_classes.get_pressed_keys", return_value=keys), patch(
        "bm_classes.is_key_pressed", _is_pressed
    ):
        for step in range(0, duration_ms, 16):
            game.simulate(16, now_ms=start_ms + step)
            if clear_label:
                assert_sprites_clear_of_walls(game, f"{clear_label}@{step}", ignore_cells)
            if step % every_ms == 0:
                draw_game_screen(surface, game)
                if extra_draw:
                    extra_draw(surface, game)
                if caption:
                    _draw_caption(surface, caption)
                frames.append(_surface_to_image(surface))
    return frames


def capture_title() -> None:
    width, height = 1280, 720
    game = Game()
    game.prep_num_players = 2
    game.prep_ai_count = 0
    game.create_players()
    surface = pygame.Surface((width, height))
    frames = []
    beats = (
        (16, "LAN Bomberman — one PC hosts the match"),
        (16, "Friends join from a browser on the same Wi-Fi"),
    )
    frame_i = 0
    for count, caption in beats:
        for _ in range(count):
            alpha = int(230 + 25 * abs((frame_i % 20) - 10) / 10)
            draw_title_page(
                surface,
                alpha=alpha,
                show_game_name=True,
                players=game.players,
                show_start_hint=True,
            )
            _draw_caption(surface, caption)
            frames.append(_surface_to_image(surface, 900))
            frame_i += 1
    save_still("title.png", _surface_to_image(surface, None))

    lobby = Game()
    lobby.prep_num_players = 3
    lobby.prep_ai_count = 2
    lobby.prep_trophy_threshold = 3
    lobby.prep_section = "start_game"
    lobby._cached_status = {"clients": {}, "players": {}, "slots": {}}
    lobby.create_players()
    lobby_surf = pygame.Surface((1600, 900))
    for _ in range(16):
        draw_game_prep(lobby_surf, lobby)
        composed = _letterbox(lobby_surf, (width, height))
        _draw_caption(composed, "Enter opens the lobby: players, CPU, trophies")
        frames.append(_surface_to_image(composed, 900))

    board = empty_arena(9, extra_pillars=classic_pillars(9), extra_destructible=((3, 5), (5, 3)))
    play = _playing_game(board)
    play.players = [
        _local_player(1, 1, "Marv", colors[0]),
        _local_player(7, 7, "Sobi", colors[1], {
            "up": Keys.I, "down": Keys.K, "left": Keys.J, "right": Keys.L, "bomb": Keys.U,
        }),
        _ai_player(7, 1, "Tom", colors[2], 0),
    ]
    play.players[2].is_ai = False
    board_surf = _surface_for(play)
    for _ in range(14):
        draw_game_screen(board_surf, play)
        draw_get_ready(board_surf)
        composed = _letterbox(board_surf, (width, height))
        _draw_caption(composed, "Get Ready — last one standing wins the round")
        frames.append(_surface_to_image(composed, 900))

    save_gif("title.gif", frames)


def capture_lobby() -> None:
    game = Game()
    game.prep_num_players = 2
    game.prep_ai_count = 1
    game.prep_trophy_threshold = 3
    game.prep_section = "local_players"
    game.prep_cursor_row = 0
    game.prep_cursor_col = 1
    game.team_mode_enabled = False
    tom = {
        "registered": True,
        "display_name": "Tom",
        "last_seen": time.time(),
        "players": [1],
        "avg_latency_5s": 18,
        "latency_samples_5s": 40,
    }
    game._cached_status = {"clients": {}, "players": {}, "slots": {}}
    game.create_players()
    surface = pygame.Surface((1600, 900))
    frames = []
    fake_now = [1_700_000_000.0]

    def _now() -> float:
        return fake_now[0]

    def _beat(n, caption, setup=None):
        if setup:
            setup()
        for _ in range(n):
            fake_now[0] += 0.08
            draw_game_prep(surface, game)
            _draw_caption(surface, caption)
            frames.append(_surface_to_image(surface, 900))

    with patch("bm_drawing.time.time", _now):
        _beat(12, "Host lobby: local keyboards, CPU opponents, trophies")

        def _locals():
            game.prep_cursor_row = 0
            game.prep_cursor_col = 2
            game.prep_num_players = 3
            game.create_players()

        _beat(12, "Local player count = people on this PC's keyboards", _locals)

        def _ai():
            game.prep_cursor_row = 1
            game.prep_cursor_col = 2
            game.prep_ai_count = 2
            game.create_players()

        _beat(12, "CPU opponents fill extra slots", _ai)

        def _trophies():
            game.prep_cursor_row = 2
            game.prep_cursor_col = 2
            game.prep_trophy_threshold = 3

        _beat(12, "First to this many trophies becomes champion", _trophies)

        def _arena():
            game.prep_cursor_row = 3
            game.prep_cursor_col = 5
            game.prep_grid_offset = 4

        _beat(12, "Arena follows player count; override by ±2/4/6 tiles", _arena)

        _beat(12, "Guests open this PC's address in a browser")

        def _remote():
            game._cached_status["clients"] = {"11": tom}
            game._cached_status["slots"] = {"1": True}
            game.create_players()

        _beat(14, "Remote clients show name, slot, and latency", _remote)

        def _color():
            game.prep_section = "local_players"
            game.prep_cursor_row = 4
            game.prep_cursor_col = 0
            game.prep_player_colors[0] = (game.prep_player_colors[0] + 3) % len(colors)
            game.create_players()

        _beat(12, "Left/Right on a row recolors that local player", _color)

        def _teams():
            game.team_mode_enabled = True
            game.prep_player_teams[0] = 0
            game.prep_player_teams[1] = 0
            game.prep_player_teams[2] = 1
            game.create_players()

        _beat(12, "T on a row assigns teams (optional)", _teams)

        def _start():
            game.prep_section = "start_game"

        _beat(14, "Tab to Start Game when the roster looks right", _start)

    save_gif("lobby.gif", frames)
    save_still("lobby.png", frames[-1] if frames else _surface_to_image(surface, None))
    game._cached_status["clients"] = {}
    draw_game_prep(surface, game)
    save_still("lobby-empty.png", _surface_to_image(surface, None))


def capture_bombs() -> None:
    frames = []
    sobi_keys = {
        "up": Keys.I, "down": Keys.K, "left": Keys.J, "right": Keys.L, "bomb": Keys.U,
    }

    board = empty_arena(9, extra_destructible=((2, 2), (6, 2), (2, 6), (6, 6)))
    require_open_neighborhood(board, [(2, 4), (3, 4), (4, 4), (5, 4)], "bomb-demo")
    game = _playing_game(board)
    marv = _local_player(2, 4, "Marv", colors[0])
    marv.fire_power = 2
    marv.bomb_capacity = 3
    game.players = [marv]
    game.current_time = 0
    assert_pieces_on_empty(game, "bomb-demo")
    surface = _surface_for(game)
    frames += _simulate_frames(
        game, surface, 900, start_ms=0, every_ms=32,
        pressed={Keys.D: True, Keys.SPACE: True},
        clear_label="bomb-demo",
        caption="Hold bomb while walking — a new bomb in each empty cell",
    )
    frames += _simulate_frames(
        game, surface, 500, every_ms=32,
        pressed={Keys.S: True},
        clear_label="bomb-demo",
        caption="Hold bomb while walking — a new bomb in each empty cell",
    )

    board = empty_arena(9)
    require_open_neighborhood(board, [(4, 4)], "bomb-demo")
    game = _playing_game(board)
    marv = _local_player(4, 2, "Marv", colors[0])
    sobi = _local_player(7, 7, "Sobi", colors[1], sobi_keys)
    marv.fire_power = 2
    sobi.fire_power = 2
    game.players = [marv, sobi]
    game.current_time = 0
    _plant(game, sobi, 4, 4, 2200)
    assert_pieces_on_empty(game, "bomb-demo")
    surface = _surface_for(game)
    frames += _hold_frames(
        game, surface, 700, every_ms=40, clear_label="bomb-demo",
        caption="On a planned blast cell you get a scared face — warning",
    )
    frames += _simulate_frames(
        game, surface, 700, every_ms=32,
        pressed={Keys.A: True},
        clear_label="bomb-demo",
        caption="Step off the blast line and the face goes back to normal",
    )

    board = empty_arena(9, extra_destructible=((3, 2), (5, 2), (3, 6), (5, 6)))
    require_open_neighborhood(board, [(3, 4), (4, 4), (5, 4)], "bomb-demo")
    game = _playing_game(board)
    marv = _local_player(1, 1, "Marv", colors[0])
    marv.fire_power = 2
    marv.bomb_capacity = 3
    game.players = [marv]
    game.current_time = 0
    _plant(game, marv, 3, 4, 280)
    _plant(game, marv, 4, 4, 2400)
    _plant(game, marv, 5, 4, 2400)
    assert_pieces_on_empty(game, "bomb-demo")
    surface = _surface_for(game)
    with patch("bm_classes.random.random", return_value=1.0):
        frames += _simulate_frames(
            game, surface, 900, every_ms=16, pressed={},
            clear_label="bomb-demo",
            caption="Chain: a blast that reaches another bomb sets it off",
        )
    save_gif("bombs.gif", frames, fps=16)
    save_still("bombs.png", frames[min(40, len(frames) - 1)])


def capture_powerups() -> None:
    frames = []
    still_pickup = None

    board = empty_arena(9)
    require_open_neighborhood(board, [(4, 4), (5, 4)], "powerup-demo")
    game = _playing_game(board)
    marv = _local_player(2, 4, "Marv", colors[0])
    marv.bomb_capacity = 1
    marv.fire_power = 1
    game.players = [marv]
    game.powerups = [PowerUp(4, 4, "bomb", spawn_time=0)]
    assert_pieces_on_empty(game, "powerup-demo")
    surface = _surface_for(game)
    hold = _hold_frames(
        game, surface, 640, every_ms=40, clear_label="powerup-demo",
        caption="Extra bomb pickup — cyan bomb icon",
    )
    frames += hold
    still_pickup = hold[min(4, len(hold) - 1)]
    frames += _simulate_frames(
        game, surface, 750, every_ms=32, pressed={Keys.D: True},
        clear_label="powerup-demo",
        caption="Walk onto it: +1 bomb you can have live at once",
    )
    frames += _simulate_frames(
        game, surface, 800, every_ms=32, pressed={Keys.D: True, Keys.SPACE: True},
        clear_label="powerup-demo",
        caption="Now two bombs can sit on the board together",
    )
    frames += _simulate_frames(
        game, surface, 450, every_ms=32, pressed={Keys.S: True},
        clear_label="powerup-demo",
        caption="Now two bombs can sit on the board together",
    )

    board = empty_arena(9, extra_destructible=((6, 4),))
    require_open_neighborhood(board, [(4, 2), (4, 4)], "powerup-demo")
    game = _playing_game(board)
    marv = _local_player(2, 2, "Marv", colors[0])
    marv.fire_power = 1
    marv.bomb_capacity = 1
    game.players = [marv]
    game.powerups = [PowerUp(4, 2, "fire", spawn_time=0)]
    assert_pieces_on_empty(game, "powerup-demo")
    surface = _surface_for(game)
    frames += _hold_frames(
        game, surface, 640, every_ms=40, clear_label="powerup-demo",
        caption="Fire pickup — +1 blast range",
    )
    frames += _simulate_frames(
        game, surface, 750, every_ms=32, pressed={Keys.D: True},
        clear_label="powerup-demo",
        caption="Fire pickup — +1 blast range",
    )
    _place(marv, 2, 6)
    _plant(game, marv, 4, 4, 260)
    with patch("bm_classes.random.random", return_value=1.0):
        frames += _simulate_frames(
            game, surface, 800, every_ms=16, pressed={},
            clear_label="powerup-demo",
            caption="Range 2 now pops the farther soft brick",
        )

    board = empty_arena(9)
    require_open_neighborhood(board, [(4, 4)], "powerup-demo")
    game = _playing_game(board)
    marv = _local_player(2, 4, "Marv", colors[0])
    marv.bomb_capacity = 1
    marv.fire_power = 1
    game.players = [marv]
    game.powerups = [PowerUp(4, 4, "quad_damage", spawn_time=0)]
    assert_pieces_on_empty(game, "powerup-demo")
    surface = _surface_for(game)
    frames += _hold_frames(
        game, surface, 640, every_ms=40, clear_label="powerup-demo",
        caption="Quad Damage — rare map spawn, 20 seconds",
    )
    frames += _simulate_frames(
        game, surface, 750, every_ms=32, pressed={Keys.D: True},
        clear_label="powerup-demo",
        caption="Collect: huge bombs, extra capacity, speed boost",
    )
    _place(marv, 2, 2)
    _plant(game, marv, 4, 4, 220)
    with patch("bm_classes.random.random", return_value=1.0):
        frames += _simulate_frames(
            game, surface, 700, every_ms=16, pressed={},
            clear_label="powerup-demo",
            caption="Quad bombs fill the + cross — stay off the arms",
        )

    board = empty_arena(9)
    require_open_neighborhood(board, [(4, 4)], "powerup-demo")
    game = _playing_game(board)
    marv = _local_player(2, 2, "Marv", colors[0])
    bo = _local_player(6, 4, "Bo", colors[1], {
        "up": Keys.I, "down": Keys.K, "left": Keys.J, "right": Keys.L, "bomb": Keys.U,
    })
    marv.fire_power = 2
    game.players = [marv, bo]
    _plant(game, marv, 4, 4, 220)
    assert_pieces_on_empty(game, "powerup-demo")
    surface = _surface_for(game)
    with patch("bm_classes.choose_death_bonus_effect", return_value="fire"):
        frames += _simulate_frames(
            game, surface, 700, every_ms=16, pressed={},
            clear_label="powerup-demo",
            caption="Death bonus: a skull drops where someone dies",
        )
        frames += _hold_frames(
            game, surface, 560, every_ms=40, clear_label="powerup-demo",
            caption="Yellow skull: random speed, fire, or bombs",
        )
        _place(marv, 6, 6)
        frames += _simulate_frames(
            game, surface, 800, every_ms=32, pressed={Keys.W: True},
            clear_label="powerup-demo",
            caption="Collect it — here +2 flames",
        )
    save_gif("powerups.gif", frames)
    save_still("powerups.png", still_pickup or frames[min(4, len(frames) - 1)])


def capture_crushing_walls() -> None:
    board = empty_arena(11)
    require_empty(board, [(5, 4), (5, 6)], "crush-demo")
    game = _playing_game(board)
    otter = _ai_player(5, 6, "Otter", colors[2], 0)
    otter.is_ai = False
    game.players = [
        _local_player(5, 4, "Marv", colors[0]),
        otter,
    ]
    assert_pieces_on_empty(game, "crush-demo")
    game.starting_player_count = 4
    game.game_start_time = 0
    game.current_time = 4000
    game.crushing_walls_active = True
    game.crushing_walls_pattern = game.generate_clockwise_pattern()
    game.crushing_walls_index = 0
    game.crushing_walls_last_time = 0
    surface = _surface_for(game)
    frames = []
    for _ in range(32):
        game.current_time += 600
        game.handle_crushing_walls()
        try:
            assert_sprites_clear_of_walls(game, "crush-demo")
        except RuntimeError:
            break
        draw_game_screen(surface, game)
        _draw_caption(surface, "Crushing walls close in when few players remain")
        frames.append(_surface_to_image(surface))
    if len(frames) < 8:
        raise RuntimeError("crush-demo produced too few wall-clear frames")
    save_gif("crushing-walls.gif", frames, fps=12)
    save_still("crushing-walls.png", frames[min(14, len(frames) - 1)])


def capture_gameplay() -> None:
    board = empty_arena(
        9,
        extra_destructible=((3, 5), (5, 3)),
        extra_pillars=classic_pillars(9),
    )
    require_empty(board, [(1, 1), (7, 1), (7, 7), (1, 7)], "gameplay-demo")
    require_open_neighborhood(board, [(3, 3), (5, 5)], "gameplay-demo")
    game = _playing_game(board)
    ada = _local_player(
        1, 1, "Ada", colors[1],
        {"up": Keys.W, "down": Keys.S, "left": Keys.A, "right": Keys.D, "bomb": Keys.SPACE},
    )
    bo = _local_player(
        7, 7, "Bo", colors[0],
        {"up": Keys.I, "down": Keys.K, "left": Keys.J, "right": Keys.L, "bomb": Keys.U},
    )
    cy = _local_player(
        7, 1, "Cy", colors[5],
        {"up": Keys.F, "down": Keys.C, "left": Keys.V, "right": Keys.B, "bomb": Keys.H},
    )
    dee = _local_player(
        1, 7, "Dee", colors[2],
        {"up": Keys.UP, "down": Keys.DOWN, "left": Keys.LEFT, "right": Keys.RIGHT, "bomb": Keys.ENTER},
    )
    for player in (ada, bo, cy, dee):
        player.bomb_capacity = 2
        player.fire_power = 2
    game.players = [ada, bo, cy, dee]
    game.current_time = 0
    _plant(game, ada, 3, 3, 800)
    _plant(game, bo, 5, 5, 1000)
    assert_pieces_on_empty(game, "gameplay-demo")
    surface = _surface_for(game)
    frames = _simulate_frames(
        game,
        surface,
        1400,
        every_ms=32,
        pressed={Keys.D: True, Keys.I: True},
        clear_label="gameplay-demo",
        caption="CPU and keyboard players share the same arena",
    )
    save_gif("gameplay.gif", frames, fps=14)
    save_still("gameplay.png", frames[min(16, len(frames) - 1)])


def capture_chain_and_killbox() -> None:
    board = empty_arena(9, extra_destructible=((2, 3), (2, 5), (6, 3), (6, 5)))
    require_empty(board, [(1, 1), (7, 7)], "chain-demo")
    require_open_neighborhood(board, [(3, 4), (4, 4), (5, 4)], "chain-demo")
    game = _playing_game(board)
    marv = _local_player(1, 1, "Marv", colors[0])
    sobi = _local_player(7, 7, "Sobi", colors[1])
    marv.fire_power = 3
    marv.bomb_capacity = 3
    sobi.fire_power = 3
    game.players = [marv, sobi]
    game.current_time = 0
    _plant(game, marv, 3, 4, 260)
    _plant(game, marv, 4, 4, 2400)
    _plant(game, marv, 5, 4, 2400)
    assert_pieces_on_empty(game, "chain-demo")
    surface = _surface_for(game)
    bm_drawing.font_small = pygame.font.SysFont("arial", 16)
    frames = []
    peak_i = None
    with patch("bm_classes.get_pressed_keys", return_value={}), patch(
        "bm_classes.is_key_pressed", return_value=False
    ):
        for step in range(0, 1100, 16):
            game.simulate(16, now_ms=step)
            assert_sprites_clear_of_walls(game, f"chain-demo@{step}")
            if step % 16 == 0:
                draw_game_screen(surface, game)
                draw_explosion_collision_debug(
                    surface, game.current_time, game.explosions, game.players,
                )
                _draw_caption(surface, "Kill box is the inner 70% of each flaming cell")
                frames.append(_surface_to_image(surface))
                if any(
                    0.35 <= (game.current_time - expl.start_time) / EXPLOSION_DURATION <= 0.65
                    for expl in game.explosions
                ):
                    peak_i = len(frames) - 1
    save_gif("blast-rules.gif", frames, fps=16)
    save_still("blast-rules.png", frames[peak_i if peak_i is not None else len(frames) // 2])


def capture_corner_slide() -> None:
    board = empty_arena(9, extra_pillars=((5, 3),))
    require_empty(board, [(1, 4), (5, 4), (6, 4)], "corner-demo")
    game = _playing_game(board)
    marv = _local_player(1, 4, "Marv", colors[0])
    game.players = [marv]
    assert_pieces_on_empty(game, "corner-demo")
    marv.pos[1] = 4 * CELL_SIZE + CELL_SIZE * 0.22
    surface = _surface_for(game)
    frames = _simulate_frames(
        game,
        surface,
        2100,
        every_ms=32,
        pressed={Keys.D: True},
        clear_label="corner-demo",
        ignore_cells=((5, 3),),
        caption="Past the midpoint of a corner? You slide around instead of sticking",
    )
    save_gif("corner-slide.gif", frames)
    save_still("corner-slide.png", frames[len(frames) // 2])


def capture_win_and_champion() -> None:
    board = empty_arena(9, extra_destructible=((3, 5), (5, 5)))
    require_empty(board, [(2, 5), (7, 7), (6, 3)], "win-demo")
    require_open_neighborhood(board, [(4, 3)], "win-demo")
    game = _playing_game(board)
    marv = _local_player(2, 5, "Marv", colors[0])
    sobi = _local_player(7, 7, "Sobi", colors[1])
    tom = _ai_player(6, 3, "Tom", colors[2], 0)
    tom.is_ai = False
    tom.ai_role = None
    marv.fire_power = 2
    marv.bomb_capacity = 3
    marv.trophies = 2
    sobi.trophies = 1
    marv.walls_destroyed = 14
    marv.players_killed = 2
    marv.powerups_collected = 5
    marv.cells_walked = 88
    sobi.alive = False
    sobi.death_time_rel_ms = 18000
    sobi.fire_power_at_death = 2
    sobi.bomb_capacity_at_death = 2
    game.players = [marv, sobi, tom]
    game.current_time = 0
    _plant(game, marv, 4, 3, 120)
    assert_pieces_on_empty(game, "win-demo")
    surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
    with patch("bm_classes.get_pressed_keys", return_value={}), patch(
        "bm_classes.is_key_pressed", return_value=False
    ):
        for step in range(0, 1800, 16):
            game.simulate(16, now_ms=step)
            if tom.alive:
                assert_sprites_clear_of_walls(game, f"win-demo@{step}")
    game._flush_kill_cams(force=True)
    game.game_state = "win"
    game.replay_loop_anchor_time = None
    marv.trophies = 3
    if tom.alive:
        tom.alive = False
        tom.death_time_rel_ms = 12000
        tom.fire_power_at_death = 3
        tom.bomb_capacity_at_death = 1
    frames = []
    fake_now = [0.0]

    def _now() -> float:
        return fake_now[0]

    replay_t = int(getattr(game, "replay_end_time", None) or game.current_time or 1800)
    with patch("bm_drawing.time.time", _now):
        for i in range(36):
            fake_now[0] = i * 0.1
            game.current_time = replay_t + i * 80
            draw_stat_screen(surface, marv, game.players, game)
            frames.append(_surface_to_image(surface, 900))
    save_gif("win-screen.gif", frames)
    save_still("win-screen.png", frames[min(12, len(frames) - 1)])


def capture_leave_prompt() -> None:
    board = empty_arena(9, extra_destructible=((3, 3), (5, 5)))
    require_empty(board, [(1, 1), (7, 7)], "leave-demo")
    game = _playing_game(board)
    noodle = _ai_player(7, 7, "Noodle", colors[3], 0)
    noodle.is_ai = False
    game.players = [
        _local_player(1, 1, "Marv", colors[0]),
        noodle,
    ]
    assert_pieces_on_empty(game, "leave-demo")
    game.open_leave_prompt()
    board_surf = _surface_for(game)
    surface = pygame.Surface((1280, 720))
    frames = []
    for i in range(24):
        game.leave_prompt_choice = "yes" if i >= 12 else "no"
        draw_game_screen(board_surf, game)
        scaled = pygame.transform.smoothscale(board_surf, (720, 720))
        surface.fill((16, 20, 28))
        surface.blit(scaled, ((1280 - 720) // 2, 0))
        draw_leave_prompt(surface, game)
        frames.append(_surface_to_image(surface, 900))
    save_gif("leave-prompt.gif", frames)
    save_still("leave-prompt.png", _surface_to_image(surface, None))


def capture_review_stills() -> None:
    board = empty_arena(
        9,
        extra_destructible=((3, 2), (5, 2), (2, 3), (6, 3)),
        extra_pillars=((2, 2), (4, 4), (6, 6)),
    )
    game = _playing_game(board)
    game.players = [
        _local_player(1, 1, "Marv", colors[0]),
        _ai_player(7, 7, "Bo", colors[1], 0),
    ]
    game.players[1].is_ai = False
    assert_pieces_on_empty(game, "get-ready")
    board_surf = _surface_for(game)
    draw_game_screen(board_surf, game)
    draw_get_ready(board_surf)
    save_still("get-ready.png", _surface_to_image(board_surf, None))

    ui = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
    ui.fill((16, 20, 28))
    bw, bh = board_surf.get_size()
    scale = min(BASE_WIDTH / bw, BASE_HEIGHT / bh)
    nw, nh = int(bw * scale), int(bh * scale)
    ui.blit(pygame.transform.smoothscale(board_surf, (nw, nh)), ((BASE_WIDTH - nw) // 2, (BASE_HEIGHT - nh) // 2))
    save_still("get-ready-window.png", _surface_to_image(ui, 900))


def main() -> int:
    _init_pygame()
    print("Capturing README animations...", flush=True)
    capture_title()
    capture_lobby()
    capture_bombs()
    capture_powerups()
    capture_crushing_walls()
    capture_gameplay()
    capture_chain_and_killbox()
    capture_corner_slide()
    capture_win_and_champion()
    capture_leave_prompt()
    capture_review_stills()
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

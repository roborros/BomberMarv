"""Render boss-lightning frames so the look can be checked without launching the game."""

import os
import sys

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import CELL_SIZE
from lightning import draw_lightning_cross

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "lightning_preview")
GRID = 9
ARMS = ((0, -1, 3 * CELL_SIZE), (0, 1, 2 * CELL_SIZE), (-1, 0, 2 * CELL_SIZE), (1, 0, 4 * CELL_SIZE))


def _background():
    surf = pygame.Surface((GRID * CELL_SIZE, GRID * CELL_SIZE))
    surf.fill((18, 22, 32))
    for y in range(GRID):
        for x in range(GRID):
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            if x == 0 or y == 0 or x == GRID - 1 or y == GRID - 1 or (x % 2 == 0 and y % 2 == 0):
                pygame.draw.rect(surf, (48, 52, 64), rect)
            else:
                pygame.draw.rect(surf, (28, 34, 46), rect)
                pygame.draw.rect(surf, (40, 48, 62), rect, 1)
    return surf


def _frame(time_ms: int, alpha: float, style: str = "marv"):
    surf = _background()
    center = (4 * CELL_SIZE + CELL_SIZE / 2, 4 * CELL_SIZE + CELL_SIZE / 2)
    grown = [(dx, dy, length * alpha) for dx, dy, length in ARMS]
    draw_lightning_cross(
        surf, center, grown, CELL_SIZE, time_ms, seed=17,
        alpha_scale=max(0.35, alpha), style=style,
    )
    return surf


def render_through_game_draw():
    """One frame from the same function the host uses in a match."""
    import types
    from bm_drawing import draw_explosions
    surf = _background()
    cells = [(4, 4)]
    cells += [(4, 4 + dy) for dy in range(-1, -4, -1)]
    cells += [(4, 4 + dy) for dy in range(1, 3)]
    cells += [(4 + dx, 4) for dx in range(-1, -3, -1)]
    cells += [(4 + dx, 4) for dx in range(1, 5)]
    explosion = types.SimpleNamespace(
        cells=cells, start_time=0, quad_damage=False, lightning=True, lightning_style="marv",
    )
    draw_explosions(surf, 180, [explosion])
    path = os.path.join(OUT, "ingame.png")
    pygame.image.save(surf, path)
    print(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    samples = (40, 90, 160, 220, 300, 370)
    frames = []
    for t in samples:
        norm = min(1.0, t / 400.0)
        if norm < 0.2:
            alpha = norm / 0.2
        elif norm <= 0.7:
            alpha = 1.0
        else:
            alpha = max(0.0, 1 - (norm - 0.7) / 0.3)
        frame = _frame(t, alpha, "marv")
        path = os.path.join(OUT, f"bolt_{t:03d}.png")
        pygame.image.save(frame, path)
        frames.append(frame)
        print(path)
    sheet = pygame.Surface((frames[0].get_width() * 3, frames[0].get_height() * 2))
    for i, frame in enumerate(frames):
        sheet.blit(frame, ((i % 3) * frame.get_width(), (i // 3) * frame.get_height()))
    sheet_path = os.path.join(OUT, "sheet.png")
    pygame.image.save(sheet, sheet_path)
    print(sheet_path)
    render_through_game_draw()
    tom = _frame(180, 1.0, "tom")
    tom_path = os.path.join(OUT, "bolt_tom.png")
    pygame.image.save(tom, tom_path)
    print(tom_path)
    marv = _frame(180, 1.0, "marv")
    pair = pygame.Surface((marv.get_width(), marv.get_height() * 2))
    pair.blit(marv, (0, 0))
    pair.blit(tom, (0, marv.get_height()))
    pair_path = os.path.join(OUT, "bolt_marv_tom.png")
    pygame.image.save(pair, pair_path)
    print(pair_path)
    try:
        from PIL import Image
        images = [Image.open(os.path.join(OUT, f"bolt_{t:03d}.png")).convert("P", palette=Image.ADAPTIVE) for t in samples]
        gif_path = os.path.join(OUT, "bolt.gif")
        images[0].save(gif_path, save_all=True, append_images=images[1:], duration=90, loop=0, disposal=2)
        print(gif_path)
    except Exception as exc:
        print("gif skipped", exc)


if __name__ == "__main__":
    main()

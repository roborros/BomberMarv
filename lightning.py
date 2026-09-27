"""Procedural lightning for boss-bomb blasts.

The hit cells stay a cross. The picture is parallel jagged arcs that hop
inside that open corridor, not a flame sprite.
"""

from __future__ import annotations

import math
import random
from typing import List, Sequence, Tuple

Point = Tuple[float, float]
Color = Tuple[int, int, int]

MARV_BOLT_PALETTE: Sequence[Color] = (
    (150, 190, 255),
    (190, 216, 255),
    (80, 130, 255),
    (110, 155, 255),
    (205, 224, 255),
)
TOM_BOLT_PALETTE: Sequence[Color] = (
    (140, 255, 185),
    (190, 255, 210),
    (60, 220, 120),
    (120, 255, 155),
    (205, 255, 220),
)
BOLT_PALETTE = MARV_BOLT_PALETTE


def is_boss_lightning_owner(owner) -> bool:
    return getattr(owner, "ai_role", "") in ("boss", "uber")


def lightning_style_for(owner) -> str:
    role = getattr(owner, "ai_role", "") if owner is not None else ""
    if role == "uber":
        return "tom"
    if role == "boss":
        return "marv"
    return ""


def palette_for(style: str) -> Sequence[Color]:
    if style == "tom":
        return TOM_BOLT_PALETTE
    return MARV_BOLT_PALETTE


def bolt_core(style: str) -> Color:
    if style == "tom":
        return (226, 255, 234)
    return (226, 236, 255)


def _perp(dx: float, dy: float) -> Point:
    length = math.hypot(dx, dy) or 1.0
    return (-dy / length, dx / length)


def _bezier(a: Point, control: Point, b: Point, samples: int = 7) -> List[Point]:
    pts = []
    n = max(2, samples)
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        pts.append((
            u * u * a[0] + 2 * u * t * control[0] + t * t * b[0],
            u * u * a[1] + 2 * u * t * control[1] + t * t * b[1],
        ))
    return pts


def bolt_polyline(
    start: Point,
    end: Point,
    rng: random.Random,
    steps: int,
    amplitude: float,
    lane: float,
) -> List[Point]:
    """Chain of curved hops from start to end, held near one parallel lane."""
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    px, py = _perp(dx, dy)
    hops = max(3, min(6, int(steps)))
    anchors = [(x0 + px * lane, y0 + py * lane)]
    prev = lane
    for i in range(1, hops):
        t = i / hops
        if rng.random() < 0.35:
            jitter = rng.uniform(-amplitude, amplitude)
        else:
            jitter = prev * 0.5 + rng.uniform(-amplitude * 0.45, amplitude * 0.45)
        jitter = max(-amplitude, min(amplitude, jitter))
        prev = jitter
        anchors.append((x0 + dx * t + px * jitter, y0 + dy * t + py * jitter))
    anchors.append((x1 + px * lane * 0.2, y1 + py * lane * 0.2))
    points: List[Point] = []
    for a, b in zip(anchors, anchors[1:]):
        mx, my = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
        bend = rng.uniform(-amplitude * 0.85, amplitude * 0.85)
        control = (mx + px * bend, my + py * bend)
        curve = _bezier(a, control, b)
        if points:
            curve = curve[1:]
        points.extend(curve)
    return points


def hop_segments(
    start: Point,
    end: Point,
    rng: random.Random,
    amplitude: float,
    count: int,
) -> List[Tuple[Point, Point]]:
    """Short arcs between two random points along the arm."""
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    px, py = _perp(dx, dy)
    hops = []
    for _ in range(max(0, count)):
        a = rng.random()
        b = min(1.0, a + rng.uniform(0.08, 0.28))
        ja = rng.uniform(-amplitude, amplitude)
        jb = rng.uniform(-amplitude, amplitude)
        hops.append((
            (x0 + dx * a + px * ja, y0 + dy * a + py * ja),
            (x0 + dx * b + px * jb, y0 + dy * b + py * jb),
        ))
    return hops


def lightning_color(bucket: int, lane_index: int, palette: Sequence[Color] | None = None) -> Color:
    colors = palette or MARV_BOLT_PALETTE
    return colors[(bucket + lane_index) % len(colors)]


def _arm_tip(cx: float, cy: float, dx: int, dy: int, length: float) -> Point:
    if length <= 0:
        return (cx, cy)
    span = math.hypot(dx, dy) or 1.0
    return (cx + dx / span * length, cy + dy / span * length)


def draw_lightning_cross(
    surface,
    center: Point,
    arms: Sequence[Tuple[int, int, float]],
    cell_size: int,
    time_ms: int,
    seed: int,
    alpha_scale: float = 1.0,
    style: str = "marv",
) -> None:
    """Draw parallel lightning along each arm. arms are (dx, dy, pixel_length)."""
    import pygame

    if alpha_scale <= 0.02:
        return
    palette = palette_for(style)
    core = bolt_core(style)
    bucket = int(time_ms) // 50
    rng = random.Random((int(seed) * 977) ^ (bucket * 1315423911))
    amplitude = cell_size * 0.16
    lanes = (-0.28, 0.0, 0.28)
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    cx, cy = center

    def stroke(points: Sequence[Point], color: Color, width: int, alpha: int) -> None:
        if len(points) < 2:
            return
        a = max(0, min(255, int(alpha * alpha_scale)))
        if a <= 0:
            return
        pix = [(int(x), int(y)) for x, y in points]
        pygame.draw.lines(layer, (*color, a), False, pix, max(1, width))
        if width <= 2:
            for x, y in pix[::3]:
                pygame.draw.circle(layer, (*color, a), (x, y), 1)

    for arm_i, (dx, dy, length) in enumerate(arms):
        if length < 8:
            continue
        tip = _arm_tip(cx, cy, dx, dy, length)
        steps = max(3, int(length / (cell_size * 0.85)))
        px, py = _perp(tip[0] - cx, tip[1] - cy)
        for lane_i, lane_t in enumerate(lanes):
            lane = lane_t * cell_size * 0.55
            color = lightning_color(bucket + arm_i, lane_i, palette)
            pts = bolt_polyline((cx, cy), tip, rng, steps, amplitude, lane)
            stroke(pts, color, max(10, cell_size // 9), 55)
            stroke(pts, color, max(4, cell_size // 22), 140)
            stroke(pts, core, 2, 235)
            if rng.random() < 0.7 and len(pts) > 4:
                fork_at = pts[rng.randrange(2, len(pts) - 2)]
                reach = rng.uniform(cell_size * 0.18, cell_size * 0.36)
                side = rng.choice((-1.0, 1.0))
                bend = rng.uniform(-10, 10)
                end = (
                    fork_at[0] + px * reach * side,
                    fork_at[1] + py * reach * side,
                )
                control = (
                    (fork_at[0] + end[0]) * 0.5 + px * bend,
                    (fork_at[1] + end[1]) * 0.5 + py * bend,
                )
                fork = _bezier(fork_at, control, end, 5)
                stroke(fork, color, 5, 90)
                stroke(fork, core, 1, 200)
        for a, b in hop_segments((cx, cy), tip, rng, amplitude * 1.2, 2):
            color = lightning_color(bucket + 1, arm_i, palette)
            mx, my = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
            control = (mx + px * rng.uniform(-18, 18), my + py * rng.uniform(-18, 18))
            hop = _bezier(a, control, b, 5)
            stroke(hop, color, 4, 110)
            stroke(hop, (255, 255, 255), 1, 210)

    for spoke in range(7):
        ang = spoke * (math.tau / 7) + (bucket % 5) * 0.2
        reach = cell_size * rng.uniform(0.18, 0.42)
        end = (cx + math.cos(ang) * reach, cy + math.sin(ang) * reach)
        side = (-math.sin(ang), math.cos(ang))
        control = (
            (cx + end[0]) * 0.5 + side[0] * rng.uniform(-16, 16),
            (cy + end[1]) * 0.5 + side[1] * rng.uniform(-16, 16),
        )
        spark = _bezier((cx, cy), control, end, 4)
        color = lightning_color(bucket, spoke, palette)
        stroke(spark, color, 4, 120)
        stroke(spark, (255, 255, 255), 1, 230)
    pygame.draw.circle(layer, (255, 255, 255, int(230 * alpha_scale)), (int(cx), int(cy)), max(3, cell_size // 28))
    surface.blit(layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

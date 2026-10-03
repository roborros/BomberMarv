"""Splash timing. The bar climbs in random steps, then holds, then fills."""

import random

STARTUP_CLIMB_MS = 4000
STARTUP_HOLD_98_MS = 2700
STARTUP_FULL_MS = 300
STARTUP_TOTAL_MS = STARTUP_CLIMB_MS + STARTUP_HOLD_98_MS + STARTUP_FULL_MS


def build_startup_load_jumps(rng=None):
    """Increasing (time_ms, percent) steps that land on 98% at 4 seconds."""
    rng = rng or random.Random()
    count = rng.randint(7, 12)
    times = []
    last = 0
    for _ in range(count - 1):
        gap = rng.randint(140, 620)
        nxt = last + gap
        if nxt >= STARTUP_CLIMB_MS - 80:
            break
        times.append(nxt)
        last = nxt
    times.append(STARTUP_CLIMB_MS)
    steps = len(times)
    weights = [rng.randint(1, 10) for _ in range(steps)]
    weight_sum = sum(weights)
    percent = 0
    jumps = []
    for index, (moment, weight) in enumerate(zip(times, weights)):
        if index == steps - 1:
            percent = 98
            moment = STARTUP_CLIMB_MS
        else:
            room = 98 - percent - (steps - index - 1)
            step = max(1, int(round(98 * weight / weight_sum)))
            step = max(1, min(step, room))
            percent += step
        jumps.append((int(moment), int(percent)))
    return jumps


def startup_load_percent(elapsed_ms, jumps):
    """0–98 while the bar is jumping, 98 for the hold, then 100."""
    elapsed = int(elapsed_ms or 0)
    if elapsed < 0:
        elapsed = 0
    full_at = STARTUP_CLIMB_MS + STARTUP_HOLD_98_MS
    if elapsed >= full_at:
        return 100
    if elapsed >= STARTUP_CLIMB_MS:
        return 98
    percent = 0
    for moment, value in jumps or ():
        if elapsed >= int(moment):
            percent = int(value)
        else:
            break
    return max(0, min(98, percent))

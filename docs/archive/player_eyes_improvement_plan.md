# Player Eyes Improvement Plan

## Goal

Replace the current small black-dot eyes with larger white ellipses/circles containing small black pupils. The pupils should be centered when the player is stationary, or offset in the direction of movement when moving—matching the existing web client implementation.

## Current State

### Python (`bm_drawing.py` – `draw_players`)

- Eyes: two small black circles (`eye_r = max(1, r//8)`)
- Fixed positions: `(pos[0] ± eye_offset_x, pos[1] - eye_offset_y)` with `eye_offset_x = r//3`, `eye_offset_y = r//3`
- No direction-based behavior

### Web (`web_client/src/renderer.ts` – `drawPlayer`)

- Eyes: white circles (`eyeRadius = max(4, size * 0.12)`)
- Pupils: black circles (`pupilRadius = max(1.5, size * 0.05)`)
- Direction-based offsets:
  - `eyeOffX = dx * (size * 0.16)`, `eyeOffY = dy * (size * 0.16)` – eye center offset when moving
  - Pupils offset further: `+ dx * 2`, `+ dy * 2` from each eye center
- `eyeGap = size * 0.18` – horizontal spacing between eyes
- Eye centers: `(px + eyeOffX ± eyeGap, py + eyeOffY - eyeGap * 0.7)`

## Size Mapping

- Web: `size = (PYTHON_CELL_SIZE * 0.85) * SCALE` ≈ `CELL_SIZE * PLAYER_DRAW_SCALE`
- Python: `r = player.draw_radius` = `CELL_SIZE * PLAYER_DRAW_SCALE / 2`
- So: `size = 2 * r`

## Implementation

### File to modify

- `bm_drawing.py` – `draw_players` (around lines 358–365)

### Changes

1. **Get direction**  
   Use `player.direction` (numpy array `[dx, dy]`). When stationary it is `[0, 0]`.

2. **Compute eye parameters** (mirror web formulas with `size = 2 * r`):
   - `eye_radius = max(4, int(r * 0.24))`  (web: `size * 0.12`)
   - `pupil_radius = max(1, int(r * 0.1))`  (web: `size * 0.05`)
   - `eye_gap = r * 0.36`  (web: `size * 0.18`)
   - `eye_offset_y = eye_gap * 0.7`  (vertical offset above center)

3. **Direction offsets** (from `player.direction`):
   - `eye_off_x = direction[0] * (r * 0.32)`  (web: `dx * (size * 0.16)`)
   - `eye_off_y = direction[1] * (r * 0.32)`
   - Pupil offset: `direction[0] * 2`, `direction[1] * 2` (in pixels, similar to web)

4. **Eye centers**:
   - Left: `(pos[0] + eye_off_x - eye_gap, pos[1] + eye_off_y - eye_offset_y)`
   - Right: `(pos[0] + eye_off_x + eye_gap, pos[1] + eye_off_y - eye_offset_y)`

5. **Drawing**:
   - Draw two white filled circles (or ellipses) at the eye centers with `eye_radius`
   - Draw two black filled circles for pupils at `(eye_center_x + dx*2, eye_center_y + dy*2)` with `pupil_radius`

6. **Handle avatar case**  
   Apply the same eye logic when an avatar is drawn (eyes on top of avatar).

### Code sketch (Python)

```python
# Get direction (0,0 when stationary)
dx = float(getattr(player, 'direction', [0, 0])[0])
dy = float(getattr(player, 'direction', [0, 0])[1])

# Eye parameters (match web: size = 2*r)
size = 2 * r
eye_radius = max(4, int(size * 0.12))
pupil_radius = max(1, int(size * 0.05))
eye_gap = size * 0.18
eye_offset_y = eye_gap * 0.7

eye_off_x = dx * (size * 0.16)
eye_off_y = dy * (size * 0.16)

# Left and right eye centers
left_cx = pos[0] + eye_off_x - eye_gap
right_cx = pos[0] + eye_off_x + eye_gap
eye_cy = pos[1] + eye_off_y - eye_offset_y

# White eyes
pygame.gfxdraw.filled_circle(surface, int(left_cx), int(eye_cy), eye_radius, (255, 255, 255))
pygame.gfxdraw.filled_circle(surface, int(right_cx), int(eye_cy), eye_radius, (255, 255, 255))
pygame.gfxdraw.aacircle(surface, int(left_cx), int(eye_cy), eye_radius, (255, 255, 255))
pygame.gfxdraw.aacircle(surface, int(right_cx), int(eye_cy), eye_radius, (255, 255, 255))

# Black pupils (offset in direction of movement)
pupil_off = 2  # pixels, matches web dx*2, dy*2
left_px = left_cx + dx * pupil_off
left_py = eye_cy + dy * pupil_off
right_px = right_cx + dx * pupil_off
right_py = eye_cy + dy * pupil_off
pygame.gfxdraw.filled_circle(surface, int(left_px), int(left_py), pupil_radius, (0, 0, 0))
pygame.gfxdraw.filled_circle(surface, int(right_px), int(right_py), pupil_radius, (0, 0, 0))
pygame.gfxdraw.aacircle(surface, int(left_px), int(left_py), pupil_radius, (0, 0, 0))
pygame.gfxdraw.aacircle(surface, int(right_px), int(right_py), pupil_radius, (0, 0, 0))
```

### Verification

- Stationary: eyes and pupils centered
- Moving: eyes and pupils shift in movement direction
- Visual match with web client for same player state

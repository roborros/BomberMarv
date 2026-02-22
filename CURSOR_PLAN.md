# BomberMarv — Pre-LAN Party Plan (March 7, 2026)

Use this as a task list. Each section is a self-contained change. Implement top-down by priority. Read ARCHITECTURE.md and PROTOCOL.md first for context.

---

## 🔴 P0 — Must Do Before LAN Party

### 1. Delete stale log file
Delete `ws_server.log.1` (~944MB). It's a leftover from before log rotation was configured.

### 2. Optimize wall collision (O(n²) → O(1) neighborhood check)
**File:** `bm_classes.py` → `Player.collides_with_walls()`

Current implementation iterates every cell in the entire grid (441 cells for 21×21). Fix:

```python
def collides_with_walls(self, board):
    # Only check 3x3 neighborhood around player's grid position
    center_x = int(self.pos[0] // CELL_SIZE)
    center_y = int(self.pos[1] // CELL_SIZE)
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            x = center_x + dx
            y = center_y + dy
            if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT:
                if board[y][x] in (INDESTRUCTIBLE, DESTRUCTIBLE):
                    wall_rect = np.array([x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE], dtype=np.float64)
                    if circle_rect_collision((self.pos[0], self.pos[1]), self.collision_radius, wall_rect):
                        return True
    return False
```

This reduces from ~441 checks to 9 checks per player per frame. With 6 players: 2,646 → 54.

### 3. Remove synchronous HTTP call from game loop
**File:** `bm_classes.py` → `Game._refresh_client_status()`

Currently makes `requests.get('http://localhost:8080/status')` synchronously in the main game loop with a 120ms timeout. This can cause frame hitches.

**Fix:** Instead of HTTP round-tripping to the WS server, share client/slot status through the existing multiprocessing queue infrastructure. Options:
- Add a second `multiprocessing.Queue` for status updates (server → host direction)
- Or use a `multiprocessing.Manager().dict()` as shared state
- Simplest: have the WS server push a status summary into the state_queue alongside game state (tag it with a different message type)

The key constraint: the WS server runs in a separate process (`multiprocessing.Process`), so you can't share Python objects directly — use queues or Manager.

### 4. Real LAN test checklist
Not a code task — but do this before March 7:
- [ ] Bring a 5-port gigabit Ethernet switch
- [ ] Test with 3+ web clients on WiFi simultaneously
- [ ] Test with host on Ethernet, clients on 5GHz WiFi
- [ ] Monitor `/metrics` and `/status` during test
- [ ] Check `broadcast_send_duration_samples_ms` p95 — should be <5ms
- [ ] Check `input_apply_p95_ms` — should be <20ms

---

## 🟡 P1 — High Impact, Do If Time Allows

### 5. Game statistics tracking
**Files:** `bm_classes.py` (Player class + Game.handle_explosions + Game.update)

Add these counters to `Player.__init__()`:
```python
self.walls_destroyed = 0
self.players_killed = 0
self.powerups_collected = 0
self.cells_walked = 0
self._last_grid_pos = None
```

**Where to increment:**
- `walls_destroyed`: In `Game.handle_explosions()`, when `self.board[y][x] == DESTRUCTIBLE` gets cleared, credit `bomb.owner.walls_destroyed += 1`. You need to track which bomb created each explosion — the `Explosion` class needs an `owner` field. Add it: `Explosion.__init__(..., owner=None)` and pass `bomb.owner` when creating explosions.
- `players_killed`: In the same method, when a player dies from an explosion, find which bomb's explosion killed them and credit the owner. Add `owner` to Explosion, then `explosion.owner.players_killed += 1` (skip self-kills or count them — your call).
- `powerups_collected`: In `Game.update()` where powerups are picked up, `player.powerups_collected += 1`.
- `cells_walked`: In `Player.update()`, after position update:
  ```python
  current_grid = self.get_grid_pos()
  if self._last_grid_pos is not None and current_grid != self._last_grid_pos:
      self.cells_walked += 1
  self._last_grid_pos = current_grid
  ```

**Reset in `Player.reset()`:** Reset `walls_destroyed`, `players_killed`, `powerups_collected`, `cells_walked`, `_last_grid_pos`.

**Display:** Update the win screen (`draw_stat_screen` in `bm_drawing.py`) to show a stats table for all players. Also serialize these in `Player.to_dict()` so the web client can show them too.

**Web client:** Update `types.ts` PlayerState interface and `renderer.ts` to render stats on the win screen.

### 6. Player photo avatars ("fotky vašich hlav")
**Concept:** Each player can upload a square image that replaces their colored circle.

**Web client lobby:**
- Add a file input next to the player name in the lobby
- On upload, read as base64, send via a new `set_avatar` message type to WS server
- Server stores in `clients[id]["avatar_base64"]`
- Server includes avatar data in status endpoint
- Include avatar base64 in player state broadcast (or better: send once on registration, cache on client)

**Web renderer (`renderer.ts`):**
- Cache loaded `Image` objects per player
- In `drawPlayers()`, if player has avatar, draw image in a circular clip instead of colored circle:
  ```typescript
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.clip();
  ctx.drawImage(avatarImg, x - radius, y - radius, radius * 2, radius * 2);
  ctx.restore();
  ```

**Pygame renderer (`bm_drawing.py`):**
- Load avatar images from a local folder (e.g., `img/avatars/player1.png`)
- Scale to player draw diameter, apply circular mask
- Blit instead of drawing colored circle

**Simpler alternative:** Skip upload, just pre-place photos in `img/avatars/` named by player name (e.g., `Tom.png`, `Marv.png`). Auto-detect at game start.

### 7. Sound & juice improvements
Quick wins for party atmosphere:

- **Lobby join sound:** Play a sound when a web client selects a slot. In `handle_client()` after `MSG_SELECT_SLOT` success, enqueue a "player_joined" event through the input queue. Handle in main loop by playing a sound.
- **Countdown sound:** In the "get_ready" state, play a beep each second. Use `self.current_time - self.game_start_time` to determine seconds remaining.
- **Screen shake on death:** In `draw_game_screen()`, when any player just died (death_animation_time > 0 and close to 1000), apply a random offset to the entire game surface blit position for ~200ms.
- **Big winner name:** On win screen, render the winner's name in the arcade font at 3x size, centered.

---

## 🟢 P2 — Post-LAN / When Bored

### 8. Extract Game class into focused modules
The `Game` class in `bm_classes.py` is ~1000+ lines doing everything. Extract:
- `lobby.py` — `handle_prep_key_event`, `create_players`, `get_all_players_info`, player/slot management
- `physics.py` — collision detection, movement, corner sliding
- `explosions.py` — `handle_explosions`, `get_explosion_cells`, chain detonation
- `powerups.py` — `place_quad_damage_powerup`, powerup collection logic
- `crushing_walls.py` — entire crushing walls feature
- `replay.py` — replay buffer, snapshot, segment management

Keep `Game` as the coordinator that delegates to these modules.

### 9. Fix wildcard imports from bm_params
`bm_params.py` loads pygame images at module level (`pygame.image.load()`). This means:
- Pygame must be initialized before any import
- Headless testing is impossible
- Any module doing `from bm_params import *` gets pygame globals in its namespace

**Fix:** Split into:
- `bm_constants.py` — pure values (CELL_SIZE, GRID_SIZE, colors, speeds, timers)
- `bm_assets.py` — image/sound loading (call explicitly after pygame init)

Then replace `from bm_params import *` with explicit imports from the appropriate module.

### 10. Binary state protocol
Current state broadcast is JSON. For 6 players + 21×27 board + entities, payloads can be 5-15KB per frame.

Options:
- **MessagePack:** Drop-in replacement, ~3x smaller, minimal code change. `pip install msgpack`, use `msgpack.packb()` instead of `json.dumps()`. Web client needs `@msgpack/msgpack` npm package.
- **Custom binary:** Board as flat Uint8Array, players as fixed-size structs. Maximum compression but more work.

Low priority — JSON works fine on LAN.

### 11. Team mode
From the poll. Design:
- 2v2, 3v3, or 2v2v2
- Teams share a color tint / outline
- Friendly fire toggle (on/off)
- Team score = sum of individual trophies
- Win condition: last team with alive player(s)

Implementation:
- Add `team` field to Player class (0, 1, 2)
- In explosion kill check: skip if `explosion.owner.team == player.team` and friendly fire is off
- Team assignment in lobby (new UI row per player)
- Win check: count alive teams instead of alive players

---

*Last updated: 2026-02-22*

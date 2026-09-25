export interface InputKeys {
  up: boolean
  down: boolean
  left: boolean
  right: boolean
  bomb: boolean
}

export function emptyKeys(): InputKeys {
  return { up: false, down: false, left: false, right: false, bomb: false }
}

export function hashInput(keys: InputKeys): string {
  return `${keys.up ? 1 : 0}${keys.down ? 1 : 0}${keys.left ? 1 : 0}${keys.right ? 1 : 0}${keys.bomb ? 1 : 0}`
}

export function applyKeyCode(keys: InputKeys, code: string, pressed: boolean): { keys: InputKeys; changed: boolean } {
  const next: InputKeys = { ...keys }
  let changed = false
  switch (code) {
    case 'ArrowUp':
    case 'KeyW':
      changed = next.up !== pressed
      next.up = pressed
      break
    case 'ArrowDown':
    case 'KeyS':
      changed = next.down !== pressed
      next.down = pressed
      break
    case 'ArrowLeft':
    case 'KeyA':
      changed = next.left !== pressed
      next.left = pressed
      break
    case 'ArrowRight':
    case 'KeyD':
      changed = next.right !== pressed
      next.right = pressed
      break
    case 'Space':
    case 'Enter':
      changed = next.bomb !== pressed
      next.bomb = pressed
      break
    default:
      break
  }
  return { keys: next, changed }
}

export function shouldSendInput(opts: {
  force: boolean
  now: number
  lastSentAt: number
  keysDirty: boolean
  hash: string
  lastHash: string
  minDeltaMs: number
  heartbeatMs: number
}): boolean {
  if (opts.force) return true
  if (opts.now - opts.lastSentAt < opts.minDeltaMs) return false
  const heartbeatDue = opts.now - opts.lastSentAt >= opts.heartbeatMs
  if (!opts.keysDirty && !heartbeatDue) return false
  if (opts.hash === opts.lastHash && !heartbeatDue) return false
  return true
}

export function resolveInputTickId(hostTick: number | undefined, localTick: number): number {
  return typeof hostTick === 'number' ? hostTick : localTick
}

export function buildGameInputPayload(opts: {
  protocol: number
  clientId: number
  playerId: number
  keys: InputKeys
  tickId: number
  timestamp: number
}): {
  type: 'game_input'
  protocol: number
  tick_id: number
  input: number[]
  input_frame: { player_id: number; up: number; down: number; left: number; right: number; bomb: number }
  client_timestamp: number
} {
  const up = opts.keys.up ? 1 : 0
  const down = opts.keys.down ? 1 : 0
  const left = opts.keys.left ? 1 : 0
  const right = opts.keys.right ? 1 : 0
  const bomb = opts.keys.bomb ? 1 : 0
  return {
    type: 'game_input',
    protocol: opts.protocol,
    tick_id: opts.tickId,
    input: [opts.clientId, opts.playerId, up, down, left, right, bomb],
    input_frame: {
      player_id: opts.playerId,
      up,
      down,
      left,
      right,
      bomb
    },
    client_timestamp: opts.timestamp
  }
}

export function inputDirection(keys: InputKeys): { dx: number; dy: number; active: boolean } {
  let dx = 0
  let dy = 0
  if (keys.up) dy -= 1
  if (keys.down) dy += 1
  if (keys.left) dx -= 1
  if (keys.right) dx += 1
  const length = Math.hypot(dx, dy)
  if (length > 1e-6) {
    dx /= length
    dy /= length
  }
  return { dx, dy, active: length > 1e-6 }
}

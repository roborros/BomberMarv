import type { ExplosionState, GameState, PlayerState } from './types'

export const BIG_EXPLOSION_TILE_THRESHOLD = 125
export const BIG_EXPLOSION_WINDOW_MS = 700
export const BIG_EXPLOSION_VOLUME = 1
export const BIG_EXPLOSION_COOLDOWN_MS = 5000
export const BIG_EXPLOSION_SOUND_COUNT = 5

export type AudioCue = 'explosion' | 'explosion_qd' | 'death' | 'qd' | 'bonus' | 'big_explosion'

export function explosionEventKey(explosion: Pick<ExplosionState, 'start_time' | 'cells' | 'quad_damage'>): string | null {
  const c = explosion.cells[0]
  if (!c) return null
  return `${explosion.start_time}:${c[0]}:${c[1]}:${explosion.quad_damage ? 1 : 0}`
}

export function collectNewExplosionKeys(
  explosions: ExplosionState[],
  knownKeys: Set<string>
): { keys: Set<string>; newlySeen: { startTime: number; cells: [number, number][]; quadDamage: boolean }[] } {
  const keys = new Set<string>()
  const newlySeen: { startTime: number; cells: [number, number][]; quadDamage: boolean }[] = []
  for (const e of explosions) {
    const key = explosionEventKey(e)
    if (!key) continue
    keys.add(key)
    if (!knownKeys.has(key)) {
      newlySeen.push({ startTime: e.start_time, cells: e.cells, quadDamage: e.quad_damage })
    }
  }
  return { keys, newlySeen }
}

export function uniqueTilesInWindow(
  events: { startTime: number; cells: [number, number][] }[],
  currentTime: number,
  windowMs = BIG_EXPLOSION_WINDOW_MS
): number {
  const cutoff = currentTime - windowMs
  const tiles = new Set<string>()
  for (const ev of events) {
    if (ev.startTime < cutoff) continue
    for (const [x, y] of ev.cells) tiles.add(`${x}:${y}`)
  }
  return tiles.size
}

export function bigExplosionReady(lastTriggerMs: number | null | undefined, nowMs: number, cooldownMs = BIG_EXPLOSION_COOLDOWN_MS): boolean {
  if (lastTriggerMs == null) return true
  return nowMs - lastTriggerMs >= cooldownMs
}

export function bigExplosionSoundIndex(roll: number, count = BIG_EXPLOSION_SOUND_COUNT): number {
  const index = Math.floor(roll * count)
  if (index < 0) return 0
  if (index >= count) return count - 1
  return index
}

export function formatMatchClock(elapsedMs: number): string {
  return String(Math.max(0, Math.floor(elapsedMs / 1000)))
}

export function formatCrushingWallStart(earlyS?: number, lateS?: number, active = false): string {
  if (active || earlyS == null || lateS == null) return ''
  return `(cw start: ${earlyS}s/${lateS}s)`
}

export function crossedBigExplosionThreshold(wasOver: boolean, tileCount: number, threshold = BIG_EXPLOSION_TILE_THRESHOLD): boolean {
  return (!wasOver) && tileCount >= threshold
}

export function collectPlayerAudioCues(previous: PlayerState, current: PlayerState): AudioCue[] {
  const cues: AudioCue[] = []
  if (previous.alive && !current.alive) cues.push('death')
  if (!previous.quad_damage && current.quad_damage) cues.push('qd')
  const prevFire = previous.fire_power ?? 0
  const prevBomb = previous.bomb_capacity ?? 0
  const nextFire = current.fire_power ?? prevFire
  const nextBomb = current.bomb_capacity ?? prevBomb
  if (nextFire > prevFire || nextBomb > prevBomb) cues.push('bonus')
  return cues
}

export function collectGameAudioCues(previous: GameState | null, current: GameState): AudioCue[] {
  if (!previous) return []
  const cues: AudioCue[] = []
  const prevPlayers = new Map(previous.players.map((p) => [p.id, p]))
  for (const p of current.players) {
    const prev = prevPlayers.get(p.id)
    if (!prev) continue
    cues.push(...collectPlayerAudioCues(prev, p))
  }
  return cues
}

export function shouldResetBigExplosionTracking(state: string): boolean {
  return state === 'get_ready' || state === 'game_prep' || state === 'startup'
}

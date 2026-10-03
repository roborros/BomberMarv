import { describe, expect, it } from 'vitest'
import {
  collectGameAudioCues,
  collectNewExplosionKeys,
  collectPlayerAudioCues,
  crossedBigExplosionThreshold,
  explosionEventKey,
  shouldResetBigExplosionTracking,
  uniqueTilesInWindow,
  BIG_EXPLOSION_COOLDOWN_MS,
  BIG_EXPLOSION_TILE_THRESHOLD,
  BIG_EXPLOSION_VOLUME,
  bigExplosionReady,
  bigExplosionSoundIndex,
  formatCrushingWallStart,
  formatMatchClock
} from './audioEvents'
import { samplePlayer, sampleState } from './testFixtures'

describe('audioEvents', () => {
  it('keys explosions by origin cell and style', () => {
    expect(explosionEventKey({ start_time: 10, cells: [[3, 4]], quad_damage: true })).toBe('10:3:4:1')
    expect(explosionEventKey({ start_time: 10, cells: [], quad_damage: false })).toBeNull()
  })

  it('detects newly seen explosions', () => {
    const known = new Set(['1:0:0:0'])
    const { newlySeen, keys } = collectNewExplosionKeys(
      [
        { start_time: 1, cells: [[0, 0]], quad_damage: false },
        { start_time: 2, cells: [[1, 1]], quad_damage: true }
      ],
      known
    )
    expect(newlySeen).toHaveLength(1)
    expect(newlySeen[0].quadDamage).toBe(true)
    expect(keys.size).toBe(2)
  })

  it('counts unique tiles inside the window', () => {
    const events = [
      { startTime: 0, cells: [[0, 0], [1, 0]] as [number, number][] },
      { startTime: 900, cells: [[1, 0], [2, 0]] as [number, number][] }
    ]
    expect(uniqueTilesInWindow(events, 1000, 200)).toBe(2)
    expect(uniqueTilesInWindow(events, 1000, 1000)).toBe(3)
  })

  it('crosses the big-explosion threshold once', () => {
    expect(BIG_EXPLOSION_TILE_THRESHOLD).toBe(125)
    expect(BIG_EXPLOSION_VOLUME).toBe(1)
    expect(crossedBigExplosionThreshold(false, BIG_EXPLOSION_TILE_THRESHOLD)).toBe(true)
    expect(crossedBigExplosionThreshold(false, BIG_EXPLOSION_TILE_THRESHOLD - 1)).toBe(false)
    expect(crossedBigExplosionThreshold(true, BIG_EXPLOSION_TILE_THRESHOLD + 10)).toBe(false)
  })

  it('emits player audio cues for death, QD, and pickups', () => {
    const prev = samplePlayer({ alive: true, quad_damage: false, fire_power: 1, bomb_capacity: 1 })
    expect(collectPlayerAudioCues(prev, { ...prev, alive: false })).toEqual(['death'])
    expect(collectPlayerAudioCues(prev, { ...prev, quad_damage: true })).toEqual(['qd'])
    expect(collectPlayerAudioCues(prev, { ...prev, fire_power: 2 })).toEqual(['bonus'])
  })

  it('collects cues across a snapshot pair', () => {
    const previous = sampleState({ players: [samplePlayer({ id: 1, alive: true })] })
    const current = sampleState({ players: [samplePlayer({ id: 1, alive: false })] })
    expect(collectGameAudioCues(previous, current)).toEqual(['death'])
    expect(collectGameAudioCues(null, current)).toEqual([])
  })

  it('resets tracking in lobby states', () => {
    expect(shouldResetBigExplosionTracking('game_prep')).toBe(true)
    expect(shouldResetBigExplosionTracking('playing')).toBe(false)
  })

  it('holds the loud hit for five seconds and rolls one of five sounds', () => {
    expect(BIG_EXPLOSION_COOLDOWN_MS).toBe(5000)
    expect(bigExplosionReady(null, 1000)).toBe(true)
    expect(bigExplosionReady(1000, 5999)).toBe(false)
    expect(bigExplosionReady(1000, 6000)).toBe(true)
    expect(bigExplosionSoundIndex(0)).toBe(0)
    expect(bigExplosionSoundIndex(0.99)).toBe(4)
    expect(formatMatchClock(65000)).toBe('65')
    expect(formatCrushingWallStart(180, 360)).toBe('(cw start: 180s/360s)')
    expect(formatCrushingWallStart(180, 360, true)).toBe('')
  })
})

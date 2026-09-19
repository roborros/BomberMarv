import { describe, expect, it } from 'vitest'
import { BOSS_NAME, BOSS_QUOTE, bossWinsLabel, championAnnouncement } from './championChallenge'

describe('championChallenge', () => {
  it('announces the winning player', () => {
    expect(championAnnouncement('Marv')).toBe('Marv is the Champion!')
  })

  it('names BomberMarv as the boss', () => {
    expect(BOSS_NAME).toBe('BomberMarv')
    expect(BOSS_QUOTE).toContain('worthy challenger')
    expect(bossWinsLabel(true)).toBe('BomberMarv wins!')
    expect(bossWinsLabel(false, 'Marv')).toBe('Marv wins!')
    expect(bossWinsLabel(false)).toBe('Draw!')
  })
})

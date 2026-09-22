import { describe, expect, it } from 'vitest'
import { BOSS_NAME, BOSS_QUOTE, bossWinsLabel, championAnnouncement, championBossCardRect } from './championChallenge'

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

  it('puts the BomberMarv card in the top-right corner', () => {
    const card = championBossCardRect(1280, 720)
    expect(card.x).toBeGreaterThan(1280 * 0.7)
    expect(card.y).toBeLessThan(40)
    expect(card.w).toBeLessThan(280)
    expect(card.h).toBeGreaterThanOrEqual(140)
    expect(card.x + card.w).toBeLessThanOrEqual(1280)
  })
})

import { describe, expect, it } from 'vitest'
import { BOSS_NAME, BOSS_QUOTE, BOMBER_TOM_NAME, BOMBER_TOM_QUOTE, MARV_KILLER_TITLE, bossResultTitle, bossWinsLabel, championAnnouncement, championBossCardRect, inviteQuoteLines, isMarvKillerWin, showsBomberTomInvite } from './championChallenge'

describe('championChallenge', () => {
  it('announces the winning player', () => {
    expect(championAnnouncement('Marv')).toBe('Marv is the Champion!')
  })

  it('names BomberMarv as the boss', () => {
    expect(BOSS_NAME).toBe('BomberMarv')
    expect(BOSS_QUOTE).toContain('worthy challenger')
    expect(bossWinsLabel(true)).toBe('BomberMarv wins!')
    expect(bossWinsLabel(true, 'BomberTom')).toBe('BomberTom wins!')
    expect(bossWinsLabel(false, 'Marv')).toBe('Marv wins!')
    expect(bossWinsLabel(false)).toBe('Draw!')
    expect(bossResultTitle(true, false)).toBe('You win')
    expect(bossResultTitle(true, true)).toBe('You lose')
    expect(bossResultTitle(false, false)).toBe('Draw')
    expect(BOMBER_TOM_NAME).toBe('BomberTom')
    expect(BOMBER_TOM_QUOTE).toContain('butcher')
    expect(inviteQuoteLines(BOMBER_TOM_QUOTE)).toEqual(['"The butcher was practice,', 'now you face me."'])
    expect(showsBomberTomInvite('Enter: fight BomberTom')).toBe(true)
    expect(showsBomberTomInvite('Enter: back to the lobby')).toBe(false)
    expect(MARV_KILLER_TITLE).toBe('MarvKiller')
    expect(isMarvKillerWin('MarvKiller')).toBe(true)
    expect(isMarvKillerWin('')).toBe(false)
  })

  it('puts the BomberMarv card in the top-right corner', () => {
    const card = championBossCardRect(1280, 720)
    expect(card.y).toBeLessThan(40)
    expect(card.w).toBeGreaterThan(400)
    expect(card.h).toBeGreaterThan(300)
    expect(card.x + card.w).toBeLessThanOrEqual(1280)
    expect(card.x).toBeGreaterThan(1280 * 0.5)
  })
})

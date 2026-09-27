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
    expect(BOMBER_TOM_QUOTE).toBe('Oh you got BomberMarv?! You thought this is the end??? You you will pay for this!')
    expect(inviteQuoteLines(BOMBER_TOM_QUOTE)).toEqual([
      '"Oh you got BomberMarv?!',
      'You thought this is the end???',
      'You you will pay for this!"',
    ])
    expect(inviteQuoteLines(BOSS_QUOTE)).toEqual(['"Finally a worthy challenger,', 'come and fight me!"'])
    expect(showsBomberTomInvite('Enter: fight BomberTom')).toBe(true)
    expect(showsBomberTomInvite('Enter: back to the lobby')).toBe(false)
    expect(MARV_KILLER_TITLE).toBe('MarvKiller')
    expect(isMarvKillerWin('MarvKiller')).toBe(true)
    expect(isMarvKillerWin('')).toBe(false)
  })

  it('puts the BomberMarv card in the top-right corner', () => {
    const card = championBossCardRect(1280, 720)
    expect(card.y).toBeLessThan(40)
    expect(card.y + card.h).toBeLessThan(Math.floor(720 * 0.34))
    expect(card.w).toBeGreaterThan(450)
    expect(card.w).toBeLessThan(560)
    expect(card.h).toBeGreaterThan(180)
    expect(card.x + card.w).toBeLessThanOrEqual(1280)
    expect(card.x).toBeGreaterThan(1280 * 0.5)
    const panelTop = 720 - Math.floor(720 * 0.52) - 10
    expect(card.y + card.h).toBeLessThan(panelTop)
    const phone = championBossCardRect(390, 700)
    expect(phone.y + phone.h).toBeLessThan(Math.floor(700 * 0.34))
    expect(phone.y + phone.h).toBeLessThan(700 - Math.floor(700 * 0.52) - 10)
  })
})

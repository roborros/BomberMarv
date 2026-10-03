import { describe, expect, it } from 'vitest'
import { KEY_GUIDE_ROWS, READY_KEY_LINES, keyGuideAction } from './keysGuide'

describe('keys guide', () => {
  it('shows the main local and browser keys before a round', () => {
    expect(READY_KEY_LINES).toEqual([
      'Local   W A S D or arrows move   ·   Space bomb',
      'Browser   W A S D or arrows move   ·   Space bomb',
    ])
  })

  it('lists every local seat plus browser bomb keys', () => {
    expect(KEY_GUIDE_ROWS[0]).toEqual({ who: 'Player 1', move: 'W A S D or arrows', bomb: 'Space' })
    expect(KEY_GUIDE_ROWS[2]).toEqual({ who: 'Player 3', move: 'F C V B', bomb: 'H' })
    expect(KEY_GUIDE_ROWS.map((row) => row.who).slice(0, 6)).toEqual([
      'Player 1', 'Player 2', 'Player 3', 'Player 4', 'Player 5', 'Player 6',
    ])
    const browser = KEY_GUIDE_ROWS.find((row) => row.who === 'Browser')
    expect(browser).toEqual({ who: 'Browser', move: 'Arrow keys or W A S D', bomb: 'Space or Enter' })
    expect(keyGuideAction(KEY_GUIDE_ROWS[0])).toBe('W A S D or arrows    ·    bomb Space')
    expect(keyGuideAction({ who: 'F11', move: 'Fullscreen', bomb: '' })).toBe('Fullscreen')
  })
})

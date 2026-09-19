import { describe, expect, it } from 'vitest'
import { buildWinStatRows, series } from './winStats'
import { samplePlayer } from './testFixtures'

describe('winStats', () => {
  it('adds round and total series', () => {
    expect(series(4, 2)).toBe(6)
    expect(series(undefined, 3)).toBe(3)
  })

  it('bolds the best death time and kill count', () => {
    const rows = buildWinStatRows([
      samplePlayer({
        id: 1,
        name: 'Marv',
        death_time_rel_ms: 8000,
        players_killed: 1,
        total_players_killed: 2
      }),
      samplePlayer({
        id: 2,
        name: 'Sobi',
        death_time_rel_ms: 12000,
        players_killed: 0,
        total_players_killed: 0,
        fire_power_at_death: 5
      })
    ])
    expect(rows[0].kills).toBe('3')
    expect(rows[0].bold.kills).toBe(true)
    expect(rows[1].death).toBe('12')
    expect(rows[1].bold.death).toBe(true)
    expect(rows[1].bold.flames).toBe(true)
  })

  it('uses a dash for survivors', () => {
    const rows = buildWinStatRows([samplePlayer({ death_time_rel_ms: null })])
    expect(rows[0].death).toBe('—')
    expect(rows[0].deathColor).toContain('160, 255, 160')
  })
})

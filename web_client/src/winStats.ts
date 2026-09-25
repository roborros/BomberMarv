import type { PlayerState } from './types'

export function series(totalVal?: number, roundVal?: number): number {
  return (totalVal ?? 0) + (roundVal ?? 0)
}

export interface WinStatRow {
  name: string
  color: [number, number, number]
  trophies: number
  death: string
  deathColor: string
  flames: string
  bombs: string
  kills: string
  walls: string
  pups: string
  qds: string
  walked: string
  bold: Record<string, boolean>
}

export function buildWinStatRows(players: PlayerState[]): WinStatRow[] {
  const sliced = players.slice(0, 8)
  const deathVals = sliced.map((p) => (p.death_time_rel_ms == null ? 999999 : Math.round(p.death_time_rel_ms / 1000)))
  const flamesVals = sliced.map((p) => p.fire_power_at_death ?? p.fire_power ?? 0)
  const bombsVals = sliced.map((p) => p.bomb_capacity_at_death ?? p.bomb_capacity ?? 0)
  const killsVals = sliced.map((p) => series(p.total_players_killed, p.players_killed))
  const wallsVals = sliced.map((p) => series(p.total_walls_destroyed, p.walls_destroyed))
  const pupsVals = sliced.map((p) => series(p.total_powerups_collected, p.powerups_collected))
  const qdsVals = sliced.map((p) => series(p.total_quad_damage_collected, p.quad_damage_collected))
  const walkedVals = sliced.map((p) => series(p.total_cells_walked, p.cells_walked))
  const maxDeath = Math.max(0, ...deathVals)
  const maxFlames = Math.max(0, ...flamesVals)
  const maxBombs = Math.max(0, ...bombsVals)
  const maxKills = Math.max(0, ...killsVals)
  const maxWalls = Math.max(0, ...wallsVals)
  const maxPups = Math.max(0, ...pupsVals)
  const maxQds = Math.max(0, ...qdsVals)
  const maxWalked = Math.max(0, ...walkedVals)
  return sliced.map((p, i) => ({
    name: p.name || `P${p.id}`,
    color: p.color,
    trophies: p.trophies ?? 0,
    death: p.death_time_rel_ms == null ? '—' : String(Math.round(p.death_time_rel_ms / 1000)),
    deathColor: p.death_time_rel_ms == null ? 'rgb(160, 255, 160)' : 'rgb(255, 160, 160)',
    flames: String(flamesVals[i]),
    bombs: String(bombsVals[i]),
    kills: String(killsVals[i]),
    walls: String(wallsVals[i]),
    pups: String(pupsVals[i]),
    qds: String(qdsVals[i]),
    walked: String(walkedVals[i]),
    bold: {
      death: deathVals[i] === maxDeath && maxDeath > 0,
      flames: flamesVals[i] === maxFlames && maxFlames > 0,
      bombs: bombsVals[i] === maxBombs && maxBombs > 0,
      kills: killsVals[i] === maxKills && maxKills > 0,
      walls: wallsVals[i] === maxWalls && maxWalls > 0,
      pups: pupsVals[i] === maxPups && maxPups > 0,
      qds: qdsVals[i] === maxQds && maxQds > 0,
      walked: walkedVals[i] === maxWalked && maxWalked > 0
    }
  }))
}

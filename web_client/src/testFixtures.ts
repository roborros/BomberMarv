import type { GameState, PlayerState } from './types'

export function samplePlayer(overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    id: 1,
    name: 'Marv',
    x: 150,
    y: 150,
    color: [100, 150, 200],
    alive: true,
    direction: [0, 0],
    quad_damage: false,
    death_anim_time: null,
    fire_power: 1,
    bomb_capacity: 1,
    ...overrides
  }
}

export function sampleState(overrides: Partial<GameState> = {}): GameState {
  return {
    time: 1000,
    state: 'playing',
    board: [
      [1, 1, 1],
      [1, 0, 1],
      [1, 1, 1]
    ],
    players: [samplePlayer()],
    bombs: [],
    explosions: [],
    powerups: [],
    crushing_walls: { active: false, index: 0 },
    ...overrides
  }
}

import { describe, expect, it } from 'vitest'
import { explosionArmFactor, getExplosionActiveCells, isPlayerNearBomb, isPlayerNearExplosion } from './explosionVisual'

describe('explosionVisual', () => {
  const explosion = {
    start_time: 0,
    cells: [[2, 2], [2, 1], [2, 0], [2, 3], [1, 2], [3, 2]] as [number, number][],
    quad_damage: false
  }

  it('keeps only the center while arms have not grown', () => {
    expect(getExplosionActiveCells(explosion, 0)).toEqual([])
    expect(getExplosionActiveCells(explosion, 1)).toEqual([[2, 2]])
    expect(explosionArmFactor(0, 0)).toBe(0)
  })

  it('fully extends arms in the middle of the animation', () => {
    const cells = getExplosionActiveCells(explosion, 200)
    expect(cells).toContainEqual([2, 0])
    expect(cells).toContainEqual([3, 2])
    expect(explosionArmFactor(0, 200)).toBe(1)
  })

  it('collapses when the animation ends', () => {
    expect(getExplosionActiveCells(explosion, 400)).toEqual([])
  })

  it('detects adjacent bombs and explosions', () => {
    const player = { x: 250, y: 250 }
    expect(isPlayerNearBomb(player, [{ x: 3, y: 2, start_time: 0, fire_power: 1, quad_damage: false }])).toBe(true)
    expect(isPlayerNearBomb(player, [{ x: 8, y: 8, start_time: 0, fire_power: 1, quad_damage: false }])).toBe(false)
    expect(isPlayerNearExplosion(player, [explosion], 200)).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import { explosionArmFactor, explosionArmPixelLength, getExplosionActiveCells, isPlayerInPlannedBlast, plannedBlastCells } from './explosionVisual'

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

  it('paints the flame to the last cell center', () => {
    const flame = explosionArmPixelLength(1, 3, 100)
    expect(flame).toBe(300)
    expect(explosionArmPixelLength(1, 0)).toBe(0)
  })

  it('collapses when the animation ends', () => {
    expect(getExplosionActiveCells(explosion, 400)).toEqual([])
  })

  it('planned blast stops at walls and caps scared range at 5', () => {
    const board = Array.from({ length: 11 }, () => Array(11).fill(0))
    board[2][6] = 1
    const cells = plannedBlastCells(2, 2, 8, board, 5)
    expect(cells).toContainEqual([2, 2])
    expect(cells).toContainEqual([5, 2])
    expect(cells).not.toContainEqual([6, 2])
    expect(cells).not.toContainEqual([7, 2])
  })

  it('scares only players standing on a planned blast cell', () => {
    const board = Array.from({ length: 9 }, () => Array(9).fill(0))
    const bombs = [{ x: 3, y: 3, start_time: 0, fire_power: 2, quad_damage: false }]
    expect(isPlayerInPlannedBlast({ x: 350, y: 350 }, bombs, board)).toBe(true)
    expect(isPlayerInPlannedBlast({ x: 550, y: 350 }, bombs, board)).toBe(true)
    expect(isPlayerInPlannedBlast({ x: 450, y: 450 }, bombs, board)).toBe(false)
    expect(isPlayerInPlannedBlast({ x: 850, y: 350 }, bombs, board)).toBe(false)
  })
})

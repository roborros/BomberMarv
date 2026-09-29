import { describe, expect, it } from 'vitest'
import {
  blastArmDirection,
  blastArmSpriteOffset,
  explosionArmFactor,
  explosionArmPixelLength,
  explosionDurationMs,
  getExplosionActiveCells,
  isPlayerInPlannedBlast,
  paintBlastArm,
  plannedBlastCells,
  type BlastArmContext,
} from './explosionVisual'

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

  it('uses the host blast duration when the snapshot provides one', () => {
    expect(explosionDurationMs(undefined)).toBe(400)
    expect(explosionDurationMs(0)).toBe(400)
    expect(explosionDurationMs(900)).toBe(900)
    expect(explosionArmFactor(0, 450, 900)).toBe(1)
  })
})

describe('blast arm direction', () => {
  const directions = [
    ['right', 1, 0, 240, 0],
    ['left', -1, 0, -240, 0],
    ['down', 0, 1, 0, 240],
    ['up', 0, -1, 0, -240],
  ] as const

  it('keeps the bulky base on the center and the tip outward', () => {
    for (const [name, dx, dy, tipX, tipY] of directions) {
      expect(blastArmDirection(dx, dy)).toBe(name)
      const base = blastArmSpriteOffset(name, 240, 1)
      const tip = blastArmSpriteOffset(name, 240, 0)
      expect(Math.hypot(base.x, base.y)).toBeLessThan(0.001)
      expect(tip.x).toBeCloseTo(tipX, 4)
      expect(tip.y).toBeCloseTo(tipY, 4)
    }
  })

  it('paints every arm with the same length flip', () => {
    const image = {} as CanvasImageSource
    for (const [, dx, dy] of directions) {
      const ops: string[] = []
      const ctx: BlastArmContext = {
        save: () => ops.push('save'),
        restore: () => ops.push('restore'),
        translate: () => ops.push('translate'),
        rotate: () => ops.push('rotate'),
        scale: (x, y) => ops.push(`scale ${x} ${y}`),
        drawImage: (_image, x, y, w, h) => ops.push(`draw ${x} ${y} ${w} ${h}`),
      }
      paintBlastArm(ctx, image, 10, 20, dx, dy, 180.8, 90)
      expect(ops).toContain('scale -1 1')
      expect(ops).toContain('draw -180 -45 180 90')
      expect(ops.at(-1)).toBe('restore')
    }
  })
})

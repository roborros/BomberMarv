import type { BombState, ExplosionState, PlayerState } from './types'

export const EXPLOSION_DURATION_MS = 400
export const CELL_SIZE = 100

export function explosionArmFactor(startTime: number, currentTimeMs: number, durationMs = EXPLOSION_DURATION_MS): number {
  const norm = Math.min(1, Math.max(0, (currentTimeMs - startTime) / durationMs))
  if (norm < 0.2) return norm / 0.2
  if (norm <= 0.7) return 1
  return Math.max(0, 1 - ((norm - 0.7) / 0.3))
}

export function getExplosionActiveCells(
  explosion: Pick<ExplosionState, 'cells' | 'start_time'>,
  currentTimeMs: number,
  durationMs = EXPLOSION_DURATION_MS
): [number, number][] {
  const armFactor = explosionArmFactor(explosion.start_time, currentTimeMs, durationMs)
  if (armFactor <= 0 || !explosion.cells?.length) return []
  const [cx, cy] = explosion.cells[0]
  const cells: [number, number][] = [[cx, cy]]
  let upMax = 0
  let downMax = 0
  let leftMax = 0
  let rightMax = 0
  for (const [x, y] of explosion.cells) {
    if (x === cx && y < cy) upMax = Math.max(upMax, cy - y)
    else if (x === cx && y > cy) downMax = Math.max(downMax, y - cy)
    else if (y === cy && x < cx) leftMax = Math.max(leftMax, cx - x)
    else if (y === cy && x > cx) rightMax = Math.max(rightMax, x - cx)
  }
  for (let i = 1; i <= Math.floor(armFactor * upMax); i++) cells.push([cx, cy - i])
  for (let i = 1; i <= Math.floor(armFactor * downMax); i++) cells.push([cx, cy + i])
  for (let i = 1; i <= Math.floor(armFactor * leftMax); i++) cells.push([cx - i, cy])
  for (let i = 1; i <= Math.floor(armFactor * rightMax); i++) cells.push([cx + i, cy])
  return cells
}

export function isAdjacentCell(ax: number, ay: number, bx: number, by: number): boolean {
  return Math.abs(ax - bx) <= 1 && Math.abs(ay - by) <= 1
}

export function isPlayerNearExplosion(
  player: Pick<PlayerState, 'x' | 'y'>,
  explosions: ExplosionState[],
  currentTimeMs: number
): boolean {
  const px = Math.floor(player.x / CELL_SIZE)
  const py = Math.floor(player.y / CELL_SIZE)
  for (const explosion of explosions) {
    for (const [ex, ey] of getExplosionActiveCells(explosion, currentTimeMs)) {
      if (isAdjacentCell(px, py, ex, ey)) return true
    }
  }
  return false
}

export function isPlayerNearBomb(player: Pick<PlayerState, 'x' | 'y'>, bombs: BombState[]): boolean {
  const px = Math.floor(player.x / CELL_SIZE)
  const py = Math.floor(player.y / CELL_SIZE)
  for (const bomb of bombs) {
    if (isAdjacentCell(px, py, bomb.x, bomb.y)) return true
  }
  return false
}

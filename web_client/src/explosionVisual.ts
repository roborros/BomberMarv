import type { BombState, ExplosionState, PlayerState } from './types'

export const EXPLOSION_DURATION_MS = 400
export const CELL_SIZE = 100

export function explosionArmPixelLength(armFactor: number, cellReach: number, cellSize = CELL_SIZE): number {
  if (cellReach <= 0 || armFactor <= 0) return 0
  return armFactor * Math.floor(cellReach) * cellSize
}

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

export const SCARED_BLAST_MAX_CELLS = 5
export const TILE_EMPTY = 0
export const TILE_INDESTRUCTIBLE = 1
export const TILE_DESTRUCTIBLE = 2

export function isAdjacentCell(ax: number, ay: number, bx: number, by: number): boolean {
  return Math.abs(ax - bx) <= 1 && Math.abs(ay - by) <= 1
}

export function plannedBlastCells(
  bombX: number,
  bombY: number,
  firePower: number,
  board: number[][],
  maxRange = SCARED_BLAST_MAX_CELLS
): [number, number][] {
  const height = board.length
  const width = board[0]?.length ?? 0
  const reach = Math.max(0, Math.min(Math.floor(firePower), Math.floor(maxRange)))
  const cells: [number, number][] = [[bombX, bombY]]
  const dirs: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1]]
  for (const [dx, dy] of dirs) {
    for (let step = 1; step <= reach; step++) {
      const nx = bombX + dx * step
      const ny = bombY + dy * step
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) break
      const tile = board[ny][nx]
      if (tile === TILE_INDESTRUCTIBLE) break
      cells.push([nx, ny])
      if (tile === TILE_DESTRUCTIBLE) break
    }
  }
  return cells
}

export function isPlayerInPlannedBlast(
  player: Pick<PlayerState, 'x' | 'y'>,
  bombs: BombState[],
  board: number[][],
  maxRange = SCARED_BLAST_MAX_CELLS
): boolean {
  const px = Math.floor(player.x / CELL_SIZE)
  const py = Math.floor(player.y / CELL_SIZE)
  for (const bomb of bombs) {
    const cells = plannedBlastCells(bomb.x, bomb.y, bomb.fire_power, board, maxRange)
    if (cells.some(([x, y]) => x === px && y === py)) return true
  }
  return false
}

export const BOSS_NAME = 'BomberMarv'
export const BOSS_COLOR: [number, number, number] = [56, 56, 62]
export const BOSS_QUOTE = 'Finally a worthy challenger, come and fight me!'
export const BOSS_CHALLENGE_HINT = 'Press Enter to fight'

export function championAnnouncement(name: string): string {
  return `${name} is the Champion!`
}

export function championBossCardRect(width: number, height: number): { x: number; y: number; w: number; h: number } {
  const margin = Math.max(14, Math.floor(Math.min(width, height) * 0.02))
  const w = Math.min(236, Math.max(156, Math.floor(width * 0.18)))
  const h = Math.min(220, Math.max(140, Math.floor(height * 0.26)))
  return { x: width - margin - w, y: margin, w, h }
}

export function bossWinsLabel(winnerIsAi: boolean, winnerName?: string | null): string {
  if (winnerIsAi) return `${BOSS_NAME} wins!`
  if (winnerName) return `${winnerName} wins!`
  return 'Draw!'
}

export const BOSS_NAME = 'BomberMarv'
export const BOSS_COLOR: [number, number, number] = [56, 56, 62]
export const BOSS_QUOTE = 'Finally a worthy challenger, come and fight me!'
export const BOSS_CHALLENGE_HINT = 'Press Enter to fight'

export function championAnnouncement(name: string): string {
  return `${name} is the Champion!`
}

export function bossWinsLabel(winnerIsAi: boolean, winnerName?: string | null): string {
  if (winnerIsAi) return `${BOSS_NAME} wins!`
  if (winnerName) return `${winnerName} wins!`
  return 'Draw!'
}

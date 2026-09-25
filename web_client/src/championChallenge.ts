export const BOSS_NAME = 'BomberMarv'
export const BOSS_COLOR: [number, number, number] = [56, 56, 62]
export const BOSS_QUOTE = 'Finally a worthy challenger, come and fight me!'
export const BOSS_CHALLENGE_HINT = 'Press Enter to fight'
export const BOMBER_TOM_NAME = 'BomberTom'
export const BOMBER_TOM_COLOR: [number, number, number] = [36, 200, 84]
export const BOMBER_TOM_QUOTE = 'The butcher was practice, now you face me.'
export const MARV_KILLER_TITLE = 'MarvKiller'

export function showsBomberTomInvite(prompt?: string | null): boolean {
  return !!prompt && prompt.toLowerCase().includes('bombertom')
}

export function isMarvKillerWin(title?: string | null): boolean {
  return title === MARV_KILLER_TITLE
}

export function inviteQuoteLines(quote: string): string[] {
  const parts = quote.split(', ')
  if (parts.length === 2) return [`"${parts[0]},`, `${parts[1]}"`]
  return [`"${quote}"`]
}

export function championAnnouncement(name: string): string {
  return `${name} is the Champion!`
}

export function championBossCardRect(width: number, height: number): { x: number; y: number; w: number; h: number } {
  const margin = Math.max(14, Math.floor(Math.min(width, height) * 0.02))
  const w = Math.min(472, Math.max(312, Math.floor(width * 0.36)))
  const h = Math.min(440, Math.max(280, Math.floor(height * 0.52)))
  return { x: width - margin - w, y: margin, w, h }
}

export function bossWinsLabel(winnerIsAi: boolean, winnerName?: string | null): string {
  if (winnerName) return `${winnerName} wins!`
  if (winnerIsAi) return `${BOSS_NAME} wins!`
  return 'Draw!'
}

export function bossResultTitle(hasWinner: boolean, winnerIsAi: boolean): string {
  if (!hasWinner) return 'Draw'
  return winnerIsAi ? 'You lose' : 'You win'
}

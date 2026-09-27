export const BOSS_NAME = 'BomberMarv'
export const BOSS_COLOR: [number, number, number] = [56, 56, 62]
export const BOSS_QUOTE = 'Finally a worthy challenger, come and fight me!'
export const BOSS_CHALLENGE_HINT = 'Press Enter to fight'
export const BOMBER_TOM_NAME = 'BomberTom'
export const BOMBER_TOM_COLOR: [number, number, number] = [36, 200, 84]
export const BOMBER_TOM_QUOTE = 'Oh you got BomberMarv?! You thought this is the end??? You you will pay for this!'
export const MARV_KILLER_TITLE = 'MarvKiller'

export function showsBomberTomInvite(prompt?: string | null): boolean {
  return !!prompt && prompt.toLowerCase().includes('bombertom')
}

export function isMarvKillerWin(title?: string | null): boolean {
  return title === MARV_KILLER_TITLE
}

function quoteBeats(quote: string): string[] {
  const text = quote.trim()
  const beats = text.split(/(?<=\?!) |(?<=\?\?\?) /).map(part => part.trim()).filter(Boolean)
  if (beats.length === 1 && text.includes(', ')) {
    const splitAt = text.indexOf(', ')
    return [`${text.slice(0, splitAt)},`, text.slice(splitAt + 2)]
  }
  return beats.length ? beats : [text]
}

function wrapWords(text: string, maxChars: number): string[] {
  const words = text.split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let current = ''
  for (const word of words) {
    const trial = current ? `${current} ${word}` : word
    if (!current || trial.length <= maxChars) current = trial
    else {
      lines.push(current)
      current = word
    }
  }
  if (current) lines.push(current)
  return lines
}

export function inviteQuoteLines(quote: string, maxChars = 42): string[] {
  const lines = quoteBeats(quote).flatMap(beat => wrapWords(beat, maxChars))
  if (lines.length === 0) return ['""']
  if (lines.length === 1) return [`"${lines[0]}"`]
  return lines.map((line, i) => {
    if (i === 0) return `"${line}`
    if (i === lines.length - 1) return `${line}"`
    return line
  })
}

export function resultContentTop(height: number): number {
  return Math.floor(height * 0.34)
}

export function championAnnouncement(name: string): string {
  return `${name} is the Champion!`
}

function resultLogoRight(width: number, height: number): number {
  const side = Math.min(Math.floor(width / 2), Math.floor(height / 4))
  return Math.floor(width / 2) + Math.floor(side / 2)
}

export function championBossCardRect(width: number, height: number): { x: number; y: number; w: number; h: number } {
  const margin = Math.max(12, Math.floor(Math.min(width, height) * 0.018))
  const h = Math.max(1, Math.min(300, resultContentTop(height) - margin - 10))
  const room = width - margin - resultLogoRight(width, height) - 18
  const w = room >= 280 ? Math.min(540, room) : Math.min(340, Math.max(200, width - 2 * margin))
  return { x: width - margin - w, y: margin, w, h }
}

export function marvKillerBannerRect(width: number, height: number): { x: number; y: number; w: number; h: number } {
  const marginY = Math.max(12, Math.floor(height * 0.03))
  const gap = 12
  const w = Math.min(760, Math.max(420, Math.floor(width * 0.52)))
  const maxH = Math.max(1, resultContentTop(height) - marginY - gap)
  const h = Math.min(190, maxH)
  return { x: Math.floor((width - w) / 2), y: marginY, w, h }
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

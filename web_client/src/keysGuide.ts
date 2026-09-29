export const READY_KEY_LINES = [
  'Local   W A S D move   ·   Space bomb',
  'Browser   Arrow keys move   ·   Space bomb',
] as const

export const CONTROLS_HINT =
  'Local: W A S D move, Space bomb.  Browser: Arrow keys or W A S D, Space or Enter bomb.'

export interface KeyGuideRow {
  who: string
  move: string
  bomb: string
}

/** Local seats match bm_params.controls_list. Browser rows match web_client/src/input.ts. */
export const KEY_GUIDE_ROWS: KeyGuideRow[] = [
  { who: 'Player 1', move: 'W A S D', bomb: 'Space' },
  { who: 'Player 2', move: 'I J K L', bomb: 'Left Ctrl' },
  { who: 'Player 3', move: 'F C V B', bomb: 'H' },
  { who: 'Player 4', move: 'Num 5 Num 1 Num 2 Num 3', bomb: 'Right Ctrl' },
  { who: 'Player 5', move: 'Home Del End PgDn', bomb: 'Backspace' },
  { who: 'Player 6', move: 'Num / Num 7 Num 8 Num 9', bomb: 'Num 0' },
  { who: 'Browser', move: 'Arrow keys or W A S D', bomb: 'Space or Enter' },
  { who: 'F11', move: 'Fullscreen', bomb: '' },
  { who: 'Esc', move: 'Pause a round. On the lobby, asks before quitting.', bomb: '' },
  { who: 'Enter', move: 'Start the match and continue after a round', bomb: '' },
]

export function keyGuideAction(row: KeyGuideRow): string {
  if (!row.bomb) return row.move
  return `${row.move}    ·    bomb ${row.bomb}`
}

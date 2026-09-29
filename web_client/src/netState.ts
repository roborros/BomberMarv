import type { BoardPatch, GameState, GameStateDelta, PlayerState } from './types'
import { clamp, percentile } from './math'

export const EXTRAPOLATE_MAX_MS = 70
export const SNAPSHOT_BUFFER_LIMIT = 16
export const TELEPORT_SNAP_PX = 180

export function cloneState(state: GameState): GameState {
  return {
    ...state,
    board: state.board.map((row) => [...row]),
    players: state.players.map((p) => ({ ...p })),
    bombs: state.bombs.map((b) => ({ ...b })),
    explosions: state.explosions.map((e) => ({ ...e, cells: e.cells.map(([x, y]) => [x, y] as [number, number]) })),
    powerups: state.powerups.map((p) => ({ ...p })),
    crushing_walls: { ...state.crushing_walls },
    leave_prompt: state.leave_prompt ? { ...state.leave_prompt } : undefined,
    _net_metrics: state._net_metrics ? { ...state._net_metrics } : undefined
  }
}

export function mergeDelta(base: GameState, delta: GameStateDelta): GameState {
  const merged = cloneState(base)
  if (delta.time !== undefined) merged.time = delta.time
  if (delta.state !== undefined) merged.state = delta.state
  if (delta.board !== undefined) merged.board = delta.board.map((row) => [...row])
  else if (delta.board_patches !== undefined) merged.board = applyBoardPatches(merged.board, delta.board_patches)
  if (delta.players !== undefined) merged.players = delta.players.map((p) => ({ ...p }))
  else if (delta.player_patches !== undefined || delta.player_removed !== undefined) {
    merged.players = applyPlayerDelta(merged.players, delta)
  }
  if (delta.bombs !== undefined) merged.bombs = delta.bombs.map((b) => ({ ...b }))
  if (delta.explosions !== undefined) {
    merged.explosions = delta.explosions.map((e) => ({ ...e, cells: e.cells.map(([x, y]) => [x, y] as [number, number]) }))
  }
  if (delta.powerups !== undefined) merged.powerups = delta.powerups.map((p) => ({ ...p }))
  if (delta.crushing_walls !== undefined) merged.crushing_walls = { ...delta.crushing_walls }
  if (delta.boss_fight_winner !== undefined) merged.boss_fight_winner = delta.boss_fight_winner
  if (delta.local_player_count !== undefined) merged.local_player_count = delta.local_player_count
  if (delta.grid_width !== undefined) merged.grid_width = delta.grid_width
  if (delta.grid_height !== undefined) merged.grid_height = delta.grid_height
  if (delta.trophy_win_threshold !== undefined) merged.trophy_win_threshold = delta.trophy_win_threshold
  if (delta.result_prompt !== undefined) merged.result_prompt = delta.result_prompt
  if (delta.leave_prompt !== undefined) merged.leave_prompt = { ...delta.leave_prompt }
  if (delta.ai_count !== undefined) merged.ai_count = delta.ai_count
  if (delta.blast_ms !== undefined) merged.blast_ms = delta.blast_ms
  if (delta._net_metrics !== undefined) merged._net_metrics = { ...(merged._net_metrics ?? {}), ...delta._net_metrics }
  if (delta._host_published_at_ms !== undefined) merged._host_published_at_ms = delta._host_published_at_ms
  if (delta._sim_tick !== undefined) merged._sim_tick = delta._sim_tick
  return merged
}

export function applyPlayerDelta(basePlayers: PlayerState[], delta: GameStateDelta): PlayerState[] {
  if (delta.players !== undefined) return delta.players.map((p) => ({ ...p }))
  let players = basePlayers.map((p) => ({ ...p }))
  const removed = new Set(delta.player_removed ?? [])
  if (removed.size > 0) players = players.filter((p) => !removed.has(p.id))
  const byId = new Map(players.map((p, index) => [p.id, index]))
  for (const patch of delta.player_patches ?? []) {
    const index = byId.get(patch.id)
    if (index === undefined) {
      players.push({ ...(patch as PlayerState) })
      byId.set(patch.id, players.length - 1)
    } else {
      players[index] = { ...players[index], ...patch }
    }
  }
  return players
}

export function applyBoardPatches(board: number[][], patches: BoardPatch[]): number[][] {
  const next = board.map((row) => [...row])
  for (const patch of patches) {
    const [x, y, cell] = patch
    if (y >= 0 && y < next.length && x >= 0 && x < (next[y]?.length ?? 0)) {
      next[y][x] = cell
    }
  }
  return next
}

export function applyKeepalive(
  state: GameState,
  patch: { time?: number; _sim_tick?: number; _host_published_at_ms?: number }
): GameState {
  return {
    ...state,
    ...(patch.time !== undefined ? { time: patch.time } : {}),
    ...(patch._sim_tick !== undefined ? { _sim_tick: patch._sim_tick } : {}),
    ...(patch._host_published_at_ms !== undefined ? { _host_published_at_ms: patch._host_published_at_ms } : {})
  }
}

export function interpolateState(a: GameState, b: GameState, alpha: number): GameState {
  const clamped = Math.max(0, Math.min(1, alpha))
  const playersById = new Map<number, PlayerState>()
  a.players.forEach((p) => playersById.set(p.id, p))
  const players = b.players.map((next) => interpolatePlayer(playersById.get(next.id), next, clamped))
  return {
    ...b,
    time: a.time + (b.time - a.time) * clamped,
    players
  }
}

export function interpolatePlayer(prev: PlayerState | undefined, next: PlayerState, alpha: number): PlayerState {
  if (!prev) return { ...next }
  if (!prev.alive || !next.alive) return { ...next }
  const dx = next.x - prev.x
  const dy = next.y - prev.y
  if (Math.hypot(dx, dy) > TELEPORT_SNAP_PX) return { ...next }
  const prevDir = prev.direction ?? [0, 0]
  const nextDir = next.direction ?? [0, 0]
  return {
    ...next,
    x: prev.x + dx * alpha,
    y: prev.y + dy * alpha,
    direction: [
      prevDir[0] + (nextDir[0] - prevDir[0]) * alpha,
      prevDir[1] + (nextDir[1] - prevDir[1]) * alpha
    ]
  }
}

export function extrapolateState(
  previous: GameState,
  latest: GameState,
  aheadMs: number,
  maxAheadMs = EXTRAPOLATE_MAX_MS
): GameState {
  const dt = latest.time - previous.time
  if (dt <= 0 || aheadMs <= 0) return latest
  const ahead = Math.min(maxAheadMs, Math.max(0, aheadMs))
  const prevPlayers = new Map(previous.players.map((p) => [p.id, p]))
  const boardRows = latest.board.length
  const boardCols = latest.board[0]?.length ?? 0
  const maxX = boardCols * 100
  const maxY = boardRows * 100
  const players = latest.players.map((curr) => {
    const prev = prevPlayers.get(curr.id)
    if (!prev || !curr.alive) return { ...curr }
    const vx = (curr.x - prev.x) / dt
    const vy = (curr.y - prev.y) / dt
    const nextX = Math.max(0, Math.min(maxX, curr.x + vx * ahead))
    const nextY = Math.max(0, Math.min(maxY, curr.y + vy * ahead))
    return { ...curr, x: nextX, y: nextY }
  })
  return { ...latest, time: latest.time + ahead, players }
}

export function shouldDropSnapshot(latestSeq: number, seq: number): boolean {
  return latestSeq >= 0 && seq <= latestSeq
}

export function updateServerClockOffset(current: number | null, sampleOffset: number): number {
  if (current === null) return sampleOffset
  return (current * 0.9) + (sampleOffset * 0.1)
}

export function trimSnapshotBuffer<T>(buffer: T[], limit = SNAPSHOT_BUFFER_LIMIT): T[] {
  if (buffer.length <= limit) return buffer
  return buffer.slice(buffer.length - limit)
}

export function computeRenderDelayMs(opts: {
  intervals: number[]
  transportActive: 'ws' | 'rtc'
  strictInputMode: boolean
  smoothed: number
}): { delay: number; smoothed: number } {
  const p50 = percentile(opts.intervals, 50) || 16
  const p95 = percentile(opts.intervals, 95) || p50
  const p99 = percentile(opts.intervals, 99) || p95
  const jitter = Math.max(0, p95 - p50)
  const burstJitter = Math.max(0, p99 - p95)
  const minDelay = opts.transportActive === 'rtc' ? 3 : 6
  const maxDelay = opts.transportActive === 'rtc' ? 14 : (opts.strictInputMode ? 26 : 22)
  const targetDelay = Math.max(minDelay, Math.min(maxDelay, p50 * 0.35 + jitter * 0.5 + burstJitter * 0.25 + 2))
  const smoothed = (opts.smoothed * 0.85) + (targetDelay * 0.15)
  return { delay: smoothed, smoothed }
}

export function resolveLocalPredictionTargetIndex(
  state: GameState,
  clientId: number | null,
  playerIds: number[]
): number {
  if (clientId === null || playerIds.length === 0) return -1
  const assignedPlayerIds = new Set(playerIds)
  return state.players.findIndex((p) => (
    typeof p.owner_client_id === 'number'
    && p.owner_client_id === clientId
    && typeof p.owner_client_player_id === 'number'
    && assignedPlayerIds.has(p.owner_client_player_id)
  ))
}

export function lerpVisualOffset(
  current: { x: number; y: number },
  target: { x: number; y: number },
  lerp: number
): { x: number; y: number } {
  return {
    x: current.x + (target.x - current.x) * lerp,
    y: current.y + (target.y - current.y) * lerp
  }
}

export function predictedLocalPosition(opts: {
  authX: number
  authY: number
  offsetX: number
  offsetY: number
  boardCols: number
  boardRows: number
  cellSize?: number
}): { x: number; y: number } {
  const cellSize = opts.cellSize ?? 100
  const maxX = opts.boardCols * cellSize
  const maxY = opts.boardRows * cellSize
  return {
    x: clamp(opts.authX + opts.offsetX, 0, maxX),
    y: clamp(opts.authY + opts.offsetY, 0, maxY)
  }
}

export function localPredictionTargetMagnitude(opts: {
  inputActive: boolean
  blocked: boolean
  transportActive: 'ws' | 'rtc'
  maxOffsetWs?: number
  maxOffsetRtc?: number
}): number {
  if (!opts.inputActive) return 0
  if (opts.blocked) return 2.0
  return opts.transportActive === 'rtc'
    ? (opts.maxOffsetRtc ?? 6)
    : (opts.maxOffsetWs ?? 9)
}

export function humanStateName(rawState: string | undefined): string {
  switch (rawState) {
    case 'startup':
      return 'Waiting for game to start...'
    case 'game_prep':
      return 'Game setup in progress...'
    case 'get_ready':
      return 'Get ready...'
    case 'playing':
      return 'Game in progress...'
    case 'win':
      return 'Round finished.'
    case 'champion':
      return 'Champion! Press Enter to fight BomberMarv.'
    case 'boss_fight':
      return 'Boss fight!'
    case 'boss_result':
      return 'Boss fight result. Reset trophies from zero?'
    default:
      return 'Waiting for game state...'
  }
}

export function slotButtonLabel(isTaken: boolean, reason?: string): string {
  if (!isTaken) return 'Join'
  return reason === 'local' ? 'Local' : 'Remote'
}

export function clipDisplayName(name: string, maxLen = 20): string {
  return name.trim().slice(0, maxLen)
}

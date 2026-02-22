import './style.css'
import { Renderer } from './renderer'
import { runRendererBenchmark } from './perf_benchmark'
import type {
  GameState,
  GameStateDeltaMessage,
  GameStateMessage,
  RegistrationConfirmedMessage,
  RegistrationRejectedMessage,
  ServerMessage,
  SlotListMessage
} from './types'
import { isServerMessage } from './types'

const PROTOCOL_VERSION = 2
const INPUT_HEARTBEAT_MS = 120
const MAX_SEND_FPS = 60
const PING_INTERVAL_MS = 10000
const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 6000
const SNAPSHOT_BUFFER_LIMIT = 16
const KEYFRAME_STALE_MS = 1500
const AUDIO_COOLDOWN_MS = 40

window.onerror = (msg, url, line, col, error) => {
  console.error('GLOBAL ERROR:', msg, url, line, col, error)
  const status = document.getElementById('status')
  if (status) status.textContent = `Script Error: ${msg}`
  return false
}

const appDiv = document.querySelector<HTMLDivElement>('#app')
if (!appDiv) throw new Error('Missing #app root element')
appDiv.innerHTML = `
  <div id="game-container">
    <canvas id="gameCanvas"></canvas>
    <div id="debug-line">Waiting for game state...</div>
    <div id="state-only" class="hidden">Waiting for game to start...</div>
    <div id="controls-hint">
      Controls: Arrow Keys to Move, Space to Place Bomb
    </div>
    <div id="status">Connecting...</div>
  </div>
`

const canvas = document.querySelector<HTMLCanvasElement>('#gameCanvas')
const debugLine = document.querySelector<HTMLDivElement>('#debug-line')
const renderToggle = document.querySelector<HTMLInputElement>('#render-toggle')
const stateOnly = document.querySelector<HTMLDivElement>('#state-only')
const statusDiv = document.querySelector<HTMLDivElement>('#status')
const lobbyOverlay = document.getElementById('lobby-overlay')
const slotContainer = document.getElementById('slot-container')
const lobbyStatus = document.getElementById('lobby-status')
const playerNameInput = document.querySelector<HTMLInputElement>('#player-name')

if (!canvas || !debugLine || !renderToggle || !stateOnly || !statusDiv || !lobbyOverlay || !slotContainer || !lobbyStatus || !playerNameInput) {
  throw new Error('Required DOM elements not found')
}

const canvasEl: HTMLCanvasElement = canvas
const debugLineEl: HTMLDivElement = debugLine
const renderToggleEl: HTMLInputElement = renderToggle
const stateOnlyEl: HTMLDivElement = stateOnly
const statusDivEl: HTMLDivElement = statusDiv
const lobbyOverlayEl: HTMLElement = lobbyOverlay
const slotContainerEl: HTMLElement = slotContainer
const lobbyStatusEl: HTMLElement = lobbyStatus
const playerNameInputEl: HTMLInputElement = playerNameInput

const renderer = new Renderer(canvasEl)
const BENCH_MODE = new URLSearchParams(window.location.search).get('bench') === '1'

if (BENCH_MODE) {
  runRendererBenchmark(canvasEl)
    .then((results) => {
      console.table(results)
      statusDivEl.textContent = `Bench done: Canvas2D ${results[0].fps.toFixed(1)} FPS, WebGL ${results[1].fps.toFixed(1)} FPS`
    })
    .catch((err) => {
      console.error('Benchmark failed', err)
    })
}

type BufferedSnapshot = { seq: number; recvTs: number; serverTs?: number; state: GameState }
let snapshotBuffer: BufferedSnapshot[] = []
let latestState: GameState | null = null
let latestSeq = -1
let clientId: number | null = null
let playerIds: number[] = []
let isRegistered = false
let reconnectAttempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null
let ws: WebSocket | null = null
let pendingSlotSelection: number | null = null
let currentPlayerName = ''
let renderEnabled = true
let latencySamples5s: Array<{ ts: number; value: number }> = []
let avgLatency5sMs = 0
let frameTimes5s: number[] = []
let avgClientFps5s = 0
let arrivalIntervalsMs: number[] = []
let pipelineSamplesMs: number[] = []
let presentDelaySamplesMs: number[] = []
let decodeSamplesMs: number[] = []
let audioUnlocked = false
let lastSoundAt: Record<string, number> = {}
let knownExplosionKeys = new Set<string>()

const SOUND_EXPLOSION = '/sounds/explosion_short.wav'
const SOUND_EXPLOSION_QD = '/sounds/explosion_short_qd.wav'
const SOUND_BONUS = '/sounds/pick-bonus.wav'
const SOUND_DEATH = '/sounds/death.wav'
const SOUND_QD = '/sounds/quad_damage.mp3'

const audioCache = new Map<string, HTMLAudioElement>()

const keys = {
  up: false,
  down: false,
  left: false,
  right: false,
  bomb: false
}
let keysDirty = false
let lastInputSentAt = 0
let lastInputHash = ''
let lastRenderLoopTs = 0

function getWsUrl(): string {
  let host = window.location.hostname
  if (host === 'localhost') host = '127.0.0.1'
  return `ws://${host}:8765`
}

function sendMessage(message: Record<string, unknown>) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message))
  }
}

function ensureAudioUnlocked() {
  if (audioUnlocked) return
  audioUnlocked = true
  // Prime audio elements after first user gesture.
  ;[SOUND_EXPLOSION, SOUND_EXPLOSION_QD, SOUND_BONUS, SOUND_DEATH, SOUND_QD].forEach((src) => {
    if (!audioCache.has(src)) {
      const a = new Audio(src)
      a.preload = 'auto'
      audioCache.set(src, a)
    }
  })
}

function playSound(src: string, volume: number) {
  if (!audioUnlocked) return
  const now = performance.now()
  const last = lastSoundAt[src] ?? 0
  if (now - last < AUDIO_COOLDOWN_MS) return
  lastSoundAt[src] = now
  let base = audioCache.get(src)
  if (!base) {
    base = new Audio(src)
    base.preload = 'auto'
    audioCache.set(src, base)
  }
  const shot = base.cloneNode(true) as HTMLAudioElement
  shot.volume = volume
  void shot.play().catch(() => {})
}

function processAudioEvents(previous: GameState | null, current: GameState) {
  const newExplosionKeys = new Set<string>()
  let explosionPlays = 0
  for (const e of current.explosions) {
    const c = e.cells[0]
    if (!c) continue
    const key = `${e.start_time}:${c[0]}:${c[1]}:${e.quad_damage ? 1 : 0}`
    newExplosionKeys.add(key)
    if (!knownExplosionKeys.has(key)) {
      playSound(e.quad_damage ? SOUND_EXPLOSION_QD : SOUND_EXPLOSION, 0.12)
      explosionPlays += 1
      if (explosionPlays >= 4) break
    }
  }
  knownExplosionKeys = newExplosionKeys

  if (!previous) return
  const prevPlayers = new Map(previous.players.map((p) => [p.id, p]))
  for (const p of current.players) {
    const prev = prevPlayers.get(p.id)
    if (!prev) continue
    if (prev.alive && !p.alive) {
      playSound(SOUND_DEATH, 0.12)
    }
    if (!prev.quad_damage && p.quad_damage) {
      playSound(SOUND_QD, 0.12)
    }
    const prevFire = prev.fire_power ?? 0
    const prevBomb = prev.bomb_capacity ?? 0
    const nextFire = p.fire_power ?? prevFire
    const nextBomb = p.bomb_capacity ?? prevBomb
    if (nextFire > prevFire || nextBomb > prevBomb) {
      playSound(SOUND_BONUS, 0.1)
    }
  }
}

function pushLimited(target: number[], value: number, max = 300) {
  target.push(value)
  if (target.length > max) target.splice(0, target.length - max)
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor((p / 100) * (sorted.length - 1))))
  return sorted[idx]
}

function cloneState(state: GameState): GameState {
  return {
    ...state,
    board: state.board.map((row) => [...row]),
    players: state.players.map((p) => ({ ...p })),
    bombs: state.bombs.map((b) => ({ ...b })),
    explosions: state.explosions.map((e) => ({ ...e, cells: e.cells.map(([x, y]) => [x, y]) })),
    powerups: state.powerups.map((p) => ({ ...p })),
    crushing_walls: { ...state.crushing_walls },
    _net_metrics: state._net_metrics ? { ...state._net_metrics } : undefined
  }
}

function mergeDelta(base: GameState, delta: Partial<GameState>): GameState {
  const merged = cloneState(base)
  if (delta.time !== undefined) merged.time = delta.time
  if (delta.state !== undefined) merged.state = delta.state
  if (delta.board !== undefined) merged.board = delta.board.map((row) => [...row])
  if (delta.players !== undefined) merged.players = delta.players.map((p) => ({ ...p }))
  if (delta.bombs !== undefined) merged.bombs = delta.bombs.map((b) => ({ ...b }))
  if (delta.explosions !== undefined) merged.explosions = delta.explosions.map((e) => ({ ...e, cells: e.cells.map(([x, y]) => [x, y]) }))
  if (delta.powerups !== undefined) merged.powerups = delta.powerups.map((p) => ({ ...p }))
  if (delta.crushing_walls !== undefined) merged.crushing_walls = { ...delta.crushing_walls }
  if (delta._net_metrics !== undefined) merged._net_metrics = { ...(merged._net_metrics ?? {}), ...delta._net_metrics }
  if (delta._host_published_at_ms !== undefined) merged._host_published_at_ms = delta._host_published_at_ms
  return merged
}

function ingestSnapshot(state: GameState, seq: number, serverTs?: number, recvTs = performance.now()) {
  if (latestSeq >= 0 && seq <= latestSeq) return
  const previous = latestState
  if (snapshotBuffer.length > 0) {
    const interval = recvTs - snapshotBuffer[snapshotBuffer.length - 1].recvTs
    if (interval > 0) pushLimited(arrivalIntervalsMs, interval)
  }
  latestState = state
  latestSeq = seq
  processAudioEvents(previous, state)
  snapshotBuffer.push({ seq, recvTs, serverTs, state })
  if (snapshotBuffer.length > SNAPSHOT_BUFFER_LIMIT) {
    snapshotBuffer = snapshotBuffer.slice(snapshotBuffer.length - SNAPSHOT_BUFFER_LIMIT)
  }
}

function interpolateState(a: GameState, b: GameState, alpha: number): GameState {
  const clamped = Math.max(0, Math.min(1, alpha))
  const playersById = new Map<number, typeof a.players[number]>()
  a.players.forEach((p) => playersById.set(p.id, p))
  const players = b.players.map((next) => {
    const prev = playersById.get(next.id)
    if (!prev) return { ...next }
    return {
      ...next,
      x: prev.x + (next.x - prev.x) * clamped,
      y: prev.y + (next.y - prev.y) * clamped
    }
  })
  return {
    ...b,
    time: a.time + (b.time - a.time) * clamped,
    players
  }
}

function getRenderDelayMs(): number {
  const p50 = percentile(arrivalIntervalsMs, 50) || 16
  const p95 = percentile(arrivalIntervalsMs, 95) || p50
  const jitter = Math.max(0, p95 - p50)
  return Math.max(8, Math.min(24, p50 * 0.5 + jitter * 0.35))
}

function renderSlots(msg: SlotListMessage) {
  slotContainerEl.innerHTML = ''
  for (let i = 1; i <= 6; i++) {
    const key = i.toString()
    const isTaken = msg.slots[key] === true
    const reason = msg.slot_reasons?.[key]
    const btn = document.createElement('button')
    btn.className = `slot-btn ${isTaken ? 'taken' : ''}`
    btn.dataset.slot = key
    btn.disabled = isTaken
    let label = 'Join'
    if (isTaken) {
      label = reason === 'local' ? 'Local' : 'Remote'
    }
    btn.innerHTML = `P${i}<br><span style="font-size:12px">${label}</span>`
    slotContainerEl.appendChild(btn)
  }
}

function getPlayerName(): string {
  return playerNameInputEl.value.trim().slice(0, 20)
}

function startHeartbeat() {
  if (pingTimer) clearInterval(pingTimer)
  pingTimer = setInterval(() => {
    sendMessage({ type: 'ping', protocol: PROTOCOL_VERSION, ts: Date.now() })
  }, PING_INTERVAL_MS)
}

function handleMessage(raw: string) {
  try {
    const decodeStart = performance.now()
    const parsed = JSON.parse(raw) as unknown
    if (!isServerMessage(parsed)) return
    pushLimited(decodeSamplesMs, performance.now() - decodeStart)
    const msg = parsed as ServerMessage

    if (msg.type === 'client_id') {
      clientId = msg.client_id
      return
    }

    if (msg.type === 'slot_list') {
      renderSlots(msg)
      return
    }

    if (msg.type === 'registration_confirmed') {
      const confirmed = msg as RegistrationConfirmedMessage
      isRegistered = true
      pendingSlotSelection = confirmed.slot
      playerIds = confirmed.player_ids || []
      lobbyOverlayEl.classList.add('hidden')
      statusDivEl.textContent = `Playing as P${confirmed.slot}`
      return
    }

    if (msg.type === 'registration_rejected') {
      const rejected = msg as RegistrationRejectedMessage
      lobbyStatusEl.textContent = `Error: ${rejected.message}`
      sendMessage({ type: 'request_slot_list', protocol: PROTOCOL_VERSION })
      return
    }

    if (msg.type === 'gamestate') {
      const stateMsg = msg as GameStateMessage
      if (isRegistered) {
        ingestSnapshot(stateMsg.data, stateMsg.seq ?? (latestSeq + 1), stateMsg.server_timestamp)
      }
      return
    }

    if (msg.type === 'gamestate_delta') {
      const deltaMsg = msg as GameStateDeltaMessage
      if (!isRegistered || !latestState) return
      if (deltaMsg.base_seq !== latestSeq) {
        // We missed continuity; wait for the next keyframe.
        return
      }
      const merged = mergeDelta(latestState, deltaMsg.delta)
      ingestSnapshot(merged, deltaMsg.seq, deltaMsg.server_timestamp)
      return
    }

    if (msg.type === 'input_ack') {
      const now = Date.now()
      const original = msg.original_timestamp
      if (typeof original === 'number') {
        const sample = Math.max(0, now - original)
        latencySamples5s.push({ ts: now, value: sample })
        const cutoff = now - 5000
        latencySamples5s = latencySamples5s.filter((s) => s.ts >= cutoff)
        if (latencySamples5s.length > 0) {
          const sum = latencySamples5s.reduce((acc, s) => acc + s.value, 0)
          avgLatency5sMs = sum / latencySamples5s.length
        } else {
          avgLatency5sMs = 0
        }
      }
      return
    }

    if (msg.type === 'error') {
      statusDivEl.textContent = `Protocol error: ${msg.message}`
    }
  } catch (e) {
    console.error('Error parsing message:', e)
  }
}

function connectWebSocket() {
  const wsUrl = getWsUrl()
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    reconnectAttempts = 0
    statusDivEl.textContent = 'Connected. Waiting for lobby...'
    lobbyStatusEl.textContent = 'Connected. Requesting slots...'
    lobbyOverlayEl.classList.remove('hidden')
    snapshotBuffer = []
    latestState = null
    latestSeq = -1
    knownExplosionKeys = new Set()
    sendMessage({ type: 'hello', protocol: PROTOCOL_VERSION, ts: Date.now() })
    if (currentPlayerName) {
      sendMessage({ type: 'set_name', protocol: PROTOCOL_VERSION, name: currentPlayerName })
    }
    sendMessage({ type: 'request_slot_list', protocol: PROTOCOL_VERSION })
    if (pendingSlotSelection !== null) {
      sendMessage({ type: 'select_slot', slot: pendingSlotSelection, protocol: PROTOCOL_VERSION, name: currentPlayerName })
    }
    startHeartbeat()
  }

  ws.onmessage = (event) => handleMessage(event.data as string)

  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
    statusDivEl.textContent = 'Connection Error'
  }

  ws.onclose = () => {
    statusDivEl.textContent = 'Disconnected. Reconnecting...'
    isRegistered = false
    if (pingTimer) {
      clearInterval(pingTimer)
      pingTimer = null
    }
    reconnectAttempts += 1
    snapshotBuffer = []
    latestState = null
    latestSeq = -1
    knownExplosionKeys = new Set()
    const waitMs = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * (2 ** (reconnectAttempts - 1)))
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(connectWebSocket, waitMs)
  }
}

slotContainerEl.addEventListener('click', (e) => {
  const target = (e.target as HTMLElement).closest('.slot-btn')
  if (!target) return
  const slot = (target as HTMLElement).dataset.slot
  if (!slot) return
  const parsed = parseInt(slot, 10)
  pendingSlotSelection = parsed
  currentPlayerName = getPlayerName()
  if (currentPlayerName) {
    sendMessage({ type: 'set_name', protocol: PROTOCOL_VERSION, name: currentPlayerName })
  }
  sendMessage({ type: 'select_slot', slot: parsed, protocol: PROTOCOL_VERSION, name: currentPlayerName })
  lobbyStatusEl.textContent = `Joining slot ${slot}...`
})

playerNameInputEl.addEventListener('change', () => {
  currentPlayerName = getPlayerName()
  if (currentPlayerName) {
    sendMessage({ type: 'set_name', protocol: PROTOCOL_VERSION, name: currentPlayerName })
  }
})

renderToggleEl.addEventListener('change', () => {
  renderEnabled = renderToggleEl.checked
  canvasEl.classList.toggle('hidden', !renderEnabled)
  stateOnlyEl.classList.toggle('hidden', renderEnabled)
})

function humanStateName(rawState: string | undefined): string {
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
      return 'Champion screen.'
    default:
      return 'Waiting for game state...'
  }
}

function updateKey(code: string, pressed: boolean) {
  let changed = false
  switch (code) {
    case 'ArrowUp':
    case 'KeyW':
      changed = keys.up !== pressed
      keys.up = pressed
      break
    case 'ArrowDown':
    case 'KeyS':
      changed = keys.down !== pressed
      keys.down = pressed
      break
    case 'ArrowLeft':
    case 'KeyA':
      changed = keys.left !== pressed
      keys.left = pressed
      break
    case 'ArrowRight':
    case 'KeyD':
      changed = keys.right !== pressed
      keys.right = pressed
      break
    case 'Space':
    case 'Enter':
      changed = keys.bomb !== pressed
      keys.bomb = pressed
      break
    default:
      break
  }
  if (changed) {
    keysDirty = true
    maybeSendInput(true)
  }
}

function inputHash(): string {
  return `${keys.up ? 1 : 0}${keys.down ? 1 : 0}${keys.left ? 1 : 0}${keys.right ? 1 : 0}${keys.bomb ? 1 : 0}`
}

function maybeSendInput(force = false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  if (clientId === null || !isRegistered || playerIds.length === 0) return
  const now = Date.now()
  const minDeltaMs = 1000 / MAX_SEND_FPS
  if (!force && now - lastInputSentAt < minDeltaMs) return
  const hash = inputHash()
  const heartbeatDue = now - lastInputSentAt >= INPUT_HEARTBEAT_MS
  if (!force && !keysDirty && !heartbeatDue) return
  if (!force && hash === lastInputHash && !heartbeatDue) return

  const playerId = playerIds[0]
  const inputData = [
    clientId,
    playerId,
    keys.up ? 1 : 0,
    keys.down ? 1 : 0,
    keys.left ? 1 : 0,
    keys.right ? 1 : 0,
    keys.bomb ? 1 : 0
  ]

  sendMessage({
    type: 'game_input',
    protocol: PROTOCOL_VERSION,
    input: inputData,
    client_timestamp: now
  })

  lastInputSentAt = now
  keysDirty = false
  lastInputHash = hash
}

window.addEventListener('keydown', (e) => updateKey(e.code, true))
window.addEventListener('keyup', (e) => updateKey(e.code, false))

function loop(ts: number) {
  frameTimes5s.push(ts)
  const cutoff = ts - 5000
  frameTimes5s = frameTimes5s.filter((t) => t >= cutoff)
  if (frameTimes5s.length > 1) {
    const span = frameTimes5s[frameTimes5s.length - 1] - frameTimes5s[0]
    avgClientFps5s = span > 0 ? ((frameTimes5s.length - 1) * 1000) / span : 0
  } else {
    avgClientFps5s = 0
  }

  if (ts - lastRenderLoopTs >= (1000 / MAX_SEND_FPS)) {
    maybeSendInput(false)
    lastRenderLoopTs = ts
  }
  if (snapshotBuffer.length > 0 && latestState) {
    const frameStart = performance.now()
    const delayMs = getRenderDelayMs()
    const renderTarget = frameStart - delayMs
    const newest = snapshotBuffer[snapshotBuffer.length - 1]
    if (frameStart - newest.recvTs > KEYFRAME_STALE_MS) {
      snapshotBuffer = [newest]
    }

    let displayState = newest.state
    if (snapshotBuffer.length >= 2) {
      let idx = 1
      while (idx < snapshotBuffer.length && snapshotBuffer[idx].recvTs < renderTarget) idx += 1
      const right = snapshotBuffer[Math.min(snapshotBuffer.length - 1, idx)]
      const left = snapshotBuffer[Math.max(0, idx - 1)]
      if (right.recvTs > left.recvTs && renderTarget >= left.recvTs && renderTarget <= right.recvTs) {
        const alpha = (renderTarget - left.recvTs) / (right.recvTs - left.recvTs)
        displayState = interpolateState(left.state, right.state, alpha)
      } else if (renderTarget < left.recvTs) {
        displayState = left.state
      } else {
        displayState = right.state
      }
    }

    const hostFps = displayState._net_metrics?.host_fps_5s
    const hostRenderFps = displayState._net_metrics?.host_render_fps_5s
    const publishTs = displayState._host_published_at_ms
    if (typeof publishTs === 'number') {
      pushLimited(presentDelaySamplesMs, Math.max(0, Date.now() - publishTs))
    }

    if (renderEnabled) {
      const debugText = renderer.render(displayState, {
        latency5sMs: avgLatency5sMs,
        fps5s: avgClientFps5s,
        hostFps5s: hostFps,
        hostRenderFps5s: hostRenderFps,
        renderPipelineP95Ms: percentile(pipelineSamplesMs, 95),
        presentDelayP95Ms: percentile(presentDelaySamplesMs, 95),
        decodeP95Ms: percentile(decodeSamplesMs, 95)
      })
      debugLineEl.textContent = debugText
    } else {
      const latencyText = `Latency(5s): ${avgLatency5sMs.toFixed(1)} ms`
      const fpsText = `Client FPS(5s): ${avgClientFps5s.toFixed(1)}`
      const hostFpsText = `Host SIM FPS(5s): ${(hostFps ?? 0).toFixed(1)}`
      const presentDelayText = `PresentDelay p95: ${percentile(presentDelaySamplesMs, 95).toFixed(1)} ms`
      const decodeText = `Decode p95: ${percentile(decodeSamplesMs, 95).toFixed(2)} ms`
      stateOnlyEl.textContent = `${humanStateName(displayState.state)} | ${latencyText} | ${fpsText} | ${hostFpsText} | ${presentDelayText} | ${decodeText}`
      debugLineEl.textContent = stateOnlyEl.textContent
    }
    pushLimited(pipelineSamplesMs, performance.now() - frameStart)
  }
  requestAnimationFrame(loop)
}

connectWebSocket()
requestAnimationFrame(loop)

window.addEventListener('keydown', ensureAudioUnlocked, { once: true })
window.addEventListener('pointerdown', ensureAudioUnlocked, { once: true })

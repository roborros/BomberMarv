import './style.css'
import { Renderer } from './renderer'
import type {
  GameState,
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
    <div id="state-only" class="hidden">Waiting for game to start...</div>
    <div id="controls-hint">
      Controls: Arrow Keys to Move, Space to Place Bomb
    </div>
    <div id="status">Connecting...</div>
  </div>
`

const canvas = document.querySelector<HTMLCanvasElement>('#gameCanvas')
const renderToggle = document.querySelector<HTMLInputElement>('#render-toggle')
const stateOnly = document.querySelector<HTMLDivElement>('#state-only')
const statusDiv = document.querySelector<HTMLDivElement>('#status')
const lobbyOverlay = document.getElementById('lobby-overlay')
const slotContainer = document.getElementById('slot-container')
const lobbyStatus = document.getElementById('lobby-status')
const playerNameInput = document.querySelector<HTMLInputElement>('#player-name')

if (!canvas || !renderToggle || !stateOnly || !statusDiv || !lobbyOverlay || !slotContainer || !lobbyStatus || !playerNameInput) {
  throw new Error('Required DOM elements not found')
}

const canvasEl: HTMLCanvasElement = canvas
const renderToggleEl: HTMLInputElement = renderToggle
const stateOnlyEl: HTMLDivElement = stateOnly
const statusDivEl: HTMLDivElement = statusDiv
const lobbyOverlayEl: HTMLElement = lobbyOverlay
const slotContainerEl: HTMLElement = slotContainer
const lobbyStatusEl: HTMLElement = lobbyStatus
const playerNameInputEl: HTMLInputElement = playerNameInput

const renderer = new Renderer(canvasEl)

let currentState: GameState | null = null
let lastServerTimestamp: number | undefined
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
    const parsed = JSON.parse(raw) as unknown
    if (!isServerMessage(parsed)) return
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
        currentState = stateMsg.data
        lastServerTimestamp = stateMsg.server_timestamp
      }
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
  if (currentState) {
    const hostFps = currentState._net_metrics?.host_fps_5s
    if (renderEnabled) {
      renderer.render(currentState, lastServerTimestamp, {
        latency5sMs: avgLatency5sMs,
        fps5s: avgClientFps5s,
        hostFps5s: hostFps
      })
    } else {
      const latencyText = `Latency(5s): ${avgLatency5sMs.toFixed(1)} ms`
      const fpsText = `Client FPS(5s): ${avgClientFps5s.toFixed(1)}`
      const hostFpsText = `Host FPS(5s): ${(hostFps ?? 0).toFixed(1)}`
      stateOnlyEl.textContent = `${humanStateName(currentState.state)} | ${latencyText} | ${fpsText} | ${hostFpsText}`
    }
  }
  requestAnimationFrame(loop)
}

connectWebSocket()
requestAnimationFrame(loop)

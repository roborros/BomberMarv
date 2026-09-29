import './style.css'
import { decode as msgpackDecode, encode as msgpackEncode } from '@msgpack/msgpack'
import { Renderer } from './renderer'
import { runRendererBenchmark } from './perf_benchmark'
import type {
  GameState,
  GameStateDeltaMessage,
  GameStateMessage,
  HelloAckMessage,
  NetMetricsMessage,
  RegistrationConfirmedMessage,
  RegistrationRejectedMessage,
  RtcFailedMessage,
  RtcIceCandidateMessage,
  RtcOfferMessage,
  RtcReadyMessage,
  ServerMessage,
  SlotListMessage,
  StateKeepaliveMessage
} from './types'
import { isServerMessage } from './types'
import { clamp, percentile, pushLimited, reconnectWaitMs } from './math'
import {
  applyKeyCode,
  buildGameInputPayload,
  hashInput,
  resolveInputTickId,
  shouldSendInput,
  type InputKeys
} from './input'
import {
  clipDisplayName,
  computeRenderDelayMs,
  extrapolateState,
  humanStateName,
  interpolateState,
  mergeDelta,
  applyKeepalive,
  resolveLocalPredictionTargetIndex as findLocalPredictionIndex,
  shouldDropSnapshot,
  slotButtonLabel,
  SNAPSHOT_BUFFER_LIMIT,
  trimSnapshotBuffer,
  updateServerClockOffset
} from './netState'
import { buildWsUrl } from './wsUrl'
import { decodeIncomingWsData, encodeWsFrame, preferredWsCodec, type WsCodec } from './wireCodec'
import { samplePresentAgeMs, sampleRttMs } from './latency'
import {
  BIG_EXPLOSION_TILE_THRESHOLD,
  BIG_EXPLOSION_VOLUME,
  BIG_EXPLOSION_WINDOW_MS,
  collectNewExplosionKeys,
  collectPlayerAudioCues,
  crossedBigExplosionThreshold,
  shouldResetBigExplosionTracking,
  uniqueTilesInWindow
} from './audioEvents'
import { CONTROLS_HINT, KEY_GUIDE_ROWS, keyGuideAction } from './keysGuide'

const PROTOCOL_VERSION = 2
const INPUT_HEARTBEAT_MS = 120
const MAX_SEND_FPS = 60
const MAX_RENDER_FPS = 60
const PING_INTERVAL_MS = 10000
const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 6000
const KEYFRAME_STALE_MS = 1500
const AUDIO_COOLDOWN_MS = 40
const BIG_EXPLOSION_SOUND_DELAY_MS = 300
const LOCAL_PREDICTION_MAX_OFFSET_PX = 9
const LOCAL_PREDICTION_LERP = 0.38
const LOCAL_PREDICTION_MAX_OFFSET_RTC_PX = 6
const RTC_ENABLED = new URLSearchParams(window.location.search).get('rtc') !== '0'
const RTC_RETRY_MS = 4000
const RTC_CODEC: 'json' | 'msgpack' = new URLSearchParams(window.location.search).get('rtc_codec') === 'msgpack' ? 'msgpack' : 'json'
const WS_CODEC_PREF: WsCodec = preferredWsCodec(window.location.search)
const STRICT_INPUT_MODE = new URLSearchParams(window.location.search).get('strict') === '1'

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
    <div id="game-stage">
      <canvas id="gameCanvas"></canvas>
    </div>
    <div id="debug-line">Waiting for game state...</div>
    <div id="state-only" class="hidden">Waiting for game to start...</div>
    <div id="controls-hint">
      ${CONTROLS_HINT}
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
const keysButton = document.getElementById('keys-button')
const keysOverlay = document.getElementById('keys-overlay')
const keysList = document.getElementById('keys-list')
const keysBack = document.getElementById('keys-back')

if (!canvas || !debugLine || !renderToggle || !stateOnly || !statusDiv || !lobbyOverlay || !slotContainer || !lobbyStatus || !playerNameInput || !keysButton || !keysOverlay || !keysList || !keysBack) {
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
const keysButtonEl: HTMLElement = keysButton
const keysOverlayEl: HTMLElement = keysOverlay
const keysListEl: HTMLElement = keysList
const keysBackEl: HTMLElement = keysBack

function showKeysScreen() {
  keysOverlayEl.classList.remove('hidden')
}

function hideKeysScreen() {
  keysOverlayEl.classList.add('hidden')
}

for (const row of KEY_GUIDE_ROWS) {
  const item = document.createElement('div')
  item.className = 'keys-row'
  const who = document.createElement('span')
  who.className = 'keys-who'
  who.textContent = row.who
  const action = document.createElement('span')
  action.className = 'keys-action'
  action.textContent = keyGuideAction(row)
  item.append(who, action)
  keysListEl.appendChild(item)
}
keysButtonEl.addEventListener('click', showKeysScreen)
keysBackEl.addEventListener('click', hideKeysScreen)

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
let wsCodec: WsCodec = 'json'
let latestHudMetrics: GameState['_net_metrics'] | undefined
let rtcPeer: RTCPeerConnection | null = null
let rtcInputChannel: RTCDataChannel | null = null
let rtcStateChannel: RTCDataChannel | null = null
let rtcRetryTimer: ReturnType<typeof setTimeout> | null = null
let transportActive: 'ws' | 'rtc' = 'ws'
let rtcFallbackEvents = 0
let pendingSlotSelection: number | null = null
let currentPlayerName = ''
let renderEnabled = false
let latencySamples5s: Array<{ ts: number; value: number }> = []
let avgLatency5sMs = 0
let frameTimes5s: number[] = []
let avgClientFps5s = 0
let arrivalIntervalsMs: number[] = []
let pipelineSamplesMs: number[] = []
let presentDelaySamplesMs: number[] = []
let decodeSamplesMs: number[] = []
let serverClockOffsetMs = 0
let hasServerClockOffset = false
let smoothedRenderDelayMs = 12
let localVisualOffset: { x: number; y: number } = { x: 0, y: 0 }
let localPredictionErrorPx: number[] = []
let localPredictionTargetKey: string | null = null
let localLastAuthPos: { x: number; y: number } | null = null
let audioUnlocked = false
let lastSoundAt: Record<string, number> = {}
let knownExplosionKeys = new Set<string>()
let recentExplosionEvents: { startTime: number; cells: [number, number][] }[] = []
let bigExplosionOverThreshold = false
let bigExplosionSoundTimers: number[] = []
let lastKeyframeRequestAt = 0

const SOUND_EXPLOSION = '/sounds/explosion_short.wav'
const SOUND_EXPLOSION_QD = '/sounds/explosion_short_qd.wav'
const SOUND_BONUS = '/sounds/pick-bonus.wav'
const SOUND_DEATH = '/sounds/death.wav'
const SOUND_QD = '/sounds/quad_damage.mp3'
const SOUND_BIG_EXPLOSION = '/sounds/mocny_stral.mp3'
const SOUND_FRESH_MEAT = '/sounds/fresh_meat.wav'

const audioCache = new Map<string, HTMLAudioElement>()

const keys: InputKeys = {
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
let lastRenderDrawTs = 0
let localInputTick = 0

function getWsUrl(): string {
  return buildWsUrl(window.location.hostname)
}

function sendMessage(message: object) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(encodeWsFrame(message as { type: string }, wsCodec))
  }
}

function requestKeyframe() {
  const now = Date.now()
  if (now - lastKeyframeRequestAt < 120) return
  lastKeyframeRequestAt = now
  sendMessage({ type: 'request_keyframe', protocol: PROTOCOL_VERSION, seq: latestSeq })
}

function isRtcInputReady(): boolean {
  return !!(rtcInputChannel && rtcInputChannel.readyState === 'open' && transportActive === 'rtc')
}

function scheduleRtcRetry() {
  if (rtcRetryTimer) return
  rtcRetryTimer = setTimeout(() => {
    rtcRetryTimer = null
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendMessage({
        type: 'hello',
        protocol: PROTOCOL_VERSION,
        ts: Date.now(),
        webrtc_supported: RTC_ENABLED && !!window.RTCPeerConnection,
        rtc_codec: RTC_CODEC,
        encoding: WS_CODEC_PREF,
        ws_codec: WS_CODEC_PREF,
        strict_input_mode: STRICT_INPUT_MODE
      })
    }
  }, RTC_RETRY_MS)
}

function closeRtcPeer() {
  try { rtcInputChannel?.close() } catch { /* noop */ }
  try { rtcStateChannel?.close() } catch { /* noop */ }
  try { rtcPeer?.close() } catch { /* noop */ }
  rtcInputChannel = null
  rtcStateChannel = null
  rtcPeer = null
  transportActive = 'ws'
}

async function handleRtcOffer(msg: RtcOfferMessage) {
  if (!RTC_ENABLED || !window.RTCPeerConnection) return
  closeRtcPeer()
  rtcPeer = new RTCPeerConnection({ iceServers: [] })
  rtcPeer.onicecandidate = (ev) => {
    if (!ev.candidate) return
    sendMessage({
      type: 'rtc_ice_candidate',
      protocol: PROTOCOL_VERSION,
      candidate: {
        candidate: ev.candidate.candidate,
        sdpMid: ev.candidate.sdpMid,
        sdpMLineIndex: ev.candidate.sdpMLineIndex
      }
    })
  }
  rtcPeer.onconnectionstatechange = () => {
    const state = rtcPeer?.connectionState
    if (state === 'connected') {
      transportActive = 'rtc'
      sendMessage({ type: 'rtc_ready', protocol: PROTOCOL_VERSION, transport: 'rtc' })
    } else if (state === 'failed' || state === 'disconnected' || state === 'closed') {
      transportActive = 'ws'
      rtcFallbackEvents += 1
      sendMessage({ type: 'rtc_failed', protocol: PROTOCOL_VERSION, reason: `state:${state}` })
      scheduleRtcRetry()
    }
  }
  rtcPeer.ondatachannel = (ev) => {
    const channel = ev.channel
    if (channel.label === 'input_unreliable') {
      rtcInputChannel = channel
    } else if (channel.label === 'state_unreliable') {
      rtcStateChannel = channel
      rtcStateChannel.onmessage = (event) => {
        try {
          let parsed: unknown
          if (typeof event.data === 'string') {
            parsed = JSON.parse(event.data)
          } else if (event.data instanceof ArrayBuffer) {
            parsed = RTC_CODEC === 'msgpack' ? msgpackDecode(new Uint8Array(event.data)) : JSON.parse(new TextDecoder().decode(new Uint8Array(event.data)))
          } else if (event.data instanceof Blob) {
            event.data.arrayBuffer().then((buf) => {
              try {
                const decoded = RTC_CODEC === 'msgpack' ? msgpackDecode(new Uint8Array(buf)) : JSON.parse(new TextDecoder().decode(new Uint8Array(buf)))
                if (!isServerMessage(decoded)) return
                handleServerMessage(decoded as ServerMessage)
              } catch {
                // noop
              }
            })
            return
          } else {
            parsed = JSON.parse(String(event.data))
          }
          if (!isServerMessage(parsed)) return
          handleServerMessage(parsed as ServerMessage)
        } catch (err) {
          console.warn('RTC state parse error', err)
        }
      }
      rtcStateChannel.onclose = () => {
        transportActive = 'ws'
        rtcFallbackEvents += 1
        sendMessage({ type: 'rtc_failed', protocol: PROTOCOL_VERSION, reason: 'state_channel_closed' })
      }
    }
  }
  await rtcPeer.setRemoteDescription({ type: 'offer', sdp: msg.sdp })
  const answer = await rtcPeer.createAnswer()
  await rtcPeer.setLocalDescription(answer)
  sendMessage({
    type: 'rtc_answer',
    protocol: PROTOCOL_VERSION,
    sdp: answer.sdp,
    sdp_type: 'answer'
  })
}

function ensureAudioUnlocked() {
  if (audioUnlocked) return
  audioUnlocked = true
  // Prime audio elements after first user gesture.
  ;[SOUND_EXPLOSION, SOUND_EXPLOSION_QD, SOUND_BONUS, SOUND_DEATH, SOUND_QD, SOUND_BIG_EXPLOSION, SOUND_FRESH_MEAT].forEach((src) => {
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

function resetBigExplosionTracking() {
  recentExplosionEvents = []
  bigExplosionOverThreshold = false
  for (const id of bigExplosionSoundTimers) window.clearTimeout(id)
  bigExplosionSoundTimers = []
}

function loudHit(state: GameState) {
  const hit = state.big_blast
  return {
    tiles: hit?.tiles ?? BIG_EXPLOSION_TILE_THRESHOLD,
    windowMs: hit?.window_ms ?? BIG_EXPLOSION_WINDOW_MS,
    delayMs: hit?.delay_ms ?? BIG_EXPLOSION_SOUND_DELAY_MS,
    volume: hit?.volume ?? BIG_EXPLOSION_VOLUME,
  }
}

function scheduleBigExplosionSound(delayMs: number, volume: number) {
  const id = window.setTimeout(() => {
    bigExplosionSoundTimers = bigExplosionSoundTimers.filter((timerId) => timerId !== id)
    playSound(SOUND_BIG_EXPLOSION, volume)
  }, delayMs)
  bigExplosionSoundTimers.push(id)
}

function processAudioEvents(previous: GameState | null, current: GameState) {
  if (shouldResetBigExplosionTracking(current.state)) {
    resetBigExplosionTracking()
  }

  const { keys: newExplosionKeys, newlySeen } = collectNewExplosionKeys(current.explosions, knownExplosionKeys)
  let explosionPlays = 0
  for (const ev of newlySeen) {
    if (explosionPlays < 4) {
      playSound(ev.quadDamage ? SOUND_EXPLOSION_QD : SOUND_EXPLOSION, 0.12)
      explosionPlays += 1
    }
  }
  knownExplosionKeys = newExplosionKeys

  const hit = loudHit(current)
  const cutoff = current.time - hit.windowMs
  recentExplosionEvents = recentExplosionEvents.filter((ev) => ev.startTime >= cutoff)
  const agedCount = uniqueTilesInWindow(recentExplosionEvents, current.time, hit.windowMs)
  bigExplosionOverThreshold = agedCount >= hit.tiles
  if (newlySeen.length) {
    recentExplosionEvents.push(...newlySeen)
    const tileCount = uniqueTilesInWindow(recentExplosionEvents, current.time, hit.windowMs)
    if (crossedBigExplosionThreshold(bigExplosionOverThreshold, tileCount, hit.tiles)) {
      scheduleBigExplosionSound(hit.delayMs, hit.volume)
    }
    bigExplosionOverThreshold = tileCount >= hit.tiles
  }

  if (!previous) return
  const prevPlayers = new Map(previous.players.map((p) => [p.id, p]))
  for (const p of current.players) {
    const prev = prevPlayers.get(p.id)
    if (!prev) continue
    for (const cue of collectPlayerAudioCues(prev, p)) {
      if (cue === 'death') playSound(SOUND_DEATH, 0.12)
      else if (cue === 'qd') playSound(SOUND_QD, 0.12)
      else if (cue === 'bonus') playSound(SOUND_BONUS, 0.1)
    }
    const voiceUntil = p.voice_until ?? 0
    const prevVoice = prev.voice_until ?? 0
    if (voiceUntil > current.time && voiceUntil !== prevVoice) playSound(SOUND_FRESH_MEAT, 0.9)
  }
}

function ingestSnapshot(state: GameState, seq: number, serverTs?: number, recvTs = Date.now()) {
  if (shouldDropSnapshot(latestSeq, seq)) return
  const previous = latestState
  if (typeof serverTs === 'number') {
    const sampleOffset = Date.now() - serverTs
    serverClockOffsetMs = updateServerClockOffset(hasServerClockOffset ? serverClockOffsetMs : null, sampleOffset)
    hasServerClockOffset = true
  }
  if (snapshotBuffer.length > 0) {
    const interval = recvTs - snapshotBuffer[snapshotBuffer.length - 1].recvTs
    if (interval > 0) pushLimited(arrivalIntervalsMs, interval)
  }
  latestState = state
  latestSeq = seq
  processAudioEvents(previous, state)
  snapshotBuffer.push({ seq, recvTs, serverTs, state })
  snapshotBuffer = trimSnapshotBuffer(snapshotBuffer, SNAPSHOT_BUFFER_LIMIT)
}

function snapshotTimelineMs(snapshot: BufferedSnapshot): number {
  if (typeof snapshot.serverTs === 'number' && hasServerClockOffset) {
    return snapshot.serverTs + serverClockOffsetMs
  }
  return snapshot.recvTs
}

function applyLocalPrediction(state: GameState, newestState: GameState): GameState {
  if (!isRegistered || playerIds.length === 0) return state
  if (state.state !== 'playing' && state.state !== 'get_ready') {
    localVisualOffset = { x: 0, y: 0 }
    localPredictionTargetKey = null
    localLastAuthPos = null
    return state
  }
  const idxDisplay = findLocalPredictionIndex(state, clientId, playerIds)
  const idxNewest = findLocalPredictionIndex(newestState, clientId, playerIds)
  if (idxDisplay < 0 || idxNewest < 0) {
    localVisualOffset = { x: 0, y: 0 }
    localPredictionTargetKey = null
    localLastAuthPos = null
    return state
  }
  const localAuth = newestState.players[idxNewest]
  if (!localAuth.alive) {
    localVisualOffset = { x: 0, y: 0 }
    localLastAuthPos = null
    return state
  }
  const targetKey = `${localAuth.owner_client_id ?? 'na'}:${localAuth.owner_client_player_id ?? 'na'}`
  if (localPredictionTargetKey !== targetKey) {
    localPredictionTargetKey = targetKey
    localVisualOffset = { x: 0, y: 0 }
    localLastAuthPos = null
  }

  const boardCols = state.board[0]?.length ?? 0
  const boardRows = state.board.length
  const maxX = boardCols * 100
  const maxY = boardRows * 100
  const prevAuth = localLastAuthPos
  const authMoveDist = prevAuth ? Math.hypot(localAuth.x - prevAuth.x, localAuth.y - prevAuth.y) : 0
  localLastAuthPos = { x: localAuth.x, y: localAuth.y }

  let dx = 0
  let dy = 0
  if (keys.up) dy -= 1
  if (keys.down) dy += 1
  if (keys.left) dx -= 1
  if (keys.right) dx += 1
  const length = Math.hypot(dx, dy)
  if (length > 1e-6) {
    dx /= length
    dy /= length
  }

  const inputActive = length > 1e-6
  // When blocked against walls/bombs, remove almost all local lead to prevent jumpy corrections.
  const blocked = inputActive && authMoveDist < 1.5
  const maxOffset = transportActive === 'rtc' ? LOCAL_PREDICTION_MAX_OFFSET_RTC_PX : LOCAL_PREDICTION_MAX_OFFSET_PX
  const targetMag = blocked ? 2.0 : maxOffset
  const targetOffsetX = inputActive ? dx * targetMag : 0
  const targetOffsetY = inputActive ? dy * targetMag : 0
  localVisualOffset.x += (targetOffsetX - localVisualOffset.x) * LOCAL_PREDICTION_LERP
  localVisualOffset.y += (targetOffsetY - localVisualOffset.y) * LOCAL_PREDICTION_LERP

  const predictedX = clamp(localAuth.x + localVisualOffset.x, 0, maxX)
  const predictedY = clamp(localAuth.y + localVisualOffset.y, 0, maxY)
  const errDist = Math.hypot(predictedX - localAuth.x, predictedY - localAuth.y)
  pushLimited(localPredictionErrorPx, errDist, 300)

  const predictedPlayers = state.players.map((p, i) =>
    i === idxDisplay ? { ...p, x: predictedX, y: predictedY } : p
  )
  return { ...state, players: predictedPlayers }
}

function getRenderDelayMs(): number {
  const result = computeRenderDelayMs({
    intervals: arrivalIntervalsMs,
    transportActive,
    strictInputMode: STRICT_INPUT_MODE,
    smoothed: smoothedRenderDelayMs
  })
  smoothedRenderDelayMs = result.smoothed
  return result.delay
}

function renderSlots(msg: SlotListMessage) {
  slotContainerEl.innerHTML = ''
  const keys = Object.keys(msg.slots).sort((a, b) => Number(a) - Number(b))
  for (const key of keys) {
    const i = Number(key)
    const isTaken = msg.slots[key] === true
    const reason = msg.slot_reasons?.[key]
    const btn = document.createElement('button')
    btn.className = `slot-btn ${isTaken ? 'taken' : ''}`
    btn.dataset.slot = key
    btn.disabled = isTaken
    const label = slotButtonLabel(isTaken, reason)
    btn.innerHTML = `<span class="slot-id">P${i}</span><span class="slot-label">${label}</span>`
    slotContainerEl.appendChild(btn)
  }
  const threshold = msg.trophy_win_threshold ?? 3
  const kicker = document.getElementById('lobby-kicker')
  const help = document.getElementById('lobby-help')
  if (kicker) kicker.textContent = `First to ${threshold} trophies`
  if (help) {
    help.textContent = `Pick a display name, choose a color slot, then join. Match stats accumulate until someone claims ${threshold} trophies.`
  }
}

function getPlayerName(): string {
  return clipDisplayName(playerNameInputEl.value)
}

function startHeartbeat() {
  if (pingTimer) clearInterval(pingTimer)
  pingTimer = setInterval(() => {
    sendMessage({ type: 'ping', protocol: PROTOCOL_VERSION, ts: Date.now() })
  }, PING_INTERVAL_MS)
}

function handleServerMessage(msg: ServerMessage) {
  if (msg.type === 'client_id') {
    clientId = msg.client_id
    return
  }

  if (msg.type === 'hello_ack') {
    const ack = msg as HelloAckMessage
    const negotiated = ack.ws_codec ?? ack.encoding
    if (negotiated === 'msgpack' || negotiated === 'json') {
      wsCodec = negotiated
    }
    if (ack.webrtc_offered && RTC_ENABLED && !!window.RTCPeerConnection) {
      statusDivEl.textContent = 'Connected. Negotiating low-latency transport...'
    }
    return
  }

  if (msg.type === 'rtc_offer') {
    void handleRtcOffer(msg as RtcOfferMessage)
    return
  }

  if (msg.type === 'rtc_ice_candidate') {
    const iceMsg = msg as RtcIceCandidateMessage
    if (rtcPeer && iceMsg.candidate?.candidate) {
      void rtcPeer.addIceCandidate({
        candidate: iceMsg.candidate.candidate,
        sdpMid: iceMsg.candidate.sdpMid ?? null,
        sdpMLineIndex: iceMsg.candidate.sdpMLineIndex ?? null
      }).catch(() => {})
    }
    return
  }

  if (msg.type === 'rtc_ready') {
    const rtcReadyMsg = msg as RtcReadyMessage
    if (rtcReadyMsg.transport === 'rtc') {
      transportActive = 'rtc'
    }
    return
  }

  if (msg.type === 'rtc_failed') {
    const rtcFailed = msg as RtcFailedMessage
    console.warn('RTC failed, using websocket fallback:', rtcFailed.reason)
    transportActive = 'ws'
    rtcFallbackEvents += 1
    scheduleRtcRetry()
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
    localVisualOffset = { x: 0, y: 0 }
    localPredictionErrorPx = []
    localPredictionTargetKey = null
    localLastAuthPos = null
    lobbyOverlayEl.classList.add('hidden')
    statusDivEl.textContent = `Playing as P${confirmed.slot}`
    return
  }

  if (msg.type === 'registration_rejected') {
    const rejected = msg as RegistrationRejectedMessage
    lobbyStatusEl.textContent = `Error: ${rejected.message}`
    lobbyOverlayEl.classList.remove('hidden')
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
      requestKeyframe()
      return
    }
    const merged = mergeDelta(latestState, deltaMsg.delta)
    ingestSnapshot(merged, deltaMsg.seq, deltaMsg.server_timestamp)
    return
  }

  if (msg.type === 'state_keepalive') {
    const keep = msg as StateKeepaliveMessage
    if (!isRegistered) return
    if (!latestState) {
      requestKeyframe()
      return
    }
    if (shouldDropSnapshot(latestSeq, keep.seq)) return
    if (latestState) {
      latestState = applyKeepalive(latestState, keep)
    }
    latestSeq = keep.seq
    if (snapshotBuffer.length > 0) {
      const last = snapshotBuffer[snapshotBuffer.length - 1]
      last.state = applyKeepalive(last.state, keep)
      last.seq = keep.seq
      last.recvTs = Date.now()
      if (typeof keep.server_timestamp === 'number') last.serverTs = keep.server_timestamp
    }
    return
  }

  if (msg.type === 'net_metrics') {
    const metricsMsg = msg as NetMetricsMessage
    latestHudMetrics = metricsMsg.metrics
    if (latestState) {
      latestState = { ...latestState, _net_metrics: metricsMsg.metrics }
    }
    return
  }

  if (msg.type === 'input_ack') {
    const now = Date.now()
    const original = msg.original_timestamp
    if (typeof original === 'number') {
      const sample = sampleRttMs(original, now)
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
}

function handleMessage(raw: unknown) {
  void (async () => {
    try {
      const decodeStart = performance.now()
      const parsed = await decodeIncomingWsData(raw)
      if (!isServerMessage(parsed)) return
      pushLimited(decodeSamplesMs, performance.now() - decodeStart)
      handleServerMessage(parsed as ServerMessage)
    } catch (e) {
      console.error('Error parsing message:', e)
    }
  })()
}

function connectWebSocket() {
  const wsUrl = getWsUrl()
  ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    reconnectAttempts = 0
    wsCodec = 'json'
    latestHudMetrics = undefined
    statusDivEl.textContent = 'Connected. Waiting for lobby...'
    lobbyStatusEl.textContent = 'Connected. Requesting slots...'
    if (pendingSlotSelection === null) {
      lobbyOverlayEl.classList.remove('hidden')
    }
    snapshotBuffer = []
    latestState = null
    latestSeq = -1
    localInputTick = 0
    localVisualOffset = { x: 0, y: 0 }
    localPredictionErrorPx = []
    localPredictionTargetKey = null
    localLastAuthPos = null
    transportActive = 'ws'
    knownExplosionKeys = new Set()
    resetBigExplosionTracking()
    sendMessage({
      type: 'hello',
      protocol: PROTOCOL_VERSION,
      ts: Date.now(),
      webrtc_supported: RTC_ENABLED && !!window.RTCPeerConnection,
      rtc_codec: RTC_CODEC,
      encoding: WS_CODEC_PREF,
      ws_codec: WS_CODEC_PREF,
      strict_input_mode: STRICT_INPUT_MODE
    })
    if (currentPlayerName) {
      sendMessage({ type: 'set_name', protocol: PROTOCOL_VERSION, name: currentPlayerName })
    }
    sendMessage({ type: 'request_slot_list', protocol: PROTOCOL_VERSION })
    if (pendingSlotSelection !== null) {
      sendMessage({ type: 'select_slot', slot: pendingSlotSelection, protocol: PROTOCOL_VERSION, name: currentPlayerName })
    }
    startHeartbeat()
  }

  ws.onmessage = (event) => handleMessage(event.data)

  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
    statusDivEl.textContent = 'Connection Error'
  }

  ws.onclose = () => {
    statusDivEl.textContent = 'Disconnected. Reconnecting...'
    isRegistered = false
    closeRtcPeer()
    if (pingTimer) {
      clearInterval(pingTimer)
      pingTimer = null
    }
    reconnectAttempts += 1
    snapshotBuffer = []
    latestState = null
    latestSeq = -1
    localInputTick = 0
    localVisualOffset = { x: 0, y: 0 }
    localPredictionErrorPx = []
    localPredictionTargetKey = null
    localLastAuthPos = null
    transportActive = 'ws'
    knownExplosionKeys = new Set()
    resetBigExplosionTracking()
    const waitMs = reconnectWaitMs(reconnectAttempts, RECONNECT_BASE_MS, RECONNECT_MAX_MS)
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

function applyRenderToggleState() {
  renderEnabled = renderToggleEl.checked
  canvasEl.classList.toggle('hidden', !renderEnabled)
  stateOnlyEl.classList.toggle('hidden', renderEnabled)
}
applyRenderToggleState()
renderToggleEl.addEventListener('change', applyRenderToggleState)

function updateKey(code: string, pressed: boolean) {
  const result = applyKeyCode(keys, code, pressed)
  keys.up = result.keys.up
  keys.down = result.keys.down
  keys.left = result.keys.left
  keys.right = result.keys.right
  keys.bomb = result.keys.bomb
  if (result.changed) {
    keysDirty = true
    maybeSendInput(true)
  }
}

function maybeSendInput(force = false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  if (clientId === null || !isRegistered || playerIds.length === 0) return
  const now = Date.now()
  const minDeltaMs = 1000 / MAX_SEND_FPS
  const hash = hashInput(keys)
  if (!shouldSendInput({
    force,
    now,
    lastSentAt: lastInputSentAt,
    keysDirty,
    hash,
    lastHash: lastInputHash,
    minDeltaMs,
    heartbeatMs: INPUT_HEARTBEAT_MS
  })) return

  const playerId = playerIds[0]
  const hostTick = latestState?._sim_tick ?? latestState?._net_metrics?.sim_tick
  const tickId = resolveInputTickId(hostTick, localInputTick)
  const payload = buildGameInputPayload({
    protocol: PROTOCOL_VERSION,
    clientId,
    playerId,
    keys,
    tickId,
    timestamp: now
  })
  if (isRtcInputReady()) {
    try {
      if (RTC_CODEC === 'msgpack') {
        rtcInputChannel!.send(msgpackEncode(payload))
      } else {
        rtcInputChannel!.send(JSON.stringify(payload))
      }
    } catch {
      transportActive = 'ws'
      rtcFallbackEvents += 1
      sendMessage(payload)
    }
  } else {
    sendMessage(payload)
  }

  lastInputSentAt = now
  keysDirty = false
  lastInputHash = hash
  localInputTick += 1
}

function isDocumentFullscreen(): boolean {
  return document.fullscreenElement != null
}

async function toggleGameFullscreen() {
  const root = document.documentElement
  if (isDocumentFullscreen()) {
    await document.exitFullscreen()
    return
  }
  await root.requestFullscreen()
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !keysOverlayEl.classList.contains('hidden')) {
    e.preventDefault()
    hideKeysScreen()
    return
  }
  if (e.code === 'F11') {
    e.preventDefault()
    void toggleGameFullscreen().then(() => renderer.fitCanvasToViewport()).catch(() => renderer.fitCanvasToViewport())
    return
  }
  updateKey(e.code, true)
})
document.addEventListener('fullscreenchange', () => renderer.fitCanvasToViewport())
window.addEventListener('keyup', (e) => updateKey(e.code, false))

function loop(ts: number) {
  const renderIntervalMs = 1000 / MAX_RENDER_FPS
  const canRenderNow = (ts - lastRenderDrawTs) >= renderIntervalMs
  if (canRenderNow) {
    frameTimes5s.push(ts)
    const cutoff = ts - 5000
    frameTimes5s = frameTimes5s.filter((t) => t >= cutoff)
    if (frameTimes5s.length > 1) {
      const span = frameTimes5s[frameTimes5s.length - 1] - frameTimes5s[0]
      avgClientFps5s = span > 0 ? ((frameTimes5s.length - 1) * 1000) / span : 0
    } else {
      avgClientFps5s = 0
    }
  }

  if (ts - lastRenderLoopTs >= (1000 / MAX_SEND_FPS)) {
    maybeSendInput(false)
    lastRenderLoopTs = ts
  }
  if (canRenderNow && snapshotBuffer.length > 0 && latestState) {
    const frameStartPerf = performance.now()
    const frameNow = Date.now()
    const delayMs = getRenderDelayMs()
    const renderTarget = frameNow - delayMs
    const newest = snapshotBuffer[snapshotBuffer.length - 1]
    if (frameNow - newest.recvTs > KEYFRAME_STALE_MS) {
      snapshotBuffer = [newest]
    }
    while (snapshotBuffer.length > 2 && snapshotTimelineMs(snapshotBuffer[1]) <= renderTarget) {
      snapshotBuffer.shift()
    }

    let displayState = newest.state
    if (snapshotBuffer.length >= 2) {
      let idx = 1
      while (idx < snapshotBuffer.length && snapshotTimelineMs(snapshotBuffer[idx]) < renderTarget) idx += 1
      const right = snapshotBuffer[Math.min(snapshotBuffer.length - 1, idx)]
      const left = snapshotBuffer[Math.max(0, idx - 1)]
      const rightTs = snapshotTimelineMs(right)
      const leftTs = snapshotTimelineMs(left)
      if (rightTs > leftTs && renderTarget >= leftTs && renderTarget <= rightTs) {
        const alpha = (renderTarget - leftTs) / (rightTs - leftTs)
        displayState = interpolateState(left.state, right.state, alpha)
      } else if (renderTarget < leftTs) {
        displayState = left.state
      } else {
        const prev = snapshotBuffer[Math.max(0, snapshotBuffer.length - 2)]
        const newestTs = snapshotTimelineMs(right)
        displayState = extrapolateState(prev.state, right.state, renderTarget - newestTs)
      }
    }

    const hostFps = latestHudMetrics?.host_fps_5s ?? displayState._net_metrics?.host_fps_5s
    const hostRenderFps = latestHudMetrics?.host_render_fps_5s ?? displayState._net_metrics?.host_render_fps_5s
    const queueDelayP95 = latestHudMetrics?.input_queue_delay_p95_ms ?? latestHudMetrics?.input_apply_p95_ms
    pushLimited(presentDelaySamplesMs, samplePresentAgeMs(newest.recvTs, frameNow))

    if (renderEnabled) {
      const predictedState = applyLocalPrediction(displayState, newest.state)
      const debugText = renderer.render(predictedState, {
        latency5sMs: avgLatency5sMs,
        fps5s: avgClientFps5s,
        hostFps5s: hostFps,
        hostRenderFps5s: hostRenderFps,
        renderPipelineP95Ms: percentile(pipelineSamplesMs, 95),
        presentDelayP95Ms: percentile(presentDelaySamplesMs, 95),
        decodeP95Ms: percentile(decodeSamplesMs, 95),
        localCorrectionP95Px: percentile(localPredictionErrorPx, 95),
        queueDelayP95Ms: queueDelayP95
      })
      debugLineEl.textContent = debugText
      const jitterMs = Math.max(0, (percentile(arrivalIntervalsMs, 95) || 0) - (percentile(arrivalIntervalsMs, 50) || 0))
      const simTick = predictedState._sim_tick ?? latestHudMetrics?.sim_tick ?? predictedState._net_metrics?.sim_tick ?? 0
      statusDivEl.textContent = `Transport: ${transportActive.toUpperCase()} | RTT(5s): ${avgLatency5sMs.toFixed(1)} ms | Jitter: ${jitterMs.toFixed(1)} ms | Tick: ${simTick} | Strict: ${STRICT_INPUT_MODE ? 'ON' : 'OFF'} | Fallbacks: ${rtcFallbackEvents}`
    } else {
      const latencyText = `RTT(5s): ${avgLatency5sMs.toFixed(1)} ms`
      const fpsText = `Client FPS(5s): ${avgClientFps5s.toFixed(1)}`
      const hostFpsText = `Host SIM FPS(5s): ${(hostFps ?? 0).toFixed(1)}`
      const presentDelayText = `PresentAge p95: ${percentile(presentDelaySamplesMs, 95).toFixed(1)} ms`
      const decodeText = `Decode p95: ${percentile(decodeSamplesMs, 95).toFixed(2)} ms`
      stateOnlyEl.textContent = `${humanStateName(displayState.state)} | ${latencyText} | ${fpsText} | ${hostFpsText} | ${presentDelayText} | ${decodeText}`
      debugLineEl.textContent = stateOnlyEl.textContent
    }
    pushLimited(pipelineSamplesMs, performance.now() - frameStartPerf)
    lastRenderDrawTs = ts
  }
  requestAnimationFrame(loop)
}

connectWebSocket()
requestAnimationFrame(loop)

window.addEventListener('keydown', ensureAudioUnlocked, { once: true })
window.addEventListener('pointerdown', ensureAudioUnlocked, { once: true })

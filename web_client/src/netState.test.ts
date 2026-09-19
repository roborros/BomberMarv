import { describe, expect, it } from 'vitest'
import {
  clipDisplayName,
  cloneState,
  computeRenderDelayMs,
  extrapolateState,
  humanStateName,
  interpolateState,
  interpolatePlayer,
  localPredictionTargetMagnitude,
  mergeDelta,
  applyKeepalive,
  applyBoardPatches,
  applyPlayerDelta,
  TELEPORT_SNAP_PX,
  predictedLocalPosition,
  resolveLocalPredictionTargetIndex,
  shouldDropSnapshot,
  slotButtonLabel,
  trimSnapshotBuffer,
  updateServerClockOffset
} from './netState'
import { samplePlayer, sampleState } from './testFixtures'

describe('netState', () => {
  it('cloneState copies nested collections', () => {
    const original = sampleState({
      players: [samplePlayer({ x: 10 })],
      explosions: [{ cells: [[1, 1], [2, 1]], start_time: 1, quad_damage: false }]
    })
    const cloned = cloneState(original)
    cloned.board[1][1] = 2
    cloned.players[0].x = 99
    cloned.explosions[0].cells[0][0] = 9
    expect(original.board[1][1]).toBe(0)
    expect(original.players[0].x).toBe(10)
    expect(original.explosions[0].cells[0][0]).toBe(1)
  })

  it('mergeDelta applies gameplay and net fields', () => {
    const merged = mergeDelta(sampleState(), {
      time: 2000,
      boss_fight_winner: { name: 'Boss', is_ai: true, color: [1, 2, 3] },
      local_player_count: 2,
      _sim_tick: 11,
      _net_metrics: { host_fps_5s: 60 }
    })
    expect(merged.time).toBe(2000)
    expect(merged.boss_fight_winner?.name).toBe('Boss')
    expect(merged.local_player_count).toBe(2)
    expect(merged._sim_tick).toBe(11)
    expect(merged._net_metrics?.host_fps_5s).toBe(60)
    expect(merged.state).toBe('playing')
  })

  it('merges player and board patches without replacing the whole lists', () => {
    const merged = mergeDelta(sampleState({
      players: [samplePlayer({ id: 1, x: 10, y: 20 }), samplePlayer({ id: 2, x: 30, y: 40 })],
      board: [
        [1, 1, 1],
        [1, 0, 1],
        [1, 1, 1]
      ]
    }), {
      player_patches: [{ id: 2, x: 50 }],
      player_removed: [],
      board_patches: [[1, 1, 2]]
    })
    expect(merged.players[0].x).toBe(10)
    expect(merged.players[1].x).toBe(50)
    expect(merged.board[1][1]).toBe(2)
    const upserted = applyPlayerDelta([samplePlayer({ id: 1, x: 1 })], {
      player_patches: [samplePlayer({ id: 3, x: 9, y: 8, name: 'New' })]
    })
    expect(upserted.map((p) => p.id)).toEqual([1, 3])
    expect(applyBoardPatches([[0, 0], [0, 0]], [[1, 0, 2]])).toEqual([[0, 2], [0, 0]])
    const dropped = mergeDelta(sampleState({
      players: [samplePlayer({ id: 1 }), samplePlayer({ id: 2 })]
    }), { player_removed: [1] })
    expect(dropped.players.map((p) => p.id)).toEqual([2])
  })

  it('applies keepalive clock fields without replacing the board', () => {
    const next = applyKeepalive(sampleState({ time: 100, _sim_tick: 4 }), {
      time: 140,
      _sim_tick: 6,
      _host_published_at_ms: 9
    })
    expect(next.time).toBe(140)
    expect(next._sim_tick).toBe(6)
    expect(next._host_published_at_ms).toBe(9)
    expect(next.board).toEqual(sampleState().board)
    expect(next.players[0].x).toBe(150)
  })

  it('interpolates player positions and time', () => {
    const a = sampleState({ time: 0, players: [samplePlayer({ id: 1, x: 0, y: 0 })] })
    const b = sampleState({ time: 100, players: [samplePlayer({ id: 1, x: 100, y: 50 })] })
    const mid = interpolateState(a, b, 0.5)
    expect(mid.time).toBe(50)
    expect(mid.players[0].x).toBe(50)
    expect(mid.players[0].y).toBe(25)
  })

  it('lerps direction and snaps teleports or deaths', () => {
    const mid = interpolatePlayer(
      samplePlayer({ id: 1, x: 0, y: 0, direction: [0, 0] }),
      samplePlayer({ id: 1, x: 10, y: 0, direction: [1, 0] }),
      0.5
    )
    expect(mid.x).toBe(5)
    expect(mid.direction[0]).toBe(0.5)
    const teleported = interpolatePlayer(
      samplePlayer({ id: 1, x: 0, y: 0 }),
      samplePlayer({ id: 1, x: TELEPORT_SNAP_PX + 1, y: 0 }),
      0.5
    )
    expect(teleported.x).toBe(TELEPORT_SNAP_PX + 1)
    const dead = interpolatePlayer(
      samplePlayer({ id: 1, x: 0, alive: false }),
      samplePlayer({ id: 1, x: 40, alive: false }),
      0.5
    )
    expect(dead.x).toBe(40)
  })

  it('extrapolates alive players and clamps to the board', () => {
    const previous = sampleState({ time: 0, players: [samplePlayer({ id: 1, x: 150, y: 150 })] })
    const latest = sampleState({
      time: 20,
      board: Array.from({ length: 3 }, () => [0, 0, 0]),
      players: [samplePlayer({ id: 1, x: 170, y: 150 })]
    })
    const next = extrapolateState(previous, latest, 20)
    expect(next.players[0].x).toBe(190)
    expect(next.time).toBe(40)
    const dead = extrapolateState(
      previous,
      { ...latest, players: [samplePlayer({ id: 1, x: 170, y: 150, alive: false })] },
      20
    )
    expect(dead.players[0].x).toBe(170)
  })

  it('drops stale snapshots and trims the buffer', () => {
    expect(shouldDropSnapshot(-1, 0)).toBe(false)
    expect(shouldDropSnapshot(4, 4)).toBe(true)
    expect(shouldDropSnapshot(4, 3)).toBe(true)
    expect(shouldDropSnapshot(4, 5)).toBe(false)
    expect(trimSnapshotBuffer([1, 2, 3, 4], 2)).toEqual([3, 4])
    expect(trimSnapshotBuffer([1, 2], 8)).toEqual([1, 2])
  })

  it('smooths server clock offset', () => {
    expect(updateServerClockOffset(null, 40)).toBe(40)
    expect(updateServerClockOffset(40, 0)).toBe(36)
  })

  it('keeps render delay inside transport bounds', () => {
    const ws = computeRenderDelayMs({
      intervals: Array(20).fill(16),
      transportActive: 'ws',
      strictInputMode: false,
      smoothed: 10
    })
    expect(ws.delay).toBeGreaterThanOrEqual(6)
    expect(ws.delay).toBeLessThanOrEqual(22)
    const rtc = computeRenderDelayMs({
      intervals: Array(20).fill(4),
      transportActive: 'rtc',
      strictInputMode: false,
      smoothed: 8
    })
    expect(rtc.delay).toBeLessThanOrEqual(14)
  })

  it('resolves the owned local player', () => {
    const state = sampleState({
      players: [
        samplePlayer({ id: 1, owner_client_id: 9, owner_client_player_id: 2 }),
        samplePlayer({ id: 2, owner_client_id: 9, owner_client_player_id: 1 })
      ]
    })
    expect(resolveLocalPredictionTargetIndex(state, 9, [1])).toBe(1)
    expect(resolveLocalPredictionTargetIndex(state, null, [1])).toBe(-1)
  })

  it('reduces local prediction lead when blocked', () => {
    expect(localPredictionTargetMagnitude({ inputActive: false, blocked: false, transportActive: 'ws' })).toBe(0)
    expect(localPredictionTargetMagnitude({ inputActive: true, blocked: true, transportActive: 'ws' })).toBe(2)
    expect(localPredictionTargetMagnitude({ inputActive: true, blocked: false, transportActive: 'rtc' })).toBe(6)
    const pos = predictedLocalPosition({
      authX: 10,
      authY: 10,
      offsetX: 1000,
      offsetY: -1000,
      boardCols: 2,
      boardRows: 2
    })
    expect(pos.x).toBe(200)
    expect(pos.y).toBe(0)
  })

  it('maps lobby labels and human-readable states', () => {
    expect(slotButtonLabel(false)).toBe('Join')
    expect(slotButtonLabel(true, 'local')).toBe('Local')
    expect(slotButtonLabel(true, 'remote')).toBe('Remote')
    expect(humanStateName('champion')).toBe('Champion! Press Enter to fight BomberMarv.')
    expect(humanStateName('nope')).toBe('Waiting for game state...')
    expect(clipDisplayName('  abcdefghijklmnopqrstuvwxyz  ')).toHaveLength(20)
  })
})

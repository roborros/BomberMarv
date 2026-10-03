import { describe, expect, it } from 'vitest'
import {
  applyKeyCode,
  buildGameInputPayload,
  deriveKeys,
  emptyKeys,
  hashInput,
  inputDirection,
  resolveInputTickId,
  shouldSendInput
} from './input'

describe('input', () => {
  it('hashes sticky key state', () => {
    expect(hashInput(emptyKeys())).toBe('00000')
    expect(hashInput({ ...emptyKeys(), up: true, bomb: true })).toBe('10001')
  })

  it('maps arrow and WASD codes', () => {
    let keys = emptyKeys()
    keys = applyKeyCode(keys, 'ArrowUp', true).keys
    keys = applyKeyCode(keys, 'KeyD', true).keys
    expect(keys.up).toBe(true)
    expect(keys.right).toBe(true)
    const released = applyKeyCode(keys, 'ArrowUp', false)
    expect(released.changed).toBe(true)
    expect(released.keys.up).toBe(false)
  })

  it('keeps moving when one of two keys for the same direction is released', () => {
    const held = new Set(['ArrowUp', 'KeyW', 'KeyD'])
    expect(deriveKeys(held).up).toBe(true)
    expect(deriveKeys(held).right).toBe(true)
    held.delete('KeyW')
    expect(deriveKeys(held).up).toBe(true)
    held.delete('ArrowUp')
    expect(deriveKeys(held).up).toBe(false)
    expect(deriveKeys(held).right).toBe(true)
    expect(deriveKeys(['Space']).bomb).toBe(true)
  })

  it('treats Space and Enter as bomb', () => {
    expect(applyKeyCode(emptyKeys(), 'Space', true).keys.bomb).toBe(true)
    expect(applyKeyCode(emptyKeys(), 'Enter', true).keys.bomb).toBe(true)
  })

  it('ignores unknown codes', () => {
    const result = applyKeyCode(emptyKeys(), 'Escape', true)
    expect(result.changed).toBe(false)
    expect(result.keys).toEqual(emptyKeys())
  })

  it('sends immediately when forced', () => {
    expect(shouldSendInput({
      force: true,
      now: 10,
      lastSentAt: 10,
      keysDirty: false,
      hash: '00000',
      lastHash: '00000',
      minDeltaMs: 16,
      heartbeatMs: 120
    })).toBe(true)
  })

  it('rate-limits unchanged input until heartbeat', () => {
    const base = {
      force: false,
      now: 50,
      lastSentAt: 40,
      keysDirty: true,
      hash: '10000',
      lastHash: '00000',
      minDeltaMs: 16,
      heartbeatMs: 120
    }
    expect(shouldSendInput(base)).toBe(false)
    expect(shouldSendInput({ ...base, now: 60 })).toBe(true)
    expect(shouldSendInput({ ...base, now: 200, keysDirty: false, hash: '00000', lastHash: '00000' })).toBe(true)
    expect(shouldSendInput({ ...base, now: 60, keysDirty: false, hash: '00000', lastHash: '00000' })).toBe(false)
  })

  it('prefers host tick ids', () => {
    expect(resolveInputTickId(42, 3)).toBe(42)
    expect(resolveInputTickId(undefined, 3)).toBe(3)
  })

  it('builds protocol v2 game_input payloads', () => {
    const payload = buildGameInputPayload({
      protocol: 2,
      clientId: 4,
      playerId: 1,
      keys: { up: true, down: false, left: false, right: true, bomb: false },
      tickId: 9,
      timestamp: 123
    })
    expect(payload.type).toBe('game_input')
    expect(payload.input).toEqual([4, 1, 1, 0, 0, 1, 0])
    expect(payload.input_frame.right).toBe(1)
    expect(payload.tick_id).toBe(9)
  })

  it('normalizes diagonal movement', () => {
    const dir = inputDirection({ up: true, down: false, left: false, right: true, bomb: false })
    expect(dir.active).toBe(true)
    expect(Math.abs(Math.hypot(dir.dx, dir.dy) - 1)).toBeLessThan(1e-6)
    expect(inputDirection(emptyKeys()).active).toBe(false)
  })
})

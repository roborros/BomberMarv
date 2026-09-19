import { describe, expect, it } from 'vitest'
import { isServerMessage } from './types'

describe('isServerMessage', () => {
  it('accepts objects with a string type', () => {
    expect(isServerMessage({ type: 'pong' })).toBe(true)
    expect(isServerMessage({ type: 'gamestate', data: {} })).toBe(true)
  })

  it('rejects non-objects and missing types', () => {
    expect(isServerMessage(null)).toBe(false)
    expect(isServerMessage('pong')).toBe(false)
    expect(isServerMessage({ kind: 'pong' })).toBe(false)
    expect(isServerMessage({ type: 2 })).toBe(false)
  })
})

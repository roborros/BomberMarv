import { describe, expect, it } from 'vitest'
import { computeBoardSignature } from './boardHash'

describe('boardHash', () => {
  it('returns empty for missing boards', () => {
    expect(computeBoardSignature([])).toBe('empty')
  })

  it('is stable for the same board', () => {
    const board = [[1, 0], [0, 2]]
    expect(computeBoardSignature(board)).toBe(computeBoardSignature(board))
  })

  it('changes when a cell changes', () => {
    const a = [[1, 0], [0, 2]]
    const b = [[1, 0], [0, 1]]
    expect(computeBoardSignature(a)).not.toBe(computeBoardSignature(b))
  })

  it('includes dimensions in the signature', () => {
    expect(computeBoardSignature([[0, 0]]).startsWith('1x2:')).toBe(true)
    expect(computeBoardSignature([[0], [0]]).startsWith('2x1:')).toBe(true)
  })

  it('hashes cells in place without flattening', () => {
    const proto = Array.prototype as { flat: (...args: unknown[]) => unknown[] }
    const originalFlat = proto.flat
    let flattened = false
    proto.flat = function (this: unknown, ...args: unknown[]) {
      flattened = true
      return originalFlat.apply(this, args)
    }
    try {
      const board = [[1, 2], [3, 4]]
      const signature = computeBoardSignature(board)
      expect(flattened).toBe(false)
      expect(board).toEqual([[1, 2], [3, 4]])
      expect(signature.startsWith('2x2:')).toBe(true)
    } finally {
      proto.flat = originalFlat
    }
  })
})

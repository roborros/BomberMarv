import { describe, expect, it } from 'vitest'
import { clamp, percentile, pushLimited, reconnectWaitMs } from './math'

describe('math', () => {
  it('clamps to the inclusive range', () => {
    expect(clamp(5, 0, 10)).toBe(5)
    expect(clamp(-2, 0, 10)).toBe(0)
    expect(clamp(99, 0, 10)).toBe(10)
  })

  it('returns 0 for empty percentile samples', () => {
    expect(percentile([], 50)).toBe(0)
  })

  it('uses nearest-rank indices', () => {
    expect(percentile([1, 2, 3, 4, 5], 0)).toBe(1)
    expect(percentile([1, 2, 3, 4, 5], 50)).toBe(3)
    expect(percentile([1, 2, 3, 4, 5], 100)).toBe(5)
  })

  it('does not mutate the original percentile array', () => {
    const values = [5, 1, 3]
    percentile(values, 50)
    expect(values).toEqual([5, 1, 3])
  })

  it('trims pushLimited to the max length', () => {
    const target: number[] = []
    for (let i = 0; i < 5; i++) pushLimited(target, i, 3)
    expect(target).toEqual([2, 3, 4])
  })

  it('uses exponential reconnect backoff capped at max', () => {
    expect(reconnectWaitMs(1, 500, 6000)).toBe(500)
    expect(reconnectWaitMs(2, 500, 6000)).toBe(1000)
    expect(reconnectWaitMs(5, 500, 6000)).toBe(6000)
    expect(reconnectWaitMs(0, 500, 6000)).toBe(500)
  })
})

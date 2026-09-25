import { describe, expect, it } from 'vitest'
import { samplePresentAgeMs, sampleQueueDelayMs, sampleRttMs } from './latency'

describe('latency samples', () => {
  it('computes same-clock RTT and clamps negatives', () => {
    expect(sampleRttMs(10, 25)).toBe(15)
    expect(sampleRttMs(40, 10)).toBe(0)
    expect(sampleRttMs(Number.NaN, 10)).toBe(0)
  })

  it('measures present age from receive time, not host clock', () => {
    expect(samplePresentAgeMs(1000, 1016)).toBe(16)
    expect(samplePresentAgeMs(2000, 1990)).toBe(0)
  })

  it('measures queue delay without mixing clocks', () => {
    expect(sampleQueueDelayMs(100, 108)).toBe(8)
    expect(sampleQueueDelayMs(120, 100)).toBe(0)
  })
})

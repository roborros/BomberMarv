import { describe, expect, it } from 'vitest'
import { computeCanvasBackingStore } from './canvasScale'

describe('computeCanvasBackingStore', () => {
  it('shrinks backing store when the board is CSS-scaled down', () => {
    const store = computeCanvasBackingStore({
      worldWidth: 2100,
      worldHeight: 2100,
      viewportWidth: 940,
      viewportHeight: 900,
      devicePixelRatio: 1
    })
    expect(store.cssWidth).toBeLessThan(2100)
    expect(store.backingWidth).toBe(store.cssWidth)
    expect(store.backingWidth).toBeLessThan(2100)
    expect(store.worldToBackingX).toBeCloseTo(store.backingWidth / 2100)
  })

  it('caps device pixel ratio and never uses a zero size', () => {
    const store = computeCanvasBackingStore({
      worldWidth: 2100,
      worldHeight: 2100,
      viewportWidth: 2000,
      viewportHeight: 2000,
      devicePixelRatio: 3
    })
    expect(store.cssScale).toBeLessThanOrEqual(1)
    expect(store.backingWidth).toBe(store.cssWidth * 2)
    const empty = computeCanvasBackingStore({
      worldWidth: 0,
      worldHeight: 0,
      viewportWidth: 10,
      viewportHeight: 10,
      devicePixelRatio: 0
    })
    expect(empty.backingWidth).toBeGreaterThan(0)
    expect(empty.backingHeight).toBeGreaterThan(0)
  })
})

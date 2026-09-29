import { describe, expect, it } from 'vitest'
import { canvasFitBox, computeCanvasBackingStore, visibleViewportSize } from './canvasScale'

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

  it('keeps the whole board inside a short fullscreen monitor', () => {
    const store = computeCanvasBackingStore({
      worldWidth: 2100,
      worldHeight: 2100,
      viewportWidth: 1280,
      viewportHeight: 720,
      devicePixelRatio: 1.5,
      horizontalPad: 0,
      verticalPad: 0
    })
    expect(store.cssWidth).toBeLessThanOrEqual(1280)
    expect(store.cssHeight).toBeLessThanOrEqual(720)
    expect(store.cssWidth).toBe(store.cssHeight)
  })

  it('does not force a minimum larger than the screen', () => {
    const store = computeCanvasBackingStore({
      worldWidth: 1500,
      worldHeight: 1500,
      viewportWidth: 400,
      viewportHeight: 300,
      devicePixelRatio: 1
    })
    expect(store.cssWidth).toBeLessThanOrEqual(400)
    expect(store.cssHeight).toBeLessThanOrEqual(300)
  })
})

describe('visible screen', () => {
  it('uses the monitor the window is on when another measurement is larger', () => {
    expect(visibleViewportSize({
      innerWidth: 1920,
      innerHeight: 1080,
      clientWidth: 1280,
      clientHeight: 720,
      visualWidth: 1280,
      visualHeight: 720,
      screenWidth: 1280,
      screenHeight: 720
    })).toEqual({ width: 1280, height: 720 })
  })

  it('fits the stage inside that screen and leaves the frame inside the glass', () => {
    const box = canvasFitBox({
      stageWidth: 1900,
      stageHeight: 1000,
      viewport: { width: 1280, height: 720 },
      frame: 8
    })
    expect(box.width).toBeLessThanOrEqual(1280)
    expect(box.height).toBeLessThanOrEqual(720)
    expect(box).toEqual({ width: 1272, height: 712 })
  })
})

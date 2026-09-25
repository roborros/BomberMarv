export const CANVAS_HORIZONTAL_PAD = 40
export const CANVAS_VERTICAL_PAD = 240
export const MAX_DEVICE_PIXEL_RATIO = 2

export interface CanvasBackingStore {
  cssWidth: number
  cssHeight: number
  backingWidth: number
  backingHeight: number
  worldToBackingX: number
  worldToBackingY: number
  cssScale: number
}

export function computeCanvasBackingStore(opts: {
  worldWidth: number
  worldHeight: number
  viewportWidth: number
  viewportHeight: number
  devicePixelRatio: number
  horizontalPad?: number
  verticalPad?: number
  maxDevicePixelRatio?: number
}): CanvasBackingStore {
  const worldWidth = Math.max(1, opts.worldWidth)
  const worldHeight = Math.max(1, opts.worldHeight)
  const padX = opts.horizontalPad ?? CANVAS_HORIZONTAL_PAD
  const padY = opts.verticalPad ?? CANVAS_VERTICAL_PAD
  const maxW = Math.max(320, opts.viewportWidth - padX)
  const maxH = Math.max(240, opts.viewportHeight - padY)
  const cssScale = Math.min(maxW / worldWidth, maxH / worldHeight, 1)
  const cssWidth = Math.max(1, Math.floor(worldWidth * cssScale))
  const cssHeight = Math.max(1, Math.floor(worldHeight * cssScale))
  const rawDpr = Number.isFinite(opts.devicePixelRatio) && opts.devicePixelRatio > 0 ? opts.devicePixelRatio : 1
  const dpr = Math.min(rawDpr, opts.maxDevicePixelRatio ?? MAX_DEVICE_PIXEL_RATIO)
  const backingWidth = Math.max(1, Math.round(cssWidth * dpr))
  const backingHeight = Math.max(1, Math.round(cssHeight * dpr))
  return {
    cssWidth,
    cssHeight,
    backingWidth,
    backingHeight,
    worldToBackingX: backingWidth / worldWidth,
    worldToBackingY: backingHeight / worldHeight,
    cssScale
  }
}

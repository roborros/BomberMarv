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

export interface ViewportMetrics {
  innerWidth: number
  innerHeight: number
  clientWidth: number
  clientHeight: number
  visualWidth?: number
  visualHeight?: number
  screenWidth?: number
  screenHeight?: number
}

function positiveLengths(values: Array<number | undefined>): number[] {
  return values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0)
}

/** Smallest reported size, so a stale or larger monitor cannot size the view past the one in use. */
export function visibleViewportSize(metrics: ViewportMetrics): { width: number; height: number } {
  const widths = positiveLengths([metrics.innerWidth, metrics.clientWidth, metrics.visualWidth, metrics.screenWidth])
  const heights = positiveLengths([metrics.innerHeight, metrics.clientHeight, metrics.visualHeight, metrics.screenHeight])
  return {
    width: Math.max(1, Math.floor(widths.length ? Math.min(...widths) : 1)),
    height: Math.max(1, Math.floor(heights.length ? Math.min(...heights) : 1)),
  }
}

/** Stage box clamped to the visible monitor, leaving room for the canvas frame. */
export function canvasFitBox(opts: {
  stageWidth: number
  stageHeight: number
  viewport: { width: number; height: number }
  frame?: number
}): { width: number; height: number } {
  const frame = Math.max(0, opts.frame ?? 0)
  const viewportW = Math.max(1, opts.viewport.width)
  const viewportH = Math.max(1, opts.viewport.height)
  const stageW = opts.stageWidth > 1 ? opts.stageWidth : viewportW
  const stageH = opts.stageHeight > 1 ? opts.stageHeight : viewportH
  const width = Math.max(1, Math.floor(Math.min(stageW, viewportW) - frame))
  const height = Math.max(1, Math.floor(Math.min(stageH, viewportH) - frame))
  return {
    width: Math.min(width, viewportW),
    height: Math.min(height, viewportH),
  }
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
  const viewportWidth = Math.max(1, opts.viewportWidth)
  const viewportHeight = Math.max(1, opts.viewportHeight)
  const padX = Math.max(0, opts.horizontalPad ?? CANVAS_HORIZONTAL_PAD)
  const padY = Math.max(0, opts.verticalPad ?? CANVAS_VERTICAL_PAD)
  const maxW = Math.max(1, Math.min(viewportWidth, viewportWidth - padX))
  const maxH = Math.max(1, Math.min(viewportHeight, viewportHeight - padY))
  const cssScale = Math.min(maxW / worldWidth, maxH / worldHeight, 1)
  const cssWidth = Math.min(maxW, Math.max(1, Math.floor(worldWidth * cssScale)))
  const cssHeight = Math.min(maxH, Math.max(1, Math.floor(worldHeight * cssScale)))
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

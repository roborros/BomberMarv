/** Canvas twin of the host boss-lightning blast. */

const MARV_PALETTE = ['#96beff', '#bed8ff', '#5082ff', '#6e9bff', '#cde0ff']
const TOM_PALETTE = ['#8cffb9', '#beffd2', '#3cdc78', '#78ff9b', '#cdffdc']
const MARV_CORE = '#e2ecff'
const TOM_CORE = '#e2ffea'

function paletteFor(style?: string): string[] {
  return style === 'tom' ? TOM_PALETTE : MARV_PALETTE
}

function coreFor(style?: string): string {
  return style === 'tom' ? TOM_CORE : MARV_CORE
}

type Point = [number, number]

function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function perp(dx: number, dy: number): Point {
  const length = Math.hypot(dx, dy) || 1
  return [-dy / length, dx / length]
}

function bezier(a: Point, control: Point, b: Point, samples = 7): Point[] {
  const pts: Point[] = []
  const n = Math.max(2, samples)
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const u = 1 - t
    pts.push([
      u * u * a[0] + 2 * u * t * control[0] + t * t * b[0],
      u * u * a[1] + 2 * u * t * control[1] + t * t * b[1],
    ])
  }
  return pts
}

function bolt(start: Point, end: Point, rand: () => number, steps: number, amplitude: number, lane: number): Point[] {
  const [x0, y0] = start
  const [x1, y1] = end
  const dx = x1 - x0
  const dy = y1 - y0
  const [px, py] = perp(dx, dy)
  const hops = Math.max(3, Math.min(6, steps))
  const anchors: Point[] = [[x0 + px * lane, y0 + py * lane]]
  let prev = lane
  for (let i = 1; i < hops; i++) {
    const t = i / hops
    let jitter = rand() < 0.35
      ? (rand() * 2 - 1) * amplitude
      : prev * 0.5 + (rand() * 2 - 1) * amplitude * 0.45
    jitter = Math.max(-amplitude, Math.min(amplitude, jitter))
    prev = jitter
    anchors.push([x0 + dx * t + px * jitter, y0 + dy * t + py * jitter])
  }
  anchors.push([x1 + px * lane * 0.2, y1 + py * lane * 0.2])
  const points: Point[] = []
  for (let i = 0; i < anchors.length - 1; i++) {
    const a = anchors[i]
    const b = anchors[i + 1]
    const bend = (rand() * 2 - 1) * amplitude * 0.85
    const control: Point = [(a[0] + b[0]) * 0.5 + px * bend, (a[1] + b[1]) * 0.5 + py * bend]
    const curve = bezier(a, control, b)
    points.push(...(points.length ? curve.slice(1) : curve))
  }
  return points
}

function stroke(ctx: CanvasRenderingContext2D, points: Point[], color: string, width: number, alpha: number) {
  if (points.length < 2 || alpha <= 0) return
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(points[0][0], points[0][1])
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
  ctx.stroke()
  ctx.restore()
}

export function drawLightningExplosion(
  ctx: CanvasRenderingContext2D,
  center: Point,
  arms: Array<[number, number, number]>,
  cellSize: number,
  timeMs: number,
  seed: number,
  alphaScale: number,
  style = 'marv',
) {
  const palette = paletteFor(style)
  const core = coreFor(style)
  if (alphaScale <= 0.02) return
  const bucket = Math.floor(timeMs / 50)
  const rand = mulberry32((seed * 977) ^ (bucket * 1315423911))
  const amplitude = cellSize * 0.16
  const lanes = [-0.28, 0, 0.28]
  const [cx, cy] = center
  ctx.save()
  ctx.globalCompositeOperation = 'lighter'
  for (let armI = 0; armI < arms.length; armI++) {
    const [dx, dy, length] = arms[armI]
    if (length < 8) continue
    const span = Math.hypot(dx, dy) || 1
    const tip: Point = [cx + (dx / span) * length, cy + (dy / span) * length]
    const [px, py] = perp(tip[0] - cx, tip[1] - cy)
    const steps = Math.max(3, Math.floor(length / (cellSize * 0.85)))
    lanes.forEach((laneT, laneI) => {
      const color = palette[(bucket + armI + laneI) % palette.length]
      const pts = bolt([cx, cy], tip, rand, steps, amplitude, laneT * cellSize * 0.55)
      stroke(ctx, pts, color, Math.max(10, cellSize / 9), 0.28 * alphaScale)
      stroke(ctx, pts, color, Math.max(4, cellSize / 22), 0.55 * alphaScale)
      stroke(ctx, pts, core, 2, 0.9 * alphaScale)
    })
  }
  for (let spoke = 0; spoke < 7; spoke++) {
    const ang = spoke * ((Math.PI * 2) / 7) + (bucket % 5) * 0.2
    const reach = cellSize * (0.18 + rand() * 0.24)
    const end: Point = [cx + Math.cos(ang) * reach, cy + Math.sin(ang) * reach]
    const side: Point = [-Math.sin(ang), Math.cos(ang)]
    const bend = (rand() * 2 - 1) * 16
    const control: Point = [(cx + end[0]) * 0.5 + side[0] * bend, (cy + end[1]) * 0.5 + side[1] * bend]
    const color = palette[(bucket + spoke) % palette.length]
    const spark = bezier([cx, cy], control, end, 4)
    stroke(ctx, spark, color, 4, 0.5 * alphaScale)
    stroke(ctx, spark, '#ffffff', 1, 0.9 * alphaScale)
  }
  ctx.globalAlpha = 0.9 * alphaScale
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.arc(cx, cy, Math.max(3, cellSize / 28), 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
}

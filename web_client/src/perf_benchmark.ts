import { percentile } from './math'

export interface BenchmarkResult {
  mode: 'canvas2d' | 'webgl';
  fps: number;
  avgFrameMs: number;
  p95FrameMs: number;
}

async function runCanvas2dBenchmark(canvas: HTMLCanvasElement, durationMs = 3000): Promise<BenchmarkResult> {
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas2D context unavailable')
  const frameTimes: number[] = []
  const start = performance.now()
  let last = start
  let frame = 0
  while (performance.now() - start < durationMs) {
    const now = performance.now()
    const dt = now - last
    last = now
    frameTimes.push(dt)
    ctx.fillStyle = '#202a38'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    for (let i = 0; i < 350; i++) {
      const x = (i * 37 + frame * 3) % canvas.width
      const y = (i * 53 + frame * 2) % canvas.height
      ctx.fillStyle = `hsl(${(i + frame) % 360}, 70%, 55%)`
      ctx.fillRect(x, y, 18, 18)
    }
    frame += 1
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  }
  const avg = frameTimes.length ? frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length : 0
  return {
    mode: 'canvas2d',
    fps: avg > 0 ? 1000 / avg : 0,
    avgFrameMs: avg,
    p95FrameMs: percentile(frameTimes, 95)
  }
}

async function runWebglBenchmark(canvas: HTMLCanvasElement, durationMs = 3000): Promise<BenchmarkResult> {
  const gl = canvas.getContext('webgl2') ?? canvas.getContext('webgl')
  if (!gl) {
    return { mode: 'webgl', fps: 0, avgFrameMs: 0, p95FrameMs: 0 }
  }
  const frameTimes: number[] = []
  const start = performance.now()
  let last = start
  let frame = 0
  while (performance.now() - start < durationMs) {
    const now = performance.now()
    const dt = now - last
    last = now
    frameTimes.push(dt)
    const c = ((frame % 200) / 200)
    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.clearColor(0.15 + c * 0.2, 0.2, 0.3, 1.0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    frame += 1
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  }
  const avg = frameTimes.length ? frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length : 0
  return {
    mode: 'webgl',
    fps: avg > 0 ? 1000 / avg : 0,
    avgFrameMs: avg,
    p95FrameMs: percentile(frameTimes, 95)
  }
}

export async function runRendererBenchmark(canvas: HTMLCanvasElement): Promise<BenchmarkResult[]> {
  const originalWidth = canvas.width
  const originalHeight = canvas.height
  canvas.width = Math.max(originalWidth, 1200)
  canvas.height = Math.max(originalHeight, 800)
  const canvas2d = await runCanvas2dBenchmark(canvas, 2500)
  const webgl = await runWebglBenchmark(canvas, 2500)
  return [canvas2d, webgl]
}

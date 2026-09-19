export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

export function pushLimited(target: number[], value: number, max = 300): number[] {
  target.push(value)
  if (target.length > max) target.splice(0, target.length - max)
  return target
}

export function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor((p / 100) * (sorted.length - 1))))
  return sorted[idx]
}

export function reconnectWaitMs(attempts: number, baseMs = 500, maxMs = 6000): number {
  const n = Math.max(1, attempts)
  return Math.min(maxMs, baseMs * (2 ** (n - 1)))
}

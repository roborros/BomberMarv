export function sampleRttMs(sentAt: number, receivedAt: number): number {
  if (!Number.isFinite(sentAt) || !Number.isFinite(receivedAt)) return 0
  return Math.max(0, receivedAt - sentAt)
}

export function samplePresentAgeMs(receivedAt: number, now: number): number {
  if (!Number.isFinite(receivedAt) || !Number.isFinite(now)) return 0
  return Math.max(0, now - receivedAt)
}

export function sampleQueueDelayMs(receivedAt: number, appliedAt: number): number {
  if (!Number.isFinite(receivedAt) || !Number.isFinite(appliedAt)) return 0
  return Math.max(0, appliedAt - receivedAt)
}

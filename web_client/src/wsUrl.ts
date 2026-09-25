export function buildWsUrl(hostname: string, port = 8765): string {
  const host = hostname === 'localhost' ? '127.0.0.1' : hostname
  return `ws://${host}:${port}`
}

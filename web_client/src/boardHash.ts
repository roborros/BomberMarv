export function computeBoardSignature(board: number[][]): string {
  if (!board || board.length === 0) return 'empty'
  const height = board.length
  const width = board[0]?.length ?? 0
  let hash = 2166136261
  for (let y = 0; y < height; y++) {
    const row = board[y]
    for (let x = 0; x < width; x++) {
      hash ^= (row[x] & 0xff)
      hash = Math.imul(hash, 16777619)
    }
  }
  return `${height}x${width}:${hash >>> 0}`
}

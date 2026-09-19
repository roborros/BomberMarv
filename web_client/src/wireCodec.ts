import { decode as msgpackDecode, encode as msgpackEncode } from '@msgpack/msgpack'

export type WsCodec = 'json' | 'msgpack'

const GAMEPLAY_UPLINK = new Set(['game_input'])

export function preferredWsCodec(search = ''): WsCodec {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  return params.get('ws_codec') === 'json' ? 'json' : 'msgpack'
}

export function isGameplayUplink(type: string): boolean {
  return GAMEPLAY_UPLINK.has(type)
}

export function encodeWsFrame(message: { type: string }, codec: WsCodec): string | Uint8Array {
  if (codec === 'msgpack' && isGameplayUplink(message.type)) {
    return msgpackEncode(message)
  }
  return JSON.stringify(message)
}

export function decodeWsFrame(data: string | ArrayBuffer | Uint8Array): unknown {
  if (typeof data === 'string') {
    return JSON.parse(data)
  }
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data)
  try {
    return msgpackDecode(bytes)
  } catch {
    return JSON.parse(new TextDecoder().decode(bytes))
  }
}

export async function decodeIncomingWsData(data: unknown): Promise<unknown> {
  if (typeof data === 'string' || data instanceof ArrayBuffer || data instanceof Uint8Array) {
    return decodeWsFrame(data)
  }
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    return decodeWsFrame(new Uint8Array(await data.arrayBuffer()))
  }
  throw new Error('unsupported websocket payload')
}

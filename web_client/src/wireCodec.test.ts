import { describe, expect, it } from 'vitest'
import { decode as msgpackDecode } from '@msgpack/msgpack'
import { decodeWsFrame, encodeWsFrame, isGameplayUplink, preferredWsCodec } from './wireCodec'

describe('wireCodec', () => {
  it('defaults to msgpack unless json is requested', () => {
    expect(preferredWsCodec('')).toBe('msgpack')
    expect(preferredWsCodec('?rtc=1')).toBe('msgpack')
    expect(preferredWsCodec('?ws_codec=json')).toBe('json')
  })

  it('keeps control messages as JSON even when codec is msgpack', () => {
    const encoded = encodeWsFrame({ type: 'hello', protocol: 2 }, 'msgpack')
    expect(typeof encoded).toBe('string')
    expect(JSON.parse(encoded as string).type).toBe('hello')
  })

  it('encodes game_input as msgpack when negotiated', () => {
    const encoded = encodeWsFrame({ type: 'game_input', protocol: 2 }, 'msgpack')
    expect(encoded).toBeInstanceOf(Uint8Array)
    expect(msgpackDecode(encoded as Uint8Array)).toEqual({ type: 'game_input', protocol: 2 })
    expect(isGameplayUplink('game_input')).toBe(true)
    expect(isGameplayUplink('ping')).toBe(false)
  })

  it('decodes JSON text and msgpack binary, with JSON fallback', () => {
    expect(decodeWsFrame(JSON.stringify({ type: 'pong' }))).toEqual({ type: 'pong' })
    const packed = encodeWsFrame({ type: 'game_input', tick_id: 3 }, 'msgpack') as Uint8Array
    expect(decodeWsFrame(packed)).toEqual({ type: 'game_input', tick_id: 3 })
    const jsonBytes = new TextEncoder().encode(JSON.stringify({ type: 'error', message: 'x' }))
    expect(decodeWsFrame(jsonBytes)).toEqual({ type: 'error', message: 'x' })
  })
})

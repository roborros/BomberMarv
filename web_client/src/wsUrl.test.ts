import { describe, expect, it } from 'vitest'
import { buildWsUrl } from './wsUrl'

describe('buildWsUrl', () => {
  it('maps localhost to loopback', () => {
    expect(buildWsUrl('localhost')).toBe('ws://127.0.0.1:8765')
  })

  it('keeps LAN hostnames and custom ports', () => {
    expect(buildWsUrl('192.168.1.10', 9000)).toBe('ws://192.168.1.10:9000')
    expect(buildWsUrl('host.local')).toBe('ws://host.local:8765')
  })
})

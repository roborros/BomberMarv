# BomberMarv

LAN/WLAN multiplayer Bomberman-style game with:

- authoritative Python game simulation (host machine)
- pygame local rendering
- TypeScript web client for remote players on local network

## Supported topology

- Host runs the Python game loop and websocket server.
- Remote players join from browser clients on the same LAN/WLAN.
- Internet exposure is not in scope.

## Run

From repo root:

- `python run_all.py` (recommended)  
  Starts Python host loop + web client dev server.
- or run host manually:
  - `python pyBomberMarv.py`
  - `cd web_client && bun run dev`

## Network ports

- WebSocket: `8765`
- HTTP diagnostics: `8080`
- Web client dev server (Vite): `5173`

## Diagnostics endpoints

- `GET /health` -> server health
- `GET /versions` -> ws/http version info
- `GET /status` -> players/clients/slots snapshot
- `GET /metrics` -> queue and runtime counters
- `GET /config` -> input sending config

## WebRTC hybrid transport (LAN/WLAN)

- Control plane stays on WebSocket (`hello`, registration, slots, lobby/control).
- Gameplay plane can use WebRTC DataChannels (`input_unreliable`, `state_unreliable`) when negotiated.
- Runtime fallback is automatic to WS gameplay if RTC is unavailable or drops.
- Feature flags:
  - `BM_RTC_ENABLED=1` enables server-side RTC negotiation path.
  - `BM_RTC_FORCE_WS=1` forces WS-only gameplay path (kill-switch).
  - `BM_STRICT_INPUT_MODE=1` enables strict tick-indexed input path (LAN experiment).
  - `BM_INPUT_LEAD_TICKS=1` configures input lead/apply window in ticks.
- Optional client query flags:
  - `?rtc=0` disables RTC on the web client.
  - `?rtc_codec=msgpack` requests MessagePack on RTC data channels (JSON remains default).
  - `?strict=1` enables strict tick-indexed input sending from web client.

## Protocol

- Protocol version: `2`
- Client uses typed JSON messages (`hello`, `request_slot_list`, `select_slot`, `game_input`, `ping`).
- Server replies with typed envelopes and includes `protocol` in payloads.

See:

- `ARCHITECTURE.md`
- `PROTOCOL.md`
- `PERF_TUNING.md`

## Testing

- Python smoke imports: `python test_imports.py`
- Python unit tests: `python -m unittest discover -s tests -p "test_*.py"`
- Web client build/typecheck: `cd web_client && bun run build`

## Notes

- Legacy `client.html` path was removed. Use `web_client` only.
- For lowest latency, run host on wired Ethernet and clients on clean 5GHz/6GHz WLAN.

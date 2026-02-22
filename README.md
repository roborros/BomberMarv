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

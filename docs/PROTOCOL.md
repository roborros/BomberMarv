# Wire Protocol (LAN/WLAN)

Protocol version: `2`

All messages are JSON with:

- `type`: string
- `protocol`: number (recommended on client -> required by server for strict mode)

## Client -> Server

- `hello`
  - `{ "type": "hello", "protocol": 2, "ts": <ms>, "webrtc_supported": <bool>, "encoding": "json|msgpack", "ws_codec": "json|msgpack", "rtc_codec": "json|msgpack", "strict_input_mode": <bool> }`
  - `encoding` / `ws_codec` request MessagePack for gameplay frames on the WebSocket. Control messages (`hello`, `ping`, slots, RTC signaling) stay JSON. If the host has no msgpack extra, `hello_ack.ws_codec` is `json`.

- `request_slot_list`
  - `{ "type": "request_slot_list", "protocol": 2 }`

- `select_slot`
  - `{ "type": "select_slot", "protocol": 2, "slot": <1..6> }`

- `game_input`
  - Legacy:
    - `{ "type": "game_input", "protocol": 2, "input": [client_id, player_id, up, down, left, right, bomb], "client_timestamp": <ms> }`
  - Tick-indexed (preferred):
    - `{ "type": "game_input", "protocol": 2, "tick_id": <non-negative int>, "input_frame": { "player_id": <int>, "up": 0|1, "down": 0|1, "left": 0|1, "right": 0|1, "bomb": 0|1 }, "client_timestamp": <ms> }`

- `ping`
  - `{ "type": "ping", "protocol": 2, "ts": <ms> }`

## Server -> Client

- `client_id`
- `hello_ack`
  - includes `ws_codec` / `encoding` (`json|msgpack`), `metrics_clock: "unix_ms"`, plus RTC flags
- `rtc_offer`
- `rtc_answer`
- `rtc_ice_candidate`
- `rtc_ready`
- `rtc_failed`
- `slot_list`
- `registration_confirmed`
- `registration_rejected`
- `gamestate`
  - `data` is the board snapshot **without** `_net_metrics`
- `gamestate_delta`
  - gameplay fields only; clock-only changes are sent as `state_keepalive`
  - `delta` is a partial patch. Player and board changes are entity-grain when possible:
    - `player_patches`: `{ "id": <int>, ...changed fields }` (new players are full objects)
    - `player_removed`: list of player ids
    - `board_patches`: `[x, y, cell]` for up to 24 cells; otherwise a full `board`
    - full `players` / `board` arrays if ids are missing/duplicate or the board size changes
- `state_keepalive`
  - `{ "type": "state_keepalive", "seq": <int>, "time": <ms>, "_sim_tick": <int>, "_host_published_at_ms": <ms>, "server_timestamp": <ms> }`
  - idle tick: seq still advances so the next delta's `base_seq` stays valid
- `net_metrics`
  - ~2 Hz HUD sample. `input_apply_*` / `input_queue_delay_*` are **host queue delay** on unix ms, not client RTT
- `input_ack`
  - may include `tick_id` and `apply_tick_id` when tick-indexed input is used
  - `original_timestamp` is echoed so the client can compute RTT on its own clock
- `pong`
- `error`

## Validation policy

- Unsupported `type` => `error`
- Malformed payload => `error`
- Protocol mismatch => `error`

## Latency fields

- `client_timestamp` from client input packet (client wall clock)
- Client **RTT** = client receive time − `input_ack.original_timestamp` (same clock; not one-way latency)
- Host **queue delay** = host `time.time_ns()` apply time − `ws_received_timestamp` (same unix ms clock; not RTT)
- `server_timestamp` in `input_ack`, `gamestate`, `state_keepalive`, and `net_metrics` is unix ms
- Optional `seq` in `gamestate` / `state_keepalive` / `gamestate_delta` for ordering
- Optional `tick_id` in `gamestate` / `gamestate_delta` / `state_keepalive` for tick alignment
- `gamestate_delta` includes:
  - `base_seq`: last sequence the delta applies to
  - `seq`: resulting sequence
  - `delta`: partial game state patch (no `_net_metrics`)
- Present-age on the client is time since the snapshot arrived locally, not host publish time minus `Date.now()` (those clocks are not guaranteed synchronized)

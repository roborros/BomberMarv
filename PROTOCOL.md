# Wire Protocol (LAN/WLAN)

Protocol version: `2`

All messages are JSON with:

- `type`: string
- `protocol`: number (recommended on client -> required by server for strict mode)

## Client -> Server

- `hello`
  - `{ "type": "hello", "protocol": 2, "ts": <ms>, "webrtc_supported": <bool>, "rtc_codec": "json|msgpack", "strict_input_mode": <bool> }`

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
- `rtc_offer`
- `rtc_answer`
- `rtc_ice_candidate`
- `rtc_ready`
- `rtc_failed`
- `slot_list`
- `registration_confirmed`
- `registration_rejected`
- `gamestate`
- `gamestate_delta`
- `input_ack`
  - may include `tick_id` and `apply_tick_id` when tick-indexed input is used
- `pong`
- `error`

## Validation policy

- Unsupported `type` => `error`
- Malformed payload => `error`
- Protocol mismatch => `error`

## Latency fields

- `client_timestamp` from client input packet
- `server_timestamp` in `input_ack` and `gamestate`
- Optional `seq` in `gamestate` for ordering
- Optional `tick_id` in `gamestate` / `gamestate_delta` for tick alignment
- `gamestate_delta` includes:
  - `base_seq`: last sequence the delta applies to
  - `seq`: resulting sequence
  - `delta`: partial game state patch

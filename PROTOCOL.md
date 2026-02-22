# Wire Protocol (LAN/WLAN)

Protocol version: `2`

All messages are JSON with:

- `type`: string
- `protocol`: number (recommended on client -> required by server for strict mode)

## Client -> Server

- `hello`
  - `{ "type": "hello", "protocol": 2, "ts": <ms> }`

- `request_slot_list`
  - `{ "type": "request_slot_list", "protocol": 2 }`

- `select_slot`
  - `{ "type": "select_slot", "protocol": 2, "slot": <1..6> }`

- `game_input`
  - `{ "type": "game_input", "protocol": 2, "input": [client_id, player_id, up, down, left, right, bomb], "client_timestamp": <ms> }`

- `ping`
  - `{ "type": "ping", "protocol": 2, "ts": <ms> }`

## Server -> Client

- `client_id`
- `hello_ack`
- `slot_list`
- `registration_confirmed`
- `registration_rejected`
- `gamestate`
- `input_ack`
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

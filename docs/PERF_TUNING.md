# Performance Tuning (LAN/WLAN)

## Goals

- Stable, responsive play with up to 6 remote clients.
- Prioritize low and consistent latency over perfect frame history.

## Current low-latency defaults

- Bounded non-blocking input/state queues.
- Send-on-change input with heartbeat fallback (`web_client/src/main.ts`).
- Adaptive interpolation delay in renderer (`20-35ms` clamp).
- WS keepalive (ping/pong + timeout) plus idle `state_keepalive` instead of full-board ticks.
- Latest-state broadcast with wakeup (no extra 8 ms sleep after a new snapshot).
- MessagePack gameplay frames on WebSocket when negotiated (`encoding=msgpack`); JSON control plane.
- HUD metrics on a ~2 Hz `net_metrics` channel, not inside 60 Hz snapshots.
- Entity-grain `player_patches` / `board_patches` instead of full arrays on every move or cell change.
- Canvas backing store matches CSS pixels × capped DPR (not the 2100×2100 world buffer).

## Metrics honesty

- Client HUD `RTT(5s)` is client-clock round trip from `input_ack.original_timestamp`.
- Host `input_apply_*` / `input_queue_delay_*` is queue wait on unix ms, not RTT and not pygame ticks.
- `PresentAge` is time since the snapshot arrived in the browser, not host unix time minus `Date.now()`.

## Host recommendations

- Use wired Ethernet for host machine.
- Keep CPU power profile in performance mode.
- Avoid heavy background CPU/disk tasks.
- Keep logs rotated (server uses rotating logs).

## WLAN recommendations

- Prefer 5GHz/6GHz AP.
- Keep client distance/signal quality strong.
- Avoid congested channels.

## Metrics to monitor

- `/metrics` endpoint:
  - `input_events_enqueued`
  - `input_events_dropped`
  - `state_queue_updates`
  - `state_queue_dropped_old`
  - `broadcast_frames`
  - `broadcast_bytes`
- `/status` endpoint:
  - client avg latency
  - registered clients and slot occupancy

## Validation matrix

- 1 client: baseline latency and jitter
- 3 clients: sustained input under moderate contention
- 6 clients: soak for 15-30 minutes

Track p50/p95/p99 for:

- input-to-apply latency
- apply-to-render latency
- end-to-end perceived latency

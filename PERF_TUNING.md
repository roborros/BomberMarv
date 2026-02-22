# Performance Tuning (LAN/WLAN)

## Goals

- Stable, responsive play with up to 6 remote clients.
- Prioritize low and consistent latency over perfect frame history.

## Current low-latency defaults

- Bounded non-blocking input/state queues.
- Send-on-change input with heartbeat fallback (`web_client/src/main.ts`).
- Adaptive interpolation delay in renderer (`20-35ms` clamp).
- WS keepalive (ping/pong + timeout).
- Latest-state broadcast semantics.

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

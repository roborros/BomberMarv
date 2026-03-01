# BomberMarv LAN Readiness Checklist

## Hardware / topology

- [ ] 5-port gigabit Ethernet switch packed
- [ ] Host connected via Ethernet
- [ ] Clients connected on 5GHz WiFi
- [ ] Test with at least 3 simultaneous web clients

## Runtime checks

- [ ] Start with `python run_all.py`
- [ ] For RTC path: set `BM_RTC_ENABLED=1` (keep `BM_RTC_FORCE_WS=0`)
- [ ] For WS fallback validation: set `BM_RTC_FORCE_WS=1`
- [ ] Optional strict input experiment: set `BM_STRICT_INPUT_MODE=1` and `BM_INPUT_LEAD_TICKS=1`
- [ ] Open diagnostics endpoints:
  - [ ] `http://<host>:8080/metrics`
  - [ ] `http://<host>:8080/status`
- [ ] Verify all clients remain registered and slot mapping is stable
- [ ] Verify transport state shows `ws`/`rtc` as expected per client

## Performance thresholds (pass criteria)

- [ ] `broadcast_send_duration_samples_ms` p95 < 5.0ms
- [ ] `input_apply_p95_ms` < 20.0ms
- [ ] No sustained `state_queue_dropped` growth during normal rounds
- [ ] No sustained `input_events_dropped` growth during normal rounds
- [ ] RTC counters increment when enabled (`broadcast_frames_rtc`, `input_events_rtc`)
- [ ] Fallback counters increment on forced drop without disconnects (`rtc_failed_events`, `broadcast_frames_ws`)
- [ ] Tick-input counters stay healthy (`input_tick_out_of_order`, `input_tick_missing`, `input_tick_late`)

## Soak matrix

- [ ] 1 client baseline (15 min) - WS then RTC
- [ ] 3 clients mixed WiFi (15 min) - WS then RTC
- [ ] 6 clients mixed WiFi (30 min) - RTC preferred, forced fallback once

## Notes during test

- Session date/time:
- Number of players:
- Network setup:
- Observed p95 send duration:
- Observed input apply p95:
- Regressions / bugs:

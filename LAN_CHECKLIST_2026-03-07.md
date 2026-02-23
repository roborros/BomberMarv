# BomberMarv LAN Readiness Checklist

## Hardware / topology

- [ ] 5-port gigabit Ethernet switch packed
- [ ] Host connected via Ethernet
- [ ] Clients connected on 5GHz WiFi
- [ ] Test with at least 3 simultaneous web clients

## Runtime checks

- [ ] Start with `python run_all.py`
- [ ] Open diagnostics endpoints:
  - [ ] `http://<host>:8080/metrics`
  - [ ] `http://<host>:8080/status`
- [ ] Verify all clients remain registered and slot mapping is stable

## Performance thresholds (pass criteria)

- [ ] `broadcast_send_duration_samples_ms` p95 < 5.0ms
- [ ] `input_apply_p95_ms` < 20.0ms
- [ ] No sustained `state_queue_dropped` growth during normal rounds
- [ ] No sustained `input_events_dropped` growth during normal rounds

## Notes during test

- Session date/time:
- Number of players:
- Network setup:
- Observed p95 send duration:
- Observed input apply p95:
- Regressions / bugs:

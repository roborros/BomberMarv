# internal imports

import multiprocessing
import os
import queue
import socket
import sys
import threading
import time
import psutil
import pygame
from frontend import FrontendManager
from bm_drawing import (
    draw_boss_result_screen,
    draw_champion_screen,
    draw_game_prep,
    draw_game_screen,
    draw_get_ready,
    draw_leave_prompt,
    draw_quit_prompt,
    draw_stat_screen,
    draw_title_page,
)
import bm_params
from bm_params import BASE_HEIGHT, BASE_WIDTH
from bm_classes import Game
from queue_utils import put_latest_nonblocking
from bm_sounds import play_sound_events
from lobby import build_status_signature
from timing_abstraction import get_ticks
from net_protocol import (
    DEFAULT_INPUT_HOLD_TIMEOUT_MS,
    DEFAULT_INPUT_TIMEOUT_MS,
    HeldKeyWatchdog,
    RollingClockOffset,
    SubTickInputLatch,
    evaluate_input_freshness,
)
from render_snapshot import RenderSnapshot, RenderStateHub, build_render_snapshot
from latency_metrics import (
    build_hud_metrics,
    gameplay_fingerprint,
    prepare_wire_state,
    queue_delay_ms,
    should_attach_hud_metrics,
    should_publish_snapshot,
    wall_clock_ms,
)
import ws_stream_server


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_ws_server_with_queue(input_queue, state_queue, status_queue):
    from bm_paths import is_frozen, user_log_path

    log_path = user_log_path("ws_server.log") if is_frozen() else "ws_server.log"
    args = (input_queue, state_queue, status_queue, log_path)
    # Frozen Windows builds cannot reliably spawn a second Process of the exe.
    if is_frozen():
        thread = threading.Thread(
            target=ws_stream_server.run_server_with_queue,
            args=args,
            daemon=True,
            name="ws-server",
        )
        thread.start()
        return thread
    process = multiprocessing.Process(target=ws_stream_server.run_server_with_queue, args=args)
    process.daemon = True
    process.start()
    return process


def kill_existing_ws_server_processes():
    """Kill any running ws_stream_server.py processes (zombie cleanup)."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and "python" in proc.info["name"].lower():
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if "ws_stream_server.py" in cmdline:
                    print(f"Killing zombie ws_stream_server.py process (PID {proc.pid})")
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def kill_processes_on_ports(ports):
    """Kill any processes listening on the given TCP ports."""
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                for conn in proc.connections(kind="inet"):
                    laddr = getattr(conn, "laddr", None)
                    if not laddr:
                        continue
                    port = getattr(laddr, "port", None)
                    if port in ports:
                        print(f"Killing process PID {proc.pid} ({proc.info.get('name')}) using port {port}")
                        proc.kill()
                        break
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
    except Exception as e:
        print(f"DEBUG: Failed to enumerate processes for port cleanup: {e}")


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    idx = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


def draw_from_snapshot(game_surface, snapshot: RenderSnapshot, hud_metrics=None, ui_font=None):
    """Render one frame onto ``game_surface`` strictly from a detached ``RenderSnapshot``."""
    if snapshot.game_state == "startup":
        from startup_load import startup_load_percent

        elapsed = snapshot.current_time - snapshot.startup_start_time
        draw_title_page(
            game_surface,
            alpha=255,
            show_game_name=True,
            players=snapshot.players,
            show_start_hint=False,
            loading_percent=startup_load_percent(elapsed, getattr(snapshot, "startup_jumps", ())),
        )
    elif snapshot.game_state == "game_prep":
        draw_game_prep(game_surface, snapshot)
        draw_quit_prompt(game_surface, snapshot)
    elif snapshot.game_state == "get_ready":
        draw_game_screen(game_surface, snapshot)
        draw_get_ready(game_surface)
    elif snapshot.game_state == "boss_fight":
        draw_game_screen(game_surface, snapshot)
        if snapshot.current_time < snapshot.game_start_time:
            draw_get_ready(game_surface)
    elif snapshot.game_state == "playing":
        draw_game_screen(game_surface, snapshot)
    elif snapshot.game_state == "win":
        alive_players = [p for p in snapshot.players if p.alive]
        winner = alive_players[0] if len(alive_players) == 1 else None
        draw_stat_screen(game_surface, winner, snapshot.players, snapshot)
    elif snapshot.game_state == "champion":
        champ = snapshot.champion_player()
        if champ is None:
            alive_players = [p for p in snapshot.players if p.alive]
            champ = alive_players[0] if alive_players else None
        draw_champion_screen(game_surface, champ, snapshot.players, snapshot)
    elif snapshot.game_state == "boss_result":
        winner = snapshot.boss_fight_winner
        draw_boss_result_screen(game_surface, winner, snapshot.players, snapshot)

    draw_leave_prompt(game_surface, snapshot)

    if bm_params.DEBUG_MODE and isinstance(hud_metrics, dict) and ui_font is not None:
        perf_text = (
            f"SIM FPS(5s): {hud_metrics.get('host_fps_5s', 0)} | "
            f"RENDER FPS(5s): {hud_metrics.get('host_render_fps_5s', 0)} | "
            f"INPUT p95: {hud_metrics.get('input_apply_p95_ms', 0)}ms"
        )
        perf_surface = ui_font.render(perf_text, True, (210, 230, 255))
        perf_rect = perf_surface.get_rect(bottomleft=(20, BASE_HEIGHT - 14))
        game_surface.blit(perf_surface, perf_rect)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    kill_existing_ws_server_processes()
    kill_processes_on_ports({8080, 8765})

    input_queue = multiprocessing.Queue(maxsize=2048)
    state_queue = multiprocessing.Queue(maxsize=16)
    status_queue = multiprocessing.Queue(maxsize=128)
    ws_process = start_ws_server_with_queue(input_queue, state_queue, status_queue)
    from bm_paths import print_join_urls

    print_join_urls(http_port=ws_stream_server.HTTP_PORT, ws_port=ws_stream_server.PORT)
    runtime_metrics = {
        "input_events_processed": 0,
        "input_events_errors": 0,
        "input_timed_out": 0,
        "input_hold_released": 0,
        "state_queue_sent": 0,
        "state_queue_dropped": 0,
        "input_apply_samples_ms": [],
        "sim_step_samples_ms": [],
        "sim_loop_timestamps_ms": [],
        "render_loop_timestamps_ms": [],
        "avg_sim_fps_5s": 0.0,
        "avg_render_fps_5s": 0.0,
        "render_draw_samples_ms": [],
        "render_present_samples_ms": [],
        "last_metrics_log_time": 0,
        "sim_tick": 0,
        "input_tick_reused": 0,
        "input_tick_buffered": 0,
        "input_tick_apply_lag_samples": [],
    }
    input_reuse_horizon_ticks = max(1, int(os.environ.get("BM_INPUT_REUSE_HORIZON_TICKS", "2") or 2))
    input_timeout_ms = max(20, int(os.environ.get("BM_INPUT_TIMEOUT_MS", str(DEFAULT_INPUT_TIMEOUT_MS)) or DEFAULT_INPUT_TIMEOUT_MS))
    input_hold_timeout_ms = max(
        50,
        int(os.environ.get("BM_INPUT_HOLD_TIMEOUT_MS", str(DEFAULT_INPUT_HOLD_TIMEOUT_MS)) or DEFAULT_INPUT_HOLD_TIMEOUT_MS),
    )
    remote_players_seen = set()
    remote_last_applied_tick = {}
    clock_offset_tracker = RollingClockOffset()
    sub_tick_latch = SubTickInputLatch()
    held_key_watchdog = HeldKeyWatchdog(hold_timeout_ms=input_hold_timeout_ms)
    render_hub = RenderStateHub()
    latest_hud_metrics = [None]
    stop_event = threading.Event()

    theGame = Game()
    theGame.set_status_queue(status_queue)

    frontend = FrontendManager(theGame)
    window = frontend.initialize()
    theGame.set_frontend(frontend)
    # Mark detached renderer mode so only the 60 Hz backend thread mutates theGame
    # and the renderer thread only reads one-way RenderSnapshots.
    theGame._detached_renderer = True

    def get_ui_font():
        if bm_params.font_small is not None:
            return bm_params.font_small
        return pygame.font.SysFont("arial", 48)

    def update_rate_metrics(now_ms):
        sim_series = list(runtime_metrics["sim_loop_timestamps_ms"])
        render_series = list(runtime_metrics["render_loop_timestamps_ms"])
        cutoff = now_ms - 5000
        sim_trimmed = [t for t in sim_series if t >= cutoff]
        render_trimmed = [t for t in render_series if t >= cutoff]
        runtime_metrics["sim_loop_timestamps_ms"] = sim_trimmed
        runtime_metrics["render_loop_timestamps_ms"] = render_trimmed
        sim_span = sim_trimmed[-1] - sim_trimmed[0] if len(sim_trimmed) > 1 else 0
        render_span = render_trimmed[-1] - render_trimmed[0] if len(render_trimmed) > 1 else 0
        runtime_metrics["avg_sim_fps_5s"] = (
            ((len(sim_trimmed) - 1) * 1000.0) / sim_span if sim_span > 0 else 0.0
        )
        runtime_metrics["avg_render_fps_5s"] = (
            ((len(render_trimmed) - 1) * 1000.0) / render_span if render_span > 0 else 0.0
        )

    def drain_remote_input(current_tick):
        now_wall_ms = wall_clock_ms()
        applied_player_keys = set()
        while True:
            try:
                event = input_queue.get_nowait()
                if isinstance(event, dict) and event.get("type") == "player_joined":
                    theGame._emit_sound("bonus")
                    continue
                if isinstance(event, dict) and event.get("type") == "client_key_debug":
                    print(
                        f"DEBUG: CLIENT DEBUG -> event={event.get('event')} "
                        f"key={event.get('key')} pressed={event.get('pressed_keys')}"
                    )
                received_ts = event.get("ws_received_timestamp") if isinstance(event, dict) else None
                client_ts = event.get("client_timestamp") if isinstance(event, dict) else None
                precomputed_excess = event.get("transit_excess_ms") if isinstance(event, dict) else None
                client_id = int(event.get("client_id", 0) or 0) if isinstance(event, dict) else 0
                player_id = int(event.get("player_id", 0) or 0) if isinstance(event, dict) else 0

                is_fresh, _age_ms, _reason = evaluate_input_freshness(
                    client_id=client_id,
                    client_timestamp_ms=client_ts,
                    ws_received_ms=received_ts,
                    apply_now_ms=now_wall_ms,
                    clock_tracker=clock_offset_tracker,
                    max_input_age_ms=input_timeout_ms,
                    precomputed_transit_excess_ms=precomputed_excess,
                )
                if not is_fresh:
                    runtime_metrics["input_timed_out"] += 1
                    continue

                if isinstance(received_ts, (int, float)):
                    sample = queue_delay_ms(received_ts, now_wall_ms)
                    runtime_metrics["input_apply_samples_ms"].append(sample)
                    if len(runtime_metrics["input_apply_samples_ms"]) > 300:
                        runtime_metrics["input_apply_samples_ms"] = runtime_metrics["input_apply_samples_ms"][-300:]

                if isinstance(event, dict) and event.get("type") == "set_input_state":
                    player_key = (client_id, player_id)
                    remote_players_seen.add(player_key)
                    keys_payload = event.get("keys") if isinstance(event.get("keys"), dict) else {}
                    sub_tick_latch.record(client_id, player_id, keys_payload)
                    held_key_watchdog.observe(client_id, player_id, keys_payload, now_wall_ms)
                    remote_last_applied_tick[player_key] = current_tick
                    applied_player_keys.add(player_key)
                    tick_id = event.get("tick_id")
                    if isinstance(tick_id, (int, float)):
                        lag = max(0, int(current_tick - int(tick_id)))
                        runtime_metrics["input_tick_apply_lag_samples"].append(lag)
                        if len(runtime_metrics["input_tick_apply_lag_samples"]) > 300:
                            runtime_metrics["input_tick_apply_lag_samples"] = runtime_metrics["input_tick_apply_lag_samples"][-300:]
                else:
                    theGame.handle_web_key_event(event)
                runtime_metrics["input_events_processed"] += 1
            except queue.Empty:
                break
            except Exception as e:
                print(f"DEBUG: Exception processing input queue: {e}")
                runtime_metrics["input_events_errors"] += 1
                continue

        # Apply latched remote inputs (including sub-tick bomb/direction taps) for this 60 Hz step.
        for cid, pid, effective_keys in sub_tick_latch.consume_all():
            theGame.handle_web_key_event(
                {
                    "type": "set_input_state",
                    "client_id": cid,
                    "player_id": pid,
                    "keys": effective_keys,
                }
            )

        # Auto-release stuck held keys if a client holding a key stopped sending heartbeats.
        for cid, pid in held_key_watchdog.check_expired(now_wall_ms, input_hold_timeout_ms):
            zero_keys = sub_tick_latch.force_release(cid, pid)
            theGame.handle_web_key_event(
                {
                    "type": "set_input_state",
                    "client_id": cid,
                    "player_id": pid,
                    "keys": zero_keys,
                }
            )
            runtime_metrics["input_hold_released"] += 1

        for player_key in remote_players_seen:
            last_tick = remote_last_applied_tick.get(player_key)
            if last_tick is None or player_key in applied_player_keys:
                continue
            if (current_tick - last_tick) <= input_reuse_horizon_ticks:
                runtime_metrics["input_tick_reused"] += 1

    def maybe_refresh_lobby_status():
        if theGame.game_state not in ["startup", "game_prep"]:
            return
        if hasattr(theGame, "_last_status_refresh") and (theGame.current_time - theGame._last_status_refresh) <= 1500:
            return
        previous_status_sig = getattr(theGame, "_last_status_signature", None)
        theGame._refresh_client_status()
        new_status_sig = build_status_signature(getattr(theGame, "_cached_status", None))
        theGame._last_status_signature = new_status_sig
        if theGame.game_state == "game_prep" and new_status_sig != previous_status_sig:
            theGame.create_players()
        theGame._last_status_refresh = theGame.current_time

    def drain_status_updates():
        latest_status = None
        while True:
            try:
                message = status_queue.get_nowait()
                if isinstance(message, dict) and message.get("type") == "status":
                    latest_status = message.get("status")
            except queue.Empty:
                break
            except Exception:
                break
        if isinstance(latest_status, dict):
            theGame._cached_status = latest_status

    def build_state_payload():
        state_payload = theGame.to_dict()
        hud = build_hud_metrics(
            input_queue_delay_samples_ms=runtime_metrics["input_apply_samples_ms"],
            sim_step_samples_ms=runtime_metrics["sim_step_samples_ms"],
            tick_lag_samples=runtime_metrics["input_tick_apply_lag_samples"],
            input_events_processed=runtime_metrics["input_events_processed"],
            input_events_errors=runtime_metrics["input_events_errors"],
            state_queue_sent=runtime_metrics["state_queue_sent"],
            state_queue_dropped=runtime_metrics["state_queue_dropped"],
            host_fps_5s=runtime_metrics["avg_sim_fps_5s"],
            host_render_fps_5s=runtime_metrics["avg_render_fps_5s"],
            sim_tick=int(runtime_metrics["sim_tick"]),
            input_tick_reused=int(runtime_metrics["input_tick_reused"]),
            input_tick_buffered=int(runtime_metrics["input_tick_buffered"]),
        )
        state_payload["_net_metrics"] = hud
        state_payload["_host_published_at_ms"] = wall_clock_ms()
        state_payload["_sim_tick"] = int(runtime_metrics["sim_tick"])
        latest_hud_metrics[0] = hud
        return state_payload

    last_countdown_second = [None]
    last_state_publish_ms = [-1]
    last_state_fingerprint = [None]
    last_hud_metrics_ms = [-1]

    def simulate_step(step_ms):
        """Execute one strict 60 Hz backend simulation step.

        Never blocks on rendering, window scaling, or audio playback.
        """
        frontend.drain_backend_events()
        step_started = time.perf_counter()
        runtime_metrics["sim_tick"] += 1
        current_tick = int(runtime_metrics["sim_tick"])
        theGame.dt = int(step_ms)
        theGame.current_time = get_ticks()
        runtime_metrics["sim_loop_timestamps_ms"].append(theGame.current_time)
        drain_remote_input(current_tick)
        drain_status_updates()
        maybe_refresh_lobby_status()
        countdown_second = theGame.simulate(step_ms, now_ms=theGame.current_time)
        if countdown_second is not None and countdown_second != last_countdown_second[0]:
            last_countdown_second[0] = countdown_second
            theGame._emit_sound("bonus")
        step_duration_ms = (time.perf_counter() - step_started) * 1000.0
        runtime_metrics["sim_step_samples_ms"].append(step_duration_ms)
        if len(runtime_metrics["sim_step_samples_ms"]) > 300:
            runtime_metrics["sim_step_samples_ms"] = runtime_metrics["sim_step_samples_ms"][-300:]
        update_rate_metrics(theGame.current_time)
        state_payload = build_state_payload()
        now_ms = wall_clock_ms()
        game_state = state_payload.get("state")
        if game_state in {"playing", "get_ready", "boss_fight"}:
            fingerprint = last_state_fingerprint[0]
        else:
            fingerprint = gameplay_fingerprint(state_payload)
        if should_publish_snapshot(
            game_state,
            fingerprint,
            last_state_fingerprint[0],
            now_ms,
            last_state_publish_ms[0],
        ):
            hud = None
            if should_attach_hud_metrics(now_ms, last_hud_metrics_ms[0]):
                hud = state_payload.get("_net_metrics")
                last_hud_metrics_ms[0] = now_ms
            wire_payload = prepare_wire_state(
                state_payload,
                wall_ms=now_ms,
                hud_metrics=hud if isinstance(hud, dict) else None,
                sim_tick=int(runtime_metrics["sim_tick"]),
            )
            put_latest_nonblocking(
                state_queue,
                wire_payload,
                runtime_metrics,
                sent_key="state_queue_sent",
                dropped_key="state_queue_dropped",
            )
            last_state_publish_ms[0] = now_ms
            last_state_fingerprint[0] = fingerprint

        # Publish one-way detached render snapshot (including announced sound_events) for the renderer thread.
        render_snap = build_render_snapshot(theGame, seq=current_tick)
        render_hub.publish(render_snap)

        if theGame.current_time - runtime_metrics["last_metrics_log_time"] > 5000:
            runtime_metrics["last_metrics_log_time"] = theGame.current_time
            print(
                "[NET] input_events="
                f"{runtime_metrics['input_events_processed']} "
                f"timed_out={runtime_metrics['input_timed_out']} "
                f"state_sent={runtime_metrics['state_queue_sent']} "
                f"state_dropped={runtime_metrics['state_queue_dropped']} "
                f"input_p95_ms={state_payload['_net_metrics']['input_apply_p95_ms']} "
                f"sim_fps_5s={state_payload['_net_metrics']['host_fps_5s']} "
                f"render_fps_5s={state_payload['_net_metrics']['host_render_fps_5s']} "
                f"draw_p95_ms={round(percentile(runtime_metrics['render_draw_samples_ms'], 95), 2)} "
                f"present_p95_ms={round(percentile(runtime_metrics['render_present_samples_ms'], 95), 2)}"
            )
        return state_payload

    def render_frame(snapshot: RenderSnapshot):
        """Render and play audio events on the local renderer thread from a detached RenderSnapshot."""
        draw_started = time.perf_counter()
        if snapshot.sound_events:
            try:
                play_sound_events(snapshot.sound_events)
            except Exception:
                pass
        frontend.screen.ensure_surface_size(snapshot.surface_size)
        game_surface = frontend.screen.get_surface()
        draw_from_snapshot(
            game_surface,
            snapshot,
            hud_metrics=latest_hud_metrics[0],
            ui_font=get_ui_font() if bm_params.DEBUG_MODE else None,
        )
        draw_duration_ms = (time.perf_counter() - draw_started) * 1000.0
        runtime_metrics["render_draw_samples_ms"].append(draw_duration_ms)
        if len(runtime_metrics["render_draw_samples_ms"]) > 300:
            runtime_metrics["render_draw_samples_ms"] = runtime_metrics["render_draw_samples_ms"][-300:]
        present_started = time.perf_counter()
        frontend.render()
        present_duration_ms = (time.perf_counter() - present_started) * 1000.0
        runtime_metrics["render_present_samples_ms"].append(present_duration_ms)
        if len(runtime_metrics["render_present_samples_ms"]) > 300:
            runtime_metrics["render_present_samples_ms"] = runtime_metrics["render_present_samples_ms"][-300:]
        runtime_metrics["render_loop_timestamps_ms"].append(snapshot.current_time)

    # Seed initial snapshot before starting the 60 Hz backend thread.
    build_state_payload()
    render_hub.publish(build_render_snapshot(theGame, seq=0))

    sim_step_ms = 1000.0 / 60.0
    sim_step_ns = int(1_000_000_000 // 60)

    def backend_sim_loop():
        """Dedicated hard 60 FPS backend simulation thread. Waits for nothing."""
        next_deadline_ns = time.perf_counter_ns()
        while not stop_event.is_set() and not frontend.should_quit:
            now_ns = time.perf_counter_ns()
            if now_ns < next_deadline_ns:
                rem_ns = next_deadline_ns - now_ns
                if rem_ns > 1_500_000:
                    time.sleep((rem_ns - 500_000) / 1_000_000_000.0)
                continue
            simulate_step(sim_step_ms)
            next_deadline_ns += sim_step_ns
            # If the OS scheduler ever stalled the thread by multiple ticks, advance the deadline
            # rather than burst-stepping faster than real time.
            after_ns = time.perf_counter_ns()
            if after_ns - next_deadline_ns > sim_step_ns * 2:
                next_deadline_ns = after_ns + sim_step_ns

    sim_thread = threading.Thread(
        target=backend_sim_loop,
        daemon=True,
        name="bm-sim-60hz",
    )
    sim_thread.start()

    render_step_ms = 1000.0 / 60.0
    next_render_due_ms = 0.0

    try:
        while not frontend.should_quit:
            frontend.process_events()
            now_ms = time.perf_counter() * 1000.0
            if now_ms >= next_render_due_ms:
                snap = render_hub.consume_latest()
                if snap is not None:
                    render_frame(snap)
                    if snap.quit_requested:
                        frontend.should_quit = True
                next_render_due_ms = now_ms + render_step_ms
            else:
                wait_ms = max(0.0, min(render_step_ms, next_render_due_ms - now_ms))
                if wait_ms > 1.0:
                    time.sleep(wait_ms / 1000.0)
    finally:
        stop_event.set()
        sim_thread.join(timeout=1.0)

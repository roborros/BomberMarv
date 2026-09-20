# internal imports

import socket
import multiprocessing
import os
import sys
import threading
import psutil
import queue
import time
import pygame
from frontend import FrontendManager
from bm_drawing import (
    draw_boss_result_screen,
    draw_champion_screen,
    draw_controls,
    draw_game_prep,
    draw_game_screen,
    draw_get_ready,
    draw_leave_prompt,
    draw_stat_screen,
    draw_title_page,
)
import bm_params
from bm_params import BASE_HEIGHT, BASE_WIDTH
from bm_classes import Game
from queue_utils import put_latest_nonblocking
from bm_sounds import bonus_sound
from lobby import build_status_signature
from timing_abstraction import get_ticks
from net_protocol import should_buffer_remote_input
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


## TODO
# rework explosion animation
# store all necessary params to bomb class, do not access player later
# trophy - make a nicer image
# rework champion page
# add player menu (number, names, colors, controls)
# add param menu
# exe compilation
# add unit tests
# add developer mode with simple ui and collision box visualization, direction of movement, etc.
# game class to store all game state instead of global variables and add methods to it?
# abstract pyge away from the game logic to not be locked in
# ingame ECS key to pause the game
# port to browser https://pygame-web.github.io/





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
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = ' '.join(proc.info.get('cmdline') or [])
                if 'ws_stream_server.py' in cmdline:
                    print(f"Killing zombie ws_stream_server.py process (PID {proc.pid})")
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def kill_processes_on_ports(ports):
    """Kill any processes listening on the given TCP ports."""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections(kind='inet'):
                    laddr = getattr(conn, 'laddr', None)
                    if not laddr:
                        continue
                    port = getattr(laddr, 'port', None)
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

if __name__ == "__main__":
    multiprocessing.freeze_support()
    kill_existing_ws_server_processes()
    # Free the TCP ports if occupied
    kill_processes_on_ports({8080, 8765})
    
    # Start the input server with a multiprocessing queue for input only
    input_queue = multiprocessing.Queue(maxsize=2048)
    state_queue = multiprocessing.Queue(maxsize=16)
    status_queue = multiprocessing.Queue(maxsize=128)
    ws_process = start_ws_server_with_queue(input_queue, state_queue, status_queue)
    from bm_paths import print_join_urls

    print_join_urls(http_port=ws_stream_server.HTTP_PORT, ws_port=ws_stream_server.PORT)
    runtime_metrics = {
        "input_events_processed": 0,
        "input_events_errors": 0,
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
    pending_remote_input_by_tick = {}
    remote_players_seen = set()
    remote_last_applied_tick = {}
    
    # Get reference to server functions for game state updates
    # update_game_state = ws_stream_server.update_game_state # No longer needed

    theGame = Game()
    theGame.set_status_queue(status_queue)
    # Don't call init_game() here - we want to start in prep mode
    # theGame.init_game()

    # Set game instance in WebSocket server for input handling
    # ws_stream_server.set_game_instance(theGame) # This only sets it in the main process, not helpful for the server process input validation, but maybe okay for now.

    # Create frontend and initialize
    frontend = FrontendManager(theGame)
    window = frontend.initialize()
    theGame.set_frontend(frontend)

    def get_ui_font():
        if bm_params.font_small is not None:
            return bm_params.font_small
        return pygame.font.SysFont("arial", 48)

    def update_rate_metrics(now_ms):
        sim_series = runtime_metrics["sim_loop_timestamps_ms"]
        render_series = runtime_metrics["render_loop_timestamps_ms"]
        cutoff = now_ms - 5000
        runtime_metrics["sim_loop_timestamps_ms"] = [t for t in sim_series if t >= cutoff]
        runtime_metrics["render_loop_timestamps_ms"] = [t for t in render_series if t >= cutoff]
        sim_span = (
            runtime_metrics["sim_loop_timestamps_ms"][-1] - runtime_metrics["sim_loop_timestamps_ms"][0]
            if len(runtime_metrics["sim_loop_timestamps_ms"]) > 1
            else 0
        )
        render_span = (
            runtime_metrics["render_loop_timestamps_ms"][-1] - runtime_metrics["render_loop_timestamps_ms"][0]
            if len(runtime_metrics["render_loop_timestamps_ms"]) > 1
            else 0
        )
        runtime_metrics["avg_sim_fps_5s"] = (
            ((len(runtime_metrics["sim_loop_timestamps_ms"]) - 1) * 1000.0) / sim_span if sim_span > 0 else 0.0
        )
        runtime_metrics["avg_render_fps_5s"] = (
            ((len(runtime_metrics["render_loop_timestamps_ms"]) - 1) * 1000.0) / render_span if render_span > 0 else 0.0
        )

    def drain_remote_input(current_tick):
        while True:
            try:
                event = input_queue.get_nowait()
                if isinstance(event, dict) and event.get("type") == "player_joined":
                    try:
                        bonus_sound.play()
                    except Exception:
                        pass
                    continue
                if isinstance(event, dict) and event.get('type') == 'client_key_debug':
                    print(f"DEBUG: CLIENT DEBUG -> event={event.get('event')} key={event.get('key')} pressed={event.get('pressed_keys')}")
                received_ts = event.get("ws_received_timestamp") if isinstance(event, dict) else None
                if isinstance(received_ts, (int, float)):
                    sample = queue_delay_ms(received_ts, wall_clock_ms())
                    runtime_metrics["input_apply_samples_ms"].append(sample)
                    if len(runtime_metrics["input_apply_samples_ms"]) > 300:
                        runtime_metrics["input_apply_samples_ms"] = runtime_metrics["input_apply_samples_ms"][-300:]
                if isinstance(event, dict) and event.get("type") == "set_input_state":
                    player_key = (int(event.get("client_id", 0) or 0), int(event.get("player_id", 0) or 0))
                    remote_players_seen.add(player_key)
                    apply_tick_raw = event.get("apply_tick_id")
                    apply_tick = int(apply_tick_raw) if isinstance(apply_tick_raw, (int, float)) else None
                    if should_buffer_remote_input(apply_tick, current_tick):
                        bucket = pending_remote_input_by_tick.setdefault(apply_tick, [])
                        bucket.append(event)
                        runtime_metrics["input_tick_buffered"] += 1
                    else:
                        theGame.handle_web_key_event(event)
                        remote_last_applied_tick[player_key] = current_tick
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

    def apply_buffered_remote_input(current_tick):
        due_ticks = sorted(tick for tick in pending_remote_input_by_tick.keys() if tick <= current_tick)
        applied_player_keys = set()
        for tick in due_ticks:
            events = pending_remote_input_by_tick.pop(tick, [])
            for event in events:
                theGame.handle_web_key_event(event)
                player_key = (int(event.get("client_id", 0) or 0), int(event.get("player_id", 0) or 0))
                remote_last_applied_tick[player_key] = current_tick
                applied_player_keys.add(player_key)
                tick_id = event.get("tick_id")
                if isinstance(tick_id, (int, float)):
                    lag = max(0, int(current_tick - int(tick_id)))
                    runtime_metrics["input_tick_apply_lag_samples"].append(lag)
                    if len(runtime_metrics["input_tick_apply_lag_samples"]) > 300:
                        runtime_metrics["input_tick_apply_lag_samples"] = runtime_metrics["input_tick_apply_lag_samples"][-300:]

        # Deterministic short-horizon reuse accounting: keep last applied input state for a few ticks.
        for player_key in remote_players_seen:
            last_tick = remote_last_applied_tick.get(player_key)
            if last_tick is None or player_key in applied_player_keys:
                continue
            if (current_tick - last_tick) <= input_reuse_horizon_ticks:
                runtime_metrics["input_tick_reused"] += 1

    def maybe_refresh_lobby_status():
        if theGame.game_state not in ["startup", "game_prep"]:
            return
        if hasattr(theGame, '_last_status_refresh') and (theGame.current_time - theGame._last_status_refresh) <= 1500:
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
        return state_payload

    last_countdown_second = [None]
    last_state_publish_ms = [-1]
    last_state_fingerprint = [None]
    last_hud_metrics_ms = [-1]

    def simulate_step(step_ms):
        step_started = time.perf_counter()
        runtime_metrics["sim_tick"] += 1
        current_tick = int(runtime_metrics["sim_tick"])
        theGame.dt = int(step_ms)
        theGame.current_time = get_ticks()
        runtime_metrics["sim_loop_timestamps_ms"].append(theGame.current_time)
        drain_remote_input(current_tick)
        apply_buffered_remote_input(current_tick)
        drain_status_updates()
        maybe_refresh_lobby_status()
        countdown_second = theGame.simulate(step_ms, now_ms=theGame.current_time)
        if countdown_second is not None and countdown_second != last_countdown_second[0]:
            last_countdown_second[0] = countdown_second
            try:
                bonus_sound.play()
            except Exception:
                pass
        step_duration_ms = (time.perf_counter() - step_started) * 1000.0
        runtime_metrics["sim_step_samples_ms"].append(step_duration_ms)
        if len(runtime_metrics["sim_step_samples_ms"]) > 300:
            runtime_metrics["sim_step_samples_ms"] = runtime_metrics["sim_step_samples_ms"][-300:]
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
        if theGame.current_time - runtime_metrics["last_metrics_log_time"] > 5000:
            runtime_metrics["last_metrics_log_time"] = theGame.current_time
            print(
                "[NET] input_events="
                f"{runtime_metrics['input_events_processed']} "
                f"state_sent={runtime_metrics['state_queue_sent']} "
                f"state_dropped={runtime_metrics['state_queue_dropped']} "
                f"input_p95_ms={state_payload['_net_metrics']['input_apply_p95_ms']} "
                f"sim_fps_5s={state_payload['_net_metrics']['host_fps_5s']} "
                f"render_fps_5s={state_payload['_net_metrics']['host_render_fps_5s']} "
                f"draw_p95_ms={round(percentile(runtime_metrics['render_draw_samples_ms'], 95), 2)} "
                f"present_p95_ms={round(percentile(runtime_metrics['render_present_samples_ms'], 95), 2)}"
            )
        return state_payload

    def render_frame(state_payload):
        draw_started = time.perf_counter()
        theGame.handle_window_events()
        game_surface = frontend.screen.get_surface()
        if theGame.game_state == "startup":
            elapsed = theGame.current_time - theGame.startup_start_time
            if elapsed < 2000:
                alpha = 255
            elif elapsed < 2800:
                alpha = max(0, int(255 * (2800 - elapsed) / 800))
            else:
                alpha = 0
            draw_title_page(game_surface, alpha)
            if int(elapsed) >= 2200:
                draw_controls(game_surface, theGame.players)
                start_text = get_ui_font().render("Press Enter to start the game", True, (255, 255, 255))
                start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
                game_surface.blit(start_text, start_rect)
        elif theGame.game_state == "game_prep":
            draw_game_prep(game_surface, theGame)
        elif theGame.game_state == "get_ready":
            draw_game_screen(game_surface, theGame)
            draw_get_ready(game_surface)
        elif theGame.game_state == "boss_fight":
            draw_game_screen(game_surface, theGame)
            if theGame.current_time < theGame.game_start_time:
                draw_get_ready(game_surface)
        elif theGame.game_state == "playing":
            # Keep host render path single-pass; double rendering for shake was a major FPS sink.
            draw_game_screen(game_surface, theGame)
        elif theGame.game_state == "win":
            alive_players = [p for p in theGame.players if p.alive]
            draw_stat_screen(game_surface, alive_players[0] if alive_players else None, theGame.players, theGame)
        elif theGame.game_state == "champion":
            alive_players = [p for p in theGame.players if p.alive]
            draw_champion_screen(game_surface, alive_players[0] if alive_players else None, theGame.players, theGame)
        elif theGame.game_state == "boss_result":
            winner = getattr(theGame, 'boss_fight_winner', None)
            draw_boss_result_screen(game_surface, winner, theGame.players, theGame)

        draw_leave_prompt(game_surface, theGame)

        if bm_params.DEBUG_MODE:
            perf = state_payload["_net_metrics"]
            perf_text = (
                f"SIM FPS(5s): {perf['host_fps_5s']} | RENDER FPS(5s): {perf['host_render_fps_5s']} "
                f"| INPUT p95: {perf['input_apply_p95_ms']}ms"
            )
            perf_surface = get_ui_font().render(perf_text, True, (210, 230, 255))
            perf_rect = perf_surface.get_rect(bottomleft=(20, BASE_HEIGHT - 14))
            game_surface.blit(perf_surface, perf_rect)
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
        runtime_metrics["render_loop_timestamps_ms"].append(theGame.current_time)

    sim_step_ms = 1000.0 / 60.0
    render_step_ms = 1000.0 / 60.0
    max_accumulator_ms = sim_step_ms * 5.0
    max_sim_steps_per_frame = 4
    accumulator_ms = 0.0
    last_tick = time.perf_counter()
    next_render_due_ms = 0.0
    latest_payload = build_state_payload()

    while True:
        now = time.perf_counter()
        elapsed_ms = (now - last_tick) * 1000.0
        last_tick = now
        accumulator_ms = min(max_accumulator_ms, accumulator_ms + elapsed_ms)

        sim_steps_this_frame = 0
        while accumulator_ms >= sim_step_ms and sim_steps_this_frame < max_sim_steps_per_frame:
            latest_payload = simulate_step(sim_step_ms)
            accumulator_ms -= sim_step_ms
            sim_steps_this_frame += 1

        # If rendering stalls for a moment, drop extra catch-up debt to avoid visible hitch bursts.
        if accumulator_ms >= sim_step_ms * (max_sim_steps_per_frame * 2):
            accumulator_ms = min(accumulator_ms, sim_step_ms)

        update_rate_metrics(theGame.current_time)
        now_ms = now * 1000.0
        if now_ms >= next_render_due_ms:
            render_frame(latest_payload)
            next_render_due_ms = now_ms + render_step_ms
        else:
            # Avoid busy-spin when both sim and render are waiting.
            wait_ms = min(render_step_ms, max(0.0, next_render_due_ms - now_ms), max(0.0, sim_step_ms - accumulator_ms))
            if wait_ms > 0.5:
                time.sleep(wait_ms / 1000.0)

        if frontend.should_quit:
            break


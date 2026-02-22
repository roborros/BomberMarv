# internal imports

import socket
import multiprocessing
import psutil
import queue
import statistics
import time
import pygame
from frontend import FrontendManager
from bm_drawing import (
    draw_champion_screen,
    draw_controls,
    draw_game_prep,
    draw_game_screen,
    draw_get_ready,
    draw_stat_screen,
    draw_title_page,
)
import bm_params
from bm_params import BASE_HEIGHT, BASE_WIDTH
from bm_classes import Game
from queue_utils import put_latest_nonblocking
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

def start_ws_server_with_queue(input_queue, state_queue):
    # Start the server in a process, passing input queue and state queue, and log output to ws_server.log
    p = multiprocessing.Process(target=ws_stream_server.run_server_with_queue, args=(input_queue, state_queue, "ws_server.log"))
    p.daemon = True
    p.start()
    return p

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
    kill_existing_ws_server_processes()
    # Free the TCP ports if occupied
    kill_processes_on_ports({8080, 8765})
    
    # Start the input server with a multiprocessing queue for input only
    input_queue = multiprocessing.Queue(maxsize=2048)
    state_queue = multiprocessing.Queue(maxsize=16)
    ws_process = start_ws_server_with_queue(input_queue, state_queue)
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
        "last_metrics_log_time": 0,
    }
    
    # Get reference to server functions for game state updates
    # update_game_state = ws_stream_server.update_game_state # No longer needed

    theGame = Game()
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
        return pygame.font.SysFont("arial", 24)

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

    def drain_remote_input():
        while True:
            try:
                event = input_queue.get_nowait()
                if isinstance(event, dict) and event.get('type') == 'client_key_debug':
                    print(f"DEBUG: CLIENT DEBUG -> event={event.get('event')} key={event.get('key')} pressed={event.get('pressed_keys')}")
                received_ts = event.get("ws_received_timestamp") if isinstance(event, dict) else None
                if isinstance(received_ts, (int, float)):
                    sample = max(0, int(theGame.current_time - int(received_ts)))
                    runtime_metrics["input_apply_samples_ms"].append(sample)
                    if len(runtime_metrics["input_apply_samples_ms"]) > 300:
                        runtime_metrics["input_apply_samples_ms"] = runtime_metrics["input_apply_samples_ms"][-300:]
                theGame.handle_web_key_event(event)
                runtime_metrics["input_events_processed"] += 1
            except queue.Empty:
                break
            except Exception as e:
                print(f"DEBUG: Exception processing input queue: {e}")
                runtime_metrics["input_events_errors"] += 1
                break

    def maybe_refresh_lobby_status():
        if theGame.game_state not in ["startup", "game_prep"]:
            return
        if hasattr(theGame, '_last_status_refresh') and (theGame.current_time - theGame._last_status_refresh) <= 1500:
            return
        previous_status_sig = getattr(theGame, "_last_status_signature", None)
        theGame._refresh_client_status()
        new_status_sig = None
        if isinstance(getattr(theGame, "_cached_status", None), dict):
            status = theGame._cached_status
            clients = status.get("clients", {})
            slots = status.get("slots", {})
            clients_sig = []
            for cid, info in clients.items():
                if not isinstance(info, dict):
                    continue
                clients_sig.append(
                    (
                        str(cid),
                        bool(info.get("registered", False)),
                        info.get("slot"),
                        str(info.get("display_name") or ""),
                        round(float(info.get("avg_latency_5s", 0.0)), 1),
                    )
                )
            slots_sig = [(str(slot_id), bool(is_taken)) for slot_id, is_taken in slots.items()]
            new_status_sig = (
                tuple(sorted(clients_sig)),
                tuple(sorted(slots_sig)),
            )
        theGame._last_status_signature = new_status_sig
        if theGame.game_state == "game_prep" and new_status_sig != previous_status_sig:
            theGame.create_players()
        theGame._last_status_refresh = theGame.current_time

    def build_state_payload():
        state_payload = theGame.to_dict()
        samples = runtime_metrics["input_apply_samples_ms"]
        sim_samples = runtime_metrics["sim_step_samples_ms"]
        avg_input_apply = sum(samples) / len(samples) if samples else 0.0
        avg_sim_step = statistics.fmean(sim_samples) if sim_samples else 0.0
        state_payload["_net_metrics"] = {
            "input_events_processed": runtime_metrics["input_events_processed"],
            "input_events_errors": runtime_metrics["input_events_errors"],
            "state_queue_sent": runtime_metrics["state_queue_sent"],
            "state_queue_dropped": runtime_metrics["state_queue_dropped"],
            "avg_input_apply_ms": round(avg_input_apply, 2),
            "input_apply_p50_ms": round(percentile(samples, 50), 2),
            "input_apply_p95_ms": round(percentile(samples, 95), 2),
            "input_apply_p99_ms": round(percentile(samples, 99), 2),
            "sim_step_avg_ms": round(avg_sim_step, 2),
            "sim_step_p95_ms": round(percentile(sim_samples, 95), 2),
            "host_fps_5s": round(runtime_metrics["avg_sim_fps_5s"], 1),
            "host_render_fps_5s": round(runtime_metrics["avg_render_fps_5s"], 1),
        }
        state_payload["_host_published_at_ms"] = int(time.time() * 1000)
        return state_payload

    def simulate_step(step_ms):
        step_started = time.perf_counter()
        theGame.dt = int(step_ms)
        theGame.current_time = pygame.time.get_ticks()
        runtime_metrics["sim_loop_timestamps_ms"].append(theGame.current_time)
        drain_remote_input()
        maybe_refresh_lobby_status()
        if theGame.game_state == "get_ready":
            if theGame.current_time >= theGame.game_start_time:
                theGame.game_state = "playing"
        elif theGame.game_state == "playing":
            theGame.update()
        step_duration_ms = (time.perf_counter() - step_started) * 1000.0
        runtime_metrics["sim_step_samples_ms"].append(step_duration_ms)
        if len(runtime_metrics["sim_step_samples_ms"]) > 300:
            runtime_metrics["sim_step_samples_ms"] = runtime_metrics["sim_step_samples_ms"][-300:]
        state_payload = build_state_payload()
        put_latest_nonblocking(
            state_queue,
            state_payload,
            runtime_metrics,
            sent_key="state_queue_sent",
            dropped_key="state_queue_dropped",
        )
        if theGame.current_time - runtime_metrics["last_metrics_log_time"] > 5000:
            runtime_metrics["last_metrics_log_time"] = theGame.current_time
            print(
                "[NET] input_events="
                f"{runtime_metrics['input_events_processed']} "
                f"state_sent={runtime_metrics['state_queue_sent']} "
                f"state_dropped={runtime_metrics['state_queue_dropped']} "
                f"input_p95_ms={state_payload['_net_metrics']['input_apply_p95_ms']} "
                f"sim_fps_5s={state_payload['_net_metrics']['host_fps_5s']} "
                f"render_fps_5s={state_payload['_net_metrics']['host_render_fps_5s']}"
            )
        return state_payload

    def render_frame(state_payload):
        theGame.handle_window_events()
        game_surface = frontend.screen.get_surface()
        if theGame.game_state == "startup":
            elapsed = theGame.current_time - theGame.startup_start_time
            if elapsed < 2000:
                alpha = 255
            elif elapsed < 2800:
                alpha = int(255 * (2500 - elapsed) / 500)
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
        elif theGame.game_state == "playing":
            draw_game_screen(game_surface, theGame)
        elif theGame.game_state == "win":
            draw_title_page(game_surface, alpha=255)
            alive_players = [p for p in theGame.players if p.alive]
            draw_stat_screen(game_surface, alive_players[0] if alive_players else None, theGame.players, theGame)
        elif theGame.game_state == "champion":
            alive_players = [p for p in theGame.players if p.alive]
            draw_champion_screen(game_surface, alive_players[0] if alive_players else None)

        perf = state_payload["_net_metrics"]
        perf_text = (
            f"SIM FPS(5s): {perf['host_fps_5s']} | RENDER FPS(5s): {perf['host_render_fps_5s']} "
            f"| INPUT p95: {perf['input_apply_p95_ms']}ms"
        )
        perf_surface = get_ui_font().render(perf_text, True, (210, 230, 255))
        perf_rect = perf_surface.get_rect(bottomleft=(20, BASE_HEIGHT - 14))
        game_surface.blit(perf_surface, perf_rect)
        frontend.render()
        runtime_metrics["render_loop_timestamps_ms"].append(theGame.current_time)

    sim_step_ms = 1000.0 / 60.0
    max_accumulator_ms = sim_step_ms * 5.0
    accumulator_ms = 0.0
    last_tick = time.perf_counter()
    latest_payload = build_state_payload()

    while True:
        now = time.perf_counter()
        elapsed_ms = (now - last_tick) * 1000.0
        last_tick = now
        accumulator_ms = min(max_accumulator_ms, accumulator_ms + elapsed_ms)

        while accumulator_ms >= sim_step_ms:
            latest_payload = simulate_step(sim_step_ms)
            accumulator_ms -= sim_step_ms

        update_rate_metrics(theGame.current_time)
        render_frame(latest_payload)

        if frontend.should_quit:
            break


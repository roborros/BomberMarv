# internal imports

import socket
import multiprocessing
import psutil
import queue
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

if __name__ == "__main__":
    kill_existing_ws_server_processes()
    # Free the TCP ports if occupied
    kill_processes_on_ports({8080, 8765})
    
    # Start the input server with a multiprocessing queue for input only
    input_queue = multiprocessing.Queue(maxsize=2048)
    state_queue = multiprocessing.Queue(maxsize=4)
    ws_process = start_ws_server_with_queue(input_queue, state_queue)
    runtime_metrics = {
        "input_events_processed": 0,
        "input_events_errors": 0,
        "state_queue_sent": 0,
        "state_queue_dropped": 0,
        "input_apply_samples_ms": [],
        "frame_timestamps_ms": [],
        "avg_fps_5s": 0.0,
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

    while True:
        theGame.tick()
        runtime_metrics["frame_timestamps_ms"].append(theGame.current_time)
        cutoff = theGame.current_time - 5000
        runtime_metrics["frame_timestamps_ms"] = [t for t in runtime_metrics["frame_timestamps_ms"] if t >= cutoff]
        span = runtime_metrics["frame_timestamps_ms"][-1] - runtime_metrics["frame_timestamps_ms"][0] if len(runtime_metrics["frame_timestamps_ms"]) > 1 else 0
        if span > 0:
            runtime_metrics["avg_fps_5s"] = ((len(runtime_metrics["frame_timestamps_ms"]) - 1) * 1000.0) / span
        else:
            runtime_metrics["avg_fps_5s"] = 0.0
        
        
        theGame.handle_window_events()
        # Handle web key events from input_queue (use non-blocking drain)
        processed_events = 0
        while True:
            try:
                event = input_queue.get_nowait()
                processed_events += 1
                if isinstance(event, dict) and event.get('type') == 'client_key_debug':
                    print(f"DEBUG: CLIENT DEBUG -> event={event.get('event')} key={event.get('key')} pressed={event.get('pressed_keys')}")
                received_ts = event.get("ws_received_timestamp") if isinstance(event, dict) else None
                if isinstance(received_ts, (int, float)):
                    sample = max(0, int(theGame.current_time - int(received_ts)))
                    runtime_metrics["input_apply_samples_ms"].append(sample)
                    if len(runtime_metrics["input_apply_samples_ms"]) > 200:
                        runtime_metrics["input_apply_samples_ms"] = runtime_metrics["input_apply_samples_ms"][-200:]
                theGame.handle_web_key_event(event)
                runtime_metrics["input_events_processed"] += 1
            except queue.Empty:
                if processed_events and processed_events > 0:
                    pass
                break
            except Exception as e:
                print(f"DEBUG: Exception processing input queue: {e}")
                runtime_metrics["input_events_errors"] += 1
                break
        
                
        # Get the game surface from frontend
        game_surface = frontend.screen.get_surface()
        
        # Periodically refresh client status in lobby states to discover new web players
        if theGame.game_state in ["startup", "game_prep"]:
            if not hasattr(theGame, '_last_status_refresh') or theGame.current_time - theGame._last_status_refresh > 1500:
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
                # If in game_prep, update local lobby player list only when remote state changed.
                if theGame.game_state == "game_prep":
                    if new_status_sig != previous_status_sig:
                        theGame.create_players()
                theGame._last_status_refresh = theGame.current_time

        # Publish latest state with bounded queue policy.
        state_payload = theGame.to_dict()
        samples = runtime_metrics["input_apply_samples_ms"]
        if samples:
            avg_input_apply = sum(samples) / len(samples)
        else:
            avg_input_apply = 0.0
        state_payload["_net_metrics"] = {
            "input_events_processed": runtime_metrics["input_events_processed"],
            "input_events_errors": runtime_metrics["input_events_errors"],
            "state_queue_sent": runtime_metrics["state_queue_sent"],
            "state_queue_dropped": runtime_metrics["state_queue_dropped"],
            "avg_input_apply_ms": round(avg_input_apply, 2),
            "host_fps_5s": round(runtime_metrics["avg_fps_5s"], 1),
        }
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
                f"avg_apply_ms={state_payload['_net_metrics']['avg_input_apply_ms']} "
                f"fps_5s={state_payload['_net_metrics']['host_fps_5s']}"
            )

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
                # Display "Press Enter to start the game" message
                start_text = get_ui_font().render("Press Enter to start the game", True, (255, 255, 255))
                start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
                game_surface.blit(start_text, start_rect)
        elif theGame.game_state == "game_prep":
            draw_game_prep(game_surface, theGame)
        elif theGame.game_state == "get_ready":
            if theGame.current_time < theGame.game_start_time:
                draw_game_screen(game_surface, theGame)
                draw_get_ready(game_surface)
            else:
                theGame.game_state = "playing"  
        elif theGame.game_state == "playing":
            theGame.update()
            draw_game_screen(game_surface, theGame)
        elif theGame.game_state == "win":
            draw_title_page(game_surface, alpha=255)
            alive_players = [p for p in theGame.players if p.alive]
            draw_stat_screen(game_surface, alive_players[0] if alive_players else None, theGame.players, theGame)
        elif theGame.game_state == "champion":
            alive_players = [p for p in theGame.players if p.alive]
            draw_champion_screen(game_surface, alive_players[0] if alive_players else None)

        # Always show host perf info on every host-rendered screen.
        perf = state_payload["_net_metrics"]
        perf_text = f"HOST FPS(5s): {perf['host_fps_5s']} | INPUT LAT(5s): {perf['avg_input_apply_ms']}ms"
        perf_surface = get_ui_font().render(perf_text, True, (210, 230, 255))
        perf_rect = perf_surface.get_rect(bottomleft=(20, BASE_HEIGHT - 14))
        game_surface.blit(perf_surface, perf_rect)

        
        
        # Use frontend renderer
        frontend.render()
        
        # Check if we should quit
        if frontend.should_quit:
            break


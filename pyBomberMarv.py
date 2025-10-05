# internal imports

from PIL import Image
import socket
import multiprocessing
import psutil
import queue
from turbojpeg import TurboJPEG, TJPF_RGB
import numpy as np
from frontend import FrontendManager
from bm_drawing import draw_game_screen, draw_get_ready, draw_title_page, draw_stat_screen, draw_champion_screen
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

def start_ws_server_with_queue(input_queue):
    # Start the server in a process, passing input queue only, and log output to ws_server.log
    p = multiprocessing.Process(target=ws_stream_server.run_server_with_queue, args=(input_queue, "ws_server.log"))
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
    
    
    from bm_params import *
    from bm_sounds import *
    from lib_collisions import *
    from lib_grid import *
    from bm_drawing import *
    from bm_classes import *
    
    kill_existing_ws_server_processes()
    # Free the TCP ports if occupied
    kill_processes_on_ports({8080, 8765})
    
    # Start the input server with a multiprocessing queue for input only
    input_queue = multiprocessing.Queue()
    ws_process = start_ws_server_with_queue(input_queue)
    
    # Get reference to server functions for game state updates
    update_game_state = ws_stream_server.update_game_state

    print("DEBUG: Creating Game instance...")
    theGame = Game()
    print("DEBUG: Game instance created")
    # Don't call init_game() here - we want to start in prep mode
    # theGame.init_game()

    # Set game instance in WebSocket server for input handling
    ws_stream_server.set_game_instance(theGame)

    # Create frontend and initialize
    print("DEBUG: Creating frontend...")
    frontend = FrontendManager(theGame)
    print("DEBUG: Initializing frontend...")
    window = frontend.initialize()
    print("DEBUG: Setting frontend in game...")
    theGame.set_frontend(frontend)
    print("DEBUG: Starting main game loop...")

    while True:
        theGame.tick()
        
        
        theGame.handle_window_events()
        # Handle web key events from input_queue (use non-blocking drain)
        processed_events = 0
        while True:
            try:
                event = input_queue.get_nowait()
                processed_events += 1
                print(f"DEBUG: Main game received event: {event}")
                if isinstance(event, dict) and event.get('type') == 'client_key_debug':
                    print(f"DEBUG: CLIENT DEBUG -> event={event.get('event')} key={event.get('key')} pressed={event.get('pressed_keys')}")
                theGame.handle_web_key_event(event)
            except queue.Empty:
                if processed_events and processed_events > 0:
                    print(f"DEBUG: Processed {processed_events} input events this tick")
                break
            except Exception as e:
                print(f"DEBUG: Exception processing input queue: {e}")
                break
        
                
        # Get the game surface from frontend
        game_surface = frontend.screen.get_surface()
        
        # Update server with current game state (only when it changes)
        update_game_state(theGame.game_state)

        if theGame.game_state == "startup":
            # Draw startup screen
            from bm_drawing import draw_title_page, draw_controls
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
                from bm_drawing import font_small
                from bm_params import BASE_WIDTH, BASE_HEIGHT
                start_text = font_small.render("Press Enter to start the game", True, (255, 255, 255))
                start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
                game_surface.blit(start_text, start_rect)
        elif theGame.game_state == "game_prep":
            # Draw game prep screen
            from bm_drawing import draw_game_prep
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
            draw_stat_screen(game_surface, alive_players[0] if alive_players else None, theGame.players)
        elif theGame.game_state == "champion":
            alive_players = [p for p in theGame.players if p.alive]
            draw_champion_screen(game_surface, alive_players[0] if alive_players else None)

        
        
        # Use frontend renderer
        frontend.render()
        
        # Check if we should quit
        if frontend.should_quit:
            break


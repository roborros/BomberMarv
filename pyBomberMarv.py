# internal imports

from PIL import Image
import socket
import multiprocessing
import ws_stream_server  # Import as a module
import psutil
from turbojpeg import TurboJPEG, TJPF_RGB
import numpy as np
from frontend import FrontendManager
from bm_drawing import draw_game_screen, draw_get_ready, draw_title_page, draw_stat_screen, draw_champion_screen


## TODO
# improve collisions - rounded rectangle corners, alley clamping
# rework explosion animation and colision box
# split BE/FE
# store all necessary params to bomb class, do not access player later
# bomb collision with a player is strictly based on distance I am hedding towards (out of the center is allowed + 10 size margin)
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
# remove bomb owner lesf tate from the bomb class and related collision checks
# abstract state changes to the game class method




def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def start_ws_server_with_queue(frame_queue, input_queue):
    # Start the server in a process, passing both queues, and log output to ws_server.log
    p = multiprocessing.Process(target=ws_stream_server.run_server_with_queue, args=(frame_queue, input_queue, "ws_server.log"))
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

if __name__ == "__main__":
    
    
    from bm_params import *
    from bm_sounds import *
    from lib_collisions import *
    from lib_grid import *
    from bm_drawing import *
    from bm_classes import *
    
    kill_existing_ws_server_processes()
    
    # Start the streaming server with a multiprocessing queue for frames and input
    frame_queue = multiprocessing.Queue(maxsize=2)
    input_queue = multiprocessing.Queue()
    ws_process = start_ws_server_with_queue(frame_queue, input_queue)

    theGame = Game()
    theGame.init_game()

    # Create frontend and initialize
    frontend = FrontendManager(theGame)
    window = frontend.initialize()
    theGame.set_frontend(frontend)

    while True:
        theGame.tick()
        
        
        theGame.handle_window_events()
        # Handle web key events from input_queue
        while not input_queue.empty():
            try:
                event = input_queue.get_nowait()
                theGame.handle_web_key_event(event)
            except Exception:
                break
        
                
        # Get the game surface from frontend
        game_surface = frontend.screen.get_surface()
        
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


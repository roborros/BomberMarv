# internal imports

from PIL import Image
import io
import threading
import subprocess
import socket
import multiprocessing
import ws_stream_server  # Import as a module
import psutil
from turbojpeg import TurboJPEG, TJPF_RGB
import numpy as np




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

# BUG

# test version for web deployment using piglet

def save_surface_as_jpeg(surface):
    data = pygame.image.tostring(surface, 'RGB')
    width, height = surface.get_size()
    arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))   
    jpeg_bytes = jpeg.encode(arr, quality=65, pixel_format=TJPF_RGB)
    return jpeg_bytes



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
    
    jpeg = TurboJPEG("C:\\libjpeg-turbo-gcc64\\bin\\libturbojpeg.dll")
    
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

    theScreen = Screen()

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
                
        if theGame.game_state == "startup":
            theScreen.draw_startup(theGame)
        elif theGame.game_state == "get_ready":
            if theGame.current_time < theGame.game_start_time:
                draw_game_screen(theScreen.surface, theGame)
                draw_get_ready(theScreen.surface)
            else:
                theGame.game_state = "playing"  
        elif theGame.game_state == "playing":
            theGame.update()
            draw_game_screen(theScreen.surface, theGame)
        elif theGame.game_state == "win":
            draw_title_page(theScreen.surface, alpha=255)
            alive_players = [p for p in theGame.players if p.alive]
            draw_stat_screen(theScreen.surface, alive_players[0] if alive_players else None, theGame.players)
        elif theGame.game_state == "champion":
            alive_players = [p for p in theGame.players if p.alive]
            draw_champion_screen(theScreen.surface, alive_players[0] if alive_players else None)

        
        jpeg_bytes = save_surface_as_jpeg(theScreen.surface)
        
        
        if jpeg_bytes is not None:
            # Only keep the latest frame in the queue
            while not frame_queue.empty():
                try:
                    frame_queue.get_nowait()
                except:
                    break
            frame_queue.put(jpeg_bytes)
        
        
        draw_adjust_screen_size(theGame.window_size, theScreen.surface, window)


# internal imports
from bm_params import *
from bm_sounds import *
from lib_collisions import *
from lib_grid import *
from bm_drawing import *
from bm_classes import *
from PIL import Image
import io
import threading
import subprocess
import socket


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

def save_surface_as_jpeg(surface, filename="current_frame.jpg"):
    # Convert pygame surface to string buffer and then to PIL Image
    # If using pyglet, adapt accordingly
    try:
        import pygame
        import os
        import time
        # Convert surface to string buffer
        data = pygame.image.tostring(surface, 'RGB')
        img = Image.frombytes('RGB', surface.get_size(), data)
        tmp_filename = filename + ".tmp"
        img.save(tmp_filename, 'JPEG', quality=25)
        # Atomic rename with retry on Windows
        for attempt in range(10):
            try:
                os.replace(tmp_filename, filename)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.01)  # Wait 10ms and try again
    except ImportError:
        # If using pyglet or another library, adapt this part
        pass

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def start_ws_server():
    # Check if either port is in use
    if is_port_in_use(8080):
        print("Port 8080 is already in use. Not starting HTTP server.")
        return
    if is_port_in_use(8765):
        print("Port 8765 is already in use. Not starting WebSocket server.")
        return
    # Start the WebSocket/HTTP server in a background thread
    def run_server():
        subprocess.Popen(["python", "ws_stream_server.py"])
    threading.Thread(target=run_server, daemon=True).start()

# Start the streaming server
start_ws_server()

theGame = Game()
theGame.init_game()

theScreen = Screen()

while True:
    theGame.tick()
    
    theGame.handle_window_events()
    
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
    
    
    save_surface_as_jpeg(theScreen.surface)
    
    
    draw_adjust_screen_size(theGame.window_size, theScreen.surface, window)
    
    #automate_player(theGame.players[0], theGame.dt, theGame.board, theGame.bombs)

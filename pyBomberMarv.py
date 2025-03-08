

# internal imports
from bm_params import *
from bm_sounds import *
from lib_collisions import *
from lib_grid import *
from bm_drawing import *
from bm_classes import *


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
    
    draw_adjust_screen_size(theGame.window_size, theScreen.surface, window)
    #automate_player(theGame.players[0], theGame.dt, theGame.board, theGame.bombs)

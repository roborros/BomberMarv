

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
# collect and present game stats and events (how many bonuses (show plot in time), bombs, kills)
# BUG


theGame = Game()
theGame.init_game()

theScreen = Screen()

while True:
    theGame.tick()
    
    theGame.handle_window_events()
    
    if theGame.game_state == "startup":
        
        theScreen.draw_startup(game_surface,theGame)
    
    elif theGame.game_state == "get_ready":
        
        if theGame.current_time < theGame.game_start_time:
            draw_game_screen(game_surface, theGame)
            start_text = arcade_font.render("Get Ready!", True, (180, 60, 120))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT- 500))
            game_surface.blit(start_text, start_rect)
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
    
    draw_adjust_screen_size(theGame.window_size, game_surface, window)


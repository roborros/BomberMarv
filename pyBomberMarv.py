

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

# BUG


theGame = Game()
theGame.init_game()


while True:
    dt = clock.tick(FPS) # should be constant but when moved to params the game seems to by appx 30% faster, WHY?
    theGame.tick()
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        elif event.type == pygame.VIDEORESIZE:
            window_size = event.size
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    window = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
                    window_size = window.get_size()
                else:
                    window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
                    window_size = INITIAL_WINDOW_SIZE
            elif event.key == pygame.K_RETURN:
                if theGame.game_state in ["win", "champion", "startup"]:
                    theGame.init_game()
                    theGame.game_state = "playing"

    game_surface.fill(COLOR_BG) # move inside drawinf fcns
    
    
    if theGame.game_state == "startup":
        elapsed = theGame.current_time - theGame.startup_start_time
        if elapsed < 2000:
            alpha = 255
        elif elapsed < 2800:
            alpha = int(255 * (2500 - elapsed) / 500)
       
        draw_title_page(game_surface, alpha)
        
        if int(elapsed) >= 2200:
            draw_controls(game_surface, theGame.players)

            # Display "Press Enter to start the game" message
            start_text = font_small.render("Press Enter to start the game", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            game_surface.blit(start_text, start_rect)
        
        

    elif theGame.game_state == "playing":
        if theGame.current_time < theGame.game_start_time:
            draw_game_screen(game_surface, theGame)
            start_text = font_small.render("Get Ready!", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            game_surface.blit(start_text, start_rect)
        else:
            for player in theGame.players:
                player.update(dt, theGame.board, theGame.bombs, theGame.current_time)
            triggered_explosions = []
            for bomb in theGame.bombs[:]:
                if bomb.update(theGame.current_time):
                    exp = Explosion(theGame.get_explosion_cells(bomb), theGame.current_time, bomb.quad_damage)
                    triggered_explosions.append(exp)
                    bomb.owner.active_bombs -= 1
                    theGame.bombs.remove(bomb)
            chain_cells = set()
            for exp in triggered_explosions:
                for cell in exp.cells:
                    chain_cells.add(cell)
            chain_triggered = True
            while chain_triggered:
                chain_triggered = False
                for bomb in theGame.bombs[:]:
                    if (bomb.x, bomb.y) in chain_cells:
                        exp = Explosion(theGame.get_explosion_cells(bomb), theGame.current_time,bomb.quad_damage)
                        triggered_explosions.append(exp)
                        for cell in exp.cells:
                            chain_cells.add(cell)
                        bomb.owner.active_bombs -= 1
                        theGame.bombs.remove(bomb)
                        chain_triggered = True
            theGame.explosions.extend(triggered_explosions)
            for explosion in theGame.explosions[:]:
                if not explosion.is_active(theGame.current_time):
                    theGame.handle_explosion(explosion)
                    theGame.explosions.remove(explosion)
            for player in theGame.players:
                if not player.alive:
                    continue
                for pu in theGame.powerups[:]:
                    if player.get_grid_pos() == (pu.x, pu.y):
                        if pu.type == "bomb":
                            player.bomb_capacity += 1
                            bonus_sound.play()
                        elif pu.type == "fire":
                            player.fire_power += 1
                            bonus_sound.play()
                        elif pu.type == "quad_damage":
                            player.quad_damage = True
                            player.quad_damage_start_time = theGame.current_time
                            player.bomb_capacity += QUAD_DAMAGE_POWER
                            player.fire_power += QUAD_DAMAGE_POWER
                            qd_sound.play()
                        theGame.powerups.remove(pu)
                        
            theGame.place_quad_damage_powerup()
            alive_players = [p for p in theGame.players if p.alive]
            if len(alive_players) <= 1:
                if alive_players:
                    alive_players[0].trophies += 1
                    if alive_players[0].trophies >= TROPHY_WIN_THRESHOLD:
                        theGame.game_state = "champion"
                    else:
                        theGame.game_state = "win"
                else:
                    theGame.game_state = "win"
            draw_game_screen(game_surface, theGame)

    elif theGame.game_state == "win":
        draw_title_page(game_surface, alpha=255)
        draw_stat_screen(game_surface, alive_players[0] if alive_players else None, theGame.players)

    elif theGame.game_state == "champion":
        draw_champion_screen(game_surface, alive_players[0] if alive_players else None)
    
    draw_adjust_screen_size(window_size, game_surface, window)


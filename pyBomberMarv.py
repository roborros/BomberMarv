

# internal imports
from bm_params import *
from bm_sounds import *
from lib_collisions import *
from lib_grid import *
from bm_drawing import *
from bm_classes import *
from bm_game_sm import *


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

## BUG
# stat screen does not show the player tropies


def place_quad_damage_powerup():
    if (pygame.time.get_ticks() - theGame.game_start_time) >= QUAD_DAMAGE_DELAY*1000:  # 2 minutes
        if not any(pu.type == "quad_damage" for pu in theGame.powerups):
            empty_cells = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH) if theGame.board[y][x] == EMPTY]
            if empty_cells and random.random() < QUAD_DAMAGE_PROBABILITY:
                x, y = random.choice(empty_cells)
                theGame.powerups.append(PowerUp(x, y, "quad_damage"))

def handle_explosion(explosion):
    if explosion.quad_damage:
        explosion_sound_qd.play()
    else:
        explosion_sound.play()
        
    for (x, y) in explosion.cells:
        if theGame.board[y][x] == DESTRUCTIBLE:
            theGame.board[y][x] = EMPTY
            if random.random() < POWERUP_PROBABILITY:
                pu_type = random.choice(["bomb", "fire"])
                theGame.powerups.append(PowerUp(x, y, pu_type, spawn_time=explosion.start_time))
    for pu in theGame.powerups[:]:
        if pu.spawn_time < explosion.start_time and (pu.x, pu.y) in explosion.cells:
            theGame.powerups.remove(pu)
    for player in theGame.players:
        if player.alive:
            for cell in explosion.cells:
                explosion_rect = pygame.Rect(cell[0]*CELL_SIZE, cell[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE)
                if circle_rect_collision((player.pos.x, player.pos.y), player.collision_radius, explosion_rect):
                    player.alive = False
                    player.death_animation_time = 1000  # 1 second death animation
                    death_sound.play()
                    break


# --- Main Game Loop ---

# --- Global State for Screens ---
game_state = "startup"  # "startup", "playing", "win", "champion"
startup_start_time = pygame.time.get_ticks()

# --- Fullscreen and Resizable Window Setup ---
is_fullscreen = False
window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
pygame.display.set_caption("BomberMarv")
clock = pygame.time.Clock()
game_surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))

theGame = Game()
theGame.init_game()

window_size = INITIAL_WINDOW_SIZE

while True:
    dt = clock.tick(FPS)
    current_time = pygame.time.get_ticks()
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
            elif theGame.game_state == "playing" and current_time >= theGame.game_start_time:
                for player in theGame.players:
                    if event.key == player.controls['bomb']:
                        player.drop_bomb(theGame.bombs, current_time)

    game_surface.fill(COLOR_BG)
    if theGame.game_state == "startup":
        elapsed = current_time - startup_start_time
        if elapsed < 2000:
            alpha = 255
        elif elapsed < 2800:
            alpha = int(255 * (2500 - elapsed) / 500)
       
        
        if int(elapsed) >= 2200:
            draw_controls(game_surface, theGame.players)

            # Display "Press Enter to start the game" message
            start_text = font_small.render("Press Enter to start the game", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            game_surface.blit(start_text, start_rect)
        
        draw_title_page(game_surface, alpha)

    elif theGame.game_state == "playing":
        if current_time < theGame.game_start_time:
            draw_board(game_surface, theGame)
            draw_powerups(game_surface, theGame)
            draw_bombs(game_surface, current_time, theGame.bombs)
            draw_explosions(game_surface, current_time, theGame.explosions)
            draw_players(game_surface,theGame.players)
            start_text = font_small.render("Get Ready!", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            game_surface.blit(start_text, start_rect)
        else:
            for player in theGame.players:
                player.update(dt, theGame.board, theGame.bombs)
            triggered_explosions = []
            for bomb in theGame.bombs[:]:
                if bomb.update(current_time):
                    exp = Explosion(theGame.get_explosion_cells(bomb), current_time, bomb.quad_damage)
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
                        exp = Explosion(theGame.get_explosion_cells(bomb), current_time,bomb.quad_damage)
                        triggered_explosions.append(exp)
                        for cell in exp.cells:
                            chain_cells.add(cell)
                        bomb.owner.active_bombs -= 1
                        theGame.bombs.remove(bomb)
                        chain_triggered = True
            theGame.explosions.extend(triggered_explosions)
            for explosion in theGame.explosions[:]:
                if not explosion.is_active(current_time):
                    handle_explosion(explosion)
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
                            player.quad_damage_start_time = current_time
                            player.bomb_capacity += QUAD_DAMAGE_POWER
                            player.fire_power += QUAD_DAMAGE_POWER
                            qd_sound.play()
                        theGame.powerups.remove(pu)
                        
            place_quad_damage_powerup()  # Call the function to place the quad damage powerup
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
            draw_board(game_surface, theGame)
            draw_powerups(game_surface, theGame)
            draw_bombs(game_surface, current_time, theGame.bombs)
            draw_explosions(game_surface, current_time, theGame.explosions)
            draw_players(game_surface, theGame.players)

    elif theGame.game_state == "win":
        draw_title_page(game_surface, alpha=255)
        draw_stat_screen(game_surface, alive_players[0] if alive_players else None, theGame.players)

    elif theGame.game_state == "champion":
        draw_champion_screen(game_surface, alive_players[0] if alive_players else None)
    
    factor = min(window_size[0] / BASE_WIDTH, window_size[1] / BASE_HEIGHT)
    new_width = int(BASE_WIDTH * factor)
    new_height = int(BASE_HEIGHT * factor)
    scaled_surface = pygame.transform.smoothscale(game_surface, (new_width, new_height))
    window.fill((0,0,0))
    x_offset = (window_size[0] - new_width) // 2
    y_offset = (window_size[1] - new_height) // 2
    window.blit(scaled_surface, (x_offset, y_offset))
    pygame.display.flip()



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





def get_explosion_cells(bomb):
    cells = [(bomb.x, bomb.y)]
    for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
        for i in range(1, bomb.fire_power + 1):
            nx = bomb.x + dx * i
            ny = bomb.y + dy * i
            if nx < 0 or nx >= GRID_WIDTH or ny < 0 or ny >= GRID_HEIGHT:
                break
            if theGame.board[ny][nx] == INDESTRUCTIBLE:
                break
            cells.append((nx, ny))
            if theGame.board[ny][nx] == DESTRUCTIBLE:
                break
    return cells

def draw_board(surface):
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            if theGame.board[y][x] == EMPTY:
                pygame.gfxdraw.box(surface, rect, COLOR_BG)
            elif theGame.board[y][x] == INDESTRUCTIBLE:
                pygame.gfxdraw.box(surface, rect, COLOR_INDESTRUCTIBLE)
                pygame.draw.rect(surface, (80,80,80), rect, 1)
            elif theGame.board[y][x] == DESTRUCTIBLE:
                pygame.gfxdraw.box(surface, rect, COLOR_DESTRUCTIBLE)
                draw_brick_pattern(rect, surface)
                pygame.draw.rect(surface, (80,80,80), rect, 1)

def draw_powerups(surface):
    for p in theGame.powerups:
        center = (p.x * CELL_SIZE + CELL_SIZE//2, p.y * CELL_SIZE + CELL_SIZE//2)
        size = CELL_SIZE - 20
        draw_powerup_icon(surface, center, size, p.type)

def draw_powerup_icon(surface, center, size, powerup_type):
    if powerup_type == "bomb":
        draw_bomb_powerup_icon(surface, center, size)
    elif powerup_type == "fire":
        draw_fire_powerup_icon(surface, center, size)
    elif powerup_type == "quad_damage":
        draw_quad_damage_powerup_icon(surface, center, size)

def draw_bomb_powerup_icon(surface, center, size):
    size = int(size * 1.3)
    rect = pygame.Rect(center[0] - size//2, center[1] - size//2, size, size)
    blue_border = (0, 255, 255)
    pygame.draw.rect(surface, blue_border, rect, 4)
    bomb_r = size // 3
    cell_center = center
    bomb_radius = bomb_r
    pygame.gfxdraw.filled_circle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_FILL)
    pygame.gfxdraw.aacircle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_OUTLINE)
    fuse_radius = max(2, bomb_radius // 3)
    fuse_offset = int(bomb_radius * 0.6)
    fuse_center = (cell_center[0], cell_center[1] - fuse_offset)
    pygame.gfxdraw.filled_circle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)
    pygame.gfxdraw.aacircle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)   

def draw_fire_powerup_icon(surface, center, size):
    size2 = int(size * 1.3)
    rect = pygame.Rect(center[0] - size2//2, center[1] - size2//2, size2, size2)
    blue_border = (0, 255, 255)
    pygame.draw.rect(surface, blue_border, rect, 4)
    
     # Scale the fire powerup image to fit the size
    scaled_image = pygame.transform.smoothscale(fire_powerup_image, (size, size))
    
    # Get the rectangle for the scaled image and center it
    image_rect = scaled_image.get_rect(center=center)
    
    # Blit the scaled image onto the surface
    surface.blit(scaled_image, image_rect)
    
def draw_quad_damage_powerup_icon(surface, center, size):
    # Scale the quad damage image to fit the size
    scaled_image = pygame.transform.smoothscale(quad_damage_image, (size, size))
    
    # Get the rectangle for the scaled image and center it
    image_rect = scaled_image.get_rect(center=center)
    
    # Blit the scaled image onto the surface
    surface.blit(scaled_image, image_rect)


def place_quad_damage_powerup():
    if (pygame.time.get_ticks() - theGame.game_start_time) >= QUAD_DAMAGE_DELAY*1000:  # 2 minutes
        if not any(pu.type == "quad_damage" for pu in theGame.powerups):
            empty_cells = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH) if theGame.board[y][x] == EMPTY]
            if empty_cells and random.random() < QUAD_DAMAGE_PROBABILITY:
                x, y = random.choice(empty_cells)
                theGame.powerups.append(PowerUp(x, y, "quad_damage"))

def draw_trophy_icon(surface, pos, size):
    trophy_color = (212, 175, 55)
    x, y = pos
    width = size
    height = size
    dome_rect = pygame.Rect(x, y, width, int(height * 0.6))
    pygame.draw.ellipse(surface, trophy_color, dome_rect)
    cup_rect = pygame.Rect(x + int(width * 0.2), y + int(height * 0.5), int(width * 0.6), int(height * 0.3))
    pygame.draw.rect(surface, trophy_color, cup_rect)
    base_rect = pygame.Rect(x + int(width * 0.3), y + int(height * 0.85), int(width * 0.4), int(height * 0.15))
    pygame.draw.rect(surface, trophy_color, base_rect)

def draw_players(surface):
    for player in theGame.players:
        if not player.alive and player.death_animation_time <= 0:
            continue
        pos = (int(player.pos.x), int(player.pos.y))
        r = player.draw_radius
        if player.alive:
            pygame.gfxdraw.filled_circle(surface, pos[0], pos[1], r, player.color)
            pygame.gfxdraw.aacircle(surface, pos[0], pos[1], r, player.color)
            helmet_color = (min(player.color[0]+30,255), min(player.color[1]+30,255), min(player.color[2]+30,255))
            rect_head = pygame.Rect(pos[0]-r, pos[1]-r, 2*r, 2*r)
            pygame.draw.arc(surface, helmet_color, rect_head, math.pi, 2*math.pi, 3)
            eye_r = max(1, r//8)
            eye_offset_x = r//3
            eye_offset_y = r//3
            pygame.gfxdraw.filled_circle(surface, pos[0]-eye_offset_x, pos[1]-eye_offset_y, eye_r, (0,0,0))
            pygame.gfxdraw.filled_circle(surface, pos[0]+eye_offset_x, pos[1]-eye_offset_y, eye_r, (0,0,0))
            leg_width = r//3
            leg_height = r//4
            leg_offset = int(6 * math.sin(player.animation_time / 150.0))
            left_leg = pygame.Rect(pos[0] - r//2 - leg_width//2, pos[1] + r - 2 + leg_offset, leg_width, leg_height)
            right_leg = pygame.Rect(pos[0] + r//2 - leg_width//2, pos[1] + r - 2 - leg_offset, leg_width, leg_height)
            leg_color = (player.color[0]//2, player.color[1]//2, player.color[2]//2)
            pygame.draw.rect(surface, leg_color, left_leg)
            pygame.draw.rect(surface, leg_color, right_leg)
        
            if player.quad_damage:
                elapsed = pygame.time.get_ticks() - player.quad_damage_start_time
                pulse = 1 + 0.1 * math.sin(2 * math.pi * (elapsed / 500.0))
                rect_size = int((2 * r + 10) * pulse)
                rect = pygame.Rect(pos[0] - rect_size // 2, pos[1] - rect_size // 2, rect_size, rect_size)
                pygame.draw.rect(surface, (0, 255, 255), rect, 4)
            
            # Draw player name
            name_text = font_small.render(player.name, True, (255, 255, 255))
            name_rect = name_text.get_rect(center=(pos[0], pos[1] - r - 10))
            surface.blit(name_text, name_rect)
        else:
            # Draw death animation
            alpha = int(255 * (player.death_animation_time / 1000.0))
            death_color = (255, 0, 0, alpha)
            pygame.gfxdraw.filled_circle(surface, pos[0], pos[1], r, death_color)
            pygame.gfxdraw.aacircle(surface, pos[0], pos[1], r, death_color)

def draw_bombs(surface, current_time):
    for bomb in theGame.bombs:
        cell_center = (bomb.x * CELL_SIZE + CELL_SIZE//2, bomb.y * CELL_SIZE + CELL_SIZE//2)
        elapsed = current_time - bomb.start_time
        pulse = 1 + BOMB_PULSE_AMPLITUDE * math.sin(2 * math.pi * (elapsed / BOMB_PULSE_SPEED))
        bomb_radius = int(BOMB_BASE_RADIUS * pulse)
        pygame.gfxdraw.filled_circle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_FILL)
        pygame.gfxdraw.aacircle(surface, cell_center[0], cell_center[1], bomb_radius, COLOR_BOMB_OUTLINE)
        fuse_radius = max(2, bomb_radius // 3)
        fuse_offset = int(bomb_radius * 0.6)
        fuse_center = (cell_center[0], cell_center[1] - fuse_offset)
        pygame.gfxdraw.filled_circle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)
        pygame.gfxdraw.aacircle(surface, fuse_center[0], fuse_center[1], fuse_radius, COLOR_FUSE)

def draw_explosions(surface, current_time):
    for explosion in theGame.explosions:
        norm = (current_time - explosion.start_time) / EXPLOSION_DURATION
        norm = min(norm, 1)
        if norm < 0.2:
            arm_factor = norm / 0.2
        elif norm <= 0.7:
            arm_factor = 1
        else:
            arm_factor = (1 - (norm - 0.7) / 0.3)
        
        cx, cy = explosion.cells[0]
        center_pixel = (cx * CELL_SIZE + CELL_SIZE // 2, cy * CELL_SIZE + CELL_SIZE // 2)
        
        up_max = max([cy - cell[1] for cell in explosion.cells if cell[0] == cx and cell[1] < cy] or [0])
        down_max = max([cell[1] - cy for cell in explosion.cells if cell[0] == cx and cell[1] > cy] or [0])
        left_max = max([cx - cell[0] for cell in explosion.cells if cell[1] == cy and cell[0] < cx] or [0])
        right_max = max([cell[0] - cx for cell in explosion.cells if cell[1] == cy and cell[0] > cx] or [0])
        
        up_length = arm_factor * up_max * CELL_SIZE
        down_length = arm_factor * down_max * CELL_SIZE
        left_length = arm_factor * left_max * CELL_SIZE
        right_length = arm_factor * right_max * CELL_SIZE
        
        if explosion.quad_damage:
            img = blast_image_qd
            center_img = blast_centre_image_qd
        else:
            img = blast_image
            center_img = blast_centre_image
        
        # Draw the center of the explosion using the center image
        scaled_center_img = pygame.transform.smoothscale(center_img, (CELL_SIZE * FLAME_ARM_THICKNESS_RATIO, CELL_SIZE * FLAME_ARM_THICKNESS_RATIO))
        center_rect = scaled_center_img.get_rect(center=center_pixel)
        surface.blit(scaled_center_img, center_rect)
        
        # Draw the arms of the explosion using the blast image
        if up_length > 0:
            draw_blast_arm(surface, center_pixel, (0, -up_length), img)
        
        if down_length > 0:
            draw_blast_arm(surface, center_pixel, (0, down_length), img)
        
        if left_length > 0:
            draw_blast_arm(surface, center_pixel, (-left_length, 0), img)
        
        if right_length > 0:
            draw_blast_arm(surface, center_pixel, (right_length, 0), img)

def draw_blast_arm(surface, start_pos, end_offset, image):
    x1, y1 = start_pos
    x2, y2 = x1 + end_offset[0], y1 + end_offset[1]
    length = math.hypot(x2 - x1, y2 - y1)
    
    # Calculate the angle for rotation
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    
    # Scale the image to the length of the arm
    scaled_image = pygame.transform.smoothscale(image, (int(length), int(CELL_SIZE * FLAME_ARM_THICKNESS_RATIO)))
    
    # Rotate the image
    if angle == 0:
        rotated_image = pygame.transform.rotate(scaled_image, 180)
    elif angle == 180:
        rotated_image = scaled_image
    else:
        rotated_image = pygame.transform.rotate(scaled_image, angle)
    
     # Get the rectangle for the rotated image and place its right edge at the center of the starting cell
    image_rect = rotated_image.get_rect()
    image_rect.center = (x1, y1)
    if angle == -90:
        image_rect.bottom = y1
    elif angle == 0:
        image_rect.left = x1
    elif angle == 90:
        image_rect.top = y1
    else:
        image_rect.right = x1
    
    # Blit the rotated image onto the surface
    surface.blit(rotated_image, image_rect)
    

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

def draw_controls(surface):
    font = pygame.font.SysFont("arial", 40)
    y_offset = BASE_HEIGHT - BASE_HEIGHT // 3
    control_text = "Controls: Up -  Down - Left - Right - Bomb"
    text = font.render(control_text, True, (255, 255, 255))
    rect = text.get_rect(center=(BASE_WIDTH // 2, y_offset))
    surface.blit(text, rect)
    y_offset += 50
    for i, player in enumerate(players):
        controls = player.controls
        control_text = f"{player.name}: {pygame.key.name(controls['up'])} - {pygame.key.name(controls['down'])} - {pygame.key.name(controls['left'])} - {pygame.key.name(controls['right'])} - {pygame.key.name(controls['bomb'])}"
        text = font.render(control_text, True, player.color)
        rect = text.get_rect(center=(BASE_WIDTH // 2, y_offset))
        surface.blit(text, rect)
        y_offset += 50

def draw_stat_screen(surface, winner):
    font = pygame.font.SysFont("arial", 48, bold=True)
    draw_title_page(surface, alpha=255)
    if winner:
        x_start = BASE_WIDTH//2 + 150
        icon_size = 24
        for i in range(winner.trophies):
            trophy_pos = (x_start + i * (icon_size + 5), BASE_HEIGHT//2 + 70)
            draw_trophy_icon(surface, trophy_pos, icon_size)
        text = font.render(f"{winner.name} wins!", True, winner.color)
    else:
        text = font.render("No one wins!", True, (255,255,255))
    rect = text.get_rect(center=(BASE_WIDTH//2, BASE_HEIGHT//2 + 80))
    surface.blit(text, rect)
    font_small = pygame.font.SysFont("arial", 32)
    y_offset = BASE_HEIGHT//2 + 110
    for i, player in enumerate(players):
        trophy_surface = pygame.Surface((150, 40), pygame.SRCALPHA)
        for j in range(player.trophies):
            draw_trophy_icon(trophy_surface, (j * 30, 0), 24+10)
        win_text = font_small.render(f"{player.name}:", True, player.color)
        surface.blit(win_text, (50, y_offset))
        surface.blit(trophy_surface, (200, y_offset))
        y_offset += 40
        
    #draw_controls(surface)

def draw_champion_screen(surface, champion):
    font = pygame.font.SysFont("arial", 60, bold=True)
    draw_title_page(surface, alpha=255)
    trophy_surface = pygame.Surface((200, 40), pygame.SRCALPHA)
    for j in range(champion.trophies):
        draw_trophy_icon(trophy_surface, (j * 30, 0), 24)
    text = font.render(f"Champion: {champion.name}", True, champion.color)
    rect = text.get_rect(center=(BASE_WIDTH//2, BASE_HEIGHT//2 - 100))
    surface.blit(text, rect)
    surface.blit(trophy_surface, (BASE_WIDTH//2 - 100, BASE_HEIGHT//2 + 100))

def get_explosion_cells(bomb):
    cells = [(bomb.x, bomb.y)]
    for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
        for i in range(1, bomb.fire_power + 1):
            nx = bomb.x + dx * i
            ny = bomb.y + dy * i
            if nx < 0 or nx >= GRID_WIDTH or ny < 0 or ny >= GRID_HEIGHT:
                break
            if theGame.board[ny][nx] == INDESTRUCTIBLE:
                break
            cells.append((nx, ny))
            if theGame.board[ny][nx] == DESTRUCTIBLE:
                break
    return cells

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
                if game_state in ["win", "champion", "startup"]:
                    theGame.init_game()
                    game_state = "playing"
            elif game_state == "playing" and current_time >= theGame.game_start_time:
                for player in theGame.players:
                    if event.key == player.controls['bomb']:
                        player.drop_bomb(theGame.bombs, current_time)

    game_surface.fill(COLOR_BG)
    if game_state == "startup":
        elapsed = current_time - startup_start_time
        if elapsed < 2000:
            alpha = 255
        elif elapsed < 2800:
            alpha = int(255 * (2500 - elapsed) / 500)
       
        
        if int(elapsed) >= 2200:
            draw_controls(game_surface)

            # Display "Press Enter to start the game" message
            start_text = font_small.render("Press Enter to start the game", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            game_surface.blit(start_text, start_rect)
        
        draw_title_page(game_surface, alpha)

    elif game_state == "playing":
        if current_time < theGame.game_start_time:
            draw_board(game_surface)
            draw_powerups(game_surface)
            draw_bombs(game_surface, current_time)
            draw_explosions(game_surface, current_time)
            draw_players(game_surface)
            start_text = font_small.render("Get Ready!", True, (255, 255, 255))
            start_rect = start_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT - 50))
            game_surface.blit(start_text, start_rect)
        else:
            for player in theGame.players:
                player.update(dt, theGame.board, theGame.bombs)
            triggered_explosions = []
            for bomb in theGame.bombs[:]:
                if bomb.update(current_time):
                    exp = Explosion(get_explosion_cells(bomb), current_time, bomb.quad_damage)
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
                        exp = Explosion(get_explosion_cells(bomb), current_time,bomb.quad_damage)
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
                        game_state = "champion"
                    else:
                        game_state = "win"
                else:
                    game_state = "win"
            draw_board(game_surface)
            draw_powerups(game_surface)
            draw_bombs(game_surface, current_time)
            draw_explosions(game_surface, current_time)
            draw_players(game_surface)

    elif game_state == "win":
        draw_title_page(game_surface, alpha=255)
        draw_stat_screen(game_surface, alive_players[0] if alive_players else None)

    elif game_state == "champion":
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

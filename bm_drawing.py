
import pygame
from bm_params import *

def draw_brick_pattern(rect, surface):
    brick_height = rect.height // 4
    brick_width = rect.width // 3
    mortar_color = (80, 80, 80)
    rows = 2
    for row in range(rows):
        offset = brick_width // 2 if row % 2 == 1 else 0
        y = rect.top + row * (rect.height // rows)
        x = rect.left + offset
        while x < rect.right:
            brick_rect = pygame.Rect(x, y, brick_width, rect.height // rows)
            pygame.draw.rect(surface, mortar_color, brick_rect, 1)
            x += brick_width
            
            
def draw_title_page(surface, alpha=255):
    # Get the original dimensions of the logo
    logo_width, logo_height = logo_image.get_size()
    
    # Calculate the scaling factor to fit the logo within the desired width and height
    max_width = BASE_WIDTH // 2
    max_height = BASE_HEIGHT // 4
    scale_factor = min(max_width / logo_width, max_height / logo_height)
    
    # Calculate the new dimensions while maintaining the aspect ratio
    new_width = int(logo_width * scale_factor)
    new_height = int(logo_height * scale_factor)
    
    # Scale the logo image to the new dimensions
    logo_scaled = pygame.transform.smoothscale(logo_image, (new_width, new_height))
    logo_scaled.set_alpha(alpha)
    
    # Get the rectangle for the scaled logo and center it
    rect = logo_scaled.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT // 4))
    
    # Blit the scaled logo onto the surface
    surface.blit(logo_scaled, rect)
    
    # Render the game name in big arcade font
    game_name_text = arcade_font.render("BomberMarv", True, (255, 255, 255))
    game_name_rect = game_name_text.get_rect(center=(BASE_WIDTH // 2, BASE_HEIGHT // 2))
    surface.blit(game_name_text, game_name_rect)
    
    # Render the version tag
    version_font = pygame.font.SysFont("arial", 24)
    version_text = version_font.render(VERSION, True, (255, 255, 255))
    version_rect = version_text.get_rect(bottomright=(BASE_WIDTH - 10, BASE_HEIGHT - 10))
    surface.blit(version_text, version_rect)
    


def draw_trophy_icon(surface, pos, size):
    trophy_color = (212, 175, 55)
    x, y = pos
    width = size
    height = size
    # Draw a dome (ellipse) for the top of the trophy
    dome_rect = pygame.Rect(x, y, width, int(height * 0.6))
    pygame.draw.ellipse(surface, trophy_color, dome_rect)
    # Draw the cup
    cup_rect = pygame.Rect(x + int(width * 0.2), y + int(height * 0.5), int(width * 0.6), int(height * 0.3))
    pygame.draw.rect(surface, trophy_color, cup_rect)
    # Draw a base
    base_rect = pygame.Rect(x + int(width * 0.3), y + int(height * 0.85), int(width * 0.4), int(height * 0.15))
    pygame.draw.rect(surface, trophy_color, base_rect)
    
def draw_board(surface,theGame):
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
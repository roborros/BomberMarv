"""
Pygame implementation of the rendering backend
"""
import pygame
import pygame.gfxdraw
from rendering_backend import RenderingBackend, DrawCommand, DrawRect, DrawCircle, DrawText, DrawImage, DrawLine, FillBackground
from typing import Dict, Optional
import os

class PygameRenderingBackend(RenderingBackend):
    """Pygame implementation of the rendering backend"""
    
    def __init__(self, width: int, height: int, window_title: str = "BomberMarv"):
        super().__init__(width, height)
        self.window_title = window_title
        self.screen: Optional[pygame.Surface] = None
        self.surface: Optional[pygame.Surface] = None
        self.fonts: Dict[tuple, pygame.font.Font] = {}
        self.images: Dict[str, pygame.Surface] = {}
        self.window_size = (width, height)
        self.is_fullscreen = False
    
    def init(self) -> bool:
        """Initialize pygame"""
        try:
            # Adopt existing display surface if already created by the game (bm_params/Game)
            if not pygame.get_init():
                pygame.init()
            existing = pygame.display.get_surface()
            if existing is not None:
                self.screen = existing
                self.window_size = existing.get_size()
            else:
                self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
                pygame.display.set_caption(self.window_title)
            self.surface = pygame.Surface((self.width, self.height))
            return True
        except Exception as e:
            print(f"Failed to initialize pygame: {e}")
            return False
    
    def clear(self):
        """Clear the surface"""
        if self.surface:
            self.surface.fill((0, 0, 0))
        self.clear_commands()
    
    def present(self):
        """Present the frame to screen"""
        if not self.screen or not self.surface:
            return
        
        # Scale surface to fit window
        factor = min(self.window_size[0] / self.width, self.window_size[1] / self.height)
        new_width = int(self.width * factor)
        new_height = int(self.height * factor)
        scaled_surface = pygame.transform.smoothscale(self.surface, (new_width, new_height))
        
        # Center the scaled surface
        self.screen.fill((0, 0, 0))
        x_offset = (self.window_size[0] - new_width) // 2
        y_offset = (self.window_size[1] - new_height) // 2
        self.screen.blit(scaled_surface, (x_offset, y_offset))
        
        pygame.display.flip()
    
    def shutdown(self):
        """Cleanup pygame"""
        pygame.quit()
    
    def handle_events(self):
        """Handle pygame events and return them"""
        return pygame.event.get()
    
    def get_font(self, font_name: str, font_size: int) -> pygame.font.Font:
        """Get or create a font"""
        key = (font_name, font_size)
        if key not in self.fonts:
            if font_name == "arial":
                self.fonts[key] = pygame.font.SysFont("arial", font_size)
            elif font_name == "comic_sans":
                self.fonts[key] = pygame.font.SysFont("Comic Sans MS", font_size, bold=True)
            else:
                self.fonts[key] = pygame.font.SysFont("arial", font_size)
        return self.fonts[key]
    
    def load_image(self, image_name: str) -> Optional[pygame.Surface]:
        """Load or get cached image"""
        if image_name not in self.images:
            image_path = os.path.join("img", f"{image_name}.png")
            if os.path.exists(image_path):
                try:
                    self.images[image_name] = pygame.image.load(image_path)
                except Exception as e:
                    print(f"Failed to load image {image_path}: {e}")
                    return None
            else:
                print(f"Image not found: {image_path}")
                return None
        return self.images[image_name]
    
    def set_window_size(self, width: int, height: int):
        """Update window size"""
        self.window_size = (width, height)
        if not self.is_fullscreen:
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.window_size = self.screen.get_size()
        else:
            self.window_size = (1200, 900)  # Default windowed size
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
    
    # Implementation of abstract drawing methods
    def _fill_background(self, cmd: FillBackground):
        if self.surface:
            self.surface.fill(cmd.color)
    
    def _draw_rect(self, cmd: DrawRect):
        if not self.surface:
            return
        
        rect = pygame.Rect(cmd.x, cmd.y, cmd.width, cmd.height)
        pygame.draw.rect(self.surface, cmd.color, rect)
        
        if cmd.border_width > 0 and cmd.border_color:
            pygame.draw.rect(self.surface, cmd.border_color, rect, cmd.border_width)
    
    def _draw_circle(self, cmd: DrawCircle):
        if not self.surface:
            return
        
        center = (int(cmd.x), int(cmd.y))
        radius = int(cmd.radius)
        
        # Use gfxdraw for better quality
        pygame.gfxdraw.filled_circle(self.surface, center[0], center[1], radius, cmd.color)
        pygame.gfxdraw.aacircle(self.surface, center[0], center[1], radius, cmd.color)
        
        if cmd.border_width > 0 and cmd.border_color:
            for i in range(cmd.border_width):
                pygame.gfxdraw.aacircle(self.surface, center[0], center[1], radius + i, cmd.border_color)
    
    def _draw_text(self, cmd: DrawText):
        if not self.surface:
            return
        
        font = self.get_font(cmd.font_name, cmd.font_size)
        text_surface = font.render(cmd.text, True, cmd.color)
        
        if cmd.center:
            rect = text_surface.get_rect(center=(cmd.x, cmd.y))
            self.surface.blit(text_surface, rect)
        else:
            self.surface.blit(text_surface, (cmd.x, cmd.y))
    
    def _draw_image(self, cmd: DrawImage):
        if not self.surface:
            return
        
        image = self.load_image(cmd.image_name)
        if not image:
            return
        
        if cmd.width and cmd.height:
            image = pygame.transform.smoothscale(image, (int(cmd.width), int(cmd.height)))
        
        if cmd.alpha < 1.0:
            image = image.copy()
            image.set_alpha(int(255 * cmd.alpha))
        
        self.surface.blit(image, (cmd.x, cmd.y))
    
    def _draw_line(self, cmd: DrawLine):
        if not self.surface:
            return
        
        start = (int(cmd.x1), int(cmd.y1))
        end = (int(cmd.x2), int(cmd.y2))
        pygame.draw.line(self.surface, cmd.color, start, end, cmd.width)
"""
Frontend module for handling all pygame/screen/window related functionality.
This is the only module that should import pygame directly.
"""

import math
import os
import pygame
import sys
from typing import Optional, Tuple
from event_abstraction import EventProcessor, GameCommandHandler
from input_abstraction import note_key_event
from bm_params import BASE_WIDTH, BASE_HEIGHT, INITIAL_WINDOW_SIZE


def present_rect(
    src_w: int, src_h: int, win_w: int, win_h: int, *, cover: bool,
) -> Tuple[int, int, int, int]:
    """Uniform scale of a fixed picture onto a window. Returns dest size and offset.

    Cover grows until every edge of the window is filled, cropping the overflow.
    Contain fits the whole picture and can leave a bar on the longer axis.
    The source size is the game surface and is not changed here.
    """
    src_w = max(1, int(src_w))
    src_h = max(1, int(src_h))
    win_w = max(1, int(win_w))
    win_h = max(1, int(win_h))
    scale = (max if cover else min)(win_w / src_w, win_h / src_h)
    dest_w = max(1, math.ceil(src_w * scale - 1e-9))
    dest_h = max(1, math.ceil(src_h * scale - 1e-9))
    if cover:
        dest_w = max(dest_w, win_w)
        dest_h = max(dest_h, win_h)
    else:
        dest_w = min(dest_w, win_w)
        dest_h = min(dest_h, win_h)
    offset_x = (win_w - dest_w) // 2
    offset_y = (win_h - dest_h) // 2
    return dest_w, dest_h, offset_x, offset_y


def choose_desktop_size(sizes, info_w: int, info_h: int) -> Tuple[int, int]:
    """Primary monitor size, then the display info."""
    if sizes:
        width, height = sizes[0]
        if int(width) > 0 and int(height) > 0:
            return int(width), int(height)
    return max(1, int(info_w or 1)), max(1, int(info_h or 1))


def monitor_size(sizes, display_index, info_w: int, info_h: int) -> Tuple[int, int]:
    """Resolution of the display the window is on, not a larger sibling monitor."""
    try:
        index = int(display_index)
    except (TypeError, ValueError):
        index = -1
    if sizes and 0 <= index < len(sizes):
        width, height = sizes[index]
        if int(width) > 0 and int(height) > 0:
            return int(width), int(height)
    return max(1, int(info_w or 1)), max(1, int(info_h or 1))


def current_monitor_size() -> Tuple[int, int]:
    try:
        sizes = pygame.display.get_desktop_sizes()
    except (pygame.error, AttributeError):
        sizes = ()
    info = pygame.display.Info()
    index = -1
    try:
        from pygame._sdl2 import video as sdl_video
        index = int(sdl_video.Window.from_display_module().display_index)
    except (pygame.error, AttributeError, TypeError, ValueError):
        index = -1
    return monitor_size(sizes, index, info.current_w, info.current_h)


def _enable_dpi_awareness() -> None:
    """Use real pixels so a fullscreen window can reach the edges of the monitor."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

class FrontendScreen:
    """Handles all screen-related functionality"""
    
    def __init__(self):
        self.surface = pygame.Surface((BASE_WIDTH, BASE_HEIGHT))
        self.window_size = INITIAL_WINDOW_SIZE
        self.window = None
    
    def set_window(self, window):
        """Set the pygame window reference"""
        self.window = window
    
    def update_window_size(self, window_size):
        """Update the window size"""
        self.window_size = window_size
    
    def get_surface(self):
        """Get the game surface for drawing"""
        return self.surface
    
    def get_window_size(self):
        """Get the current window size"""
        return self.window_size

class FrontendWindow:
    """Handles all window-related functionality"""
    
    def __init__(self):
        self.is_fullscreen = False
        self.window = None
    
    def create_window(self, size: Tuple[int, int], resizable: bool = True) -> pygame.Surface:
        """Create a pygame window"""
        flags = pygame.RESIZABLE if resizable else 0
        self.window = pygame.display.set_mode(size, flags)
        return self.window
    
    def toggle_fullscreen(self) -> Tuple[int, int]:
        """Toggle fullscreen mode and return new window size"""
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            width, height = current_monitor_size()
            self.window = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
        return self.window.get_size()
    
    def resize_window(self, size: Tuple[int, int]) -> pygame.Surface:
        """Resize the window"""
        self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
        return self.window
    
    def close_window(self):
        """Close the window and exit"""
        pygame.quit()
        sys.exit()
    
    def flip_display(self):
        """Update the display"""
        pygame.display.flip()

class FrontendRenderer:
    """Handles all rendering functionality"""
    
    def __init__(self, screen: FrontendScreen, window: FrontendWindow):
        self.screen = screen
        self.window = window
        # smoothscale is visibly nicer, but significantly slower at large internal resolutions.
        self.use_smoothscale = os.environ.get("BM_USE_SMOOTHSCALE", "1") == "1"
    
    def draw_adjust_screen_size(self):
        """Draw the game surface scaled to fit the window"""
        # Get current window size to ensure it's up to date
        current_window_size = self.window.window.get_size()
        self.screen.update_window_size(current_window_size)
        
        surf_w, surf_h = self.screen.surface.get_size()
        win_w, win_h = self.screen.window_size
        new_width, new_height, x_offset, y_offset = present_rect(
            surf_w, surf_h, win_w, win_h, cover=False,
        )

        if new_width <= 0 or new_height <= 0:
            return

        if new_width == surf_w and new_height == surf_h:
            scaled_surface = self.screen.surface
        elif new_width < surf_w or new_height < surf_h:
            # Quality-first downscaling now that host render is capped to 60 FPS.
            if self.use_smoothscale:
                scaled_surface = pygame.transform.smoothscale(self.screen.surface, (new_width, new_height))
            else:
                scaled_surface = pygame.transform.scale(self.screen.surface, (new_width, new_height))
        elif self.use_smoothscale:
            scaled_surface = pygame.transform.smoothscale(self.screen.surface, (new_width, new_height))
        else:
            scaled_surface = pygame.transform.scale(self.screen.surface, (new_width, new_height))
        self.window.window.fill((0, 0, 0))
        self.window.window.blit(scaled_surface, (x_offset, y_offset))
        self.window.flip_display()

class FrontendEventHandler:
    """Handles all frontend events and delegates to backend game logic"""
    
    def __init__(self, game_instance):
        self.game = game_instance
        self.command_handler = GameCommandHandler(game_instance)
    
    def process_events(self):
        """Process all pygame events and delegate to game logic"""
        for event in pygame.event.get():
            note_key_event(event)
            # Convert pygame event to game event
            game_event = EventProcessor.process_pygame_event(event)
            
            if game_event:
                # Handle the game event
                handled = self.command_handler.handle_command(game_event)
                
                if not handled:
                    # If not handled by command handler, try legacy handlers
                    self._handle_legacy_event(event)
    
    def _handle_legacy_event(self, event):
        """Handle events that don't fit the new command system"""
        # This is for backward compatibility with existing code
        # that might not be fully migrated to the command system
        
        if event.type == pygame.KEYDOWN and self.game.game_state == "game_prep":
            # Handle prep screen events that might not be covered by commands
            self.game.handle_prep_key_event(event)

class FrontendManager:
    """Main frontend manager that coordinates all frontend components"""
    
    def __init__(self, game_instance):
        self.game = game_instance
        self.should_quit = False
        
        # Real pixels, then pygame, so fullscreen can use the whole monitor.
        _enable_dpi_awareness()
        pygame.init()
        pygame.font.init()
        
        # Initialize fonts and set global variables immediately
        self._initialize_globals()
        
        # Now create the components
        self.screen = FrontendScreen()
        self.window = FrontendWindow()
        self.renderer = FrontendRenderer(self.screen, self.window)
        self.event_handler = FrontendEventHandler(game_instance)
    
    def _initialize_globals(self):
        """Initialize global variables that were previously in bm_params.py"""
        import bm_params
        bm_params.init_assets()
        
        # Initialize fonts (2x size)
        bm_params.arcade_font = pygame.font.SysFont('Comic Sans MS', 180)
        bm_params.font_small = pygame.font.SysFont("arial", 64)
        
        # Set default window size (will be updated after window creation)
        bm_params.INITIAL_WINDOW_SIZE = (1200, 800)
        
        # Set icon
        pygame.display.set_icon(bm_params.logo_image)
    
    def initialize(self) -> pygame.Surface:
        """Initialize the frontend and return the main window"""
        import bm_params
        
        # Calculate proper window size based on display info
        display_info = pygame.display.Info()
        calculated_size = (int(display_info.current_w * 0.7), int(display_info.current_h * 0.7))
        bm_params.INITIAL_WINDOW_SIZE = calculated_size
        
        window = self.window.create_window(bm_params.INITIAL_WINDOW_SIZE, resizable=True)
        self.screen.set_window(window)
        
        # Update window size to match actual window size
        actual_size = window.get_size()
        self.screen.update_window_size(actual_size)
        
        # Debug: Print window sizes
        # print(f"Expected window size: {bm_params.INITIAL_WINDOW_SIZE}")
        # print(f"Actual window size: {actual_size}")
        # print(f"Screen window size: {self.screen.get_window_size()}")
        
        # Set global variables
        bm_params.window = window
        bm_params.game_surface = self.screen.get_surface()
        
        # Set caption
        pygame.display.set_caption("BomberMarv")
        
        return window
    
    def process_events(self):
        """Process all events"""
        self.event_handler.process_events()
    
    def render(self):
        """Render the current frame"""
        self.renderer.draw_adjust_screen_size()
    
    def cleanup(self):
        """Cleanup frontend resources"""
        pygame.quit()

# Convenience functions for backward compatibility
def create_frontend(game_instance) -> FrontendManager:
    """Create a frontend manager for the given game instance"""
    return FrontendManager(game_instance)

def get_pygame():
    """Get pygame module (for cases where direct access is needed)"""
    return pygame



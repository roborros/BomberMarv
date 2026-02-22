"""
Frontend module for handling all pygame/screen/window related functionality.
This is the only module that should import pygame directly.
"""

import os
import pygame
import sys
from typing import Optional, Tuple
from event_abstraction import EventProcessor, GameCommandHandler
from bm_params import BASE_WIDTH, BASE_HEIGHT, INITIAL_WINDOW_SIZE

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
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
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
        
        factor = min(self.screen.window_size[0] / BASE_WIDTH, 
                    self.screen.window_size[1] / BASE_HEIGHT)
        new_width = int(BASE_WIDTH * factor)
        new_height = int(BASE_HEIGHT * factor)

        if new_width <= 0 or new_height <= 0:
            return

        if new_width == BASE_WIDTH and new_height == BASE_HEIGHT:
            scaled_surface = self.screen.surface
        elif self.use_smoothscale:
            scaled_surface = pygame.transform.smoothscale(self.screen.surface, (new_width, new_height))
        else:
            scaled_surface = pygame.transform.scale(self.screen.surface, (new_width, new_height))
        self.window.window.fill((0, 0, 0))
        x_offset = (self.screen.window_size[0] - new_width) // 2
        y_offset = (self.screen.window_size[1] - new_height) // 2
        
        # Debug: Print scaling info (only once)
        # if not hasattr(self, '_debug_printed'):
        #     print(f"BASE_WIDTH: {BASE_WIDTH}, BASE_HEIGHT: {BASE_HEIGHT}")
        #     print(f"Window size: {self.screen.window_size}")
        #     print(f"Scaling factor: {factor}")
        #     print(f"Scaled size: {new_width}x{new_height}")
        #     print(f"Offsets: x={x_offset}, y={y_offset}")
        #     self._debug_printed = True
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
        
        # Initialize pygame first
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
        
        # Initialize fonts
        bm_params.arcade_font = pygame.font.SysFont('Comic Sans MS', 90)
        bm_params.font_small = pygame.font.SysFont("arial", 32)
        
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



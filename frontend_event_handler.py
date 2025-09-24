"""
Frontend event handler for separating pygame events from game logic.
This handles all pygame-specific event processing and delegates to the backend.
"""

import pygame
from event_abstraction import EventProcessor, GameCommandHandler

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

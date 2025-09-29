"""
Event abstraction layer for separating frontend events from backend game logic.
This provides a clean interface between pygame events and game commands.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Any

class EventType(Enum):
    """Types of events that can be processed by the game"""
    WINDOW_CLOSE = "window_close"
    WINDOW_RESIZE = "window_resize"
    KEY_PRESS = "key_press"
    KEY_RELEASE = "key_release"
    MOUSE_CLICK = "mouse_click"
    MOUSE_MOVE = "mouse_move"

class GameCommand(Enum):
    """Commands that can be sent to the game backend"""
    # Window commands
    TOGGLE_FULLSCREEN = "toggle_fullscreen"
    RESIZE_WINDOW = "resize_window"
    CLOSE_WINDOW = "close_window"
    
    # Game state commands
    START_GAME = "start_game"
    QUICK_START_GAME = "quick_start_game"
    ENTER_PREP_SCREEN = "enter_prep_screen"
    EXIT_PREP_SCREEN = "exit_prep_screen"
    RESTART_GAME = "restart_game"
    
    # Prep screen commands
    NAVIGATE_UP = "navigate_up"
    NAVIGATE_DOWN = "navigate_down"
    NAVIGATE_LEFT = "navigate_left"
    NAVIGATE_RIGHT = "navigate_right"
    SWITCH_SECTION = "switch_section"
    ENTER_EDIT_MODE = "enter_edit_mode"
    EXIT_EDIT_MODE = "exit_edit_mode"
    EDIT_VALUE = "edit_value"
    EDIT_PLAYER_NAME = "edit_player_name"
    EDIT_CONTROL_KEY = "edit_control_key"
    CANCEL_EDIT = "cancel_edit"
    
    # Text input commands
    ADD_CHARACTER = "add_character"
    REMOVE_CHARACTER = "remove_character"
    CLEAR_TEXT = "clear_text"

@dataclass
class GameEvent:
    """Represents a processed game event with command and data"""
    event_type: EventType
    command: GameCommand
    data: Optional[dict] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}

class EventProcessor:
    """Converts pygame events to game events"""
    
    @staticmethod
    def process_pygame_event(event) -> Optional[GameEvent]:
        """Convert a pygame event to a game event"""
        # Import pygame here to avoid circular imports
        import pygame
        
        if event.type == pygame.QUIT:
            return GameEvent(
                event_type=EventType.WINDOW_CLOSE,
                command=GameCommand.CLOSE_WINDOW
            )
        
        elif event.type == pygame.VIDEORESIZE:
            return GameEvent(
                event_type=EventType.WINDOW_RESIZE,
                command=GameCommand.RESIZE_WINDOW,
                data={"size": event.size}
            )
        
        elif event.type == pygame.KEYDOWN:
            return EventProcessor._process_keydown(event)
        
        elif event.type == pygame.KEYUP:
            return EventProcessor._process_keyup(event)
        
        return None
    
    @staticmethod
    def _process_keydown(event) -> Optional[GameEvent]:
        """Process keydown events"""
        from input_abstraction import Keys
        
        # Window controls
        if event.key == Keys.F11:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.TOGGLE_FULLSCREEN
            )
        
        # Game state controls
        elif event.key in (Keys.ENTER, Keys.KP_ENTER):
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.START_GAME
            )
        
        elif event.key == Keys.SPACE:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.QUICK_START_GAME
            )
        
        # Navigation controls
        elif event.key == Keys.UP:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.NAVIGATE_UP
            )
        elif event.key == Keys.DOWN:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.NAVIGATE_DOWN
            )
        elif event.key == Keys.LEFT:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.NAVIGATE_LEFT
            )
        elif event.key == Keys.RIGHT:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.NAVIGATE_RIGHT
            )
        elif event.key == Keys.TAB:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.SWITCH_SECTION
            )
        elif event.key == Keys.ESCAPE:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.CANCEL_EDIT
            )
        elif event.key == Keys.BACKSPACE:
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.REMOVE_CHARACTER
            )
        
        # Text input
        elif event.unicode and event.unicode.isprintable():
            return GameEvent(
                event_type=EventType.KEY_PRESS,
                command=GameCommand.ADD_CHARACTER,
                data={"character": event.unicode}
            )
        
        return None
    
    @staticmethod
    def _process_keyup(event) -> Optional[GameEvent]:
        """Process keyup events"""
        # Currently no keyup events are processed
        return None

class GameCommandHandler:
    """Handles game commands and delegates to appropriate game logic"""
    
    def __init__(self, game_instance):
        self.game = game_instance
    
    def handle_command(self, game_event: GameEvent) -> bool:
        """Handle a game command. Returns True if handled, False otherwise."""
        command = game_event.command
        data = game_event.data or {}
        
        # Window commands
        if command == GameCommand.TOGGLE_FULLSCREEN:
            self._handle_toggle_fullscreen()
            return True
        
        elif command == GameCommand.RESIZE_WINDOW:
            self._handle_resize_window(data.get("size"))
            return True
        
        elif command == GameCommand.CLOSE_WINDOW:
            self._handle_close_window()
            return True
        
        # Game state commands
        elif command == GameCommand.START_GAME:
            return self._handle_start_game()
        
        elif command == GameCommand.QUICK_START_GAME:
            return self._handle_quick_start_game()
        
        # Prep screen commands
        elif command in [GameCommand.NAVIGATE_UP, GameCommand.NAVIGATE_DOWN, 
                        GameCommand.NAVIGATE_LEFT, GameCommand.NAVIGATE_RIGHT,
                        GameCommand.SWITCH_SECTION, GameCommand.CANCEL_EDIT]:
            return self._handle_prep_navigation(command, data)
        
        # Text input commands
        elif command in [GameCommand.ADD_CHARACTER, GameCommand.REMOVE_CHARACTER, 
                        GameCommand.CLEAR_TEXT]:
            return self._handle_text_input(command, data)
        
        return False
    
    def _handle_toggle_fullscreen(self):
        """Handle fullscreen toggle"""
        self.game.is_fullscreen = not self.game.is_fullscreen
        if self.game.is_fullscreen:
            window = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
            if self.game.screen:
                self.game.screen.update_window_size(window.get_size())
        else:
            from bm_params import INITIAL_WINDOW_SIZE
            window = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
            if self.game.screen:
                self.game.screen.update_window_size(INITIAL_WINDOW_SIZE)
    
    def _handle_resize_window(self, size):
        """Handle window resize"""
        if self.game.screen:
            self.game.screen.update_window_size(size)
    
    def _handle_close_window(self):
        """Handle window close"""
        # Signal the frontend to quit instead of calling pygame.quit() directly
        if hasattr(self.game, 'frontend') and self.game.frontend:
            self.game.frontend.should_quit = True
        import sys
        sys.exit()
    
    def _handle_start_game(self):
        """Handle start game command"""
        if self.game.game_state == "startup":
            if not self.game.prep_screen_completed:
                self.game.game_state = "game_prep"
            else:
                self.game.init_game()
                self.game.game_state = "get_ready"
            return True
        
        elif self.game.game_state == "game_prep":
            return self.game.handle_prep_enter_key()
        
        elif self.game.game_state in ["win", "champion"]:
            self.game.init_game()
            self.game.game_state = "get_ready"
            return True
        
        return False
    
    def _handle_quick_start_game(self):
        """Handle quick start game command"""
        if self.game.game_state == "game_prep":
            # Use the backend logic for quick start
            from backend_game_logic import BackendGameLogic
            backend = BackendGameLogic(self.game)
            return backend._quick_start_game()
        
        return False
    
    def _handle_prep_navigation(self, command, data):
        """Handle prep screen navigation commands"""
        if self.game.game_state != "game_prep":
            return False
        
        # Create a mock event for the existing prep key handler
        mock_event = type('MockEvent', (), {
            'key': self._command_to_key(command),
            'unicode': data.get('character', '')
        })()
        
        self.game.handle_prep_key_event(mock_event)
        return True
    
    def _handle_text_input(self, command, data):
        """Handle text input commands"""
        if self.game.game_state != "game_prep":
            return False
        
        # Create a mock event for the existing prep key handler
        mock_event = type('MockEvent', (), {
            'key': self._command_to_key(command),
            'unicode': data.get('character', '')
        })()
        
        self.game.handle_prep_key_event(mock_event)
        return True
    
    def _command_to_key(self, command):
        """Convert command to pygame key constant"""
        from input_abstraction import Keys
        
        command_to_key = {
            GameCommand.NAVIGATE_UP: Keys.UP,
            GameCommand.NAVIGATE_DOWN: Keys.DOWN,
            GameCommand.NAVIGATE_LEFT: Keys.LEFT,
            GameCommand.NAVIGATE_RIGHT: Keys.RIGHT,
            GameCommand.SWITCH_SECTION: Keys.TAB,
            GameCommand.CANCEL_EDIT: Keys.ESCAPE,
            GameCommand.REMOVE_CHARACTER: Keys.BACKSPACE,
        }
        
        return command_to_key.get(command, None)

"""
Backend game logic handler for managing game state and logic.
This contains all game state management separated from frontend concerns.
"""

from typing import Optional, Dict, Any
from event_abstraction import GameCommand, GameEvent
from input_abstraction import Keys

class BackendGameLogic:
    """Handles all backend game logic and state management"""
    
    def __init__(self, game_instance):
        self.game = game_instance
    
    def handle_game_state_transition(self, command: GameCommand, data: Optional[Dict[str, Any]] = None) -> bool:
        """Handle game state transitions based on commands"""
        if data is None:
            data = {}
        
        current_state = self.game.game_state
        
        # State transition matrix
        transitions = {
            "startup": {
                GameCommand.START_GAME: self._transition_startup_to_prep,
                GameCommand.ENTER_PREP_SCREEN: self._transition_to_prep,
            },
            "game_prep": {
                GameCommand.START_GAME: self._transition_prep_to_ready,
                GameCommand.QUICK_START_GAME: self._transition_prep_to_ready,
                GameCommand.EXIT_PREP_SCREEN: self._transition_prep_to_startup,
            },
            "get_ready": {
                GameCommand.START_GAME: self._transition_ready_to_playing,
            },
            "playing": {
                GameCommand.RESTART_GAME: self._transition_playing_to_ready,
            },
            "win": {
                GameCommand.RESTART_GAME: self._transition_win_to_ready,
            },
            "champion": {
                GameCommand.RESTART_GAME: self._transition_champion_to_ready,
            }
        }
        
        state_transitions = transitions.get(current_state, {})
        transition_func = state_transitions.get(command)
        
        if transition_func:
            return transition_func(data)
        
        return False
    
    def _transition_startup_to_prep(self, data: Dict[str, Any]) -> bool:
        """Transition from startup to prep screen"""
        if not self.game.prep_screen_completed:
            self.game.game_state = "game_prep"
            return True
        return False
    
    def _transition_to_prep(self, data: Dict[str, Any]) -> bool:
        """Transition to prep screen"""
        self.game.game_state = "game_prep"
        return True
    
    def _transition_prep_to_ready(self, data: Dict[str, Any]) -> bool:
        """Transition from prep screen to ready state"""
        # Check if this is a quick start command
        if data and data.get('command') == GameCommand.QUICK_START_GAME:
            return self._quick_start_game()
        else:
            # Create a mock key event for ENTER
            from input_abstraction import Keys
            class MockEvent:
                def __init__(self, key):
                    self.key = key
            mock_event = MockEvent(Keys.ENTER)
            self.game.handle_prep_key_event(mock_event)
            return True
    
    def _quick_start_game(self) -> bool:
        """Quick start game with default settings"""
        # Use current player count but ensure we have at least 1 player
        if self.game.prep_num_players < 1:
            self.game.prep_num_players = 1
        
        # Ensure we have enough names and colors
        while len(self.game.prep_player_names) < self.game.prep_num_players:
            self.game.prep_player_names.append(f"Player {len(self.game.prep_player_names) + 1}")
        
        while len(self.game.prep_player_colors) < self.game.prep_num_players:
            self.game.prep_player_colors.append(len(self.game.prep_player_colors))
        
        # Ensure we have enough controls
        default_controls = [
            {'up': Keys.W, 'down': Keys.S, 'left': Keys.A, 'right': Keys.D, 'bomb': Keys.SPACE},
            {'up': Keys.UP, 'down': Keys.DOWN, 'left': Keys.LEFT, 'right': Keys.RIGHT, 'bomb': Keys.RETURN},
            {'up': Keys.I, 'down': Keys.K, 'left': Keys.J, 'right': Keys.L, 'bomb': Keys.U},
            {'up': Keys.T, 'down': Keys.G, 'left': Keys.F, 'right': Keys.H, 'bomb': Keys.R}
        ]
        
        while len(self.game.prep_controls) < self.game.prep_num_players:
            self.game.prep_controls.append(default_controls[len(self.game.prep_controls) % len(default_controls)])
        
        # Create players and start game
        self.game.create_players()
        self.game.prep_screen_completed = True
        self.game.init_game()
        self.game.game_state = "get_ready"
        return True
    
    def _transition_prep_to_startup(self, data: Dict[str, Any]) -> bool:
        """Transition from prep screen back to startup"""
        self.game.game_state = "startup"
        self.game.startup_start_time = self.game.get_ticks()
        return True
    
    def _transition_ready_to_playing(self, data: Dict[str, Any]) -> bool:
        """Transition from ready to playing state"""
        if self.game.current_time >= self.game.game_start_time:
            self.game.game_state = "playing"
            return True
        return False
    
    def _transition_playing_to_ready(self, data: Dict[str, Any]) -> bool:
        """Transition from playing to ready state"""
        self.game.init_game()
        self.game.game_state = "get_ready"
        return True
    
    def _transition_win_to_ready(self, data: Dict[str, Any]) -> bool:
        """Transition from win to ready state"""
        self.game.init_game()
        self.game.game_state = "get_ready"
        return True
    
    def _transition_champion_to_ready(self, data: Dict[str, Any]) -> bool:
        """Transition from champion to ready state"""
        # Reset trophy counters now that champion has been announced
        if hasattr(self.game, 'reset_trophies'):
            self.game.reset_trophies()
        self.game.init_game()
        self.game.game_state = "get_ready"
        return True
    
    def handle_window_management(self, command: GameCommand, data: Dict[str, Any]) -> bool:
        """Handle window management commands"""
        if command == GameCommand.TOGGLE_FULLSCREEN:
            self._toggle_fullscreen()
            return True
        
        elif command == GameCommand.RESIZE_WINDOW:
            self._resize_window(data.get("size"))
            return True
        
        elif command == GameCommand.CLOSE_WINDOW:
            self._close_window()
            return True
        
        return False
    
    def _toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        # Delegate to frontend
        if hasattr(self.game, 'frontend') and self.game.frontend:
            new_size = self.game.frontend.window.toggle_fullscreen()
            self.game.frontend.screen.update_window_size(new_size)
        else:
            # Fallback for backward compatibility
            self.game.is_fullscreen = not self.game.is_fullscreen
    
    def _resize_window(self, size):
        """Resize window"""
        if self.game.screen:
            self.game.screen.update_window_size(size)
    
    def _close_window(self):
        """Close window and exit"""
        # Delegate to frontend
        if hasattr(self.game, 'frontend') and self.game.frontend:
            self.game.frontend.window.close_window()
        else:
            # Fallback for backward compatibility
            import sys
            sys.exit()
    
    def handle_prep_screen_logic(self, command: GameCommand, data: Dict[str, Any]) -> bool:
        """Handle prep screen specific logic"""
        if self.game.game_state != "game_prep":
            return False
        
        # Delegate to existing prep screen logic
        if command in [GameCommand.NAVIGATE_UP, GameCommand.NAVIGATE_DOWN, 
                      GameCommand.NAVIGATE_LEFT, GameCommand.NAVIGATE_RIGHT,
                      GameCommand.SWITCH_SECTION, GameCommand.CANCEL_EDIT,
                      GameCommand.ADD_CHARACTER, GameCommand.REMOVE_CHARACTER]:
            
            # Create a mock event for the existing prep key handler
            mock_event = self._create_mock_event(command, data)
            self.game.handle_prep_key_event(mock_event)
            return True
        
        return False
    
    def _create_mock_event(self, command: GameCommand, data: Dict[str, Any]):
        """Create a mock pygame event for legacy handlers"""
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
        
        key = command_to_key.get(command)
        
        return type('MockEvent', (), {
            'key': key,
            'unicode': data.get('character', '')
        })()

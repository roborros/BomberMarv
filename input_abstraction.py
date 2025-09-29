"""
Input abstraction layer for keyboard detection.
This provides a clean interface that can be easily swapped between different input backends.
Currently uses pygame as the backend, but can be easily replaced with other libraries.
"""

import pygame
from typing import Dict, Set, Optional, Any
from abc import ABC, abstractmethod

# Key constants abstraction
class Keys:
    """Key constants that can be used across different input backends"""
    # Navigation keys
    UP = pygame.K_UP
    DOWN = pygame.K_DOWN
    LEFT = pygame.K_LEFT
    RIGHT = pygame.K_RIGHT
    
    # Action keys
    ENTER = pygame.K_RETURN
    RETURN = pygame.K_RETURN  # Alias for ENTER
    KP_ENTER = pygame.K_KP_ENTER
    SPACE = pygame.K_SPACE
    ESCAPE = pygame.K_ESCAPE
    TAB = pygame.K_TAB
    BACKSPACE = pygame.K_BACKSPACE
    
    # Function keys
    F11 = pygame.K_F11
    
    # Letter keys
    A = pygame.K_a
    B = pygame.K_b
    C = pygame.K_c
    D = pygame.K_d
    E = pygame.K_e
    F = pygame.K_f
    G = pygame.K_g
    H = pygame.K_h
    I = pygame.K_i
    J = pygame.K_j
    K = pygame.K_k
    L = pygame.K_l
    M = pygame.K_m
    N = pygame.K_n
    O = pygame.K_o
    P = pygame.K_p
    Q = pygame.K_q
    R = pygame.K_r
    S = pygame.K_s
    T = pygame.K_t
    U = pygame.K_u
    V = pygame.K_v
    W = pygame.K_w
    X = pygame.K_x
    Y = pygame.K_y
    Z = pygame.K_z

class InputBackend(ABC):
    """Abstract base class for input backends"""
    
    @abstractmethod
    def get_pressed_keys(self) -> Dict[int, bool]:
        """Get dictionary of pressed keys where key is key_code and value is pressed state"""
        pass
    
    @abstractmethod
    def is_key_pressed(self, key_code: int) -> bool:
        """Check if a specific key is pressed"""
        pass
    
    @abstractmethod
    def get_key_name(self, key_code: int) -> str:
        """Get the name of a key for display purposes"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """Clean up any resources used by the input backend"""
        pass

class PygameInputBackend(InputBackend):
    """Pygame-based input backend"""
    
    def get_pressed_keys(self) -> Dict[int, bool]:
        """Get pressed keys using pygame"""
        pressed = pygame.key.get_pressed()
        return {i: bool(pressed[i]) for i in range(len(pressed)) if pressed[i]}
    
    def is_key_pressed(self, key_code: int) -> bool:
        """Check if a key is pressed using pygame"""
        keys = pygame.key.get_pressed()
        return bool(keys[key_code])
    
    def get_key_name(self, key_code: int) -> str:
        """Get key name using pygame"""
        return pygame.key.name(key_code)
    
    def cleanup(self):
        """Pygame cleanup is handled by pygame.quit()"""
        pass

class KeyboardInputBackend(InputBackend):
    """Keyboard library-based input backend (example implementation)"""
    
    def __init__(self):
        # This would be implemented if using the 'keyboard' library
        # import keyboard
        # self.keyboard = keyboard
        pass
    
    def get_pressed_keys(self) -> Dict[int, bool]:
        """Get pressed keys using keyboard library"""
        # Example implementation - would need actual keyboard library integration
        return {}
    
    def is_key_pressed(self, key_code: int) -> bool:
        """Check if a key is pressed using keyboard library"""
        # Example implementation
        return False
    
    def get_key_name(self, key_code: int) -> str:
        """Get key name using keyboard library"""
        # Example implementation
        return f"key_{key_code}"
    
    def cleanup(self):
        """Clean up keyboard library resources"""
        pass

class InputManager:
    """Main input manager that uses the configured backend"""
    
    def __init__(self, backend: InputBackend = None):
        self.backend = backend or PygameInputBackend()
    
    def set_backend(self, backend: InputBackend):
        """Switch to a different input backend"""
        if self.backend:
            self.backend.cleanup()
        self.backend = backend
    
    def get_pressed_keys(self) -> Dict[int, bool]:
        """Get all currently pressed keys"""
        return self.backend.get_pressed_keys()
    
    def is_key_pressed(self, key_code: int) -> bool:
        """Check if a specific key is pressed"""
        return self.backend.is_key_pressed(key_code)
    
    def get_key_name(self, key_code: int) -> str:
        """Get the name of a key for display"""
        return self.backend.get_key_name(key_code)
    
    def cleanup(self):
        """Clean up input resources"""
        if self.backend:
            self.backend.cleanup()

# Global input manager instance
input_manager = InputManager()

# Convenience functions that use the global input manager
def get_pressed_keys() -> Dict[int, bool]:
    """Get all currently pressed keys"""
    return input_manager.get_pressed_keys()

def is_key_pressed(key_code: int) -> bool:
    """Check if a specific key is pressed"""
    return input_manager.is_key_pressed(key_code)

def get_key_name(key_code: int) -> str:
    """Get the name of a key for display"""
    return input_manager.get_key_name(key_code)

def set_input_backend(backend: InputBackend):
    """Switch to a different input backend"""
    input_manager.set_backend(backend)

def cleanup_input():
    """Clean up input resources"""
    input_manager.cleanup()

# Example of how to switch backends:
# 
# # Switch to keyboard library backend
# from input_abstraction import KeyboardInputBackend, set_input_backend
# set_input_backend(KeyboardInputBackend())
#
# # Switch back to pygame backend
# from input_abstraction import PygameInputBackend, set_input_backend
# set_input_backend(PygameInputBackend())

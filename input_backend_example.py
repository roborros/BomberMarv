"""
Example of how to swap input backends using the abstraction layer.
This demonstrates how easy it is to switch between different input sources.
"""

from input_abstraction import set_input_backend, PygameInputBackend, KeyboardInputBackend, cleanup_input

def demo_input_switching():
    """Demonstrate how to switch between different input backends"""
    
    print("=== Input Backend Switching Demo ===")
    
    # Currently using pygame backend (default)
    print("1. Using pygame backend (default)")
    from input_abstraction import is_key_pressed, get_key_name
    print(f"   Space key pressed: {is_key_pressed(32)}")  # 32 is space key in pygame
    print(f"   Space key name: {get_key_name(32)}")
    
    # Switch to keyboard library backend (example)
    print("\n2. Switching to keyboard library backend...")
    set_input_backend(KeyboardInputBackend())
    print(f"   Space key pressed: {is_key_pressed(32)}")
    print(f"   Space key name: {get_key_name(32)}")
    
    # Switch back to pygame backend
    print("\n3. Switching back to pygame backend...")
    set_input_backend(PygameInputBackend())
    print(f"   Space key pressed: {is_key_pressed(32)}")
    print(f"   Space key name: {get_key_name(32)}")
    
    # Clean up
    cleanup_input()
    print("\n4. Input resources cleaned up")

def create_custom_backend():
    """Example of creating a custom input backend"""
    
    from input_abstraction import InputBackend
    
    class CustomInputBackend(InputBackend):
        """Custom input backend that could use any input library"""
        
        def __init__(self):
            # Initialize your custom input library here
            # e.g., pynput, keyboard, msvcrt, etc.
            pass
        
        def get_pressed_keys(self):
            """Implement key detection using your preferred library"""
            # Return dict of {key_code: pressed_state}
            return {}
        
        def is_key_pressed(self, key_code):
            """Check if specific key is pressed"""
            return False
        
        def get_key_name(self, key_code):
            """Get key name for display"""
            return f"custom_key_{key_code}"
        
        def cleanup(self):
            """Clean up resources"""
            pass
    
    # Use the custom backend
    set_input_backend(CustomInputBackend())
    print("Custom input backend set!")

if __name__ == "__main__":
    # Run the demo
    demo_input_switching()
    
    # Show how to create custom backend
    print("\n=== Custom Backend Example ===")
    create_custom_backend()

#!/usr/bin/env python3
"""
Test script for the dual rendering system
Verifies that all components can be imported and initialized
"""
import sys
import traceback

def test_imports():
    """Test that all new modules can be imported"""
    print("Testing imports...")
    
    try:
        from rendering_backend import RenderingBackend, WebRenderingBackend, DrawCommand
        print("✅ rendering_backend imported")
    except Exception as e:
        print(f"❌ rendering_backend failed: {e}")
        return False
    
    try:
        from pygame_backend import PygameRenderingBackend
        print("✅ pygame_backend imported")
    except Exception as e:
        print(f"❌ pygame_backend failed: {e}")
        return False
    
    try:
        import bm_drawing_new
        print("✅ bm_drawing_new imported")
    except Exception as e:
        print(f"❌ bm_drawing_new failed: {e}")
        return False
    
    try:
        from game_state_serializer import serialize_game_state, serialize_draw_commands
        print("✅ game_state_serializer imported")
    except Exception as e:
        print(f"❌ game_state_serializer failed: {e}")
        return False
    
    try:
        from websocket_game_server import WebSocketGameServer
        print("✅ websocket_game_server imported")
    except Exception as e:
        print(f"❌ websocket_game_server failed: {e}")
        return False
    
    return True

def test_rendering_backend():
    """Test rendering backend initialization"""
    print("\nTesting rendering backends...")
    
    try:
        from rendering_backend import WebRenderingBackend
        backend = WebRenderingBackend(800, 600)
        backend.init()
        
        # Test drawing commands
        backend.draw_rect(10, 10, 100, 100, (255, 0, 0))
        backend.draw_circle(200, 200, 50, (0, 255, 0))
        backend.draw_text("Test", 300, 300, "arial", 24, (255, 255, 255))
        
        commands = backend.get_commands()
        print(f"✅ Web backend created {len(commands)} draw commands")
        return True
        
    except Exception as e:
        print(f"❌ Web backend test failed: {e}")
        traceback.print_exc()
        return False

def test_game_serialization():
    """Test game state serialization"""
    print("\nTesting game state serialization...")
    
    try:
        from bm_classes import Game
        from game_state_serializer import serialize_game_state, to_json
        
        game = Game()
        game.init_game()
        
        # Serialize game state
        state = serialize_game_state(game)
        json_str = to_json(state)
        
        print(f"✅ Game state serialized ({len(json_str)} bytes)")
        return True
        
    except Exception as e:
        print(f"❌ Game serialization test failed: {e}")
        traceback.print_exc()
        return False

def test_dual_manager():
    """Test the dual game manager"""
    print("\nTesting dual game manager...")
    
    try:
        # Import without running
        from pyBomberMarv_dual import GameManager
        print("✅ GameManager imported successfully")
        
        # Test initialization (but don't run the game loop)
        # manager = GameManager(enable_pygame=False, enable_web=False)
        # print("✅ GameManager initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ Dual manager test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("BomberMarv Dual Rendering System Test")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Rendering Backend Test", test_rendering_backend),
        ("Game Serialization Test", test_game_serialization),
        ("Dual Manager Test", test_dual_manager),
    ]
    
    passed = 0
    total = len(tests)
    
    for name, test_func in tests:
        print(f"\n{name}")
        print("-" * len(name))
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {name} PASSED")
            else:
                print(f"❌ {name} FAILED")
        except Exception as e:
            print(f"❌ {name} CRASHED: {e}")
            traceback.print_exc()
    
    print(f"\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The dual rendering system is ready.")
        print("\nNext steps:")
        print("1. Set up web client: python setup_web_client.py")
        print("2. Run dual system: python pyBomberMarv_dual.py")
        print("3. Open browser: http://localhost:8080")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
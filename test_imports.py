#!/usr/bin/env python3

print("Testing imports...")

try:
    print("1. Testing basic imports...")
    from PIL import Image
    print("   PIL import OK")
    
    import socket
    print("   socket import OK")
    
    import multiprocessing
    print("   multiprocessing import OK")
    
    import psutil
    print("   psutil import OK")
    
    from turbojpeg import TurboJPEG, TJPF_RGB
    print("   turbojpeg import OK")
    
    import numpy as np
    print("   numpy import OK")
    
    print("2. Testing game imports...")
    from frontend import FrontendManager
    print("   frontend import OK")
    
    from bm_drawing import draw_game_screen, draw_get_ready, draw_title_page, draw_stat_screen, draw_champion_screen
    print("   bm_drawing import OK")
    
    print("3. Testing ws_stream_server import...")
    import ws_stream_server
    print("   ws_stream_server import OK")
    
    print("All imports successful!")
    
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()

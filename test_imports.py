#!/usr/bin/env python3
"""Smoke-import the host, renderer, and websocket server."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

print("Testing imports...")

try:
    import numpy  # noqa: F401
    print("   numpy import OK")
    import psutil  # noqa: F401
    print("   psutil import OK")
    import websockets  # noqa: F401
    print("   websockets import OK")
    import aiohttp  # noqa: F401
    print("   aiohttp import OK")
    from PIL import Image  # noqa: F401
    print("   PIL import OK")

    from frontend import FrontendManager  # noqa: F401
    print("   frontend import OK")

    from bm_drawing import (  # noqa: F401
        draw_champion_screen,
        draw_game_screen,
        draw_get_ready,
        draw_stat_screen,
        draw_title_page,
    )
    print("   bm_drawing import OK")

    import ws_stream_server  # noqa: F401
    print("   ws_stream_server import OK")

    print("All imports successful!")
except Exception as exc:
    print(f"Import failed: {exc}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

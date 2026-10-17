"""Five remote clients plus a host sim, looking for a comms crash.

Run from the repo root:
  python tools/stress_five_clients.py
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import socket
import sys
import tempfile
import threading
import time
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("BM_RTC_ENABLED", "0")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    ws_port = _free_port()
    http_port = _free_port()
    os.environ["BM_WS_PORT"] = str(ws_port)
    os.environ["BM_HTTP_PORT"] = str(http_port)

    import psutil
    import websockets
    from queue_utils import put_latest_nonblocking
    from tests.helpers import silence_sounds
    from ws_stream_server import run_server_with_queue
    import ws_stream_server as wss

    wss.PORT = ws_port
    wss.HTTP_PORT = http_port

    input_q: queue.Queue = queue.Queue(maxsize=2048)
    state_q: queue.Queue = queue.Queue(maxsize=16)
    status_q: queue.Queue = queue.Queue(maxsize=128)
    log_path = os.path.join(tempfile.gettempdir(), "bm_stress_ws.log")
    server = threading.Thread(
        target=run_server_with_queue,
        args=(input_q, state_q, status_q, log_path),
        daemon=True,
        name="stress-ws",
    )
    server.start()
    import urllib.request

    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/health", timeout=0.4) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.05)
    else:
        print("server did not listen")
        return 1

    stats = {
        "received": [0, 0, 0, 0, 0],
        "max_bytes": [0, 0, 0, 0, 0],
        "errors": [],
        "seats": [],
    }

    async def client(index: int):
        uri = f"ws://127.0.0.1:{http_port}/ws"
        try:
            await asyncio.sleep(0.6)
            async with websockets.connect(uri, max_size=8 * 1024 * 1024) as ws:
                await ws.send(json.dumps({"type": "hello", "protocol": 2, "encoding": "json"}))
                await ws.send(json.dumps({"type": "login", "protocol": 2, "name": f"P{index}"}))
                seat = None
                while seat is None:
                    raw = await asyncio.wait_for(ws.recv(), 4)
                    stats["received"][index] += 1
                    stats["max_bytes"][index] = max(stats["max_bytes"][index], len(raw) if isinstance(raw, str) else len(raw))
                    msg = json.loads(raw)
                    if msg.get("type") == "registration_confirmed":
                        seat = int(msg["slot"])
                        stats["seats"].append(seat)
                dirs = [(1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)]
                end = time.time() + 12
                tick = 0
                while time.time() < end:
                    dx, dy_up, dy_down, left = dirs[tick % 4]
                    # cycle up/down/left/right plus bomb half the time
                    keys = {
                        "up": 1 if tick % 4 == 0 else 0,
                        "down": 1 if tick % 4 == 1 else 0,
                        "left": 1 if tick % 4 == 2 else 0,
                        "right": 1 if tick % 4 == 3 else 0,
                        "bomb": 1 if tick % 2 == 0 else 0,
                    }
                    payload = {
                        "type": "game_input",
                        "protocol": 2,
                        "tick_id": tick,
                        "input": [index + 1, seat, keys["up"], keys["down"], keys["left"], keys["right"], keys["bomb"]],
                        "input_frame": {"player_id": seat, **keys},
                        "client_timestamp": int(time.time() * 1000),
                    }
                    await ws.send(json.dumps(payload))
                    tick += 1
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 0.02)
                        stats["received"][index] += 1
                        size = len(raw) if isinstance(raw, str) else len(raw)
                        stats["max_bytes"][index] = max(stats["max_bytes"][index], size)
                    except asyncio.TimeoutError:
                        pass
                    await asyncio.sleep(0.016)
        except Exception:
            stats["errors"].append(traceback.format_exc())

    host_error = []
    host_stats = {}

    def host():
        try:
            silence_sounds()
            from bm_classes import Game
            import pygame

            pygame.init()
            pygame.display.set_mode((320, 240))
            pygame.font.init()
            game = Game()
            game.prep_num_players = 1
            game.prep_ai_count = 0
            game.game_state = "game_prep"
            game.set_status_queue(status_q)
            put_latest_nonblocking(
                state_q,
                game.to_dict(),
                {"state_queue_sent": 0, "state_queue_dropped": 0},
                "state_queue_sent",
                "state_queue_dropped",
            )
            time.sleep(0.3)
            seen = 0
            wait_until = time.time() + 6
            while time.time() < wait_until and seen < 5:
                try:
                    message = status_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if isinstance(message, dict) and message.get("type") == "status":
                    game._cached_status = message.get("status")
                    clients = (game._cached_status or {}).get("clients") or {}
                    seen = sum(1 for info in clients.values() if isinstance(info, dict) and info.get("registered"))
            game.start_match_from_lobby()
            surface = pygame.Surface((game.grid_width * 100, game.grid_height * 100))
            from bm_drawing import draw_game_screen

            metrics = {"state_queue_sent": 0, "state_queue_dropped": 0}
            max_put_ms = 0.0
            max_json = 0
            steps = 0
            sim_errors = 0
            now = 0
            for _ in range(12 * 60):
                now += 16
                game.current_time = now
                while True:
                    try:
                        event = input_q.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        game.handle_web_key_event(event)
                    except Exception:
                        sim_errors += 1
                        host_error.append(traceback.format_exc())
                try:
                    game.simulate(16, now_ms=now)
                except Exception:
                    sim_errors += 1
                    host_error.append(traceback.format_exc())
                    break
                try:
                    payload = game.to_dict()
                    encoded = json.dumps(payload)
                    max_json = max(max_json, len(encoded))
                except Exception:
                    sim_errors += 1
                    host_error.append(traceback.format_exc())
                    break
                started = time.perf_counter()
                put_latest_nonblocking(state_q, payload, metrics, "state_queue_sent", "state_queue_dropped")
                max_put_ms = max(max_put_ms, (time.perf_counter() - started) * 1000.0)
                if steps % 15 == 0 and game.game_state in ("playing", "get_ready"):
                    draw_game_screen(surface, game)
                steps += 1
            proc = psutil.Process()
            host_stats.update(
                {
                    "steps": steps,
                    "state": game.game_state,
                    "players": len(game.players),
                    "bombs": len(game.bombs),
                    "explosions": len(game.explosions),
                    "max_json": max_json,
                    "max_put_ms": round(max_put_ms, 2),
                    "sent": metrics["state_queue_sent"],
                    "dropped": metrics["state_queue_dropped"],
                    "sim_errors": sim_errors,
                    "rss_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
                    "input_q": input_q.qsize(),
                    "state_q": state_q.qsize(),
                }
            )
        except Exception:
            host_error.append(traceback.format_exc())

    async def run_clients():
        await asyncio.gather(*(client(i) for i in range(5)))

    host_thread = threading.Thread(target=host, name="stress-host")
    host_thread.start()
    asyncio.run(run_clients())
    host_thread.join(timeout=60)
    print("HOST", json.dumps(host_stats))
    print("SEATS", stats["seats"])
    print("RECV", stats["received"])
    print("MAX_BYTES", stats["max_bytes"])
    print("SERVER_ALIVE", server.is_alive(), "HOST_ALIVE", host_thread.is_alive())
    if host_error:
        print("HOST_ERRORS")
        print("\n---\n".join(host_error[:4]))
    if stats["errors"]:
        print("CLIENT_ERRORS")
        print("\n---\n".join(stats["errors"][:4]))
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        interesting = [line for line in text.splitlines() if "ERROR" in line or "Traceback" in line or "Exception" in line]
        print("LOG_ISSUES", len(interesting))
        for line in interesting[:30]:
            print(line)
    failed = bool(host_error or stats["errors"] or host_thread.is_alive())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

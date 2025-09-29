# --- Logging Setup ---
def setup_logging(logfile):
    import logging
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
        handlers=[
            logging.FileHandler(logfile, mode='a', encoding='utf-8'),
            logging.StreamHandler(sys.__stdout__)
        ]
    )
    class StreamToLogger:
        def __init__(self, level):
            self.level = level
        def write(self, message):
            if message.strip():
                logging.log(self.level, message.strip())
        def flush(self): pass
    sys.stdout = StreamToLogger(logging.INFO)
    sys.stderr = StreamToLogger(logging.ERROR)
    import builtins
    builtins.print = lambda *args, **kwargs: logging.info(' '.join(str(a) for a in args))
# --- End Logging Setup ---

import asyncio
import websockets
import aiohttp
from aiohttp import web
import threading
import json
import queue
import profiler
import os
import uuid
import time


# Set the port for the WebSocket server
PORT = 8765

HTTP_PORT = 8080
CLIENT_HTML = "client.html"

WS_SERVER_VERSION = "1.2.0"
HTTP_SERVER_VERSION = "1.1.0"

# Only call setup_logging at the top-level, not inside run_server_with_queue (to avoid double setup)
setup_logging("ws_server.log")

def run_server_with_queue(frame_queue, input_queue, log_path=None):
    import asyncio
    import websockets
    import threading
    import aiohttp
    from aiohttp import web
    import json
    import profiler
    import uuid

    PORT = 8765
    HTTP_PORT = 8080
    CLIENT_HTML = "client.html"

    latest_frame = None
    latest_frame_lock = threading.Lock()
    client_id_counter = 0
    client_id_lock = threading.Lock()
    client_ids = set()
    
    # Track clients and their players
    clients = {}  # {client_id: {websocket, players: [player_ids], last_seen: timestamp, latency_samples: [latencies]}}
    players = {}  # {player_id: {client_id, keys: {up, down, left, right, bomb}}}
    tracking_lock = threading.Lock()

    def frame_updater():
        nonlocal latest_frame
        while True:
            try:
                frame = frame_queue.get(timeout=1)
                with latest_frame_lock:
                    latest_frame = frame
            except Exception:
                continue

    threading.Thread(target=frame_updater, daemon=True).start()

    async def stream_frames(websocket):
        nonlocal client_id_counter
        # Assign a unique client_id to this client
        with client_id_lock:
            client_id = client_id_counter
            client_id_counter += 1
            client_ids.add(client_id)
        
        # Register client
        with tracking_lock:
            clients[client_id] = {
                'websocket': websocket,
                'players': [],
                'last_seen': time.time(),
                'latency_samples': []
            }
        
        # Send client_id to client as a JSON message
        await websocket.send(json.dumps({"type": "client_id", "client_id": client_id}))
        print(f"Client connected: {websocket.remote_address}, assigned client_id: {client_id}")
        pressed_keys = set()
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    if msg:
                        try:
                            data = json.loads(msg)
                            data['client_id'] = client_id  # Attach client_id to all events
                            
                            if data.get('type') == 'game_input':
                                # New format: compact game input [client_id, player_id, up, down, left, right, bomb, ...]
                                game_input = data.get('input', [])
                                print(f"Client {client_id} game input: {game_input}")
                                
                                # Update player tracking
                                with tracking_lock:
                                    clients[client_id]['last_seen'] = time.time()
                                    
                                    # Process each player's input
                                    if len(game_input) > 1:
                                        i = 1  # Skip client_id at index 0
                                        while i < len(game_input):
                                            if i + 5 < len(game_input):  # Need at least 6 values: player_id, up, down, left, right, bomb
                                                player_id = game_input[i]
                                                up, down, left, right, bomb = game_input[i+1:i+6]
                                                
                                                # Register player if not exists
                                                if player_id not in players:
                                                    players[player_id] = {
                                                        'client_id': client_id,
                                                        'keys': {'up': 0, 'down': 0, 'left': 0, 'right': 0, 'bomb': 0}
                                                    }
                                                    clients[client_id]['players'].append(player_id)
                                                
                                                # Update player keys
                                                players[player_id]['keys'] = {
                                                    'up': up, 'down': down, 'left': left, 'right': right, 'bomb': bomb
                                                }
                                                
                                                i += 6  # Move to next player
                                            else:
                                                break
                                
                                input_queue.put(data)
                            elif data.get('type') == 'keys_update':
                                # Legacy format: client sends all currently pressed keys
                                new_pressed_keys = set(data.get('pressed_keys', []))
                                pressed_keys = new_pressed_keys
                                print(f"Client {client_id} pressed keys: {sorted(pressed_keys)}")
                                input_queue.put(data)
                            elif data.get('type') == 'keydown':
                                # Legacy format: individual key events
                                pressed_keys.add(data.get('key'))
                                print(f"Client {client_id} pressed keys: {sorted(pressed_keys)}")
                                input_queue.put(data)
                            elif data.get('type') == 'keyup':
                                # Legacy format: individual key events
                                pressed_keys.discard(data.get('key'))
                                print(f"Client {client_id} pressed keys: {sorted(pressed_keys)}")
                                input_queue.put(data)
                            
                            # Send acknowledgment back to client for latency measurement
                            server_timestamp = time.time() * 1000  # Convert to milliseconds
                            client_timestamp = data.get('client_timestamp')
                            
                            # Calculate latency if client timestamp is provided
                            if client_timestamp:
                                latency = server_timestamp - client_timestamp
                                with tracking_lock:
                                    if client_id in clients:
                                        clients[client_id]['latency_samples'].append(latency)
                                        # Keep only last 100 samples to prevent memory growth
                                        if len(clients[client_id]['latency_samples']) > 100:
                                            clients[client_id]['latency_samples'] = clients[client_id]['latency_samples'][-100:]
                            
                            ack_msg = {
                                "type": "input_ack",
                                "client_id": client_id,
                                "original_timestamp": client_timestamp,
                                "server_timestamp": server_timestamp
                            }
                            await websocket.send(json.dumps(ack_msg))
                        except Exception as e:
                            print(f"Error parsing input: {e}")
                except asyncio.TimeoutError:
                    pass
                # No longer sending image frames - this is now input-only
                await asyncio.sleep(0.01)
        except websockets.ConnectionClosed as cc:
            print(f"WebSocket connection closed: {cc}")
        except Exception as e:
            print(f"Error in stream_frames: {e}")
        print(f"Exiting stream_frames for {websocket.remote_address}, client_id: {client_id}")
        with client_id_lock:
            client_ids.discard(client_id)
        
        with tracking_lock:
            # Remove all players from this client
            if client_id in clients:
                for player_id in clients[client_id]['players']:
                    if player_id in players:
                        del players[player_id]
                del clients[client_id]

    async def handle_root(request):
        return web.FileResponse(CLIENT_HTML)

    async def handle_static(request):
        path = request.match_info.get('filename', None)
        if path and os.path.exists(path):
            return web.FileResponse(path)
        return web.Response(status=404)

    async def handle_versions(request):
        return web.json_response({
            "ws_server": WS_SERVER_VERSION,
            "http_server": HTTP_SERVER_VERSION
        })
    
    async def handle_config(request):
        import bm_params
        return web.json_response({
            "key_send_frequency_limit": bm_params.KEY_SEND_FREQUENCY_LIMIT,
            "send_on_change": bm_params.SEND_ON_CHANGE,
            "periodic_sending": bm_params.PERIODIC_SENDING,
            "min_send_frequency": bm_params.MIN_SEND_FREQUENCY,
            "max_send_frequency": bm_params.MAX_SEND_FREQUENCY
        })
    
    async def handle_status(request):
        """Get current client and player status"""
        with tracking_lock:
            status = {
                'clients': {},
                'players': {}
            }
            
            for client_id, client_data in clients.items():
                latency_samples = client_data.get('latency_samples', [])
                avg_latency = sum(latency_samples) / len(latency_samples) if latency_samples else 0
                
                status['clients'][client_id] = {
                    'players': client_data['players'],
                    'last_seen': client_data['last_seen'],
                    'avg_latency': round(avg_latency, 2),
                    'latency_samples': len(latency_samples)
                }
            
            for player_id, player_data in players.items():
                status['players'][player_id] = {
                    'client_id': player_data['client_id'],
                    'keys': player_data['keys']
                }
        
        return web.json_response(status)

    def start_http_server():
        app = web.Application()
        app.router.add_get('/', handle_root)
        app.router.add_get('/{filename}', handle_static)
        app.router.add_get('/versions', handle_versions)
        app.router.add_get('/config', handle_config)
        app.router.add_get('/status', handle_status)
        runner = web.AppRunner(app)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def run():
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
            await site.start()
            print(f"HTTP server started on port {HTTP_PORT}")
            while True:
                await asyncio.sleep(3600)
        loop.run_until_complete(run())

    async def main():
        print(f"Starting WebSocket server on port {PORT}")
        ws_server = websockets.serve(stream_frames, "0.0.0.0", PORT, max_size=2**22)
        threading.Thread(target=start_http_server, daemon=True).start()
        await ws_server
        await asyncio.Future()  # run forever

    asyncio.run(main())

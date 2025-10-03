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

# Global game state tracking
_current_game_state = "game_prep"  # Start in prep mode to allow immediate client registration
_game_state_lock = threading.Lock()
game_instance = None

def update_game_state(new_state):
    """Update the current game state (called from main game)"""
    global _current_game_state
    with _game_state_lock:
        _current_game_state = new_state
        #print(f"Game state changed to: {new_state}")

def get_game_state():
    """Get the current game state"""
    global _current_game_state
    with _game_state_lock:
        return _current_game_state

def set_game_instance(game):
    """Set the game instance for input handling"""
    global game_instance
    game_instance = game

def run_server_with_queue(input_queue, log_path=None):
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

    client_id_counter = 0
    client_id_lock = threading.Lock()
    client_ids = set()

    # Track clients and their players
    clients = {}  # {client_id: {websocket, players: [player_ids], last_seen: timestamp, latency_samples: [latencies], registered: bool}}
    players = {}  # {player_id: {client_id, keys: {up, down, left, right, bomb}}}
    tracking_lock = threading.Lock()

    async def handle_client(websocket):
        nonlocal client_id_counter
        # Assign a unique client_id to this client
        with client_id_lock:
            client_id = client_id_counter
            client_id_counter += 1
            client_ids.add(client_id)
        
        # Create client entry but don't register yet
        with tracking_lock:
            clients[client_id] = {
                'websocket': websocket,
                'players': [],
                'last_seen': time.time(),
                'latency_samples': [],
                'registered': False
            }
        
        # Send client_id to client as a JSON message
        await websocket.send(json.dumps({"type": "client_id", "client_id": client_id}))
        print(f"Client connected: {websocket.remote_address}, assigned client_id: {client_id} (not registered yet)")
        pressed_keys = set()
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    if msg:
                        try:
                            data = json.loads(msg)
                            data['client_id'] = client_id  # Attach client_id to all events
                            
                            if data.get('type') == 'register_client':
                                # Handle explicit client registration
                                current_state = get_game_state()
                                if current_state == "game_prep":
                                    with tracking_lock:
                                        if client_id in clients:
                                            clients[client_id]['registered'] = True
                                            clients[client_id]['last_seen'] = time.time()
                                            
                                            # Assign player IDs based on requested number of players
                                            requested_players = data.get('num_players', 1)
                                            current_player_count = len(clients[client_id]['players'])
                                            
                                            # Only assign new players if we need more
                                            if current_player_count < requested_players:
                                                for i in range(current_player_count, requested_players):
                                                    player_id = len(players) + 1
                                                    players[player_id] = {
                                                        'client_id': client_id,
                                                        'keys': {'up': 0, 'down': 0, 'left': 0, 'right': 0, 'bomb': 0}
                                                    }
                                                    clients[client_id]['players'].append(player_id)
                                                    print(f"Assigned player ID {player_id} to client {client_id}")
                                            
                                            # Remove excess players if fewer requested
                                            elif current_player_count > requested_players:
                                                excess_players = clients[client_id]['players'][requested_players:]
                                                for player_id in excess_players:
                                                    if player_id in players:
                                                        del players[player_id]
                                                        print(f"Removed player ID {player_id} from client {client_id}")
                                                clients[client_id]['players'] = clients[client_id]['players'][:requested_players]
                                            
                                            # Send assigned player IDs back to client
                                            assigned_player_ids = clients[client_id]['players']
                                            await websocket.send(json.dumps({
                                                "type": "player_ids_assigned",
                                                "client_id": client_id,
                                                "player_ids": assigned_player_ids
                                            }))
                                    
                                    # Send registration confirmation
                                    await websocket.send(json.dumps({
                                        "type": "registration_confirmed",
                                        "client_id": client_id,
                                        "game_state": current_state,
                                        "message": "Successfully registered for game"
                                    }))
                                    print(f"Client {client_id} registered successfully")
                                else:
                                    # Send registration rejection
                                    await websocket.send(json.dumps({
                                        "type": "registration_rejected",
                                        "client_id": client_id,
                                        "game_state": current_state,
                                        "message": f"Registration not allowed in {current_state} state. Only allowed during game preparation."
                                    }))
                                    print(f"Client {client_id} registration rejected - game state: {current_state}")
                                continue
                            
                            elif data.get('type') == 'game_input':
                                # Only process game input from registered clients
                                with tracking_lock:
                                    if client_id not in clients or not clients[client_id]['registered']:
                                        await websocket.send(json.dumps({
                                            "type": "input_rejected",
                                            "client_id": client_id,
                                            "message": "Client not registered. Please register first."
                                        }))
                                        continue
                                
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
                                                requested_player_id = game_input[i]
                                                up, down, left, right, bomb = game_input[i+1:i+6]
                                                
                                                # Assign server-side player ID if not exists
                                                if requested_player_id not in players:
                                                    # Check if this client already has a player with this ID
                                                    if requested_player_id in clients[client_id]['players']:
                                                        # Client already has this player ID, use it
                                                        player_id = requested_player_id
                                                    else:
                                                        # Assign new server-side player ID
                                                        player_id = len(players) + 1
                                                        print(f"Assigned server player ID {player_id} to client {client_id} (requested {requested_player_id})")
                                                    
                                                    players[player_id] = {
                                                        'client_id': client_id,
                                                        'keys': {'up': 0, 'down': 0, 'left': 0, 'right': 0, 'bomb': 0}
                                                    }
                                                    clients[client_id]['players'].append(player_id)
                                                else:
                                                    player_id = requested_player_id
                                                
                                                # Update player keys
                                                players[player_id]['keys'] = {
                                                    'up': up, 'down': down, 'left': left, 'right': right, 'bomb': bomb
                                                }
                                                
                                                # Send input to game if available
                                                if game_instance:
                                                    # Convert binary input to key events
                                                    key_events = []
                                                    if up: key_events.append({'type': 'keydown', 'key': 'up', 'client_id': client_id, 'player_id': requested_player_id})
                                                    if down: key_events.append({'type': 'keydown', 'key': 'down', 'client_id': client_id, 'player_id': requested_player_id})
                                                    if left: key_events.append({'type': 'keydown', 'key': 'left', 'client_id': client_id, 'player_id': requested_player_id})
                                                    if right: key_events.append({'type': 'keydown', 'key': 'right', 'client_id': client_id, 'player_id': requested_player_id})
                                                    if bomb: key_events.append({'type': 'keydown', 'key': 'bomb', 'client_id': client_id, 'player_id': requested_player_id})
                                                    
                                                    # Send key events to game
                                                    for key_event in key_events:
                                                        try:
                                                            game_instance.handle_web_key_event(key_event)
                                                        except Exception as e:
                                                            print(f"Error sending input to game: {e}")
                                                
                                                i += 6  # Move to next player
                                            else:
                                                break
                                        
                                        # Send assigned player IDs back to client
                                        assigned_player_ids = clients[client_id]['players']
                                        await websocket.send(json.dumps({
                                            "type": "player_ids_assigned",
                                            "client_id": client_id,
                                            "player_ids": assigned_player_ids
                                        }))
                                
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
            print(f"Error in handle_client: {e}")
        print(f"Exiting handle_client for {websocket.remote_address}, client_id: {client_id}")
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
                    'latency_samples': len(latency_samples),
                    'registered': client_data.get('registered', False)
                }
            
            for player_id, player_data in players.items():
                status['players'][player_id] = {
                    'client_id': player_data['client_id'],
                    'keys': player_data['keys']
                }
        
        return web.json_response(status)

    def start_http_server():
        try:
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
                try:
                    await runner.setup()
                    site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
                    await site.start()
                    print(f"HTTP server started on port {HTTP_PORT}")
                    while True:
                        await asyncio.sleep(3600)
                except Exception as e:
                    print(f"HTTP server failed to start: {e}")
                    raise
            loop.run_until_complete(run())
        except Exception as e:
            print(f"HTTP server startup failed: {e}")
            import traceback
            traceback.print_exc()

    async def main():
        print(f"Starting WebSocket server on port {PORT}")
        ws_server = websockets.serve(handle_client, "0.0.0.0", PORT, max_size=2**22)
        threading.Thread(target=start_http_server, daemon=True).start()
        await ws_server
        await asyncio.Future()  # run forever

    asyncio.run(main())

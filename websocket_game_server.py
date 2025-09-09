"""
Enhanced WebSocket server for real-time game state broadcasting
Supports both game state updates and drawing command streaming
"""
import asyncio
import websockets
import json
import multiprocessing
import threading
import time
import socket
from typing import Set, Dict, Any, Optional
from game_state_serializer import serialize_game_state, serialize_draw_commands, to_json, from_json

class WebSocketGameServer:
    def __init__(self, port: int = 8765):
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.game_state_queue: Optional[multiprocessing.Queue] = None
        self.input_queue: Optional[multiprocessing.Queue] = None
        self.draw_commands_queue: Optional[multiprocessing.Queue] = None
        self.running = False
        self.status_sock: Optional[socket.socket] = None
        
    async def register_client(self, websocket: websockets.WebSocketServerProtocol):
        """Register a new client"""
        self.clients.add(websocket)
        self.log_status(f"[WS] Client connected. Total clients: {len(self.clients)}")
        
        # Send initial connection confirmation
        await websocket.send(to_json({
            'type': 'connection_confirmed',
            'client_id': id(websocket),
            'message': 'Connected to BomberMarv game server'
        }))
    
    async def unregister_client(self, websocket: websockets.WebSocketServerProtocol):
        """Unregister a client"""
        self.clients.discard(websocket)
        self.log_status(f"[WS] Client disconnected. Total clients: {len(self.clients)}")
    
    async def broadcast_to_all(self, message: str):
        """Broadcast message to all connected clients"""
        if not self.clients:
            return
            
        # Create list to avoid set changed during iteration
        clients_copy = list(self.clients)
        disconnected = []
        
        for client in clients_copy:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.append(client)
            except Exception as e:
                self.log_status(f"[WS] Error sending to client: {e}")
                disconnected.append(client)
        
        # Remove disconnected clients
        for client in disconnected:
            self.clients.discard(client)
    
    async def handle_client_message(self, websocket: websockets.WebSocketServerProtocol, message: str):
        """Handle incoming message from client"""
        try:
            data = from_json(message)
            
            if data.get('type') == 'input_event':
                # Normalize and forward input event to game
                if self.input_queue:
                    try:
                        normalized = {
                            'type': data.get('event_type', ''),  # 'keydown' | 'keyup'
                            'key': data.get('key', ''),
                            'player_id': data.get('player_id', 0),
                            'timestamp': data.get('timestamp', 0),
                        }
                        self.input_queue.put_nowait(normalized)
                    except Exception:
                        pass  # Queue full, skip this input
            
            elif data.get('type') == 'ping':
                # Respond to ping
                await websocket.send(to_json({'type': 'pong', 'timestamp': data.get('timestamp', 0)}))
            
            elif data.get('type') == 'request_game_state':
                # Client requesting current game state (for reconnection)
                await websocket.send(to_json({'type': 'game_state_request_acknowledged'}))
                
        except json.JSONDecodeError:
            self.log_status(f"[WS] Invalid JSON received from client: {message}")
        except Exception as e:
            self.log_status(f"[WS] Error handling client message: {e}")
    
    async def client_handler(self, websocket: websockets.WebSocketServerProtocol):
        """Handle individual client connection"""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                await self.handle_client_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.log_status(f"[WS] Client handler error: {e}")
        finally:
            await self.unregister_client(websocket)
    
    async def game_state_broadcaster(self):
        """Continuously broadcast game state updates"""
        while self.running:
            try:
                if self.game_state_queue and not self.game_state_queue.empty():
                    # Get latest game state
                    game_state = None
                    while not self.game_state_queue.empty():
                        try:
                            game_state = self.game_state_queue.get_nowait()
                        except:
                            break
                    
                    if game_state:
                        message = to_json({
                            'type': 'game_state_update',
                            'data': game_state,
                            'timestamp': int(time.time() * 1000)
                        })
                        await self.broadcast_to_all(message)
                
                # Also broadcast drawing commands if available
                if self.draw_commands_queue and not self.draw_commands_queue.empty():
                    commands = None
                    while not self.draw_commands_queue.empty():
                        try:
                            commands = self.draw_commands_queue.get_nowait()
                        except:
                            break
                    
                    if commands:
                        message = to_json({
                            'type': 'draw_commands',
                            'data': commands,
                            'timestamp': int(time.time() * 1000)
                        })
                        await self.broadcast_to_all(message)
                
                await asyncio.sleep(1/60)  # 60 FPS broadcast rate
                
            except Exception as e:
                self.log_status(f"[WS] Broadcaster error: {e}")
                await asyncio.sleep(0.1)
    
    async def start_server(self):
        """Start the WebSocket server"""
        self.running = True
        
        # Start the WebSocket server
        try:
            # Connect status console if available
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.2)
                s.connect(("127.0.0.1", 8770))
                s.settimeout(None)
                self.status_sock = s
                self.log_status("[WS] Status console connected")
            except Exception:
                self.status_sock = None
            server = await websockets.serve(
                self.client_handler,
                "localhost",
                self.port,
                ping_interval=30,
                ping_timeout=10
            )
            
            self.log_status(f"[WS] WebSocket game server started on ws://localhost:{self.port}")
            
            # Start game state broadcaster
            broadcaster_task = asyncio.create_task(self.game_state_broadcaster())
            
            try:
                await server.wait_closed()
            finally:
                self.running = False
                broadcaster_task.cancel()
                
        except Exception as e:
            self.log_status(f"[WS] Failed to start WebSocket server: {e}")
            self.running = False
    
    def set_queues(self, game_state_queue: multiprocessing.Queue, 
                   input_queue: multiprocessing.Queue,
                   draw_commands_queue: Optional[multiprocessing.Queue] = None):
        """Set the communication queues"""
        self.game_state_queue = game_state_queue
        self.input_queue = input_queue
        self.draw_commands_queue = draw_commands_queue
    
    def log_status(self, message: str):
        print(message)
        try:
            if self.status_sock:
                self.status_sock.sendall((message + "\n").encode())
        except Exception:
            self.status_sock = None

def run_websocket_server(game_state_queue: multiprocessing.Queue,
                        input_queue: multiprocessing.Queue,
                        draw_commands_queue: Optional[multiprocessing.Queue] = None,
                        port: int = 8765):
    """Run the WebSocket server in a separate process"""
    server = WebSocketGameServer(port)
    server.set_queues(game_state_queue, input_queue, draw_commands_queue)
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("WebSocket server stopped")
    except Exception as e:
        print(f"WebSocket server error: {e}")

# HTTP server for serving the React client
import http.server
import socketserver
import os
from threading import Thread

class HTTPGameServer:
    def __init__(self, port: int = 8080, directory: str = "web_client"):
        self.port = port
        self.directory = directory
        
    def start_server(self):
        """Start HTTP server for serving web client"""
        os.chdir(self.directory) if os.path.exists(self.directory) else None
        
        handler = http.server.SimpleHTTPRequestHandler
        
        with socketserver.TCPServer(("", self.port), handler) as httpd:
            print(f"HTTP server serving at http://localhost:{self.port}")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("HTTP server stopped")

def start_http_server_thread(port: int = 8080, directory: str = "web_client"):
    """Start HTTP server in a separate thread"""
    server = HTTPGameServer(port, directory)
    thread = Thread(target=server.start_server, daemon=True)
    thread.start()
    return thread
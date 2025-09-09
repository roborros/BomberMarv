"""
Dual-backend BomberMarv - supports both pygame and web rendering simultaneously
"""
import multiprocessing
import sys
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional
from typing import List
import shutil
import socket

# Import rendering backends
from pygame_backend import PygameRenderingBackend
from rendering_backend import WebRenderingBackend

# Import drawing modules
import bm_drawing_new as drawing

# Import game logic and utilities
from bm_classes import Game
from bm_params import *
from bm_sounds import *
from lib_collisions import *
from lib_grid import *
from game_state_serializer import serialize_game_state, serialize_draw_commands
from websocket_game_server import run_websocket_server, start_http_server_thread

def kill_existing_web_servers(ports: List[int] = [8765, 8080]) -> None:
    """Kill any existing processes listening on the given ports.

    Tries psutil first; falls back to Windows netstat/taskkill if psutil is unavailable.
    """
    killed_any = False
    # Try psutil if available
    try:
        import psutil  # type: ignore
        try:
            listeners = set()
            for conn in psutil.net_connections(kind='inet'):
                try:
                    if conn.laddr and conn.laddr.port in ports and conn.status == psutil.CONN_LISTEN and conn.pid:
                        listeners.add(conn.pid)
                except Exception:
                    continue
            for pid in sorted(listeners):
                try:
                    p = psutil.Process(pid)
                    p.terminate()
                    try:
                        p.wait(timeout=1.5)
                    except Exception:
                        p.kill()
                    print(f"[KILL] Terminated PID {pid} listening on target port")
                    killed_any = True
                except Exception:
                    continue
        except Exception:
            pass
    except ImportError:
        psutil = None  # noqa: F841

    # Fallback for Windows without psutil or if nothing killed
    if os.name == 'nt' and not killed_any:
        for port in ports:
            try:
                # Find PIDs listening on :port and kill them
                cmd = 'for /f "tokens=5" %a in ("' \
                      'netstat -ano ^| findstr LISTENING ^| findstr :{port}' \
                      '") do @taskkill /PID %a /F'
                # Run within cmd.exe to interpret the for loop
                subprocess.run(f"cmd /c {cmd.format(port=port)}", shell=True, capture_output=True, text=True)
                print(f"[KILL] Attempted to kill listeners on port {port}")
            except Exception:
                pass

    # Extra safety: try to kill processes that look like our previous servers by cmdline
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info.get('cmdline') or [])
                if 'websocket_game_server.py' in cmdline or 'webpack-dev-server' in cmdline:
                    proc.kill()
                    print(f"[KILL] Killed likely server process PID {proc.pid}")
            except Exception:
                continue
    except Exception:
        pass

class DualRenderingScreen:
    """Screen class that supports multiple rendering backends"""
    
    def __init__(self, pygame_backend: Optional[PygameRenderingBackend] = None,
                 web_backend: Optional[WebRenderingBackend] = None):
        self.pygame_backend = pygame_backend
        self.web_backend = web_backend
        self.active_backends = [b for b in [pygame_backend, web_backend] if b is not None]
    
    def render_frame(self, game, game_state: str):
        """Render a frame using all active backends"""
        for backend in self.active_backends:
            backend.clear()
            
            # Render based on game state
            if game_state == "startup":
                self.draw_startup(backend, game)
            elif game_state == "game_prep":
                self.draw_game_prep(backend, game)
            elif game_state == "get_ready":
                if game.current_time < game.game_start_time:
                    drawing.draw_game_screen(backend, game)
                    drawing.draw_get_ready(backend)
            elif game_state == "playing":
                drawing.draw_game_screen(backend, game)
            elif game_state == "win":
                drawing.draw_title_page(backend, alpha=1.0)
                alive_players = [p for p in game.players if p.alive]
                winner = alive_players[0] if alive_players else None
                drawing.draw_stat_screen(backend, winner, game.players)
            elif game_state == "champion":
                alive_players = [p for p in game.players if p.alive]
                if alive_players:
                    drawing.draw_champion_screen(backend, alive_players[0])

            # Optional FPS overlay for pygame backend only (web shows its own)
            if getattr(game, 'show_fps', False) and hasattr(game, 'clock'):
                try:
                    fps_value = int(game.clock.get_fps())
                    backend.draw_text(f"FPS: {fps_value}", 10, 10, "arial", 20, (255, 255, 255))
                except Exception:
                    pass
            
            backend.present()
    
    def draw_startup(self, backend, game):
        """Draw startup screen"""
        elapsed = game.current_time - game.startup_start_time
        alpha = 1.0
        
        if elapsed < 2000:
            alpha = 1.0
        elif elapsed < 2800:
            alpha = (2800 - elapsed) / 800
        else:
            alpha = 0.0
        
        drawing.draw_title_page(backend, alpha)
        
        if elapsed >= 2200:
            drawing.draw_controls(backend, game.players)
            backend.draw_text("Press Enter to start the game", BASE_WIDTH // 2, BASE_HEIGHT - 50,
                            "arial", 32, (255, 255, 255), center=True)
    
    def draw_game_prep(self, backend, game):
        """Draw game prep screen - simplified version"""
        backend.fill_background(COLOR_BG)
        
        # Title
        backend.draw_text("Game Setup", BASE_WIDTH // 2, 60, "arial", 48, (255, 255, 255), center=True)
        
        # Simple player list
        y = 150
        for i, player in enumerate(game.players):
            backend.draw_text(f"Player {i+1}: {player.name}", 100, y, "arial", 32, player.color)
            y += 50
        
        # Instructions
        backend.draw_text("Press Enter to start", BASE_WIDTH // 2, BASE_HEIGHT - 100,
                         "arial", 32, (255, 255, 255), center=True)
    
    def get_pygame_events(self):
        """Get pygame events if pygame backend is active"""
        if self.pygame_backend:
            return self.pygame_backend.handle_events()
        return []
    
    def get_web_commands(self):
        """Get drawing commands from web backend"""
        if self.web_backend:
            return self.web_backend.get_commands()
        return []

class GameManager:
    """Manages the game loop and dual rendering"""
    
    def __init__(self, enable_pygame: bool = True, enable_web: bool = True, auto_setup: bool = True):
        self.enable_pygame = enable_pygame
        self.enable_web = enable_web
        self.auto_setup = auto_setup
        
        # Initialize backends
        self.pygame_backend = None
        self.web_backend = None
        
        if enable_pygame:
            self.pygame_backend = PygameRenderingBackend(BASE_WIDTH, BASE_HEIGHT, "BomberMarv")
            if not self.pygame_backend.init():
                print("Failed to initialize pygame backend")
                self.pygame_backend = None
        
        if enable_web:
            self.web_backend = WebRenderingBackend(BASE_WIDTH, BASE_HEIGHT)
            self.web_backend.init()
            # Ensure web backend is actively producing commands even if pygame blocks
        
        # Initialize screen with active backends
        self.screen = DualRenderingScreen(self.pygame_backend, self.web_backend)
        
        # Initialize game
        self.game = Game()
        # Ensure pygame backend uses the same display surface created by Game
        if self.pygame_backend:
            try:
                import pygame  # local import to avoid hard dep when pygame disabled
                current_display = pygame.display.get_surface()
                if current_display is not None:
                    self.pygame_backend.screen = current_display
                    self.pygame_backend.window_size = current_display.get_size()
            except Exception:
                pass
        self.game.init_game()
        
        # Web server queues
        self.game_state_queue = None
        self.input_queue = None
        self.draw_commands_queue = None
        self.web_process = None
        self.http_thread = None
        self.status_sock = None
        
        # Only proceed with web bits if still enabled after optional auto-setup
        if enable_web:
            if self.auto_setup:
                setup_ok = self.setup_web_client()
                if not setup_ok:
                    self.enable_web = False
            # Re-check the effective flag before starting servers
            if self.enable_web:
                self.setup_web_server()
        # Connect to status console if available
        self._connect_status_console()
    def _connect_status_console(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect(("127.0.0.1", 8770))
            s.settimeout(None)
            self.status_sock = s
            self._log_status("[GAME] Status console connected")
        except Exception:
            self.status_sock = None

    def _log_status(self, message: str):
        try:
            print(message)
            if self.status_sock:
                self.status_sock.sendall((message + "\n").encode())
        except Exception:
            self.status_sock = None
    
    def check_node_installed(self):
        """Check if Node.js is installed"""
        try:
            # Try to locate node via PATH first
            node_path = shutil.which('node')
            if node_path:
                result = subprocess.run([node_path, '--version'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    version = result.stdout.strip()
                    print(f"[OK] Node.js found: {version} ({node_path})")
                    return True
            # Fallbacks on Windows: use 'where node'
            if os.name == 'nt':
                where = subprocess.run('where node', shell=True, capture_output=True, text=True, timeout=10)
                if where.returncode == 0 and where.stdout.strip():
                    node_path = where.stdout.splitlines()[0].strip()
                    result = subprocess.run([node_path, '--version'], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        version = result.stdout.strip()
                        print(f"[OK] Node.js found: {version} ({node_path})")
                        return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _run_npm(self, npm_args: List[str], cwd: Path, timeout: int = 180):
        """Run npm with robust Windows handling. Returns (returncode, stdout, stderr)."""
        attempts = []
        # 1) Try PATH-resolved npm
        npm_path = shutil.which('npm')
        if npm_path:
            attempts.append([npm_path] + npm_args)
        # 2) Try npm.cmd explicitly (Windows)
        if os.name == 'nt':
            npm_cmd = shutil.which('npm.cmd')
            if npm_cmd:
                attempts.append([npm_cmd] + npm_args)
            # 3) Common install locations
            for base in [os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')]:
                if base:
                    candidate = Path(base) / 'nodejs' / 'npm.cmd'
                    if candidate.exists():
                        attempts.append([str(candidate)] + npm_args)
        # 4) Shell fallback
        shell_cmd = 'npm ' + ' '.join(npm_args)
        try_shell = os.name == 'nt'

        last_rc, last_out, last_err = 127, '', 'npm not found'
        for cmd in attempts:
            try:
                res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
                return res.returncode, res.stdout, res.stderr
            except FileNotFoundError:
                last_rc, last_out, last_err = 127, '', f"not found: {' '.join(cmd)}"
                continue
        if try_shell:
            res = subprocess.run(shell_cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=True)
            return res.returncode, res.stdout, res.stderr
        return last_rc, last_out, last_err

    def install_web_dependencies(self):
        """Install Node.js dependencies for web client"""
        web_client_dir = Path("web_client")
        
        if not web_client_dir.exists():
            print("[ERROR] web_client directory not found!")
            return False
        
        package_json = web_client_dir / "package.json"
        if not package_json.exists():
            print("[ERROR] package.json not found in web_client/")
            return False
        
        node_modules = web_client_dir / "node_modules"
        if node_modules.exists():
            print("[OK] Node modules already installed")
            return True
        
        print("[NPM] Installing Node.js dependencies...")
        rc, out, err = self._run_npm(['install'], cwd=web_client_dir, timeout=300)
        if rc == 0:
            print("[OK] Dependencies installed successfully")
            return True
        else:
            print(f"[FAIL] npm install failed (rc={rc}): {err or out}")
            print("[HINT] If you just installed Node.js, restart your IDE/terminal so PATH updates apply.")
            return False

    def build_web_client(self):
        """Build the React web client"""
        web_client_dir = Path("web_client")
        dist_dir = web_client_dir / "dist"
        
        # Check if already built
        if dist_dir.exists() and any(dist_dir.iterdir()):
            print("[OK] Web client already built")
            return True
        
        print("[BUILD] Building React web client...")
        rc, out, err = self._run_npm(['run', 'build'], cwd=web_client_dir, timeout=300)
        if rc == 0:
            print("[OK] Web client built successfully")
            return True
        else:
            print(f"[FAIL] Build failed (rc={rc}): {err or out}")
            print("[HINT] If you just installed Node.js, restart your IDE/terminal so PATH updates apply.")
            return False

    def setup_web_client(self):
        """Automatically set up the web client"""
        print("[START] Setting up BomberMarv web client...")
        
        # Check Node.js
        if not self.check_node_installed():
            print("[ERROR] Node.js not found!")
            print("Please install Node.js from https://nodejs.org/ (version 14+)")
            print("Continuing without web client...")
            self.enable_web = False
            return False
        
        # Install dependencies
        if not self.install_web_dependencies():
            print("[FAIL] Failed to install dependencies")
            print("Continuing without web client...")
            self.enable_web = False
            return False
        
        # Build client
        if not self.build_web_client():
            print("[FAIL] Failed to build web client")
            print("Continuing without web client...")
            self.enable_web = False
            return False
        
        print("[OK] Web client setup complete!")
        return True

    def setup_web_server(self):
        """Set up WebSocket and HTTP servers"""
        # Ensure no stale servers are running from previous sessions/projects
        kill_existing_web_servers([8765, 8080])

        self.game_state_queue = multiprocessing.Queue(maxsize=2)
        self.input_queue = multiprocessing.Queue(maxsize=10)
        self.draw_commands_queue = multiprocessing.Queue(maxsize=2)
        
        # Start WebSocket server process
        self.web_process = multiprocessing.Process(
            target=run_websocket_server,
            args=(self.game_state_queue, self.input_queue, self.draw_commands_queue)
        )
        self.web_process.daemon = True
        self.web_process.start()
        
        # Start HTTP server for serving React client
        web_client_dist = Path("web_client/dist")
        web_client_src = Path("web_client/src")
        # If dist missing or empty, try to build once here as a fallback
        need_build = False
        if (not web_client_dist.exists()) or (web_client_dist.exists() and not any(web_client_dist.iterdir())):
            print("[INFO] web_client/dist not found or empty. Attempting one-time build...")
            need_build = True
        else:
            try:
                dist_index = web_client_dist / "index.html"
                dist_mtime = dist_index.stat().st_mtime if dist_index.exists() else 0
                # If any src file is newer than dist, rebuild
                latest_src_mtime = max((p.stat().st_mtime for p in web_client_src.rglob("*.js")), default=0)
                if latest_src_mtime > dist_mtime:
                    print("[BUILD] Detected newer source files. Rebuilding web client...")
                    need_build = True
            except Exception:
                pass
        if need_build:
            build_ok = self.build_web_client()
            if not build_ok:
                print("[WARN] Build failed. Serving raw web_client directory (you will see a file listing).")
        serve_dir = str(web_client_dist) if web_client_dist.exists() and any(web_client_dist.iterdir()) else "web_client"
        self.http_thread = start_http_server_thread(8080, serve_dir)
        
        self._log_status("Web servers started:")
        self._log_status("  - WebSocket: ws://localhost:8765")
        self._log_status("  - HTTP: http://localhost:8080")
    
    def handle_input(self):
        """Handle input from both pygame and web clients"""
        # Handle pygame events once per frame (avoid draining the queue multiple times)
        if self.pygame_backend:
            self.game.handle_window_events()
        
        # Handle web input
        if self.input_queue:
            while not self.input_queue.empty():
                try:
                    web_event = self.input_queue.get_nowait()
                    self.game.handle_web_key_event(web_event)
                except:
                    break
    
    def broadcast_game_state(self):
        """Broadcast current game state to web clients"""
        if not self.game_state_queue:
            return
        
        try:
            # Clear old states and send latest
            while not self.game_state_queue.empty():
                try:
                    self.game_state_queue.get_nowait()
                except:
                    break
            
            game_state = serialize_game_state(self.game)
            self.game_state_queue.put_nowait(game_state)
        except:
            pass  # Queue full, skip this update
    
    def broadcast_draw_commands(self):
        """Broadcast drawing commands to web clients"""
        if not self.draw_commands_queue or not self.web_backend:
            return
        
        try:
            commands = self.web_backend.get_commands()
            if commands:
                # Clear old commands and send latest
                while not self.draw_commands_queue.empty():
                    try:
                        self.draw_commands_queue.get_nowait()
                    except:
                        break
                
                serialized_commands = serialize_draw_commands(commands)
                self.draw_commands_queue.put_nowait(serialized_commands)
        except:
            pass  # Queue full, skip this update
    
    def run(self):
        """Main game loop"""
        self._log_status("\n" + "="*60)
        self._log_status("[GAME] BomberMarv Dual Rendering System")
        self._log_status("="*60)
        self._log_status(f"Pygame: {'ON' if self.pygame_backend else 'OFF'}")
        self._log_status(f"Web: {'ON' if self.web_backend else 'OFF'}")
        
        if self.pygame_backend:
            self._log_status("[LOCAL] Local pygame window will open")
        
        if self.web_backend:
            self._log_status("[START] Web client available at: http://localhost:8080")
            self._log_status("[WS] WebSocket server: ws://localhost:8765")
            
        self._log_status("\nControls:")
        self._log_status("   Desktop: WASD + Space (bomb)")
        self._log_status("   Web: WASD + Space or touch controls")
        self._log_status("   Exit: Ctrl+C")
        self._log_status("-"*60)
        
        try:
            while True:
                # Update game timing
                self.game.tick()
                
                # Handle input from all sources
                self.handle_input()
                
                # Update game logic based on state
                if self.game.game_state == "playing":
                    self.game.update()
                elif self.game.game_state == "get_ready":
                    if self.game.current_time >= self.game.game_start_time:
                        self.game.game_state = "playing"
                        self._log_status("[STATE] Transition to playing")
                elif self.game.game_state == "startup":
                    # Auto-advance after logo to prep for web-only users
                    if self.game.current_time - self.game.startup_start_time > 2500:
                        self.game.game_state = "game_prep"
                        self._log_status("[STATE] Transition to game_prep")
                
                # Render frame on all backends
                self.screen.render_frame(self.game, self.game.game_state)
                
                # Broadcast to web clients
                if self.enable_web:
                    self.broadcast_game_state()
                    self.broadcast_draw_commands()
                
                # Clear web backend commands for next frame
                if self.web_backend:
                    self.web_backend.clear_commands()
        
        except KeyboardInterrupt:
            self._log_status("\nShutting down...")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        if self.pygame_backend:
            self.pygame_backend.shutdown()
        
        if self.web_process:
            self.web_process.terminate()
            self.web_process.join(timeout=2)
        if self.status_sock:
            try:
                self.status_sock.close()
            except Exception:
                pass

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="BomberMarv - Dual Rendering Game")
    parser.add_argument("--pygame-only", action="store_true", help="Enable only pygame rendering")
    parser.add_argument("--web-only", action="store_true", help="Enable only web rendering")
    parser.add_argument("--no-pygame", action="store_true", help="Disable pygame rendering")
    parser.add_argument("--no-web", action="store_true", help="Disable web rendering")
    parser.add_argument("--no-auto-setup", action="store_true", help="Disable automatic web client setup")
    parser.add_argument("--setup-only", action="store_true", help="Only set up web client, don't run game")
    
    args = parser.parse_args()
    
    # Handle setup-only mode
    if args.setup_only:
        print("[START] Setting up BomberMarv web client...")
        manager = GameManager(enable_pygame=False, enable_web=False, auto_setup=False)
        success = manager.setup_web_client()
        if success:
            print("[OK] Setup complete! Run without --setup-only to start the game.")
        else:
            print("[FAIL] Setup failed!")
            sys.exit(1)
        return

    # Determine which backends to enable
    enable_pygame = True
    enable_web = True
    auto_setup = not args.no_auto_setup
    
    if args.pygame_only:
        enable_web = False
    elif args.web_only:
        enable_pygame = False
    elif args.no_pygame:
        enable_pygame = False
    elif args.no_web:
        enable_web = False
    
    if not enable_pygame and not enable_web:
        print("Error: At least one rendering backend must be enabled")
        sys.exit(1)
    
    # Start the game
    game_manager = GameManager(enable_pygame, enable_web, auto_setup)
    game_manager.run()

if __name__ == "__main__":
    main()
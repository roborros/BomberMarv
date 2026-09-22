import subprocess
import time
import os
import signal
import sys
import threading
import re
import psutil
import socket
import shutil

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def detect_lan_ip():
    """Best-effort local LAN IP detection for client URL output."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        host = socket.gethostname()
        ip = socket.gethostbyname(host)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"

def stream_reader(process, prefix):
    """Reads output from a subprocess, strips ANSI codes, and prints it with a prefix."""
    for line in iter(process.stdout.readline, ''):
        # Strip ANSI escape codes
        clean_line = ansi_escape.sub('', line)
        print(f"[{prefix}] {clean_line.strip()}")
    print(f"[{prefix}] Stream ended")

def kill_processes_on_ports(ports):
    """Kill any processes listening on the given TCP ports."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port in ports:
                    print(f"Cleaning up port {conn.laddr.port} (PID {proc.pid}: {proc.info['name']})")
                    proc.kill()
                    break
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

def cleanup_previous_instances():
    """Finds and kills all previous instances of the game components."""
    print("Cleaning up previous instances...")
    
    # 1. Kill by port
    target_ports = {8080, 8765, 5173}
    kill_processes_on_ports(target_ports)
    
    # 2. Kill by name/cmdline (redundancy)
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = " ".join(proc.info.get('cmdline') or [])
            name = proc.info.get('name', '').lower()
            
            # Kill previous pyBomberMarv or ws_stream_server
            if 'python' in name and ('pyBomberMarv.py' in cmdline or 'ws_stream_server.py' in cmdline):
                if proc.pid != os.getpid(): # Don't kill self
                    print(f"Killing previous backend process: PID {proc.pid}")
                    proc.kill()
            
            # Kill Bun/Vite frontend processes
            if 'bun' in name or 'node' in name:
                if 'vite' in cmdline or 'web_client' in cmdline:
                    print(f"Killing previous frontend process: PID {proc.pid}")
                    proc.kill()
                    
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    
    # Give the OS a moment to free up resources
    time.sleep(0.5)

def main():
    print("Starting BomberMarv Ecosystem...")

    # Cleanup first
    cleanup_previous_instances()

    # Define paths
    root_dir = os.path.dirname(os.path.abspath(__file__))
    web_client_dir = os.path.join(root_dir, 'web_client')

    processes = []

    try:
        # Start Python Backend
        print("Launching Python Backend...")
        # Unbuffered output for real-time logging
        backend_env = os.environ.copy()
        backend_env["PYTHONUNBUFFERED"] = "1"
        backend_env.setdefault("BM_RTC_ENABLED", "1")
        backend_env.setdefault("BM_RTC_FORCE_WS", "0")
        backend_env.setdefault("BM_STRICT_INPUT_MODE", "0")
        backend_env.setdefault("BM_INPUT_LEAD_TICKS", "1")
        print(
            f"RTC flags: BM_RTC_ENABLED={backend_env['BM_RTC_ENABLED']} "
            f"BM_RTC_FORCE_WS={backend_env['BM_RTC_FORCE_WS']}"
        )
        print(
            f"Input flags: BM_STRICT_INPUT_MODE={backend_env['BM_STRICT_INPUT_MODE']} "
            f"BM_INPUT_LEAD_TICKS={backend_env['BM_INPUT_LEAD_TICKS']}"
        )
        
        backend_process = subprocess.Popen(
            [sys.executable, 'pyBomberMarv.py'],
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=backend_env
        )
        processes.append(('Backend', backend_process))
        
        # Start logging thread for backend
        threading.Thread(target=stream_reader, args=(backend_process, "BACKEND"), daemon=True).start()

        # Start Bun Frontend
        print("Launching Bun Frontend...")
        # bun executable path - assuming it's in path or finding it
        # User has bun in C:\Users\mbrab\.bun\bin\bun.exe, let's try 'bun' first if in path, else specific
        # The user was running bun from path in previous steps so 'bun' should work if env vars are propagated, 
        # but earlier it wasn't. Let's use the explicit path if available, or just 'bun' and hope.
        # Actually, let's try to detect bun.
        bun_cmd = 'bun'
        # Check if bun is in path
        if shutil.which("bun") is None:
             # Try default location
             user_profile = os.environ.get('USERPROFILE', '')
             expected_bun = os.path.join(user_profile, '.bun', 'bin', 'bun.exe')
             if os.path.exists(expected_bun):
                 bun_cmd = expected_bun
        
        # Prepare environment for frontend
        frontend_env = os.environ.copy()
        frontend_env["NO_COLOR"] = "1"
        frontend_env["FORCE_COLOR"] = "0"
        
        frontend_process = subprocess.Popen(
            [bun_cmd, 'run', 'dev', '--', '--host'],
            cwd=web_client_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=frontend_env
        )
        processes.append(('Frontend', frontend_process))
        
        # Start logging thread for frontend
        threading.Thread(target=stream_reader, args=(frontend_process, "FRONTEND"), daemon=True).start()

        print("All services started. Press Ctrl+C to stop.")
        try:
            from bm_paths import list_lan_ips
            lan_ips = list_lan_ips()
        except Exception:
            lan_ips = [detect_lan_ip()]
        print(f"Client URL (this PC): http://127.0.0.1:5173")
        if lan_ips:
            for ip in lan_ips:
                print(f"Client URL (LAN): http://{ip}:5173")
        else:
            print("Client URL (LAN): not detected")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            # Check if processes are still alive
            if backend_process.poll() is not None:
                print("Backend process ended unexpectedly.")
                break
            if frontend_process.poll() is not None:
                print("Frontend process ended unexpectedly.")
                break

    except KeyboardInterrupt:
        print("\nStopping services...")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                print(f"Terminating {name}...")
                proc.terminate()
                # Windows terminate might not close the tree if shell=True for frontend
                # But bun run dev usually spawns vite.
                # Try to kill forcefully if needed or taskkill
                try:
                    # On Windows, terminate() sends generic sigterm? 
                    # For shell=True, it kills the shell, not necessarily the child.
                    # We might need taskkill /T /F /PID
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except:
                    pass
        
        print("Shutdown complete.")

if __name__ == "__main__":
    main()

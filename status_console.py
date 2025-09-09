import socket
import socketserver
import threading
import sys
import time

HOST = "127.0.0.1"
PORT = 8770

class LogHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            peer = f"{self.client_address[0]}:{self.client_address[1]}"
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                for line in data.decode(errors='replace').splitlines():
                    ts = time.strftime("%H:%M:%S")
                    print(f"[{ts}] {line}")
        except Exception:
            pass

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    print("=== BomberMarv Status Console ===")
    print(f"Listening on {HOST}:{PORT}...")
    with ThreadedTCPServer((HOST, PORT), LogHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Shutting down status console...")

if __name__ == "__main__":
    main()


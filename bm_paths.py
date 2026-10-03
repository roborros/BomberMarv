"""Resolve asset and log paths for script runs and the frozen Windows build."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> str:
    """Directory that contains img/, sounds/, and bundled web files."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str:
    return os.path.join(app_root(), *parts)


def user_data_dir() -> str:
    folder = os.path.join(os.environ.get("LOCALAPPDATA") or app_root(), "BomberMarv")
    os.makedirs(folder, exist_ok=True)
    return folder


def user_log_path(name: str = "ws_server.log") -> str:
    """Rotating WS logs for the packaged exe; script runs still use the cwd file."""
    return os.path.join(user_data_dir(), name)


def user_settings_path() -> str:
    override = os.environ.get("BOMBERMARV_SETTINGS")
    if override:
        return override
    return os.path.join(user_data_dir(), "settings.json")


def find_client_static_dir() -> str | None:
    candidates = (
        resource_path("web_client_dist"),
        resource_path("web_client", "dist"),
    )
    for path in candidates:
        if os.path.isfile(os.path.join(path, "index.html")):
            return path
    return None


def _is_usable_lan_ip(ip: str) -> bool:
    if not ip or ":" in ip:
        return False
    if ip.startswith("127.") or ip.startswith("169.254."):
        return False
    return True


def _is_ipv4_family(family) -> bool:
    if family == socket.AF_INET:
        return True
    return getattr(family, "name", "") == "AF_INET"


_lan_lock = threading.Lock()
_lan_ips: list[str] = []
_lan_probed_at = 0.0
_lan_refreshing = False
_LAN_REFRESH_S = 30.0


def _probe_lan_ips() -> list[str]:
    """IPv4 addresses other PCs on the LAN can use. Loopback is omitted.

    This may talk to the OS network stack. Call it from startup or a background
    thread, never from the lobby frame that also pumps the window.
    """
    found: list[str] = []

    def _add(ip: str) -> None:
        if _is_usable_lan_ip(ip) and ip not in found:
            found.append(ip)

    try:
        import psutil

        for _name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if _is_ipv4_family(getattr(addr, "family", None)):
                    _add(getattr(addr, "address", "") or "")
    except Exception:
        pass
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.4)
        sock.connect(("8.8.8.8", 80))
        _add(sock.getsockname()[0])
    except Exception:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return found


def _remember_lan_ips(ips: list[str]) -> None:
    global _lan_ips, _lan_probed_at
    with _lan_lock:
        _lan_ips = list(ips)
        _lan_probed_at = time.monotonic()


def _schedule_lan_refresh() -> None:
    global _lan_refreshing
    with _lan_lock:
        if _lan_refreshing:
            return
        _lan_refreshing = True

    def _run() -> None:
        global _lan_refreshing
        try:
            _remember_lan_ips(_probe_lan_ips())
        finally:
            with _lan_lock:
                _lan_refreshing = False

    threading.Thread(target=_run, name="bombermarv-lan-ip", daemon=True).start()


def list_lan_ips() -> list[str]:
    """Blocking LAN address probe. Startup and tests use this."""
    ips = _probe_lan_ips()
    _remember_lan_ips(ips)
    return ips


def cached_lan_ips() -> list[str]:
    """Last known LAN addresses. Never blocks; refreshes in the background."""
    with _lan_lock:
        ips = list(_lan_ips)
        probed_at = _lan_probed_at
    age = None if probed_at <= 0 else time.monotonic() - probed_at
    if age is None or age >= _LAN_REFRESH_S:
        _schedule_lan_refresh()
    return ips


def detect_lan_ip() -> str:
    ips = list_lan_ips()
    return ips[0] if ips else "127.0.0.1"


def http_join_port() -> int:
    raw = os.environ.get("BM_HTTP_PORT", "8080")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 8080


def lan_join_label(http_port: int | None = None) -> str:
    """Address guests type in a browser on the same network."""
    port = http_join_port() if http_port is None else int(http_port)
    return f"http://{detect_lan_ip()}:{port}"


def cached_lan_join_label(http_port: int | None = None) -> str:
    """Join address for the lobby frame. Does not probe the network."""
    port = http_join_port() if http_port is None else int(http_port)
    ips = cached_lan_ips()
    ip = ips[0] if ips else "…"
    return f"http://{ip}:{port}"


def print_join_urls(http_port: int = 8080, ws_port: int = 8765) -> None:
    lan_ips = list_lan_ips()
    print("", flush=True)
    print("BomberMarv join links", flush=True)
    print(f"  This PC:  http://127.0.0.1:{http_port}", flush=True)
    if lan_ips:
        for index, ip in enumerate(lan_ips):
            label = "LAN:     " if index == 0 else "         "
            print(f"  {label} http://{ip}:{http_port}", flush=True)
        print(f"  WS LAN:   ws://{lan_ips[0]}:{ws_port}", flush=True)
    else:
        print("  LAN:      not detected — other PCs cannot join until this machine has a LAN address", flush=True)
    print("", flush=True)

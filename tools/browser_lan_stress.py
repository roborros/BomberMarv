"""Six Chrome windows against a live host, with LAN/WAN delay and client-side bots.

Each browser logs in, then plays from the snapshots it receives: it walks open
cells and plants bombs. That input goes through the delayed websocket, so the
host simulates real movement, bombs, and blasts instead of an idle lobby.

WebRTC is disabled in these pages. Chrome's network throttle does not apply to
it, and the delay proxy only sits on the websocket.

Set BM_STRESS_PLAY_SECONDS to shorten a run. Default is 70.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil
import websockets

ROOT = Path(__file__).resolve().parents[1]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
CLIENT_URL = "http://127.0.0.1:5173/"
PLAY_SECONDS = max(5, int(os.environ.get("BM_STRESS_PLAY_SECONDS", "70") or 70))
PROXY_PORT = 8876
DEBUG_PORTS = list(range(9331, 9337))

# One-way delay seconds, and max bytes/s from the host toward that browser.
PROFILES = [
    ("LanA", 0.004, 8_000_000),
    ("LanB", 0.006, 8_000_000),
    ("LanC", 0.010, 4_000_000),
    ("WanA", 0.025, 800_000),
    ("WanB", 0.045, 300_000),
    ("WanC", 0.080, 80_000),
]


def log(message: str) -> None:
    print(message, flush=True)


def http_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def wait_tcp(port: int, timeout: float = 40.0) -> None:
    import socket

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except Exception as exc:
            last = exc
            time.sleep(0.2)
    raise TimeoutError(f"port {port} not accepting: {last}")


def wait_http(url: str, timeout: float = 40.0, as_json: bool = False) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if as_json:
                http_json(url, timeout=1.5)
            else:
                with urllib.request.urlopen(url, timeout=1.5) as response:
                    if response.status >= 400:
                        raise RuntimeError(f"status {response.status}")
            return
        except Exception as exc:
            last = exc
            time.sleep(0.25)
    raise TimeoutError(f"{url} not ready: {last}")


def host_pids() -> list[int]:
    found = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "pyBomberMarv.py" in cmd:
                found.append(int(proc.info["pid"]))
        except (psutil.Error, TypeError):
            continue
    return found


def host_window():
    user32 = __import__("ctypes").windll.user32
    return user32.FindWindowW(None, "BomberMarv")


def focus_host_and_start() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    hwnd = 0
    deadline = time.time() + 8
    while time.time() < deadline and not hwnd:
        hwnd = host_window()
        if not hwnd:
            time.sleep(0.2)
    if not hwnd:
        return "window-missing"
    user32.ShowWindow(hwnd, 9)
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current = kernel32.GetCurrentThreadId()
    if fg_thread:
        user32.AttachThreadInput(current, fg_thread, True)
    if target_thread:
        user32.AttachThreadInput(current, target_thread, True)
    user32.BringWindowToTop(hwnd)
    focused = bool(user32.SetForegroundWindow(hwnd))
    if fg_thread:
        user32.AttachThreadInput(current, fg_thread, False)
    if target_thread:
        user32.AttachThreadInput(current, target_thread, False)
    time.sleep(0.3)

    # SDL ignores virtual-key injection unless the scancode is set.
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL

    def tap(vk: int) -> int:
        scan = user32.MapVirtualKeyW(vk, 0)
        down_lparam = 1 | (scan << 16)
        up_lparam = down_lparam | (1 << 30) | (1 << 31)
        posted = int(bool(user32.PostMessageW(hwnd, 0x0100, vk, down_lparam)))
        time.sleep(0.06)
        posted += int(bool(user32.PostMessageW(hwnd, 0x0101, vk, up_lparam)))
        time.sleep(0.12)
        return posted

    # Tab moves from the roster to Start Game. Enter confirms.
    first = tap(0x09)
    second = tap(0x0D)
    front = user32.GetForegroundWindow()
    return f"keys-sent hwnd={hwnd} focused={focused} front_is_game={front == hwnd} send={first},{second}"


def start_host(log_path: Path, force_ws: bool) -> subprocess.Popen:
    env = os.environ.copy()
    env.pop("SDL_VIDEODRIVER", None)
    env["PYTHONUNBUFFERED"] = "1"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["BM_RTC_ENABLED"] = "1"
    env["BM_RTC_FORCE_WS"] = "1" if force_ws else "0"
    handle = log_path.open("w", encoding="utf-8", errors="replace")
    return subprocess.Popen(
        [sys.executable, "run_all.py"],
        cwd=str(ROOT),
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
    )


def stop_process_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        for child in children:
            child.kill()
        parent.kill()
    except psutil.Error:
        proc.kill()


def last_net_line(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if "[NET]" in line]
    return lines[-1] if lines else ""


def host_died(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return "Backend process ended unexpectedly" in text


WS_REWRITE = r"""
(() => {
  const Orig = window.WebSocket;
  const CELL = 100;
  const bot = {
    clientId: null,
    playerId: null,
    state: null,
    seq: -1,
    dir: [1, 0],
    sends: 0,
    plantedUntil: 0,
  };

  function publishBot() {
    const state = bot.state;
    window.__bmBot = {
      sends: bot.sends,
      playerId: bot.playerId,
      state: state && state.state,
      bombs: state && state.bombs ? state.bombs.length : 0,
      explosions: state && state.explosions ? state.explosions.length : 0,
    };
  }

  function applyPlayerDelta(base, delta) {
    if (Array.isArray(delta.players)) return delta.players.map((player) => Object.assign({}, player));
    let players = (base || []).map((player) => Object.assign({}, player));
    const removed = new Set(delta.player_removed || []);
    players = players.filter((player) => !removed.has(player.id));
    const byId = {};
    players.forEach((player, index) => { byId[player.id] = index; });
    for (const patch of delta.player_patches || []) {
      const index = byId[patch.id];
      if (index == null) {
        players.push(Object.assign({}, patch));
        byId[patch.id] = players.length - 1;
      } else {
        players[index] = Object.assign({}, players[index], patch);
      }
    }
    return players;
  }

  function applyBoardPatches(board, patches) {
    const next = (board || []).map((row) => row.slice());
    for (const item of patches || []) {
      if (!item || item.length < 3) continue;
      const x = item[0];
      const y = item[1];
      if (next[y] && x >= 0 && x < next[y].length) next[y][x] = item[2];
    }
    return next;
  }

  function applyDelta(base, delta) {
    const merged = Object.assign({}, base);
    Object.keys(delta || {}).forEach((key) => {
      if (key === 'player_patches' || key === 'player_removed' || key === 'board_patches' || key === 'players' || key === 'board') return;
      merged[key] = delta[key];
    });
    if (delta && (delta.players || delta.player_patches || delta.player_removed)) {
      merged.players = applyPlayerDelta(base.players, delta);
    }
    if (delta && delta.board) merged.board = delta.board;
    else if (delta && delta.board_patches) merged.board = applyBoardPatches(base.board, delta.board_patches);
    return merged;
  }

  function ingest(raw) {
    let text = raw;
    if (raw instanceof ArrayBuffer) text = new TextDecoder().decode(raw);
    if (typeof text !== 'string') return;
    let msg;
    try { msg = JSON.parse(text); } catch (e) { return; }
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'client_id') bot.clientId = msg.client_id;
    if (msg.type === 'registration_confirmed') {
      bot.playerId = msg.slot;
      if (msg.client_id != null) bot.clientId = msg.client_id;
    }
    if (msg.type === 'gamestate' && msg.data) {
      bot.state = msg.data;
      bot.seq = msg.seq;
    } else if (msg.type === 'gamestate_delta' && bot.state && msg.base_seq === bot.seq && msg.delta) {
      bot.state = applyDelta(bot.state, msg.delta);
      bot.seq = msg.seq;
    }
    publishBot();
  }

  function emptyKeys() {
    return { up: 0, down: 0, left: 0, right: 0, bomb: 0 };
  }

  function keysFromStep(dx, dy, bomb) {
    return {
      up: dy < 0 ? 1 : 0,
      down: dy > 0 ? 1 : 0,
      left: dx < 0 ? 1 : 0,
      right: dx > 0 ? 1 : 0,
      bomb: bomb ? 1 : 0,
    };
  }

  function chooseKeys() {
    const state = bot.state;
    if (!state || (state.state !== 'playing' && state.state !== 'boss_fight')) return emptyKeys();
    const me = (state.players || []).find((player) => player.id === bot.playerId);
    if (!me || me.alive === false) return emptyKeys();
    const board = state.board || [];
    const cx = Math.floor(me.x / CELL);
    const cy = Math.floor(me.y / CELL);
    const bombs = new Set((state.bombs || []).map((bomb) => bomb.x + ',' + bomb.y));
    const flames = new Set();
    (state.explosions || []).forEach((explosion) => {
      (explosion.cells || []).forEach((cell) => {
        if (cell && cell.length >= 2) flames.add(cell[0] + ',' + cell[1]);
      });
    });
    const open = [];
    [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach((step) => {
      const x = cx + step[0];
      const y = cy + step[1];
      const row = board[y];
      if (!row || row[x] !== 0) return;
      const id = x + ',' + y;
      open.push({ step, flame: flames.has(id), bomb: bombs.has(id) });
    });
    const safe = open.filter((choice) => !choice.flame && !choice.bomb);
    const flee = open.filter((choice) => !choice.flame);
    const pool = safe.length ? safe : flee;
    let best = null;
    pool.forEach((choice) => {
      let score = 0;
      if (choice.step[0] === bot.dir[0] && choice.step[1] === bot.dir[1]) score += 3;
      if (choice.step[0] === -bot.dir[0] && choice.step[1] === -bot.dir[1]) score -= 2;
      if (choice.bomb) score -= 4;
      if (best == null || score > best.score) best = { score, step: choice.step };
    });
    const here = cx + ',' + cy;
    const softBeside = [[1, 0], [-1, 0], [0, 1], [0, -1]].some((step) => {
      const row = board[cy + step[1]];
      return row && row[cx + step[0]] === 2;
    });
    const now = Date.now();
    const plant = softBeside && safe.length > 0 && !bombs.has(here) && !flames.has(here) && now >= bot.plantedUntil;
    if (plant) bot.plantedUntil = now + 1800;
    if (!best) return keysFromStep(0, 0, plant);
    bot.dir = best.step;
    return keysFromStep(best.step[0], best.step[1], plant);
  }

  function sendDrive() {
    const sock = window.__bmSocket;
    if (!sock || sock.readyState !== 1 || bot.playerId == null || bot.clientId == null) return;
    const keys = chooseKeys();
    const tick = bot.state && typeof bot.state._sim_tick === 'number' ? bot.state._sim_tick : bot.sends;
    sock.send(JSON.stringify({
      type: 'game_input',
      protocol: 2,
      tick_id: tick,
      input: [bot.clientId, bot.playerId, keys.up, keys.down, keys.left, keys.right, keys.bomb],
      input_frame: {
        player_id: bot.playerId,
        up: keys.up,
        down: keys.down,
        left: keys.left,
        right: keys.right,
        bomb: keys.bomb,
      },
      client_timestamp: Date.now(),
    }));
    bot.sends += 1;
    publishBot();
  }

  if (!window.__bmDriveTimer) {
    window.__bmDriveTimer = setInterval(sendDrive, 120);
  }

  function Wrapped(url, protocols) {
    try {
      const parsed = new URL(url, window.location.href);
      if (parsed.port === '8765') {
        parsed.port = 'PORT';
        url = parsed.toString();
      }
    } catch (e) {}
    const sock = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
    window.__bmSocket = sock;
    sock.addEventListener('open', () => { window.__bmWs = 'open'; });
    sock.addEventListener('close', (ev) => { window.__bmWs = 'close:' + ev.code; });
    sock.addEventListener('error', () => { window.__bmWs = 'error'; });
    sock.addEventListener('message', (ev) => ingest(ev.data));
    const origSend = sock.send.bind(sock);
    sock.send = (data) => {
      try { window.__bmLastSend = String(data).slice(0, 180); } catch (e) {}
      return origSend(data);
    };
    return sock;
  }
  Wrapped.prototype = Orig.prototype;
  window.WebSocket = Wrapped;
  window.RTCPeerConnection = undefined;
})();
""".replace("PORT", str(PROXY_PORT))


class Browser:
    def __init__(self, name: str, port: int, work: Path):
        self.name = name
        self.port = port
        self.work = work
        self.proc: subprocess.Popen | None = None
        self.ws = None
        self.seq = 0
        self.notes = []

    def launch(self) -> None:
        if self.work.exists():
            shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True, exist_ok=True)
        index = DEBUG_PORTS.index(self.port)
        col = index % 3
        row = index // 3
        cmd = [
            str(CHROME),
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.work}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            "--mute-audio",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--autoplay-policy=no-user-gesture-required",
            "--window-size=500,400",
            f"--window-position={40 + col * 520},{40 + row * 430}",
            "about:blank",
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            parent = psutil.Process(self.proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.Error:
            try:
                self.proc.kill()
            except Exception:
                pass

    async def connect(self) -> None:
        deadline = time.time() + 20
        page = None
        while time.time() < deadline:
            try:
                pages = http_json(f"http://127.0.0.1:{self.port}/json")
                page = next((item for item in pages if item.get("type") == "page"), None)
                if page and page.get("webSocketDebuggerUrl"):
                    break
            except Exception:
                page = None
            await asyncio.sleep(0.2)
        if not page:
            raise TimeoutError(f"{self.name} debugger never came up")
        self.ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=8_000_000)
        await self.call("Page.enable")
        await self.call("Page.addScriptToEvaluateOnNewDocument", {"source": WS_REWRITE})
        await self.call("Page.navigate", {"url": CLIENT_URL})

    async def call(self, method: str, params: dict | None = None, timeout: float = 15.0):
        self.seq += 1
        await self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=max(0.2, deadline - time.time()))
            data = json.loads(raw)
            if data.get("id") != self.seq:
                continue
            if "error" in data:
                raise RuntimeError(f"{self.name} {method}: {data['error']}")
            return data.get("result")
        raise TimeoutError(f"{self.name} {method} timed out")

    async def js(self, expression: str):
        result = await self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if result and result.get("exceptionDetails"):
            raise RuntimeError(f"{self.name} js: {result['exceptionDetails']}")
        return (result or {}).get("result", {}).get("value")

    async def login(self) -> None:
        deadline = time.time() + 25
        last = ""
        while time.time() < deadline:
            try:
                result = await self.js(
                    """
                    (() => {
                      const box = document.querySelector('#render-toggle');
                      if (box && !box.checked) {
                        box.checked = true;
                        box.dispatchEvent(new Event('change', { bubbles: true }));
                      }
                      const status = document.getElementById('status')?.textContent || '';
                      const lobby = document.getElementById('lobby-status')?.textContent || '';
                      if (status.includes('Playing as') || status.startsWith('Transport:')) return 'in:' + status;
                      const btn = document.querySelector('#login-button');
                      const input = document.querySelector('#player-name');
                      if (input) {
                        input.value = '%s';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                      }
                      if (btn && !btn.disabled) btn.click();
                      const sock = window.__bmSocket;
                      if (sock && sock.readyState === 1) {
                        sock.send(JSON.stringify({ type: 'login', protocol: 2, name: '%s' }));
                      }
                      return [
                        'status=' + status,
                        'lobby=' + lobby,
                        'disabled=' + !!btn?.disabled,
                        'ws=' + (window.__bmWs || 'none'),
                        'ready=' + (sock ? sock.readyState : 'no-socket'),
                        'sent=' + (window.__bmLastSend || '')
                      ].join(' | ');
                    })()
                    """
                    % (self.name, self.name)
                )
            except Exception as exc:
                self.notes.append(f"js:{exc}")
                await asyncio.sleep(0.5)
                continue
            if isinstance(result, str) and result.startswith("in:"):
                self.notes.append(result)
                return
            if result != last:
                self.notes.append(str(result))
                last = str(result)
            await asyncio.sleep(0.6)
        self.notes.append("login-timeout")

    async def snapshot(self) -> dict:
        try:
            payload = await self.js(
                """
                (() => ({
                  debug: document.getElementById('debug-line')?.textContent || '',
                  status: document.getElementById('status')?.textContent || '',
                  bot: window.__bmBot || null,
                }))()
                """
            )
        except Exception as exc:
            return {"name": self.name, "error": str(exc)}
        if not isinstance(payload, dict):
            return {"name": self.name, "error": "snapshot was not an object"}
        return {
            "name": self.name,
            "debug": payload.get("debug") or "",
            "status": payload.get("status") or "",
            "bot": payload.get("bot") or {},
        }

    async def play(self) -> None:
        # Driving starts with the page. This only confirms the bot is installed.
        started = await self.js("!!window.__bmDriveTimer")
        self.notes.append(f"bot-timer={bool(started)}")


_profile_i = 0
_profile_lock = asyncio.Lock()


async def _next_profile():
    global _profile_i
    async with _profile_lock:
        profile = PROFILES[_profile_i % len(PROFILES)]
        _profile_i += 1
        return profile


async def _pipe(src, dst, delay: float, rate: float, limit_rate: bool) -> None:
    try:
        while True:
            data = await src.read(8192)
            if not data:
                break
            if delay:
                await asyncio.sleep(delay)
            dst.write(data)
            await dst.drain()
            if limit_rate and rate > 0:
                await asyncio.sleep(len(data) / rate)
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def _handle_proxy(reader, writer) -> None:
    name, delay, rate = await _next_profile()
    peer = writer.get_extra_info("peername")
    log(f"proxy {name} from {peer} delay={int(delay * 1000)}ms cap={int(rate)}B/s")
    try:
        remote_reader, remote_writer = await asyncio.open_connection("127.0.0.1", 8765)
    except Exception as exc:
        log(f"proxy upstream failed: {exc}")
        writer.close()
        return
    await asyncio.gather(
        _pipe(remote_reader, writer, delay, rate, True),
        _pipe(reader, remote_writer, delay, rate, False),
    )


async def serve_proxy() -> None:
    server = await asyncio.start_server(_handle_proxy, "127.0.0.1", PROXY_PORT)
    async with server:
        await server.serve_forever()


def _is_match(debug: str) -> bool:
    return any(token in debug for token in ("State: playing", "State: get_ready", "State: boss_fight", "State: win"))


async def run_clients(force_ws: bool) -> list[Browser]:
    work_root = ROOT / "tools" / "_lan_stress_profiles"
    browsers = [
        Browser(name, port, work_root / name)
        for (name, _delay, _rate), port in zip(PROFILES, DEBUG_PORTS)
    ]
    for browser in browsers:
        browser.launch()
    await asyncio.sleep(1.0)
    await asyncio.gather(*(browser.connect() for browser in browsers))
    await asyncio.gather(*(browser.login() for browser in browsers))
    return browsers


def metric_slice() -> dict:
    try:
        data = http_json("http://127.0.0.1:8080/metrics", timeout=2.0)
    except Exception as exc:
        return {"error": str(exc)}
    keys = (
        "broadcast_congested_skips",
        "broadcast_frames",
        "broadcast_frames_ws",
        "broadcast_frames_rtc",
        "broadcast_payload_budget_exceeded",
        "broadcast_bytes",
    )
    return {key: data.get(key) for key in keys}


def status_slice() -> dict:
    try:
        data = http_json("http://127.0.0.1:8080/status", timeout=2.0)
    except Exception as exc:
        return {"error": str(exc)}
    clients = data.get("clients") or {}
    transports = {}
    seats = []
    names = []
    for client in clients.values():
        if not isinstance(client, dict):
            continue
        transports[client.get("transport_active", "?")] = transports.get(client.get("transport_active", "?"), 0) + 1
        if client.get("registered"):
            seats.append(client.get("slot"))
            names.append(client.get("display_name"))
    return {
        "transports": transports,
        "seats": sorted(seat for seat in seats if seat is not None),
        "names": names,
        "clients": len(clients),
    }


async def play_and_watch(browsers: list[Browser], log_path: Path) -> dict:
    samples = []
    names = set(status_slice().get("names") or [])
    ours = [browser.name for browser in browsers if browser.name in names]
    log(f"logged-in test browsers: {ours} all={sorted(names)}")
    if len(ours) < 4:
        playing = False
        log("not enough browsers logged in to start a match")
        deadline = time.time() + 5
        while time.time() < deadline:
            await asyncio.sleep(5)
        return {
            "samples": [],
            "died": (not bool(host_pids())) or host_died(log_path),
            "reached_match": False,
            "logins": {browser.name: browser.notes for browser in browsers},
        }
    ready_deadline = time.time() + 20
    while time.time() < ready_deadline:
        states = await asyncio.gather(*(browser.snapshot() for browser in browsers))
        if any("State: game_prep" in item.get("debug", "") or _is_match(item.get("debug", "")) for item in states):
            break
        await asyncio.sleep(0.5)
    started = focus_host_and_start()
    log(f"host start keys: {started}")
    await asyncio.sleep(1.5)
    states = await asyncio.gather(*(browser.snapshot() for browser in browsers))
    playing = any(_is_match(item.get("debug", "")) for item in states)
    if not playing:
        started = focus_host_and_start()
        log(f"host start keys retry: {started}")
        await asyncio.sleep(2.0)
        states = await asyncio.gather(*(browser.snapshot() for browser in browsers))
        playing = any(_is_match(item.get("debug", "")) for item in states)
    log(f"match visible={playing} states={[(item.get('name'), (item.get('debug') or '')[:48]) for item in states]}")
    if playing:
        await asyncio.gather(*(browser.play() for browser in browsers))
    deadline = time.time() + (PLAY_SECONDS if playing else 8)
    while time.time() < deadline:
        await asyncio.sleep(5)
        alive = bool(host_pids()) and not host_died(log_path)
        snap = {
            "t": round(PLAY_SECONDS - (deadline - time.time()), 1),
            "alive": alive,
            "metrics": metric_slice(),
            "status": status_slice(),
            "net": last_net_line(log_path),
        }
        try:
            views = await asyncio.gather(*(browser.snapshot() for browser in browsers))
        except Exception as exc:
            views = [{"error": str(exc)}]
        snap["views"] = [
            {
                "name": item.get("name"),
                "state": (item.get("debug") or "").split("|")[0].strip(),
                "status": (item.get("status") or "")[:140],
                "bot": item.get("bot") or {},
            }
            for item in views
        ]
        samples.append(snap)
        bots = [item.get("bot") or {} for item in snap["views"]]
        sends = sum(int(bot.get("sends") or 0) for bot in bots)
        bombs = max((int(bot.get("bombs") or 0) for bot in bots), default=0)
        blasts = max((int(bot.get("explosions") or 0) for bot in bots), default=0)
        log(
            f"t={snap['t']}s alive={alive} {snap['status']} congested={snap['metrics'].get('broadcast_congested_skips')} "
            f"bot_sends={sends} bombs={bombs} explosions={blasts} "
            f"states={[item.get('state') for item in snap['views']]}"
        )
        if not alive:
            break
    return {
        "samples": samples,
        "died": (not bool(host_pids())) or host_died(log_path),
        "reached_match": playing,
        "logins": {browser.name: browser.notes for browser in browsers},
    }


async def one_pass(force_ws: bool) -> dict:
    label = "websocket-only" if force_ws else "rtc-allowed"
    log_path = ROOT / "tools" / f"lan_stress_{label}.log"
    log(f"=== pass {label} ===")
    host = start_host(log_path, force_ws)
    browsers: list[Browser] = []
    proxy_task = None
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            if log_path.exists() and "Broadcast loop started" in log_path.read_text(encoding="utf-8", errors="replace"):
                break
            await asyncio.sleep(0.2)
        else:
            raise TimeoutError("websocket server did not start")
        wait_tcp(8765)
        wait_http("http://127.0.0.1:8080/health", as_json=True)
        wait_http("http://127.0.0.1:5173/")
        window_deadline = time.time() + 15
        while time.time() < window_deadline and not host_window():
            await asyncio.sleep(0.2)
        proxy_task = asyncio.create_task(serve_proxy())
        await asyncio.sleep(0.2)
        log(f"host pids {host_pids()} window={host_window()}")
        browsers = await run_clients(force_ws)
        for browser in browsers:
            log(f"login {browser.name}: {browser.notes}")
        result = await play_and_watch(browsers, log_path)
        result["label"] = label
        result["final_net"] = last_net_line(log_path)
        result["host_exit_before_cleanup"] = host.poll()
        return result
    finally:
        for browser in browsers:
            browser.stop()
        if proxy_task is not None:
            proxy_task.cancel()
        await asyncio.sleep(0.5)
        stop_process_tree(host)
        shutil.rmtree(ROOT / "tools" / "_lan_stress_profiles", ignore_errors=True)


async def main() -> None:
    if not CHROME.exists():
        raise SystemExit(f"Chrome not found at {CHROME}")
    first = await one_pass(force_ws=False)
    summary = {"delayed-websocket": {key: first[key] for key in ("died", "reached_match", "logins", "final_net", "label") if key in first}}
    summary["delayed-websocket"]["last"] = (first.get("samples") or [{}])[-1]
    out = ROOT / "tools" / "lan_stress_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

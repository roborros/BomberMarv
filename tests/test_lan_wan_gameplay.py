"""Live LAN/WAN gameplay: two websocket clients, host sim, and state broadcast.

LAN input is applied immediately (no tick schedule). WAN input uses a future
apply_tick plus a one-way delay, which is the same path a high-latency remote
client uses. Both clients must see the same authoritative result.
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
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

from helpers import cell_center, open_board, silence_sounds
from latency_metrics import queue_delay_ms, wall_clock_ms
from net_protocol import PROTOCOL_VERSION, should_buffer_remote_input
from ws_stream_server import decode_server_payload, run_server_with_queue

silence_sounds()


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_http(url: str, timeout=6.0):
    import urllib.request

    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.4) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise TimeoutError(f"HTTP {url} not ready: {last_error}")


def _merge_player_patches(players, patches):
    merged = [dict(player) for player in players or []]
    by_id = {player.get("id"): player for player in merged}
    for patch in patches or []:
        pid = patch.get("id")
        if pid in by_id:
            by_id[pid].update(patch)
        else:
            merged.append(dict(patch))
    return merged


class ClientView:
    def __init__(self):
        self.state = {}
        self.messages = 0
        self.last_sim_tick = None

    def apply(self, msg):
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        if kind == "gamestate":
            data = dict(msg.get("data") or {})
            self.state = data
            self.last_sim_tick = data.get("_sim_tick", msg.get("tick_id"))
            self.messages += 1
            return
        if kind == "gamestate_delta":
            delta = dict(msg.get("delta") or {})
            merged = dict(self.state)
            patches = delta.pop("player_patches", None)
            delta.pop("board_patches", None)
            merged.update(delta)
            if patches:
                merged["players"] = _merge_player_patches(merged.get("players"), patches)
            self.state = merged
            self.last_sim_tick = merged.get("_sim_tick", msg.get("tick_id", self.last_sim_tick))
            self.messages += 1
            return
        if kind == "state_keepalive":
            self.last_sim_tick = msg.get("_sim_tick", self.last_sim_tick)
            self.messages += 1

    def player(self, client_id):
        for player in self.state.get("players") or []:
            owner = player.get("owner_client_id")
            if owner is None:
                continue
            if int(owner) == int(client_id):
                return player
        return None


class LiveHost:
    """Host drain/buffer/simulate/publish loop used in production."""

    def __init__(self, game, input_q, state_q, status_q):
        self.game = game
        self.input_q = input_q
        self.state_q = state_q
        self.status_q = status_q
        self.tick = 0
        self.buffered = 0
        self.applied = 0
        self.pending = {}
        self.queue_delays = []
        self.stop = threading.Event()
        self.play = threading.Event()
        self.lock = threading.Lock()
        self.lan_start_x = 0.0
        self.wan_start_x = 0.0
        self.lan_player = None
        self.wan_player = None
        self.error = None

    def drain_status(self):
        latest = None
        while True:
            try:
                message = self.status_q.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, dict) and message.get("type") == "status":
                latest = message.get("status")
        if isinstance(latest, dict):
            self.game._cached_status = latest
        return latest

    def begin_match(self, status):
        self.game._cached_status = status
        self.game.prep_num_players = 0
        self.game.prep_ai_count = 0
        self.game.create_players()
        remotes = [player for player in self.game.players if not player.is_local and not getattr(player, "is_ai", False)]
        remotes.sort(key=lambda player: int(player.client_player_id))
        if len(remotes) != 2:
            raise RuntimeError(f"expected 2 remote players, got {len(remotes)}")
        self.game.board = open_board(9, 9)
        self.game.grid_width = 9
        self.game.grid_height = 9
        self.game.bombs = []
        self.game.explosions = []
        self.game.powerups = []
        self.lan_player, self.wan_player = remotes
        self.lan_player.pos[:] = cell_center(1, 1)
        self.wan_player.pos[:] = cell_center(7, 1)
        self.lan_player.bomb_capacity = 3
        self.wan_player.bomb_capacity = 3
        self.lan_start_x = float(self.lan_player.pos[0])
        self.wan_start_x = float(self.wan_player.pos[0])
        self.game.starting_player_count = 2
        self.game.game_state = "playing"
        self.game.current_time = 1_000

    def step(self, dt=16):
        with self.lock:
            self.tick += 1
            current = self.tick
        while True:
            try:
                event = self.input_q.get_nowait()
            except queue.Empty:
                break
            if not isinstance(event, dict):
                continue
            received_ts = event.get("ws_received_timestamp")
            if isinstance(received_ts, (int, float)):
                self.queue_delays.append(queue_delay_ms(received_ts, wall_clock_ms()))
            if event.get("type") != "set_input_state":
                continue
            apply_tick_raw = event.get("apply_tick_id")
            apply_tick = int(apply_tick_raw) if isinstance(apply_tick_raw, (int, float)) else None
            if should_buffer_remote_input(apply_tick, current):
                self.pending.setdefault(apply_tick, []).append(event)
                self.buffered += 1
            else:
                self.game.handle_web_key_event(event)
                self.applied += 1
        due = sorted(tick for tick in self.pending if tick <= current)
        for tick in due:
            for event in self.pending.pop(tick):
                self.game.handle_web_key_event(event)
                self.applied += 1
        now_ms = int(self.game.current_time) + dt
        self.game.simulate(dt, now_ms=now_ms)
        payload = self.game.to_dict()
        payload["_sim_tick"] = current
        payload["_host_published_at_ms"] = wall_clock_ms()
        self.state_q.put(payload)

    def run(self):
        try:
            self.play.wait(timeout=12)
            while not self.stop.is_set():
                self.step()
                time.sleep(0.016)
        except Exception as exc:
            self.error = exc


class LanWanGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ws_stream_server as wss

        os.environ["BM_INPUT_LEAD_TICKS"] = "2"
        os.environ["BM_RTC_ENABLED"] = "0"
        cls.ws_port = _free_port()
        cls.http_port = _free_port()
        cls._orig_ws = wss.PORT
        cls._orig_http = wss.HTTP_PORT
        wss.PORT = cls.ws_port
        wss.HTTP_PORT = cls.http_port
        cls.input_q = queue.Queue()
        cls.state_q = queue.Queue()
        cls.status_q = queue.Queue()
        cls._log = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
        cls._log.close()
        cls.thread = threading.Thread(
            target=run_server_with_queue,
            args=(cls.input_q, cls.state_q, cls.status_q, cls._log.name),
            daemon=True,
            name="lan-wan-ws",
        )
        cls.thread.start()
        _wait_http(f"http://127.0.0.1:{cls.http_port}/health")

    @classmethod
    def tearDownClass(cls):
        import ws_stream_server as wss

        wss.PORT = cls._orig_ws
        wss.HTTP_PORT = cls._orig_http
        try:
            os.unlink(cls._log.name)
        except OSError:
            pass

    async def _register(self, ws, slot, name):
        first = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        self.assertEqual(first["type"], "client_id")
        await ws.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION, "encoding": "json"}))
        hello_ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        while hello_ack["type"] != "hello_ack":
            hello_ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        await ws.send(json.dumps({"type": "select_slot", "protocol": PROTOCOL_VERSION, "slot": slot, "name": name}))
        confirmed = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        while confirmed["type"] == "slot_list":
            confirmed = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        self.assertEqual(confirmed["type"], "registration_confirmed")
        return first["client_id"], int(confirmed["player_ids"][0])

    async def _pump(self, ws, view, stop):
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), 0.2)
            except asyncio.TimeoutError:
                continue
            view.apply(decode_server_payload(raw))

    async def _wait_until(self, predicate, timeout=6.0, detail="condition"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.02)
        message = detail() if callable(detail) else detail
        raise TimeoutError(message)

    def _wait_two_registered(self, timeout=6.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = _wait_http(f"http://127.0.0.1:{self.http_port}/status", timeout=1.5)
            clients = last.get("clients") or {}
            registered = [info for info in clients.values() if isinstance(info, dict) and info.get("registered")]
            if len(registered) >= 2:
                return last
            time.sleep(0.05)
        raise TimeoutError(f"did not get two registered clients: {last}")

    def test_two_ws_clients_play_lan_immediate_and_wan_buffered(self):
        import websockets

        from bm_classes import Game

        silence_sounds()
        keys_patch = patch("bm_classes.get_pressed_keys", return_value={})
        keys_patch.start()
        self.addCleanup(keys_patch.stop)

        game = Game()
        host = LiveHost(game, self.input_q, self.state_q, self.status_q)
        host_thread = threading.Thread(target=host.run, daemon=True, name="lan-wan-host")
        host_thread.start()
        self.addCleanup(host.stop.set)

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            stop = threading.Event()
            lan_view = ClientView()
            wan_view = ClientView()
            async with websockets.connect(uri) as lan_ws, websockets.connect(uri) as wan_ws:
                lan_client_id, lan_player_id = await self._register(lan_ws, 1, "LanPad")
                wan_client_id, wan_player_id = await self._register(wan_ws, 2, "WanPad")
                status = self._wait_two_registered()
                host.drain_status()
                host.begin_match(status)
                self.assertEqual(int(host.lan_player.client_id), int(lan_client_id))
                self.assertEqual(int(host.wan_player.client_id), int(wan_client_id))

                lan_pump = asyncio.create_task(self._pump(lan_ws, lan_view, stop))
                wan_pump = asyncio.create_task(self._pump(wan_ws, wan_view, stop))
                await lan_ws.send(json.dumps({"type": "request_keyframe", "protocol": PROTOCOL_VERSION, "seq": 0}))
                await wan_ws.send(json.dumps({"type": "request_keyframe", "protocol": PROTOCOL_VERSION, "seq": 0}))
                host.play.set()
                try:
                    await self._wait_until(
                        lambda: lan_view.player(lan_client_id) and wan_view.player(wan_client_id),
                        detail="both clients did not receive the roster",
                    )
                    lan_start = float(lan_view.player(lan_client_id)["x"])
                    wan_start = float(wan_view.player(wan_client_id)["x"])
                    self.assertAlmostEqual(lan_start, host.lan_start_x, delta=1.0)
                    self.assertAlmostEqual(wan_start, host.wan_start_x, delta=1.0)

                    await asyncio.sleep(0.05)
                    with host.lock:
                        wan_tick = host.tick + 2
                    await wan_ws.send(
                        json.dumps(
                            {
                                "type": "game_input",
                                "protocol": PROTOCOL_VERSION,
                                "tick_id": wan_tick,
                                "input_frame": {
                                    "player_id": wan_player_id,
                                    "up": 0,
                                    "down": 0,
                                    "left": 1,
                                    "right": 0,
                                    "bomb": 0,
                                },
                            }
                        )
                    )
                    await lan_ws.send(
                        json.dumps(
                            {
                                "type": "game_input",
                                "protocol": PROTOCOL_VERSION,
                                "input_frame": {
                                    "player_id": lan_player_id,
                                    "up": 0,
                                    "down": 0,
                                    "left": 0,
                                    "right": 1,
                                    "bomb": 1,
                                },
                            }
                        )
                    )

                    await self._wait_until(
                        lambda: host.buffered >= 1,
                        detail="WAN input was not scheduled onto the future-tick buffer",
                    )
                    self.assertAlmostEqual(float(host.wan_player.pos[0]), host.wan_start_x, delta=0.5)
                    await self._wait_until(
                        lambda: float(host.lan_player.pos[0]) > host.lan_start_x + 8,
                        detail="LAN player did not move after immediate input",
                    )

                    apply_at = wan_tick + 2
                    await self._wait_until(
                        lambda: host.tick >= apply_at and float(host.wan_player.pos[0]) < host.wan_start_x - 8,
                        timeout=8.0,
                        detail="WAN player did not move after buffered apply tick",
                    )
                    await self._wait_until(lambda: len(host.game.bombs) >= 1, detail="LAN hold-to-plant did not drop a bomb")
                    await self._wait_until(
                        lambda: (
                            lan_view.player(wan_client_id)
                            and wan_view.player(lan_client_id)
                            and float(lan_view.player(lan_client_id)["x"]) > lan_start + 8
                            and float(wan_view.player(wan_client_id)["x"]) < wan_start - 8
                            and (lan_view.state.get("bombs") or wan_view.state.get("bombs"))
                        ),
                        detail="clients did not converge on movement and bomb",
                    )
                finally:
                    stop.set()
                    lan_pump.cancel()
                    wan_pump.cancel()
                    await asyncio.gather(lan_pump, wan_pump, return_exceptions=True)

            self.assertGreaterEqual(host.buffered, 1)
            self.assertGreaterEqual(host.applied, 1)
            self.assertGreater(float(host.lan_player.pos[0]), host.lan_start_x)
            self.assertLess(float(host.wan_player.pos[0]), host.wan_start_x)
            self.assertGreaterEqual(len(host.game.bombs), 1)
            self.assertEqual(lan_view.state.get("state"), "playing")
            self.assertEqual(wan_view.state.get("state"), "playing")
            self.assertAlmostEqual(
                float(lan_view.player(lan_client_id)["x"]),
                float(host.lan_player.pos[0]),
                delta=40,
            )
            self.assertAlmostEqual(
                float(wan_view.player(wan_client_id)["x"]),
                float(host.wan_player.pos[0]),
                delta=40,
            )
            if host.queue_delays:
                self.assertGreaterEqual(min(host.queue_delays), 0)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()

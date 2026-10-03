import json
import os
import queue
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from net_protocol import PROTOCOL_VERSION
from ws_stream_server import (
    HTTP_SERVER_VERSION,
    RTC_OUTBOUND_BUFFER_LIMIT,
    WS_OUTBOUND_BUFFER_LIMIT,
    WS_SERVER_VERSION,
    _percentile,
    build_state_delta,
    classify_broadcast_for_client,
    decode_client_payload,
    decode_server_payload,
    encode_gameplay_payload,
    outbound_is_congested,
    run_server_with_queue,
)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_http(url: str, timeout=6.0):
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


class _WriteTransport:
    def __init__(self, size):
        self._size = size

    def get_write_buffer_size(self):
        return self._size


class _Socket:
    def __init__(self, size):
        self.transport = _WriteTransport(size)


class _RtcChannel:
    def __init__(self, amount, ready="open"):
        self.bufferedAmount = amount
        self.readyState = ready


class WsHelperTests(unittest.TestCase):
    def test_outbound_congestion_uses_socket_and_rtc_buffers(self):
        self.assertFalse(outbound_is_congested(_Socket(0), None, "ws"))
        self.assertFalse(outbound_is_congested(_Socket(WS_OUTBOUND_BUFFER_LIMIT), None, "ws"))
        self.assertTrue(outbound_is_congested(_Socket(WS_OUTBOUND_BUFFER_LIMIT + 1), None, "ws"))
        self.assertTrue(outbound_is_congested(_Socket(WS_OUTBOUND_BUFFER_LIMIT - 20), None, "ws", extra_bytes=21))
        self.assertFalse(outbound_is_congested(_Socket(0), None, "ws", extra_bytes=10**7))
        paused = _Socket(0)
        paused.paused = True
        self.assertTrue(outbound_is_congested(paused, None, "ws"))
        self.assertFalse(outbound_is_congested(_Socket(0), _RtcChannel(0), "rtc"))
        self.assertTrue(outbound_is_congested(_Socket(0), _RtcChannel(RTC_OUTBOUND_BUFFER_LIMIT + 1), "rtc"))
        self.assertFalse(outbound_is_congested(_Socket(0), _RtcChannel(0, ready="closed"), "rtc"))
        self.assertTrue(outbound_is_congested(_Socket(WS_OUTBOUND_BUFFER_LIMIT + 1), _RtcChannel(0, ready="closed"), "rtc"))

    def test_percentile_empty_and_order(self):
        self.assertEqual(_percentile([], 50), 0.0)
        self.assertEqual(_percentile([1, 2, 3, 4, 5], 0), 1.0)
        self.assertEqual(_percentile([1, 2, 3, 4, 5], 100), 5.0)
        self.assertEqual(_percentile([10, 20, 30], 50), 20.0)

    def test_build_state_delta_omits_unchanged(self):
        previous = {"time": 1, "state": "playing", "players": [1], "board": [[0]]}
        current = {"time": 2, "state": "playing", "players": [1], "board": [[0]]}
        delta = build_state_delta(previous, current)
        self.assertEqual(delta, {"time": 2})
        self.assertNotIn("players", delta)

    def test_build_state_delta_includes_sim_tick_not_metrics(self):
        previous = {"_sim_tick": 1, "_net_metrics": {"sim_tick": 1}, "time": 1}
        current = {"_sim_tick": 2, "_net_metrics": {"sim_tick": 2, "host_fps_5s": 60}, "time": 1}
        delta = build_state_delta(previous, current)
        self.assertEqual(delta["_sim_tick"], 2)
        self.assertNotIn("_net_metrics", delta)

    def test_classify_broadcast_keepalive_delta_and_keyframe(self):
        base = {"time": 1, "state": "playing", "players": [{"x": 1}], "_sim_tick": 1, "board": [[0]]}
        idle = dict(base)
        idle["time"] = 2
        idle["_sim_tick"] = 2
        payload, kind = classify_broadcast_for_client(
            current_state=idle,
            last_full_state=base,
            current_seq=2,
            last_broadcast_seq=1,
            client_last_seq=1,
            delta_chain_count=0,
            max_delta_chain=8,
            force_keyframe_global=False,
            force_keyframe_client=False,
            keyframe_interval_seq=10,
            server_timestamp=1,
        )
        self.assertEqual(kind, "keepalive")
        self.assertEqual(payload["type"], "state_keepalive")
        moved = dict(idle)
        moved["players"] = [{"x": 9}]
        payload, kind = classify_broadcast_for_client(
            current_state=moved,
            last_full_state=idle,
            current_seq=3,
            last_broadcast_seq=2,
            client_last_seq=2,
            delta_chain_count=0,
            max_delta_chain=8,
            force_keyframe_global=False,
            force_keyframe_client=False,
            keyframe_interval_seq=10,
            server_timestamp=1,
        )
        self.assertEqual(kind, "delta")
        self.assertEqual(payload["delta"]["players"][0]["x"], 9)
        payload, kind = classify_broadcast_for_client(
            current_state=moved,
            last_full_state=idle,
            current_seq=3,
            last_broadcast_seq=2,
            client_last_seq=-1,
            delta_chain_count=0,
            max_delta_chain=8,
            force_keyframe_global=False,
            force_keyframe_client=False,
            keyframe_interval_seq=10,
            server_timestamp=1,
        )
        self.assertEqual(kind, "keyframe")
        self.assertNotIn("_net_metrics", payload["data"])

    def test_classify_broadcast_entity_grain_player_and_board_patches(self):
        base = {
            "time": 1,
            "state": "playing",
            "players": [{"id": 1, "x": 1, "y": 1, "alive": True}],
            "_sim_tick": 1,
            "board": [[0, 0], [0, 0]],
        }
        moved = dict(base)
        moved["time"] = 2
        moved["players"] = [{"id": 1, "x": 9, "y": 1, "alive": True}]
        moved["board"] = [[0, 0], [0, 2]]
        payload, kind = classify_broadcast_for_client(
            current_state=moved,
            last_full_state=base,
            current_seq=3,
            last_broadcast_seq=2,
            client_last_seq=2,
            delta_chain_count=0,
            max_delta_chain=8,
            force_keyframe_global=False,
            force_keyframe_client=False,
            keyframe_interval_seq=10,
            server_timestamp=1,
        )
        self.assertEqual(kind, "delta")
        self.assertEqual(payload["delta"]["player_patches"], [{"id": 1, "x": 9}])
        self.assertEqual(payload["delta"]["board_patches"], [[1, 1, 2]])
        self.assertNotIn("players", payload["delta"])
        self.assertNotIn("board", payload["delta"])

    def test_decode_client_payload_json_and_invalid(self):
        payload = {"type": "ping", "protocol": PROTOCOL_VERSION}
        self.assertEqual(decode_client_payload(json.dumps(payload)), payload)
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            decode_client_payload("{nope")
        with self.assertRaises(ValueError):
            decode_client_payload(b"")

    def test_encode_json_and_optional_msgpack(self):
        payload = {"type": "ping", "protocol": PROTOCOL_VERSION}
        encoded = encode_gameplay_payload(payload, "json")
        self.assertEqual(json.loads(encoded), payload)
        packed = encode_gameplay_payload(payload, "msgpack")
        if isinstance(packed, (bytes, bytearray)):
            import msgpack

            self.assertEqual(msgpack.unpackb(packed, raw=False), payload)
        else:
            self.assertEqual(json.loads(packed), payload)


class WsServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ws_stream_server as wss

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
            name="ws-test-server",
        )
        cls.thread.start()
        _wait_http(f"http://127.0.0.1:{cls.http_port}/health")

    @classmethod
    def tearDownClass(cls):
        import ws_stream_server as wss

        wss.PORT = cls._orig_ws
        wss.HTTP_PORT = cls._orig_http

    def test_health_versions_config_status_metrics(self):
        health = _wait_http(f"http://127.0.0.1:{self.http_port}/health")
        self.assertEqual(health["status"], "ok")
        versions = _wait_http(f"http://127.0.0.1:{self.http_port}/versions")
        self.assertEqual(versions["ws_server"], WS_SERVER_VERSION)
        self.assertEqual(versions["http_server"], HTTP_SERVER_VERSION)
        config = _wait_http(f"http://127.0.0.1:{self.http_port}/config")
        self.assertIn("strict_input_mode", config)
        self.assertIn("input_lead_ticks", config)
        status = _wait_http(f"http://127.0.0.1:{self.http_port}/status")
        self.assertIn("clients", status)
        self.assertIn("slots", status)
        metrics = _wait_http(f"http://127.0.0.1:{self.http_port}/metrics")
        self.assertIn("percentiles", metrics)
        self.assertIn("messages_received", metrics)

    def test_unknown_http_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.http_port}/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_websocket_hello_slots_input_and_state(self):
        import asyncio
        import websockets

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            async with websockets.connect(uri) as ws:
                first = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(first["type"], "client_id")
                self.assertEqual(first["protocol"], PROTOCOL_VERSION)
                client_id = first["client_id"]

                await ws.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION}))
                hello_ack = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(hello_ack["type"], "hello_ack")
                self.assertEqual(hello_ack["server"], "bombermarv")

                await ws.send("not-json")
                err = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(err["type"], "error")

                await ws.send(json.dumps({"type": "unknown", "protocol": PROTOCOL_VERSION}))
                err = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(err["type"], "error")

                await ws.send(json.dumps({"type": "ping", "protocol": PROTOCOL_VERSION}))
                pong = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(pong["type"], "pong")

                await ws.send(json.dumps({"type": "request_slot_list", "protocol": PROTOCOL_VERSION}))
                slots = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(slots["type"], "slot_list")
                self.assertIn("1", slots["slots"])
                self.assertIn("8", slots["slots"])
                self.assertFalse(slots["slots"]["1"])

                await ws.send(json.dumps({"type": "select_slot", "protocol": PROTOCOL_VERSION, "slot": 1, "name": "Tester"}))
                confirmed = json.loads(await asyncio.wait_for(ws.recv(), 3))
                while confirmed["type"] == "slot_list":
                    confirmed = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(confirmed["type"], "registration_confirmed")
                self.assertEqual(confirmed["player_ids"], [confirmed["slot"]])
                player_id = int(confirmed["slot"])

                await ws.send(
                    json.dumps(
                        {
                            "type": "game_input",
                            "protocol": PROTOCOL_VERSION,
                            "tick_id": 5,
                            "input": [client_id, player_id, 1, 0, 0, 0, 0],
                            "input_frame": {"player_id": player_id, "up": 1, "down": 0, "left": 0, "right": 0, "bomb": 0},
                        }
                    )
                )
                ack = json.loads(await asyncio.wait_for(ws.recv(), 3))
                while ack["type"] in ("slot_list",):
                    ack = json.loads(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(ack["type"], "input_ack")

                self.state_q.put(
                    {
                        "time": 1,
                        "state": "playing",
                        "board": [[1, 0], [0, 1]],
                        "players": [],
                        "bombs": [],
                        "explosions": [],
                        "powerups": [],
                        "crushing_walls": {"active": False, "index": 0},
                        "local_player_count": 0,
                        "_sim_tick": 9,
                    }
                )
                deadline = time.time() + 4
                state_msg = None
                while time.time() < deadline:
                    raw = await asyncio.wait_for(ws.recv(), 3)
                    parsed = json.loads(raw)
                    if parsed["type"] == "gamestate":
                        state_msg = parsed
                        break
                self.assertIsNotNone(state_msg)
                self.assertEqual(state_msg["data"]["_sim_tick"], 9)
                self.assertEqual(state_msg["tick_id"], 9)

                await ws.send(json.dumps({"type": "request_keyframe", "protocol": PROTOCOL_VERSION, "seq": 0}))

                joined = None
                deadline = time.time() + 2
                while time.time() < deadline and joined is None:
                    try:
                        item = self.input_q.get_nowait()
                    except queue.Empty:
                        time.sleep(0.02)
                        continue
                    if item.get("type") == "set_input_state":
                        joined = item
                self.assertIsNotNone(joined)
                self.assertEqual(joined["keys"]["up"], 1)

        asyncio.run(scenario())

    async def _login(self, ws, name, message_type="login", slot=None):
        import asyncio

        payload = {"type": message_type, "protocol": PROTOCOL_VERSION, "name": name}
        if slot is not None:
            payload["slot"] = slot
        await ws.send(json.dumps(payload))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 3))
        while msg["type"] == "slot_list":
            msg = json.loads(await asyncio.wait_for(ws.recv(), 3))
        return msg

    def test_same_requested_id_gets_distinct_seats(self):
        import asyncio
        import websockets

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            async with websockets.connect(uri) as first, websockets.connect(uri) as second:
                await asyncio.wait_for(first.recv(), 3)
                await asyncio.wait_for(second.recv(), 3)
                await first.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION}))
                await second.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION}))
                await asyncio.wait_for(first.recv(), 3)
                await asyncio.wait_for(second.recv(), 3)
                first_msg = await self._login(first, "First", message_type="select_slot", slot=6)
                second_msg = await self._login(second, "Second", message_type="select_slot", slot=6)
                self.assertEqual(first_msg["type"], "registration_confirmed")
                self.assertEqual(second_msg["type"], "registration_confirmed")
                self.assertNotEqual(first_msg["player_ids"], second_msg["player_ids"])
                self.assertEqual(first_msg["player_ids"], [first_msg["slot"]])
                self.assertEqual(second_msg["player_ids"], [second_msg["slot"]])

        asyncio.run(scenario())

    def test_login_assigns_unique_ids_and_ignores_guests(self):
        import asyncio
        import websockets

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            async with websockets.connect(uri) as guest:
                await asyncio.wait_for(guest.recv(), 3)
                await guest.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION}))
                await asyncio.wait_for(guest.recv(), 3)
                await guest.send(
                    json.dumps(
                        {
                            "type": "game_input",
                            "protocol": PROTOCOL_VERSION,
                            "input_frame": {"player_id": 1, "up": 1, "down": 0, "left": 0, "right": 0, "bomb": 0},
                        }
                    )
                )
                rejected = json.loads(await asyncio.wait_for(guest.recv(), 3))
                while rejected["type"] == "slot_list":
                    rejected = json.loads(await asyncio.wait_for(guest.recv(), 3))
                self.assertEqual(rejected["type"], "registration_rejected")

                opened = [guest]
                assigned = []
                full = None
                try:
                    for index in range(9):
                        ws = await websockets.connect(uri, close_timeout=0.2)
                        opened.append(ws)
                        await asyncio.wait_for(ws.recv(), 3)
                        await ws.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION}))
                        hello = json.loads(await asyncio.wait_for(ws.recv(), 3))
                        while hello["type"] != "hello_ack":
                            hello = json.loads(await asyncio.wait_for(ws.recv(), 3))
                        msg = await self._login(ws, f"Player{index}")
                        if msg["type"] == "registration_rejected":
                            full = msg
                            break
                        self.assertEqual(msg["type"], "registration_confirmed")
                        assigned.append(int(msg["slot"]))
                        again = await self._login(ws, f"Player{index}")
                        self.assertEqual(again["type"], "registration_confirmed")
                        self.assertEqual(int(again["slot"]), int(msg["slot"]))
                finally:
                    for ws in opened[1:]:
                        await ws.close()
                self.assertIsNotNone(full)
                self.assertIn("full", str(full.get("message", "")).lower())
                self.assertEqual(len(assigned), len(set(assigned)))
                self.assertGreaterEqual(len(assigned), 1)
                self.assertTrue(all(1 <= seat <= 8 for seat in assigned))

        asyncio.run(scenario())

    def _playing_state(self, **overrides):
        state = {
            "time": 1,
            "state": "playing",
            "board": [[1, 0], [0, 1]],
            "players": [{"id": 1, "x": 150, "y": 150, "name": "P", "alive": True}],
            "bombs": [],
            "explosions": [],
            "powerups": [],
            "crushing_walls": {"active": False, "index": 0},
            "local_player_count": 0,
            "_sim_tick": 9,
        }
        state.update(overrides)
        return state

    async def _register(self, ws, slot, name):
        import asyncio

        first = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        self.assertEqual(first["type"], "client_id")
        await ws.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION, "encoding": "json"}))
        hello_ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        while hello_ack["type"] != "hello_ack":
            hello_ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        self.assertIn(hello_ack.get("ws_codec"), ("json", "msgpack"))
        await ws.send(json.dumps({"type": "select_slot", "protocol": PROTOCOL_VERSION, "slot": slot, "name": name}))
        confirmed = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        while confirmed["type"] == "slot_list":
            confirmed = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
        self.assertEqual(confirmed["type"], "registration_confirmed")
        return first["client_id"]

    async def _recv_type(self, ws, wanted, timeout=4.0):
        import asyncio

        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout)
            parsed = decode_server_payload(raw)
            if parsed.get("type") in wanted:
                return parsed
        raise TimeoutError(f"did not receive {wanted}")

    def test_keepalive_metrics_strip_and_delta_after_idle(self):
        import asyncio
        import websockets

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            async with websockets.connect(uri) as ws:
                await self._register(ws, 2, "Keep")
                first = self._playing_state(_net_metrics={"host_fps_5s": 60, "sim_tick": 9})
                self.state_q.put(first)
                state_msg = await self._recv_type(ws, {"gamestate"})
                self.assertEqual(state_msg["type"], "gamestate")
                self.assertNotIn("_net_metrics", state_msg["data"])
                self.assertEqual(state_msg["data"]["_sim_tick"], 9)

                idle = self._playing_state(time=2, _sim_tick=10, _host_published_at_ms=50)
                self.state_q.put(idle)
                keep = await self._recv_type(ws, {"state_keepalive", "gamestate", "gamestate_delta"})
                self.assertEqual(keep["type"], "state_keepalive")
                self.assertEqual(keep["_sim_tick"], 10)
                self.assertEqual(keep["seq"], state_msg["seq"] + 1)

                moved = self._playing_state(
                    time=3,
                    _sim_tick=11,
                    players=[{"id": 1, "x": 180, "y": 150, "name": "P", "alive": True}],
                )
                self.state_q.put(moved)
                delta = await self._recv_type(ws, {"gamestate_delta", "gamestate"})
                self.assertIn(delta["type"], ("gamestate_delta", "gamestate"))
                if delta["type"] == "gamestate_delta":
                    self.assertEqual(delta["base_seq"], keep["seq"])
                    if "player_patches" in delta["delta"]:
                        self.assertEqual(delta["delta"]["player_patches"][0]["x"], 180)
                    else:
                        self.assertEqual(delta["delta"]["players"][0]["x"], 180)
                    self.assertNotIn("_net_metrics", delta["delta"])

                hud_state = self._playing_state(
                    time=4,
                    _sim_tick=12,
                    players=[{"id": 1, "x": 190, "y": 150, "name": "P", "alive": True}],
                    _hud_metrics={"clock": "unix_ms", "host_fps_5s": 58.0, "input_queue_delay_p95_ms": 3.2},
                )
                self.state_q.put(hud_state)
                metrics_msg = await self._recv_type(ws, {"net_metrics"})
                self.assertEqual(metrics_msg["type"], "net_metrics")
                self.assertEqual(metrics_msg["clock"], "unix_ms")
                self.assertEqual(metrics_msg["metrics"]["host_fps_5s"], 58.0)

        asyncio.run(scenario())

    def test_msgpack_ws_gameplay_and_json_control(self):
        import asyncio
        import websockets

        try:
            import msgpack
        except Exception:
            self.skipTest("msgpack is not installed")

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            async with websockets.connect(uri) as ws:
                first = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                client_id = first["client_id"]
                await ws.send(json.dumps({"type": "hello", "protocol": PROTOCOL_VERSION, "encoding": "msgpack"}))
                hello_ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                while hello_ack["type"] != "hello_ack":
                    hello_ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(hello_ack["ws_codec"], "msgpack")
                self.assertIsInstance(json.dumps(hello_ack), str)

                await ws.send(json.dumps({"type": "ping", "protocol": PROTOCOL_VERSION}))
                pong = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(pong["type"], "pong")

                await ws.send(json.dumps({"type": "select_slot", "protocol": PROTOCOL_VERSION, "slot": 3, "name": "Pack"}))
                confirmed = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                while confirmed["type"] == "slot_list":
                    confirmed = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(confirmed["type"], "registration_confirmed")
                player_id = int(confirmed["player_ids"][0])

                packed_input = msgpack.packb(
                    {
                        "type": "game_input",
                        "protocol": PROTOCOL_VERSION,
                        "tick_id": 1,
                        "input_frame": {"player_id": player_id, "up": 0, "down": 0, "left": 0, "right": 1, "bomb": 0},
                        "client_timestamp": 123,
                    },
                    use_bin_type=True,
                )
                await ws.send(packed_input)
                ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                while ack["type"] in ("slot_list", "net_metrics"):
                    ack = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(ack["type"], "input_ack")
                self.assertEqual(ack.get("clock"), "unix_ms")

                self.state_q.put(self._playing_state(_sim_tick=21))
                raw_state = None
                deadline = time.time() + 4
                state_msg = None
                while time.time() < deadline and state_msg is None:
                    raw_state = await asyncio.wait_for(ws.recv(), 3)
                    parsed = decode_server_payload(raw_state)
                    if parsed.get("type") == "gamestate":
                        state_msg = parsed
                self.assertIsNotNone(state_msg)
                self.assertIsInstance(raw_state, (bytes, bytearray))
                self.assertEqual(state_msg["data"]["_sim_tick"], 21)

                joined = None
                deadline = time.time() + 2
                while time.time() < deadline and joined is None:
                    try:
                        item = self.input_q.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.02)
                        continue
                    if item.get("type") == "set_input_state" and item.get("client_id") == client_id:
                        joined = item
                self.assertIsNotNone(joined)
                self.assertEqual(joined["keys"]["right"], 1)

        asyncio.run(scenario())

    def test_binary_garbage_returns_error(self):
        import asyncio
        import websockets

        async def scenario():
            uri = f"ws://127.0.0.1:{self.ws_port}"
            async with websockets.connect(uri) as ws:
                await asyncio.wait_for(ws.recv(), 3)
                await ws.send(b"\xff\xfe\x00\x01not-a-frame")
                err = decode_server_payload(await asyncio.wait_for(ws.recv(), 3))
                self.assertEqual(err["type"], "error")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()

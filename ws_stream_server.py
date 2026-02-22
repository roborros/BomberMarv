import asyncio
import json
import logging
import queue
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

import websockets
from aiohttp import web

from net_protocol import (
    MSG_CLIENT_ID,
    MSG_ERROR,
    MSG_GAME_INPUT,
    MSG_GAMESTATE,
    MSG_HELLO,
    MSG_INPUT_ACK,
    MSG_PING,
    MSG_PONG,
    MSG_REGISTRATION_CONFIRMED,
    MSG_REGISTRATION_REJECTED,
    MSG_REQUEST_SLOT_LIST,
    MSG_SELECT_SLOT,
    MSG_SET_NAME,
    MSG_SLOT_LIST,
    envelope,
    validate_client_message,
)
from queue_utils import put_latest_nonblocking

PORT = 8765
HTTP_PORT = 8080
WS_SERVER_VERSION = "2.0.0"
HTTP_SERVER_VERSION = "2.0.0"


def setup_logging(logfile: str) -> logging.Logger:
    logger = logging.getLogger("ws_stream_server")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s")
    file_handler = RotatingFileHandler(logfile, maxBytes=20_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def run_server_with_queue(input_queue, state_queue=None, log_path=None):
    logger = setup_logging(log_path or "ws_server.log")

    client_id_counter = 0
    client_id_lock = threading.Lock()
    tracking_lock = threading.Lock()
    slots_lock = threading.Lock()
    state_lock = threading.Lock()

    clients: Dict[int, Dict[str, Any]] = {}
    players: Dict[int, Dict[str, Any]] = {}
    slots: Dict[int, Optional[int]] = {i: None for i in range(1, 7)}

    latest_game_state: Optional[Dict[str, Any]] = None
    latest_state_seq = 0
    last_state_json: Optional[str] = None
    last_state_seq_sent = -1

    metrics = {
        "state_queue_updates": 0,
        "state_queue_drained": 0,
        "state_queue_dropped_old": 0,
        "input_events_enqueued": 0,
        "input_events_dropped": 0,
        "messages_invalid": 0,
        "messages_received": 0,
        "broadcast_frames": 0,
        "broadcast_bytes": 0,
        "connections_opened": 0,
        "connections_closed": 0,
    }

    def enqueue_input_event(event: Dict[str, Any]) -> None:
        put_latest_nonblocking(
            input_queue,
            event,
            metrics,
            sent_key="input_events_enqueued",
            dropped_key="input_events_dropped",
        )

    def state_reader_loop():
        nonlocal latest_game_state, latest_state_seq, last_state_json, last_state_seq_sent
        logger.info("State reader thread started")
        while True:
            try:
                if not state_queue:
                    time.sleep(0.1)
                    continue
                state = state_queue.get()
                metrics["state_queue_updates"] += 1
                drained = 0
                while True:
                    try:
                        state = state_queue.get_nowait()
                        drained += 1
                    except queue.Empty:
                        break
                if drained:
                    metrics["state_queue_drained"] += drained
                    metrics["state_queue_dropped_old"] += drained
                with state_lock:
                    latest_game_state = state
                    latest_state_seq += 1
                    last_state_json = None
                    last_state_seq_sent = -1
            except Exception as exc:
                logger.error("State reader loop failed: %s", exc)
                break

    if state_queue:
        threading.Thread(target=state_reader_loop, daemon=True, name="state-reader").start()

    def build_slot_list() -> Dict[str, Any]:
        local_taken = 0
        with state_lock:
            if latest_game_state:
                try:
                    local_taken = int(latest_game_state.get("local_player_count", 0))
                except Exception:
                    local_taken = 0
        slots_dict: Dict[str, bool] = {}
        slot_reasons: Dict[str, str] = {}
        with slots_lock:
            for slot_id, occupied_by_client in slots.items():
                occupied = occupied_by_client is not None or slot_id <= local_taken
                key = str(slot_id)
                slots_dict[key] = occupied
                if occupied:
                    if slot_id <= local_taken:
                        slot_reasons[key] = "local"
                    else:
                        slot_reasons[key] = "remote"
        return {"slots": slots_dict, "slot_reasons": slot_reasons}

    async def send_json(ws, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":"))
        await ws.send(raw)

    async def broadcast_loop():
        nonlocal last_state_json, last_state_seq_sent
        logger.info("Broadcast loop started")
        last_broadcast_seq = -1
        last_broadcast_time = 0.0
        keepalive_interval_s = 0.2
        while True:
            await asyncio.sleep(0.008)
            with state_lock:
                if latest_game_state is None:
                    continue
                if last_state_json is None or last_state_seq_sent != latest_state_seq:
                    payload = envelope(
                        MSG_GAMESTATE,
                        data=latest_game_state,
                        server_timestamp=int(time.time() * 1000),
                        seq=latest_state_seq,
                    )
                    last_state_json = json.dumps(payload, separators=(",", ":"))
                    last_state_seq_sent = latest_state_seq
                current_payload = last_state_json
                current_seq = latest_state_seq
            if not current_payload:
                continue
            sockets = []
            with tracking_lock:
                for cdata in clients.values():
                    if cdata.get("registered"):
                        sockets.append(cdata["websocket"])
            if not sockets:
                continue
            now = time.time()
            state_changed = current_seq != last_broadcast_seq
            keepalive_due = (now - last_broadcast_time) >= keepalive_interval_s
            if not state_changed and not keepalive_due:
                continue
            if sockets:
                results = await asyncio.gather(
                    *[ws.send(current_payload) for ws in sockets],
                    return_exceptions=True,
                )
                metrics["broadcast_frames"] += 1
                metrics["broadcast_bytes"] += len(current_payload) * len(sockets)
                last_broadcast_seq = current_seq
                last_broadcast_time = now
                for result in results:
                    if isinstance(result, Exception):
                        logger.debug("Broadcast send exception: %s", result)

    async def cleanup_stale_clients_loop():
        while True:
            await asyncio.sleep(10)
            now = time.time()
            stale_ids: List[int] = []
            with tracking_lock:
                for cid, cdata in clients.items():
                    if now - cdata.get("last_seen", now) > 60:
                        stale_ids.append(cid)
            if not stale_ids:
                continue
            for cid in stale_ids:
                with tracking_lock:
                    cdata = clients.get(cid)
                    if not cdata:
                        continue
                    ws = cdata["websocket"]
                try:
                    await ws.close()
                except Exception:
                    pass

    async def handle_client(websocket):
        nonlocal client_id_counter
        with client_id_lock:
            client_id = client_id_counter
            client_id_counter += 1
        metrics["connections_opened"] += 1
        logger.info("Client connected: id=%s address=%s", client_id, websocket.remote_address)

        with tracking_lock:
            clients[client_id] = {
                "websocket": websocket,
                "players": [],
                "last_seen": time.time(),
                "latency_samples": [],
                "registered": False,
                "slot": None,
            }

        await send_json(websocket, envelope(MSG_CLIENT_ID, client_id=client_id))

        try:
            async for raw in websocket:
                metrics["messages_received"] += 1
                with tracking_lock:
                    if client_id in clients:
                        clients[client_id]["last_seen"] = time.time()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    metrics["messages_invalid"] += 1
                    await send_json(websocket, envelope(MSG_ERROR, message="invalid JSON"))
                    continue
                err = validate_client_message(data)
                if err:
                    metrics["messages_invalid"] += 1
                    await send_json(websocket, envelope(MSG_ERROR, message=err))
                    continue

                msg_type = data["type"]

                if msg_type == MSG_HELLO:
                    await send_json(
                        websocket,
                        envelope("hello_ack", server="bombermarv", ws_version=WS_SERVER_VERSION),
                    )
                    continue

                if msg_type == MSG_REQUEST_SLOT_LIST:
                    slot_info = build_slot_list()
                    await send_json(websocket, envelope(MSG_SLOT_LIST, **slot_info))
                    continue

                if msg_type == MSG_SET_NAME:
                    name_value = str(data.get("name", "")).strip()
                    with tracking_lock:
                        if client_id in clients:
                            clients[client_id]["display_name"] = name_value[:20] if name_value else None
                    slot_info = build_slot_list()
                    await send_json(websocket, envelope(MSG_SLOT_LIST, **slot_info))
                    continue

                if msg_type == MSG_SELECT_SLOT:
                    requested_slot = data["slot"]
                    requested_name = str(data.get("name", "")).strip()
                    success = False
                    message = "invalid slot"
                    with slots_lock:
                        if requested_slot in slots:
                            local_taken = 0
                            with state_lock:
                                if latest_game_state:
                                    try:
                                        local_taken = int(latest_game_state.get("local_player_count", 0))
                                    except Exception:
                                        local_taken = 0
                            if requested_slot <= local_taken:
                                message = "slot taken by local player"
                            elif slots[requested_slot] is None:
                                current_slot = None
                                with tracking_lock:
                                    current_slot = clients.get(client_id, {}).get("slot")
                                if current_slot:
                                    slots[current_slot] = None
                                slots[requested_slot] = client_id
                                success = True
                                message = f"joined slot {requested_slot}"
                            else:
                                message = "slot already taken"
                    if not success:
                        await send_json(websocket, envelope(MSG_REGISTRATION_REJECTED, message=message))
                        slot_info = build_slot_list()
                        await send_json(websocket, envelope(MSG_SLOT_LIST, **slot_info))
                        continue
                    with tracking_lock:
                        clients[client_id]["slot"] = requested_slot
                        clients[client_id]["registered"] = True
                        if requested_name:
                            clients[client_id]["display_name"] = requested_name[:20]
                        clients[client_id]["players"] = [requested_slot]
                        players[requested_slot] = {
                            "client_id": client_id,
                            "keys": {"up": 0, "down": 0, "left": 0, "right": 0, "bomb": 0},
                        }
                    await send_json(
                        websocket,
                        envelope(
                            MSG_REGISTRATION_CONFIRMED,
                            client_id=client_id,
                            slot=requested_slot,
                            player_ids=[requested_slot],
                            message=message,
                        ),
                    )
                    slot_info = build_slot_list()
                    await send_json(websocket, envelope(MSG_SLOT_LIST, **slot_info))
                    continue

                if msg_type == MSG_GAME_INPUT:
                    with tracking_lock:
                        if not clients.get(client_id, {}).get("registered", False):
                            await send_json(
                                websocket,
                                envelope(MSG_REGISTRATION_REJECTED, message="client not registered"),
                            )
                            continue
                    game_input = data["input"]
                    client_timestamp = data.get("client_timestamp")
                    action_to_key = {
                        "up": "arrowup",
                        "down": "arrowdown",
                        "left": "arrowleft",
                        "right": "arrowright",
                        "bomb": "space",
                    }
                    i = 1
                    with tracking_lock:
                        while i + 5 < len(game_input):
                            requested_player_id = int(game_input[i])
                            up, down, left, right, bomb = [int(v) for v in game_input[i + 1 : i + 6]]
                            if requested_player_id not in players:
                                players[requested_player_id] = {
                                    "client_id": client_id,
                                    "keys": {"up": 0, "down": 0, "left": 0, "right": 0, "bomb": 0},
                                }
                                if requested_player_id not in clients[client_id]["players"]:
                                    clients[client_id]["players"].append(requested_player_id)
                            prev_keys = players[requested_player_id]["keys"]
                            new_keys = {
                                "up": up,
                                "down": down,
                                "left": left,
                                "right": right,
                                "bomb": bomb,
                            }
                            players[requested_player_id]["keys"] = dict(new_keys)
                            for action, new_val in new_keys.items():
                                old_val = int(prev_keys.get(action, 0))
                                if new_val and not old_val:
                                    enqueue_input_event(
                                        {
                                            "type": "keydown",
                                            "key": action_to_key[action],
                                            "client_id": client_id,
                                            "player_id": requested_player_id,
                                            "ws_received_timestamp": int(time.time() * 1000),
                                        }
                                    )
                                elif not new_val and old_val:
                                    enqueue_input_event(
                                        {
                                            "type": "keyup",
                                            "key": action_to_key[action],
                                            "client_id": client_id,
                                            "player_id": requested_player_id,
                                            "ws_received_timestamp": int(time.time() * 1000),
                                        }
                                    )
                            i += 6

                    server_timestamp = int(time.time() * 1000)
                    if client_timestamp:
                        with tracking_lock:
                            latency_ms = server_timestamp - int(client_timestamp)
                            samples = clients[client_id]["latency_samples"]
                            samples.append((server_timestamp, latency_ms))
                            cutoff = server_timestamp - 5000
                            samples = [(ts, val) for (ts, val) in samples if ts >= cutoff]
                            if len(samples) > 300:
                                samples = samples[-300:]
                            clients[client_id]["latency_samples"] = samples
                    await send_json(
                        websocket,
                        envelope(
                            MSG_INPUT_ACK,
                            client_id=client_id,
                            original_timestamp=client_timestamp,
                            server_timestamp=server_timestamp,
                        ),
                    )
                    continue

                if msg_type == MSG_PING:
                    await send_json(websocket, envelope(MSG_PONG, server_timestamp=int(time.time() * 1000)))
        except websockets.ConnectionClosed:
            logger.info("WebSocket closed for client id=%s", client_id)
        except Exception as exc:
            logger.exception("Error in client handler id=%s: %s", client_id, exc)
        finally:
            metrics["connections_closed"] += 1
            with tracking_lock:
                cdata = clients.pop(client_id, None)
                if cdata:
                    for player_id in cdata["players"]:
                        players.pop(player_id, None)
            with slots_lock:
                for slot_id, cid in list(slots.items()):
                    if cid == client_id:
                        slots[slot_id] = None
                        logger.info("Released slot %s for client %s", slot_id, client_id)

    async def handle_versions(request):
        return web.json_response({"ws_server": WS_SERVER_VERSION, "http_server": HTTP_SERVER_VERSION})

    async def handle_config(request):
        import bm_params

        return web.json_response(
            {
                "send_on_change": bm_params.SEND_ON_CHANGE,
                "periodic_sending": bm_params.PERIODIC_SENDING,
                "min_send_frequency": bm_params.MIN_SEND_FREQUENCY,
                "max_send_frequency": bm_params.MAX_SEND_FREQUENCY,
            }
        )

    async def handle_status(request):
        with tracking_lock:
            status = {"clients": {}, "players": {}}
            for client_id, client_data in clients.items():
                samples = client_data.get("latency_samples", [])
                values = []
                for entry in samples:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        values.append(float(entry[1]))
                    elif isinstance(entry, (int, float)):
                        values.append(float(entry))
                avg_latency = (sum(values) / len(values)) if values else 0.0
                status["clients"][client_id] = {
                    "players": client_data["players"],
                    "last_seen": client_data["last_seen"],
                    "avg_latency": round(avg_latency, 2),
                    "avg_latency_5s": round(avg_latency, 2),
                    "latency_samples": len(values),
                    "latency_samples_5s": len(values),
                    "registered": client_data.get("registered", False),
                    "slot": client_data.get("slot"),
                    "display_name": client_data.get("display_name"),
                }
            for player_id, pdata in players.items():
                status["players"][player_id] = {"client_id": pdata["client_id"], "keys": pdata["keys"]}
        with slots_lock:
            status["slots"] = {k: (v is not None) for k, v in slots.items()}
        return web.json_response(status)

    async def handle_metrics(request):
        return web.json_response(metrics)

    async def handle_health(request):
        return web.json_response({"status": "ok", "timestamp": int(time.time() * 1000)})

    def start_http_server():
        app = web.Application()
        app.router.add_get("/health", handle_health)
        app.router.add_get("/versions", handle_versions)
        app.router.add_get("/config", handle_config)
        app.router.add_get("/status", handle_status)
        app.router.add_get("/metrics", handle_metrics)
        runner = web.AppRunner(app)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run():
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
            await site.start()
            logger.info("HTTP diagnostics server started on port %s", HTTP_PORT)
            while True:
                await asyncio.sleep(3600)

        loop.run_until_complete(run())

    async def main():
        logger.info("Starting websocket server on port %s", PORT)
        threading.Thread(target=start_http_server, daemon=True, name="http-server").start()
        asyncio.create_task(broadcast_loop())
        asyncio.create_task(cleanup_stale_clients_loop())
        ws_server = await websockets.serve(
            handle_client,
            "0.0.0.0",
            PORT,
            max_size=2**22,
            ping_interval=20,
            ping_timeout=20,
        )
        await ws_server.wait_closed()

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Process termination (Ctrl+C / taskkill) should not print a traceback.
        logger.info("Websocket server shutdown requested.")

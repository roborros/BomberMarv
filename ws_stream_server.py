import asyncio
import json
import logging
import os
import queue
import statistics
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

import websockets
from aiohttp import web

from latency_metrics import split_hud_metrics, wall_clock_ms
from net_protocol import (
    MSG_CLIENT_ID,
    MSG_ERROR,
    MSG_GAME_INPUT,
    MSG_GAMESTATE,
    MSG_GAMESTATE_DELTA,
    MSG_HELLO,
    MSG_HELLO_ACK,
    MSG_INPUT_ACK,
    MSG_NET_METRICS,
    MSG_PING,
    MSG_PONG,
    MSG_RTC_ANSWER,
    MSG_RTC_FAILED,
    MSG_RTC_ICE_CANDIDATE,
    MSG_RTC_OFFER,
    MSG_RTC_READY,
    MSG_REGISTRATION_CONFIRMED,
    MSG_REGISTRATION_REJECTED,
    MSG_REQUEST_SLOT_LIST,
    MSG_REQUEST_KEYFRAME,
    MSG_SELECT_SLOT,
    MSG_SET_NAME,
    MSG_SLOT_LIST,
    MSG_STATE_KEEPALIVE,
    build_state_delta,
    classify_state_diff,
    envelope,
    resolve_input_tick,
    resolve_ws_codec,
    validate_client_message,
)
from queue_utils import put_latest_nonblocking

try:
    import msgpack  # type: ignore
except Exception:  # pragma: no cover
    msgpack = None

try:
    from aiortc import RTCConfiguration, RTCDataChannel, RTCIceCandidate, RTCPeerConnection, RTCSessionDescription  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover
    RTCConfiguration = None  # type: ignore
    RTCDataChannel = None  # type: ignore
    RTCIceCandidate = None  # type: ignore
    RTCPeerConnection = None  # type: ignore
    RTCSessionDescription = None  # type: ignore

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


PORT = _env_int("BM_WS_PORT", 8765)
HTTP_PORT = _env_int("BM_HTTP_PORT", 8080)
WS_SERVER_VERSION = "2.1.0"
HTTP_SERVER_VERSION = "2.1.0"


def encode_gameplay_payload(payload: Dict[str, Any], codec: str) -> Any:
    """Encode a gameplay envelope as JSON text or MessagePack bytes."""
    if codec == "msgpack" and msgpack is not None:
        return msgpack.packb(payload, use_bin_type=True)
    return json.dumps(payload, separators=(",", ":"))


def decode_client_payload(raw: Any) -> Dict[str, Any]:
    """Decode a WS text JSON frame or binary MessagePack/JSON payload."""
    if isinstance(raw, (bytes, bytearray, memoryview)):
        blob = bytes(raw)
        if msgpack is not None:
            try:
                decoded = msgpack.unpackb(blob, raw=False)
                if isinstance(decoded, dict):
                    return decoded
            except Exception:
                pass
        try:
            decoded = json.loads(blob.decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid binary payload") from exc
        if not isinstance(decoded, dict):
            raise ValueError("message must be an object")
        return decoded
    if isinstance(raw, str):
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("message must be an object")
        return decoded
    raise ValueError("unsupported payload")


def decode_server_payload(raw: Any) -> Dict[str, Any]:
    """Decode a server->client frame for tests and mixed JSON/msgpack sockets."""
    if isinstance(raw, (bytes, bytearray, memoryview)):
        blob = bytes(raw)
        if msgpack is not None:
            try:
                decoded = msgpack.unpackb(blob, raw=False)
                if isinstance(decoded, dict):
                    return decoded
            except Exception:
                pass
        decoded = json.loads(blob.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("message must be an object")
        return decoded
    if isinstance(raw, str):
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("message must be an object")
        return decoded
    raise ValueError("unsupported payload")


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = max(0, min(len(sorted_values) - 1, int(round((percentile / 100.0) * (len(sorted_values) - 1)))))
    return float(sorted_values[rank])


def classify_broadcast_for_client(
    *,
    current_state: Dict[str, Any],
    last_full_state: Optional[Dict[str, Any]],
    current_seq: int,
    last_broadcast_seq: int,
    client_last_seq: int,
    delta_chain_count: int,
    max_delta_chain: int,
    force_keyframe_global: bool,
    force_keyframe_client: bool,
    keyframe_interval_seq: int,
    server_timestamp: int,
) -> tuple:
    """Choose keyframe, delta, or idle keepalive for one registered client."""
    needs_keyframe = (
        force_keyframe_global
        or force_keyframe_client
        or last_full_state is None
        or last_broadcast_seq < 0
        or (current_seq - last_broadcast_seq) >= keyframe_interval_seq
        or client_last_seq != last_broadcast_seq
        or int(delta_chain_count) >= int(max_delta_chain)
    )
    tick_id = 0
    try:
        tick_id = int((current_state or {}).get("_sim_tick", 0) or 0)
    except (TypeError, ValueError):
        tick_id = 0
    if needs_keyframe:
        return (
            envelope(
                MSG_GAMESTATE,
                data=current_state,
                server_timestamp=server_timestamp,
                seq=current_seq,
                tick_id=tick_id,
            ),
            "keyframe",
        )
    delta = build_state_delta(last_full_state or {}, current_state)
    kind = classify_state_diff(delta)
    if kind in ("keepalive", "unchanged"):
        return (
            envelope(
                MSG_STATE_KEEPALIVE,
                seq=current_seq,
                time=current_state.get("time"),
                _sim_tick=current_state.get("_sim_tick"),
                _host_published_at_ms=current_state.get("_host_published_at_ms"),
                server_timestamp=server_timestamp,
                tick_id=tick_id,
            ),
            "keepalive",
        )
    return (
        envelope(
            MSG_GAMESTATE_DELTA,
            base_seq=last_broadcast_seq,
            seq=current_seq,
            server_timestamp=server_timestamp,
            tick_id=tick_id,
            delta=delta,
        ),
        "delta",
    )


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


def run_server_with_queue(input_queue, state_queue=None, status_queue=None, log_path=None):
    logger = setup_logging(log_path or "ws_server.log")
    rtc_enabled = os.environ.get("BM_RTC_ENABLED", "0") == "1"
    rtc_force_ws = os.environ.get("BM_RTC_FORCE_WS", "0") == "1"
    strict_input_mode = os.environ.get("BM_STRICT_INPUT_MODE", "0") == "1"
    input_lead_ticks = max(0, int(os.environ.get("BM_INPUT_LEAD_TICKS", "1") or 1))
    late_tick_window = max(1, int(os.environ.get("BM_INPUT_LATE_WINDOW_TICKS", "6") or 6))
    max_delta_chain = max(1, int(os.environ.get("BM_MAX_DELTA_CHAIN", "8") or 8))
    client_bps_budget = max(50_000, int(os.environ.get("BM_CLIENT_BPS_BUDGET", "250000") or 250000))
    rtc_available = bool(rtc_enabled and not rtc_force_ws and RTCPeerConnection is not None and RTCSessionDescription is not None)

    client_id_counter = 0
    client_id_lock = threading.Lock()
    tracking_lock = threading.Lock()
    slots_lock = threading.Lock()
    state_lock = threading.Lock()

    clients: Dict[int, Dict[str, Any]] = {}
    players: Dict[int, Dict[str, Any]] = {}
    slots: Dict[int, Optional[int]] = {i: None for i in range(1, 9)}

    latest_game_state: Optional[Dict[str, Any]] = None
    latest_state_seq = 0
    latest_sim_tick = 0
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
        "state_reader_wait_samples_ms": [],
        "state_queue_age_samples_ms": [],
        "broadcast_loop_duration_samples_ms": [],
        "broadcast_send_duration_samples_ms": [],
        "broadcast_payload_bytes_samples": [],
        "broadcast_delta_frames": 0,
        "broadcast_key_frames": 0,
        "broadcast_keepalive_frames": 0,
        "broadcast_metrics_frames": 0,
        "broadcast_wakeup_signals": 0,
        "status_queue_sent": 0,
        "status_queue_dropped": 0,
        "rtc_offer_sent": 0,
        "rtc_answer_received": 0,
        "rtc_ice_received": 0,
        "rtc_ice_sent": 0,
        "rtc_ready_events": 0,
        "rtc_failed_events": 0,
        "input_events_ws": 0,
        "input_events_rtc": 0,
        "broadcast_frames_ws": 0,
        "broadcast_frames_rtc": 0,
        "broadcast_bytes_ws": 0,
        "broadcast_bytes_rtc": 0,
        "input_tick_out_of_order": 0,
        "input_tick_missing": 0,
        "input_tick_late": 0,
        "input_tick_strict_rejected": 0,
        "input_tick_applied": 0,
        "input_player_id_rejected": 0,
        "input_keyframe_requests": 0,
        "input_tick_apply_age_samples": [],
        "broadcast_payload_budget_exceeded": 0,
        "client_bps_samples": [],
    }

    aio_loop_holder: List[Any] = []
    state_wakeup_holder: List[Any] = []

    def notify_broadcast() -> None:
        if not aio_loop_holder or not state_wakeup_holder:
            return
        loop = aio_loop_holder[0]
        wakeup = state_wakeup_holder[0]
        try:
            loop.call_soon_threadsafe(wakeup.set)
            metrics["broadcast_wakeup_signals"] += 1
        except RuntimeError:
            pass

    def enqueue_input_event(event: Dict[str, Any]) -> None:
        put_latest_nonblocking(
            input_queue,
            event,
            metrics,
            sent_key="input_events_enqueued",
            dropped_key="input_events_dropped",
        )

    def add_sample(metric_key: str, value: float, limit: int = 400) -> None:
        bucket = metrics.get(metric_key)
        if not isinstance(bucket, list):
            return
        bucket.append(float(value))
        if len(bucket) > limit:
            del bucket[:-limit]

    def build_status_snapshot() -> Dict[str, Any]:
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
                    "transport_active": client_data.get("transport_active", "ws"),
                    "webrtc_supported": bool(client_data.get("webrtc_supported", False)),
                    "webrtc_offered": bool(client_data.get("webrtc_offered", False)),
                    "expected_input_tick": int(client_data.get("expected_input_tick", -1)),
                    "strict_input_mode": bool(client_data.get("strict_input_mode", False)),
                }
            for player_id, pdata in players.items():
                status["players"][player_id] = {"client_id": pdata["client_id"], "keys": pdata["keys"]}
        with slots_lock:
            status["slots"] = {k: (v is not None) for k, v in slots.items()}
        return status

    def enqueue_status_snapshot() -> None:
        if status_queue is None:
            return
        put_latest_nonblocking(
            status_queue,
            {"type": "status", "status": build_status_snapshot(), "server_timestamp": int(time.time() * 1000)},
            metrics,
            sent_key="status_queue_sent",
            dropped_key="status_queue_dropped",
        )

    def state_reader_loop():
        nonlocal latest_game_state, latest_state_seq, last_state_json, last_state_seq_sent, latest_sim_tick
        logger.info("State reader thread started")
        while True:
            try:
                if not state_queue:
                    time.sleep(0.1)
                    continue
                wait_start = time.perf_counter()
                state = state_queue.get()
                wait_ms = (time.perf_counter() - wait_start) * 1000.0
                add_sample("state_reader_wait_samples_ms", wait_ms)
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
                    if isinstance(state, dict):
                        try:
                            latest_sim_tick = int(state.get("_sim_tick", latest_sim_tick))
                        except Exception:
                            pass
                notify_broadcast()
                if isinstance(state, dict):
                    published_at_ms = state.get("_host_published_at_ms")
                    if isinstance(published_at_ms, (int, float)):
                        age_ms = max(0.0, float(wall_clock_ms()) - float(published_at_ms))
                        add_sample("state_queue_age_samples_ms", age_ms)
            except Exception as exc:
                logger.error("State reader loop failed: %s", exc)
                break

    if state_queue:
        threading.Thread(target=state_reader_loop, daemon=True, name="state-reader").start()

    def build_slot_list() -> Dict[str, Any]:
        local_taken = 0
        trophy_win_threshold = 3
        with state_lock:
            if latest_game_state:
                try:
                    local_taken = int(latest_game_state.get("local_player_count", 0))
                except Exception:
                    local_taken = 0
                try:
                    trophy_win_threshold = int(latest_game_state.get("trophy_win_threshold", 3) or 3)
                except Exception:
                    trophy_win_threshold = 3
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
        return {"slots": slots_dict, "slot_reasons": slot_reasons, "trophy_win_threshold": trophy_win_threshold}

    async def send_json(ws, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":"))
        await ws.send(raw)

    async def broadcast_slot_list() -> None:
        slot_info = build_slot_list()
        payload = envelope(MSG_SLOT_LIST, **slot_info)
        recipients = []
        with tracking_lock:
            for cdata in clients.values():
                ws = cdata.get("websocket")
                if ws is not None:
                    recipients.append(ws)
        for ws in recipients:
            try:
                await send_json(ws, payload)
            except Exception:
                pass

    def encode_payload(payload: Dict[str, Any], codec: str) -> Any:
        return encode_gameplay_payload(payload, codec)

    async def process_game_input(client_id: int, data: Dict[str, Any], source: str = "ws", websocket=None) -> None:
        with tracking_lock:
            if not clients.get(client_id, {}).get("registered", False):
                if websocket is not None:
                    await send_json(
                        websocket,
                        envelope(MSG_REGISTRATION_REJECTED, message="client not registered"),
                    )
                return
        game_input = data.get("input", [])
        input_frame = data.get("input_frame")
        tick_id_raw = data.get("tick_id")
        tick_id = int(tick_id_raw) if isinstance(tick_id_raw, int) and tick_id_raw >= 0 else None
        client_timestamp = data.get("client_timestamp")

        parsed_frames: List[Dict[str, Any]] = []
        if isinstance(input_frame, dict):
            parsed_frames.append(
                {
                    "player_id": int(input_frame.get("player_id", 0)),
                    "keys": {
                        "up": int(input_frame.get("up", 0)),
                        "down": int(input_frame.get("down", 0)),
                        "left": int(input_frame.get("left", 0)),
                        "right": int(input_frame.get("right", 0)),
                        "bomb": int(input_frame.get("bomb", 0)),
                    },
                }
            )
        else:
            i = 1
            while i + 5 < len(game_input):
                requested_player_id = int(game_input[i])
                up, down, left, right, bomb = [int(v) for v in game_input[i + 1 : i + 6]]
                parsed_frames.append(
                    {
                        "player_id": requested_player_id,
                        "keys": {"up": up, "down": down, "left": left, "right": right, "bomb": bomb},
                    }
                )
                i += 6

        recv_timestamp = wall_clock_ms()
        applied_tick_id: Optional[int] = None

        def enqueue_frame(player_id: int, keys_state: Dict[str, int], frame_tick_id: Optional[int]) -> None:
            apply_tick_id = None
            if frame_tick_id is not None:
                apply_tick_id = frame_tick_id + input_lead_ticks
            enqueue_input_event(
                {
                    "type": "set_input_state",
                    "client_id": client_id,
                    "player_id": player_id,
                    "keys": keys_state,
                    "tick_id": frame_tick_id,
                    "apply_tick_id": apply_tick_id,
                    "ws_received_timestamp": recv_timestamp,
                }
            )

        with tracking_lock:
            cdata = clients.get(client_id, {})
            client_strict_mode = bool(cdata.get("strict_input_mode", False))
            cdata.setdefault("expected_input_tick", -1)
            cdata.setdefault("input_frame_buffer", {})
            for frame in parsed_frames:
                player_id = int(frame["player_id"])
                keys_state = {
                    "up": int(frame["keys"]["up"]),
                    "down": int(frame["keys"]["down"]),
                    "left": int(frame["keys"]["left"]),
                    "right": int(frame["keys"]["right"]),
                    "bomb": int(frame["keys"]["bomb"]),
                }
                if player_id not in players:
                    if cdata.get("players") and player_id not in cdata.get("players", []):
                        metrics["input_player_id_rejected"] += 1
                        continue
                    players[player_id] = {
                        "client_id": client_id,
                        "keys": {"up": 0, "down": 0, "left": 0, "right": 0, "bomb": 0},
                    }
                    if player_id not in cdata.get("players", []):
                        cdata["players"].append(player_id)
                elif cdata.get("players") and player_id not in cdata.get("players", []):
                    metrics["input_player_id_rejected"] += 1
                    continue
                players[player_id]["keys"] = dict(keys_state)

                if tick_id is None:
                    if client_strict_mode:
                        metrics["input_tick_strict_rejected"] += 1
                        continue
                    enqueue_frame(player_id, keys_state, None)
                    continue

                expected_tick = int(cdata.get("expected_input_tick", -1))
                action, next_expected, skipped = resolve_input_tick(expected_tick, tick_id)
                if action == "drop":
                    metrics["input_tick_out_of_order"] += 1
                    continue
                if skipped:
                    metrics["input_tick_missing"] += skipped
                    stale_buffer = cdata.setdefault("input_frame_buffer", {})
                    if isinstance(stale_buffer, dict):
                        for stale_tick in [t for t in stale_buffer.keys() if t < tick_id]:
                            stale_buffer.pop(stale_tick, None)
                enqueue_frame(player_id, keys_state, tick_id)
                metrics["input_tick_applied"] += 1
                input_age_ticks = max(0, latest_sim_tick - tick_id)
                add_sample("input_tick_apply_age_samples", float(input_age_ticks))
                if input_age_ticks > late_tick_window:
                    metrics["input_tick_late"] += 1
                applied_tick_id = tick_id
                cdata["expected_input_tick"] = next_expected

        if source == "rtc":
            metrics["input_events_rtc"] += 1
        else:
            metrics["input_events_ws"] += 1

        server_timestamp = wall_clock_ms()
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
        ack_ws = websocket
        if ack_ws is None:
            with tracking_lock:
                ack_ws = clients.get(client_id, {}).get("websocket")
        if ack_ws is not None:
            await send_json(
                ack_ws,
                envelope(
                    MSG_INPUT_ACK,
                    client_id=client_id,
                    original_timestamp=client_timestamp,
                    server_timestamp=server_timestamp,
                    tick_id=tick_id,
                    apply_tick_id=applied_tick_id,
                    clock="unix_ms",
                    rtt_clock="client",
                ),
            )

    async def maybe_start_rtc_for_client(client_id: int) -> None:
        if not rtc_available:
            return
        with tracking_lock:
            cdata = clients.get(client_id)
            if not cdata:
                return
            existing_peer = cdata.get("rtc_peer")
            ws = cdata.get("websocket")
            codec = str(cdata.get("codec", "json"))
            existing_state = getattr(existing_peer, "connectionState", "") if existing_peer is not None else ""
        if existing_peer is not None:
            if existing_state in ("connected", "completed"):
                return
            try:
                await existing_peer.close()
            except Exception:
                pass
            with tracking_lock:
                c = clients.get(client_id)
                if c:
                    c["rtc_peer"] = None
                    c["rtc_input_channel"] = None
                    c["rtc_state_channel"] = None

        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        dc_input = pc.createDataChannel("input_unreliable", ordered=False, maxRetransmits=0)
        dc_state = pc.createDataChannel("state_unreliable", ordered=False, maxRetransmits=1)

        @dc_input.on("message")
        def on_input_message(message):
            try:
                with tracking_lock:
                    cdata = clients.get(client_id, {})
                    rtc_codec = str(cdata.get("rtc_codec", "json"))
                if isinstance(message, (bytes, bytearray)):
                    if rtc_codec == "msgpack" and msgpack is not None:
                        decoded = msgpack.unpackb(bytes(message), raw=False)
                    else:
                        decoded = json.loads(message.decode("utf-8"))
                else:
                    decoded = json.loads(str(message))
                if isinstance(decoded, dict) and decoded.get("type") == MSG_GAME_INPUT:
                    asyncio.create_task(process_game_input(client_id, decoded, source="rtc", websocket=None))
            except Exception:
                pass

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate is None:
                return
            payload = {
                "candidate": candidate.to_sdp(),
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
            metrics["rtc_ice_sent"] += 1
            try:
                await send_json(ws, envelope(MSG_RTC_ICE_CANDIDATE, candidate=payload))
            except Exception:
                pass

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = pc.connectionState
            with tracking_lock:
                c = clients.get(client_id)
                if c:
                    c["transport_active"] = "rtc" if state in ("connected", "completed") else "ws"
            if state in ("failed", "closed", "disconnected"):
                with tracking_lock:
                    c = clients.get(client_id)
                    if c:
                        c["transport_active"] = "ws"

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        metrics["rtc_offer_sent"] += 1
        with tracking_lock:
            cdata = clients.get(client_id)
            if cdata:
                cdata["rtc_peer"] = pc
                cdata["rtc_input_channel"] = dc_input
                cdata["rtc_state_channel"] = dc_state
                cdata["transport_active"] = "ws"
                cdata["rtc_codec"] = codec
        await send_json(
            ws,
            envelope(
                MSG_RTC_OFFER,
                sdp=str(pc.localDescription.sdp),
                sdp_type=str(pc.localDescription.type),
            ),
        )

    async def send_gameplay_frame(websocket, rtc_channel, transport_active, ws_codec, rtc_codec, payload_dict) -> tuple:
        ws_payload = encode_payload(payload_dict, ws_codec)
        sent_bytes = len(ws_payload) if isinstance(ws_payload, (bytes, bytearray)) else len(str(ws_payload))
        used_rtc = False
        if transport_active == "rtc" and rtc_channel is not None and getattr(rtc_channel, "readyState", "") == "open":
            rtc_payload = encode_payload(payload_dict, rtc_codec) if rtc_codec == "msgpack" else encode_payload(payload_dict, "json")
            if isinstance(rtc_payload, (bytes, bytearray)):
                rtc_channel.send(bytes(rtc_payload))
            else:
                rtc_channel.send(str(rtc_payload))
            used_rtc = True
            sent_bytes = len(rtc_payload) if isinstance(rtc_payload, (bytes, bytearray)) else len(str(rtc_payload))
        else:
            await websocket.send(ws_payload)
        return sent_bytes, used_rtc

    async def broadcast_loop():
        nonlocal last_state_json, last_state_seq_sent
        logger.info("Broadcast loop started")
        last_broadcast_seq = -1
        last_full_state: Optional[Dict[str, Any]] = None
        keyframe_interval_seq = 10
        wakeup = None
        while wakeup is None:
            if state_wakeup_holder:
                wakeup = state_wakeup_holder[0]
            else:
                await asyncio.sleep(0)
        while True:
            loop_started = time.perf_counter()
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=0.008)
            except asyncio.TimeoutError:
                pass
            wakeup.clear()
            with state_lock:
                if latest_game_state is None:
                    add_sample("broadcast_loop_duration_samples_ms", (time.perf_counter() - loop_started) * 1000.0)
                    continue
                queued_state = latest_game_state
                current_seq = latest_state_seq
            recipients: List[Dict[str, Any]] = []
            with tracking_lock:
                for cid, cdata in clients.items():
                    if cdata.get("registered"):
                        recipients.append(
                            {
                                "client_id": cid,
                                "websocket": cdata["websocket"],
                                "last_state_seq": int(cdata.get("last_state_seq", -1)),
                                "codec": str(cdata.get("codec", "json")),
                                "transport_active": str(cdata.get("transport_active", "ws")),
                                "rtc_codec": str(cdata.get("rtc_codec", "json")),
                                "rtc_state_channel": cdata.get("rtc_state_channel"),
                                "delta_chain_count": int(cdata.get("delta_chain_count", 0)),
                                "force_keyframe": bool(cdata.get("force_keyframe", False)),
                            }
                        )
            if not recipients:
                add_sample("broadcast_loop_duration_samples_ms", (time.perf_counter() - loop_started) * 1000.0)
                continue
            state_changed = current_seq != last_broadcast_seq
            if not state_changed:
                add_sample("broadcast_loop_duration_samples_ms", (time.perf_counter() - loop_started) * 1000.0)
                continue

            gameplay_state, hud_metrics = split_hud_metrics(queued_state)
            if not isinstance(gameplay_state, dict):
                add_sample("broadcast_loop_duration_samples_ms", (time.perf_counter() - loop_started) * 1000.0)
                continue
            force_keyframe = (
                last_full_state is None
                or last_broadcast_seq < 0
                or (current_seq - last_broadcast_seq) >= keyframe_interval_seq
            )
            server_timestamp = wall_clock_ms()
            send_plan: List[Dict[str, Any]] = []
            total_payload_bytes = 0
            for recipient in recipients:
                payload_dict, kind = classify_broadcast_for_client(
                    current_state=gameplay_state,
                    last_full_state=last_full_state,
                    current_seq=current_seq,
                    last_broadcast_seq=last_broadcast_seq,
                    client_last_seq=int(recipient["last_state_seq"]),
                    delta_chain_count=int(recipient.get("delta_chain_count", 0)),
                    max_delta_chain=max_delta_chain,
                    force_keyframe_global=force_keyframe,
                    force_keyframe_client=bool(recipient.get("force_keyframe")),
                    keyframe_interval_seq=keyframe_interval_seq,
                    server_timestamp=server_timestamp,
                )
                payload = encode_payload(payload_dict, str(recipient.get("codec", "json")))
                send_plan.append(
                    {
                        "client_id": recipient["client_id"],
                        "websocket": recipient["websocket"],
                        "transport_active": recipient.get("transport_active", "ws"),
                        "rtc_codec": recipient.get("rtc_codec", "json"),
                        "rtc_state_channel": recipient.get("rtc_state_channel"),
                        "codec": recipient.get("codec", "json"),
                        "payload": payload,
                        "payload_dict": payload_dict,
                        "kind": kind,
                    }
                )
                total_payload_bytes += len(payload) if isinstance(payload, (bytes, bytearray)) else len(str(payload))

            if total_payload_bytes:
                add_sample("broadcast_payload_bytes_samples", total_payload_bytes / max(1, len(send_plan)))
            send_started = time.perf_counter()
            results: List[Optional[Exception]] = []
            for item in send_plan:
                try:
                    sent_bytes, used_rtc = await send_gameplay_frame(
                        item["websocket"],
                        item.get("rtc_state_channel"),
                        str(item.get("transport_active", "ws")),
                        str(item.get("codec", "json")),
                        str(item.get("rtc_codec", "json")),
                        item["payload_dict"],
                    )
                    if used_rtc:
                        metrics["broadcast_frames_rtc"] += 1
                        metrics["broadcast_bytes_rtc"] += sent_bytes
                    else:
                        metrics["broadcast_frames_ws"] += 1
                        metrics["broadcast_bytes_ws"] += sent_bytes
                    item["sent_bytes"] = sent_bytes
                    results.append(None)
                except Exception as exc:
                    results.append(exc)
            send_ms = (time.perf_counter() - send_started) * 1000.0
            add_sample("broadcast_send_duration_samples_ms", send_ms)
            metrics["broadcast_frames"] += 1
            metrics["broadcast_bytes"] += total_payload_bytes
            last_broadcast_seq = current_seq
            last_full_state = gameplay_state
            keyframe_sends = 0
            delta_sends = 0
            keepalive_sends = 0
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.debug("Broadcast send exception: %s", result)
                    continue
                kind = send_plan[idx]["kind"]
                if kind == "keyframe":
                    keyframe_sends += 1
                elif kind == "delta":
                    delta_sends += 1
                else:
                    keepalive_sends += 1
                cid = send_plan[idx]["client_id"]
                with tracking_lock:
                    cdata = clients.get(cid)
                    if cdata:
                        cdata["last_state_seq"] = current_seq
                        cdata["force_keyframe"] = False
                        if kind == "keyframe":
                            cdata["delta_chain_count"] = 0
                        elif kind == "delta":
                            cdata["delta_chain_count"] = int(cdata.get("delta_chain_count", 0)) + 1
                        bytes_sent = int(send_plan[idx].get("sent_bytes") or 0)
                        now_ms = wall_clock_ms()
                        bytes_window = cdata.get("bytes_window", [])
                        if not isinstance(bytes_window, list):
                            bytes_window = []
                        bytes_window.append((now_ms, bytes_sent))
                        cutoff_ms = now_ms - 1000
                        bytes_window = [(ts, b) for (ts, b) in bytes_window if ts >= cutoff_ms]
                        cdata["bytes_window"] = bytes_window
                        bytes_per_sec = sum(int(b) for (_, b) in bytes_window)
                        add_sample("client_bps_samples", float(bytes_per_sec))
                        if bytes_per_sec > client_bps_budget:
                            metrics["broadcast_payload_budget_exceeded"] += 1
            metrics["broadcast_key_frames"] += keyframe_sends
            metrics["broadcast_delta_frames"] += delta_sends
            metrics["broadcast_keepalive_frames"] += keepalive_sends

            if hud_metrics:
                metrics_payload = envelope(
                    MSG_NET_METRICS,
                    metrics=hud_metrics,
                    clock="unix_ms",
                    seq=current_seq,
                    server_timestamp=server_timestamp,
                )
                for item in send_plan:
                    try:
                        await send_gameplay_frame(
                            item["websocket"],
                            item.get("rtc_state_channel"),
                            str(item.get("transport_active", "ws")),
                            str(item.get("codec", "json")),
                            str(item.get("rtc_codec", "json")),
                            metrics_payload,
                        )
                        metrics["broadcast_metrics_frames"] += 1
                    except Exception:
                        pass
            add_sample("broadcast_loop_duration_samples_ms", (time.perf_counter() - loop_started) * 1000.0)

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

    async def status_snapshot_loop():
        while True:
            await asyncio.sleep(1.0)
            enqueue_status_snapshot()

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
                "last_state_seq": -1,
                "codec": "json",
                "webrtc_supported": False,
                "webrtc_offered": False,
                "transport_active": "ws",
                "rtc_codec": "json",
                "strict_input_mode": False,
                "expected_input_tick": -1,
                "input_frame_buffer": {},
                "delta_chain_count": 0,
                "bytes_window": [],
                "force_keyframe": False,
                "rtc_peer": None,
                "rtc_input_channel": None,
                "rtc_state_channel": None,
            }
        enqueue_status_snapshot()

        await send_json(websocket, envelope(MSG_CLIENT_ID, client_id=client_id))

        try:
            async for raw in websocket:
                metrics["messages_received"] += 1
                with tracking_lock:
                    if client_id in clients:
                        clients[client_id]["last_seen"] = time.time()
                try:
                    data = decode_client_payload(raw)
                except (json.JSONDecodeError, ValueError, TypeError, UnicodeDecodeError):
                    metrics["messages_invalid"] += 1
                    await send_json(websocket, envelope(MSG_ERROR, message="invalid payload"))
                    continue
                err = validate_client_message(data)
                if err:
                    metrics["messages_invalid"] += 1
                    await send_json(websocket, envelope(MSG_ERROR, message=err))
                    continue

                msg_type = data["type"]

                if msg_type == MSG_HELLO:
                    requested_codec = data.get("encoding", data.get("ws_codec", "json"))
                    requested_rtc_codec = str(data.get("rtc_codec", "json")).lower()
                    ws_codec = resolve_ws_codec(requested_codec, msgpack is not None)
                    rtc_codec = resolve_ws_codec(requested_rtc_codec, msgpack is not None)
                    with tracking_lock:
                        if client_id in clients:
                            clients[client_id]["codec"] = ws_codec
                    client_webrtc_supported = bool(data.get("webrtc_supported", False))
                    client_strict_requested = bool(data.get("strict_input_mode", False))
                    with tracking_lock:
                        if client_id in clients:
                            clients[client_id]["webrtc_supported"] = client_webrtc_supported
                            clients[client_id]["webrtc_offered"] = bool(rtc_available and client_webrtc_supported)
                            clients[client_id]["rtc_codec"] = rtc_codec
                            clients[client_id]["strict_input_mode"] = bool(strict_input_mode and client_strict_requested)
                    await send_json(
                        websocket,
                        envelope(
                            MSG_HELLO_ACK,
                            server="bombermarv",
                            ws_version=WS_SERVER_VERSION,
                            webrtc_offered=bool(rtc_available and client_webrtc_supported),
                            webrtc_enabled=bool(rtc_available),
                            encoding=ws_codec,
                            ws_codec=ws_codec,
                            rtc_codec=rtc_codec,
                            strict_input_mode=bool(strict_input_mode and client_strict_requested),
                            input_lead_ticks=input_lead_ticks,
                            transport_active="ws",
                            metrics_clock="unix_ms",
                        ),
                    )
                    if rtc_available and client_webrtc_supported:
                        try:
                            await maybe_start_rtc_for_client(client_id)
                        except Exception as exc:
                            metrics["rtc_failed_events"] += 1
                            await send_json(websocket, envelope(MSG_RTC_FAILED, reason=f"rtc_offer_failed:{exc}"))
                    continue

                if msg_type == MSG_REQUEST_SLOT_LIST:
                    slot_info = build_slot_list()
                    await send_json(websocket, envelope(MSG_SLOT_LIST, **slot_info))
                    enqueue_status_snapshot()
                    continue

                if msg_type == MSG_REQUEST_KEYFRAME:
                    metrics["input_keyframe_requests"] += 1
                    with tracking_lock:
                        if client_id in clients:
                            clients[client_id]["last_state_seq"] = -1
                            clients[client_id]["force_keyframe"] = True
                    continue

                if msg_type == MSG_SET_NAME:
                    name_value = str(data.get("name", "")).strip()
                    with tracking_lock:
                        if client_id in clients:
                            clients[client_id]["display_name"] = name_value[:20] if name_value else None
                    slot_info = build_slot_list()
                    await send_json(websocket, envelope(MSG_SLOT_LIST, **slot_info))
                    enqueue_status_snapshot()
                    await broadcast_slot_list()
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
                        enqueue_status_snapshot()
                        await broadcast_slot_list()
                        continue
                    with tracking_lock:
                        clients[client_id]["slot"] = requested_slot
                        clients[client_id]["registered"] = True
                        clients[client_id]["last_state_seq"] = -1
                        if requested_name:
                            clients[client_id]["display_name"] = requested_name[:20]
                        clients[client_id]["players"] = [requested_slot]
                        players[requested_slot] = {
                            "client_id": client_id,
                            "keys": {"up": 0, "down": 0, "left": 0, "right": 0, "bomb": 0},
                        }
                    enqueue_input_event(
                        {
                            "type": "player_joined",
                            "client_id": client_id,
                            "slot": requested_slot,
                            "ws_received_timestamp": int(time.time() * 1000),
                        }
                    )
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
                    enqueue_status_snapshot()
                    await broadcast_slot_list()
                    continue

                if msg_type == MSG_GAME_INPUT:
                    await process_game_input(client_id, data, source="ws", websocket=websocket)
                    continue

                if msg_type == MSG_RTC_ANSWER:
                    metrics["rtc_answer_received"] += 1
                    with tracking_lock:
                        cdata = clients.get(client_id)
                        pc = cdata.get("rtc_peer") if cdata else None
                    if not pc:
                        await send_json(websocket, envelope(MSG_RTC_FAILED, reason="rtc_peer_missing"))
                        continue
                    try:
                        await pc.setRemoteDescription(RTCSessionDescription(sdp=str(data.get("sdp", "")), type="answer"))
                    except Exception as exc:
                        metrics["rtc_failed_events"] += 1
                        await send_json(websocket, envelope(MSG_RTC_FAILED, reason=f"rtc_answer_invalid:{exc}"))
                    continue

                if msg_type == MSG_RTC_ICE_CANDIDATE:
                    metrics["rtc_ice_received"] += 1
                    with tracking_lock:
                        cdata = clients.get(client_id)
                        pc = cdata.get("rtc_peer") if cdata else None
                    candidate = data.get("candidate", {})
                    if not pc or not isinstance(candidate, dict):
                        continue
                    try:
                        raw_candidate = candidate.get("candidate")
                        if raw_candidate:
                            ice = RTCIceCandidate(
                                sdpMid=candidate.get("sdpMid"),
                                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                                candidate=str(raw_candidate),
                            )
                            await pc.addIceCandidate(ice)
                    except Exception:
                        pass
                    continue

                if msg_type == MSG_RTC_READY:
                    metrics["rtc_ready_events"] += 1
                    with tracking_lock:
                        cdata = clients.get(client_id)
                        if cdata:
                            cdata["transport_active"] = "rtc"
                    continue

                if msg_type == MSG_RTC_FAILED:
                    metrics["rtc_failed_events"] += 1
                    with tracking_lock:
                        cdata = clients.get(client_id)
                        if cdata:
                            cdata["transport_active"] = "ws"
                    continue

                if msg_type == MSG_PING:
                    await send_json(websocket, envelope(MSG_PONG, server_timestamp=int(time.time() * 1000)))
        except websockets.ConnectionClosed:
            logger.info("WebSocket closed for client id=%s", client_id)
        except Exception as exc:
            logger.exception("Error in client handler id=%s: %s", client_id, exc)
        finally:
            metrics["connections_closed"] += 1
            rtc_peer_to_close = None
            with tracking_lock:
                cdata = clients.pop(client_id, None)
                if cdata:
                    rtc_peer_to_close = cdata.get("rtc_peer")
                    for player_id in cdata["players"]:
                        players.pop(player_id, None)
            with slots_lock:
                for slot_id, cid in list(slots.items()):
                    if cid == client_id:
                        slots[slot_id] = None
                        logger.info("Released slot %s for client %s", slot_id, client_id)
            if rtc_peer_to_close is not None:
                try:
                    await rtc_peer_to_close.close()
                except Exception:
                    pass
            enqueue_status_snapshot()
            try:
                await broadcast_slot_list()
            except Exception:
                pass

    async def handle_versions(request):
        return web.json_response(
            {
                "ws_server": WS_SERVER_VERSION,
                "http_server": HTTP_SERVER_VERSION,
                "rtc_enabled": rtc_enabled,
                "rtc_force_ws": rtc_force_ws,
                "rtc_runtime_available": rtc_available,
                "strict_input_mode": strict_input_mode,
                "input_lead_ticks": input_lead_ticks,
            }
        )

    async def handle_config(request):
        import bm_params

        return web.json_response(
            {
                "send_on_change": bm_params.SEND_ON_CHANGE,
                "periodic_sending": bm_params.PERIODIC_SENDING,
                "min_send_frequency": bm_params.MIN_SEND_FREQUENCY,
                "max_send_frequency": bm_params.MAX_SEND_FREQUENCY,
                "rtc_enabled": rtc_enabled,
                "rtc_force_ws": rtc_force_ws,
                "rtc_available_runtime": rtc_available,
                "strict_input_mode": strict_input_mode,
                "input_lead_ticks": input_lead_ticks,
                "input_late_window_ticks": late_tick_window,
                "max_delta_chain": max_delta_chain,
                "client_bps_budget": client_bps_budget,
            }
        )

    async def handle_status(request):
        return web.json_response(build_status_snapshot())

    async def handle_metrics(request):
        result = dict(metrics)
        sample_keys = (
            "state_reader_wait_samples_ms",
            "state_queue_age_samples_ms",
            "broadcast_loop_duration_samples_ms",
            "broadcast_send_duration_samples_ms",
            "broadcast_payload_bytes_samples",
            "input_tick_apply_age_samples",
            "client_bps_samples",
        )
        percentiles: Dict[str, Dict[str, float]] = {}
        for key in sample_keys:
            values = metrics.get(key, [])
            if not isinstance(values, list):
                continue
            percentiles[key] = {
                "count": float(len(values)),
                "avg": round(float(statistics.fmean(values)), 3) if values else 0.0,
                "p50": round(_percentile(values, 50), 3),
                "p95": round(_percentile(values, 95), 3),
                "p99": round(_percentile(values, 99), 3),
            }
        result["percentiles"] = percentiles
        return web.json_response(result)

    async def handle_health(request):
        return web.json_response({"status": "ok", "timestamp": int(time.time() * 1000)})

    def _mount_client_static(app: web.Application) -> None:
        from bm_paths import find_client_static_dir

        static_dir = find_client_static_dir()
        if not static_dir:
            return
        index_path = os.path.join(static_dir, "index.html")

        async def handle_index(_request):
            return web.FileResponse(index_path)

        async def handle_asset(request):
            rel = request.match_info["tail"]
            root = os.path.normpath(static_dir)
            full = os.path.normpath(os.path.join(static_dir, rel))
            try:
                inside = os.path.commonpath([root, full]) == root
            except ValueError:
                inside = False
            if not inside or not os.path.isfile(full):
                raise web.HTTPNotFound()
            return web.FileResponse(full)

        app.router.add_get("/", handle_index)
        app.router.add_get("/{tail:.*}", handle_asset)
        logger.info("Serving web client from %s", static_dir)

    def start_http_server():
        app = web.Application()
        app.router.add_get("/health", handle_health)
        app.router.add_get("/versions", handle_versions)
        app.router.add_get("/config", handle_config)
        app.router.add_get("/status", handle_status)
        app.router.add_get("/metrics", handle_metrics)
        _mount_client_static(app)
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
        aio_loop_holder.clear()
        aio_loop_holder.append(asyncio.get_running_loop())
        state_wakeup_holder.clear()
        state_wakeup_holder.append(asyncio.Event())
        threading.Thread(target=start_http_server, daemon=True, name="http-server").start()
        asyncio.create_task(broadcast_loop())
        asyncio.create_task(cleanup_stale_clients_loop())
        asyncio.create_task(status_snapshot_loop())
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

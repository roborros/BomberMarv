"""Wire protocol helpers for LAN websocket communication."""

from __future__ import annotations

from typing import Any, Dict, Optional

PROTOCOL_VERSION = 2

MSG_HELLO = "hello"
MSG_CLIENT_ID = "client_id"
MSG_REQUEST_SLOT_LIST = "request_slot_list"
MSG_SLOT_LIST = "slot_list"
MSG_SELECT_SLOT = "select_slot"
MSG_REGISTRATION_CONFIRMED = "registration_confirmed"
MSG_REGISTRATION_REJECTED = "registration_rejected"
MSG_GAME_INPUT = "game_input"
MSG_GAMESTATE = "gamestate"
MSG_GAMESTATE_DELTA = "gamestate_delta"
MSG_INPUT_ACK = "input_ack"
MSG_PING = "ping"
MSG_PONG = "pong"
MSG_ERROR = "error"
MSG_SET_NAME = "set_name"
MSG_HELLO_ACK = "hello_ack"
MSG_RTC_OFFER = "rtc_offer"
MSG_RTC_ANSWER = "rtc_answer"
MSG_RTC_ICE_CANDIDATE = "rtc_ice_candidate"
MSG_RTC_READY = "rtc_ready"
MSG_RTC_FAILED = "rtc_failed"

ALLOWED_CLIENT_MESSAGES = {
    MSG_HELLO,
    MSG_REQUEST_SLOT_LIST,
    MSG_SELECT_SLOT,
    MSG_GAME_INPUT,
    MSG_PING,
    MSG_SET_NAME,
    MSG_RTC_ANSWER,
    MSG_RTC_ICE_CANDIDATE,
    MSG_RTC_READY,
    MSG_RTC_FAILED,
}


def envelope(message_type: str, **payload: Any) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"type": message_type, "protocol": PROTOCOL_VERSION}
    msg.update(payload)
    return msg


def validate_client_message(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return "message must be an object"
    message_type = data.get("type")
    if message_type not in ALLOWED_CLIENT_MESSAGES:
        return f"unsupported message type: {message_type}"
    protocol = data.get("protocol")
    if protocol is not None and protocol != PROTOCOL_VERSION:
        return f"protocol mismatch: expected {PROTOCOL_VERSION}, got {protocol}"
    if message_type == MSG_SELECT_SLOT:
        slot = data.get("slot")
        if not isinstance(slot, int):
            return "select_slot.slot must be an integer"
    if message_type == MSG_GAME_INPUT:
        tick_id = data.get("tick_id")
        if tick_id is not None and (not isinstance(tick_id, int) or tick_id < 0):
            return "game_input.tick_id must be a non-negative integer"
        game_input = data.get("input")
        input_frame = data.get("input_frame")
        if game_input is None and input_frame is None:
            return "game_input must include input array or input_frame object"
        if game_input is not None:
            if not isinstance(game_input, list):
                return "game_input.input must be an array"
            if len(game_input) < 7:
                return "game_input.input must include client and player state"
        if input_frame is not None:
            if not isinstance(input_frame, dict):
                return "game_input.input_frame must be an object"
            player_id = input_frame.get("player_id")
            if not isinstance(player_id, int):
                return "game_input.input_frame.player_id must be an integer"
            for key_name in ("up", "down", "left", "right", "bomb"):
                value = input_frame.get(key_name)
                if value not in (0, 1, True, False):
                    return f"game_input.input_frame.{key_name} must be 0 or 1"
    if message_type in (MSG_SELECT_SLOT, MSG_SET_NAME):
        name = data.get("name")
        if name is not None:
            if not isinstance(name, str):
                return "name must be a string"
            if len(name.strip()) > 20:
                return "name must be <= 20 characters"
    if message_type == MSG_RTC_ANSWER:
        sdp = data.get("sdp")
        sdp_type = data.get("sdp_type")
        if not isinstance(sdp, str) or not sdp:
            return "rtc_answer.sdp must be a non-empty string"
        if sdp_type != "answer":
            return "rtc_answer.sdp_type must be 'answer'"
    if message_type == MSG_RTC_ICE_CANDIDATE:
        candidate = data.get("candidate")
        if not isinstance(candidate, dict):
            return "rtc_ice_candidate.candidate must be an object"
    if message_type == MSG_RTC_READY:
        transport = data.get("transport")
        if transport is not None and transport not in ("rtc", "ws"):
            return "rtc_ready.transport must be rtc or ws"
    if message_type == MSG_RTC_FAILED:
        reason = data.get("reason")
        if reason is not None and not isinstance(reason, str):
            return "rtc_failed.reason must be a string"
    return None

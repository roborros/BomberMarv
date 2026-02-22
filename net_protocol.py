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

ALLOWED_CLIENT_MESSAGES = {
    MSG_HELLO,
    MSG_REQUEST_SLOT_LIST,
    MSG_SELECT_SLOT,
    MSG_GAME_INPUT,
    MSG_PING,
    MSG_SET_NAME,
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
        game_input = data.get("input")
        if not isinstance(game_input, list):
            return "game_input.input must be an array"
        if len(game_input) < 7:
            return "game_input.input must include client and player state"
    if message_type in (MSG_SELECT_SLOT, MSG_SET_NAME):
        name = data.get("name")
        if name is not None:
            if not isinstance(name, str):
                return "name must be a string"
            if len(name.strip()) > 20:
                return "name must be <= 20 characters"
    return None

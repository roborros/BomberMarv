"""Wire protocol helpers for LAN websocket communication."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
MSG_REQUEST_KEYFRAME = "request_keyframe"
MSG_STATE_KEEPALIVE = "state_keepalive"
MSG_NET_METRICS = "net_metrics"

# How far ahead of the host sim tick a client may schedule input before it is applied immediately.
MAX_INPUT_APPLY_LEAD_TICKS = 4

GAMEPLAY_UPLINK_TYPES = frozenset({MSG_GAME_INPUT})

GAMEPLAY_DELTA_KEYS = (
    "time",
    "state",
    "bombs",
    "explosions",
    "powerups",
    "crushing_walls",
    "local_player_count",
    "boss_fight_winner",
    "trophy_win_threshold",
    "result_prompt",
    "ai_count",
    "grid_width",
    "grid_height",
    "_sim_tick",
    "_host_published_at_ms",
)
KEEPALIVE_ONLY_KEYS = frozenset({"time", "_sim_tick", "_host_published_at_ms"})
WIRE_METRICS_KEYS = frozenset({"_net_metrics", "_hud_metrics"})
MAX_BOARD_PATCH_CELLS = 24

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
    MSG_REQUEST_KEYFRAME,
}

CONTROL_UPLINK_TYPES = ALLOWED_CLIENT_MESSAGES - GAMEPLAY_UPLINK_TYPES


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
    if message_type == MSG_REQUEST_KEYFRAME:
        seq = data.get("seq")
        if seq is not None and (not isinstance(seq, int) or seq < -1):
            return "request_keyframe.seq must be an integer >= -1"
    if message_type == MSG_HELLO:
        encoding = data.get("encoding", data.get("ws_codec"))
        if encoding is not None and encoding not in ("json", "msgpack"):
            return "hello.encoding must be json or msgpack"
        rtc_codec = data.get("rtc_codec")
        if rtc_codec is not None and rtc_codec not in ("json", "msgpack"):
            return "hello.rtc_codec must be json or msgpack"
    return None


def resolve_ws_codec(requested: Any, msgpack_available: bool) -> str:
    name = str(requested or "json").strip().lower()
    if name in ("msgpack", "messagepack") and msgpack_available:
        return "msgpack"
    return "json"


def classify_state_diff(delta: Dict[str, Any]) -> str:
    if not delta:
        return "unchanged"
    keys = set(delta.keys()) - WIRE_METRICS_KEYS
    if not keys:
        return "unchanged"
    if keys.issubset(KEEPALIVE_ONLY_KEYS):
        return "keepalive"
    return "gameplay"


def _players_are_patchable(players: Any) -> bool:
    if not isinstance(players, list):
        return False
    ids = []
    for player in players:
        if not isinstance(player, dict) or player.get("id") is None:
            return False
        ids.append(player.get("id"))
    return len(ids) == len(set(ids))


def diff_players(previous_players: Any, current_players: Any) -> Dict[str, Any]:
    """Entity-grain player delta: patches + removals, or a full list fallback."""
    if previous_players == current_players:
        return {}
    if not _players_are_patchable(current_players) or (
        previous_players is not None and not _players_are_patchable(previous_players)
    ):
        return {"players": current_players}
    previous_list = previous_players if isinstance(previous_players, list) else []
    current_list = current_players if isinstance(current_players, list) else []
    prev_by_id = {player["id"]: player for player in previous_list}
    curr_by_id = {player["id"]: player for player in current_list}
    removed = sorted(id_ for id_ in prev_by_id.keys() if id_ not in curr_by_id)
    patches: List[Dict[str, Any]] = []
    for player_id, player in curr_by_id.items():
        previous = prev_by_id.get(player_id)
        if previous is None:
            patches.append(dict(player))
            continue
        patch: Dict[str, Any] = {"id": player_id}
        changed = False
        for key, value in player.items():
            if key == "id":
                continue
            if previous.get(key) != value:
                patch[key] = value
                changed = True
        if changed:
            patches.append(patch)
    if not patches and not removed:
        return {}
    result: Dict[str, Any] = {}
    if patches:
        result["player_patches"] = patches
    if removed:
        result["player_removed"] = removed
    return result


def apply_player_delta(base_players: Any, delta: Dict[str, Any]) -> List[Any]:
    if "players" in delta:
        players = delta.get("players") or []
        return [dict(player) if isinstance(player, dict) else player for player in players]
    players = [dict(player) if isinstance(player, dict) else player for player in (base_players or [])]
    removed = set(delta.get("player_removed") or [])
    if removed:
        players = [player for player in players if not (isinstance(player, dict) and player.get("id") in removed)]
    by_id = {
        player.get("id"): index
        for index, player in enumerate(players)
        if isinstance(player, dict) and player.get("id") is not None
    }
    for patch in delta.get("player_patches") or []:
        if not isinstance(patch, dict) or patch.get("id") is None:
            continue
        player_id = patch["id"]
        index = by_id.get(player_id)
        if index is None:
            players.append(dict(patch))
            by_id[player_id] = len(players) - 1
        else:
            merged = dict(players[index])
            merged.update(patch)
            players[index] = merged
    return players


def diff_board(previous_board: Any, current_board: Any, max_patches: int = MAX_BOARD_PATCH_CELLS) -> Dict[str, Any]:
    if previous_board == current_board:
        return {}
    if not isinstance(previous_board, list) or not isinstance(current_board, list):
        return {"board": current_board}
    if not previous_board or not current_board:
        return {"board": current_board}
    if len(previous_board) != len(current_board) or len(previous_board[0]) != len(current_board[0]):
        return {"board": current_board}
    patches: List[List[int]] = []
    for y, row in enumerate(current_board):
        prev_row = previous_board[y]
        if not isinstance(row, list) or not isinstance(prev_row, list):
            return {"board": current_board}
        for x, cell in enumerate(row):
            if prev_row[x] != cell:
                patches.append([x, y, cell])
                if len(patches) > max_patches:
                    return {"board": current_board}
    if not patches:
        return {}
    return {"board_patches": patches}


def apply_board_patches(board: Any, patches: Any) -> List[List[Any]]:
    next_board = [list(row) for row in (board or [])]
    for item in patches or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        x, y, cell = item[0], item[1], item[2]
        if isinstance(y, int) and isinstance(x, int) and 0 <= y < len(next_board) and 0 <= x < len(next_board[y]):
            next_board[y][x] = cell
    return next_board


def build_state_delta(previous_state: Dict[str, Any], current_state: Dict[str, Any]) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    for key in GAMEPLAY_DELTA_KEYS:
        if previous_state.get(key) != current_state.get(key):
            delta[key] = current_state.get(key)
    delta.update(diff_players(previous_state.get("players"), current_state.get("players")))
    delta.update(diff_board(previous_state.get("board"), current_state.get("board")))
    return delta


def apply_state_delta(base_state: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a gameplay delta, including entity-grain player/board patches."""
    merged = dict(base_state)
    for key, value in delta.items():
        if key in ("player_patches", "player_removed", "board_patches", "players", "board"):
            continue
        merged[key] = value
    if any(key in delta for key in ("players", "player_patches", "player_removed")):
        merged["players"] = apply_player_delta(base_state.get("players"), delta)
    if "board" in delta:
        board = delta.get("board") or []
        merged["board"] = [list(row) for row in board]
    elif "board_patches" in delta:
        merged["board"] = apply_board_patches(base_state.get("board"), delta.get("board_patches"))
    return merged


def strip_wire_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in state.items() if key not in WIRE_METRICS_KEYS}


def apply_keepalive_to_state(state: Dict[str, Any], keepalive: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(state)
    for key in KEEPALIVE_ONLY_KEYS:
        if key in keepalive and keepalive[key] is not None:
            updated[key] = keepalive[key]
    return updated


def is_gameplay_uplink(message_type: Any) -> bool:
    return message_type in GAMEPLAY_UPLINK_TYPES


def resolve_input_tick(expected_tick: int, tick_id: int) -> Tuple[str, int, int]:
    """Latest-wins tick sequencing for sticky key state.

    Returns (action, next_expected_tick, skipped_count) where action is
    ``apply`` or ``drop``. A gap (lost RTC packet) skips the hole instead of
    stalling later inputs. Repeating the last applied tick is allowed because
    clients may send several packets during one host sim tick.
    """
    if expected_tick < 0:
        return ("apply", tick_id + 1, 0)
    if tick_id < expected_tick:
        if tick_id == expected_tick - 1:
            return ("apply", expected_tick, 0)
        return ("drop", expected_tick, 0)
    skipped = max(0, tick_id - expected_tick)
    return ("apply", tick_id + 1, skipped)


def should_buffer_remote_input(apply_tick: Optional[int], current_tick: int, max_lead: int = MAX_INPUT_APPLY_LEAD_TICKS) -> bool:
    """Buffer only when apply_tick is a small number of host sim ticks in the future."""
    if apply_tick is None:
        return False
    lead = int(apply_tick) - int(current_tick)
    return 0 < lead <= max_lead

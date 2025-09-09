"""
Game state serialization for WebSocket transmission
Converts game objects to JSON-serializable dictionaries
"""
import json
from typing import Dict, List, Any
from dataclasses import asdict
from rendering_backend import DrawCommand

def serialize_player(player) -> Dict[str, Any]:
    """Serialize a player object"""
    return {
        'id': id(player),  # Use object ID as unique identifier
        'name': player.name,
        'pos': {'x': float(player.pos.x), 'y': float(player.pos.y)},
        'color': list(player.color),
        'alive': player.alive,
        'draw_radius': player.draw_radius,
        'animation_time': player.animation_time,
        'quad_damage': player.quad_damage,
        'quad_damage_start_time': player.quad_damage_start_time if player.quad_damage else 0,
        'death_animation_time': player.death_animation_time,
        'bomb_capacity': player.bomb_capacity,
        'fire_power': player.fire_power,
        'trophies': player.trophies,
        'direction': {'x': float(player.direction.x), 'y': float(player.direction.y)} if hasattr(player, 'direction') else {'x': 0, 'y': 0}
    }

def serialize_bomb(bomb) -> Dict[str, Any]:
    """Serialize a bomb object"""
    return {
        'id': id(bomb),
        'x': bomb.x,
        'y': bomb.y,
        'start_time': bomb.start_time,
        'fire_power': bomb.fire_power,
        'owner_id': id(bomb.owner),
        'quad_damage': bomb.quad_damage
    }

def serialize_explosion(explosion) -> Dict[str, Any]:
    """Serialize an explosion object"""
    return {
        'id': id(explosion),
        'cells': explosion.cells,
        'start_time': explosion.start_time,
        'quad_damage': explosion.quad_damage
    }

def serialize_powerup(powerup) -> Dict[str, Any]:
    """Serialize a powerup object"""
    return {
        'id': id(powerup),
        'x': powerup.x,
        'y': powerup.y,
        'type': powerup.type,
        'spawn_time': powerup.spawn_time
    }

def serialize_game_state(game) -> Dict[str, Any]:
    """Serialize the complete game state"""
    return {
        'game_state': game.game_state,
        'current_time': game.current_time,
        'game_start_time': game.game_start_time,
        'board': game.board,  # 2D array of integers
        'players': [serialize_player(player) for player in game.players],
        'bombs': [serialize_bomb(bomb) for bomb in game.bombs],
        'explosions': [serialize_explosion(explosion) for explosion in game.explosions],
        'powerups': [serialize_powerup(powerup) for powerup in game.powerups],
        'crushing_walls_active': game.crushing_walls_active,
        'crushing_walls_index': game.crushing_walls_index if game.crushing_walls_active else 0,
        # Game constants needed by client
        'constants': {
            'CELL_SIZE': 100,  # Fixed for web client
            'GRID_WIDTH': len(game.board[0]) if game.board else 0,
            'GRID_HEIGHT': len(game.board) if game.board else 0,
            'BASE_WIDTH': len(game.board[0]) * 100 if game.board else 1500,
            'BASE_HEIGHT': len(game.board) * 100 if game.board else 1500,
            'BOMB_PULSE_AMPLITUDE': 0.1,
            'BOMB_PULSE_SPEED': 300.0,
            'BOMB_BASE_RADIUS': 45,
            'EXPLOSION_DURATION': 400,
            'FLAME_ARM_THICKNESS_RATIO': 0.9,
            'SHOW_PLAYER_DIRECTIONS': True
        }
    }

def serialize_draw_commands(commands: List[DrawCommand]) -> List[Dict[str, Any]]:
    """Serialize drawing commands for transmission"""
    serialized = []
    for cmd in commands:
        cmd_dict = asdict(cmd)
        cmd_dict['type'] = cmd.__class__.__name__
        serialized.append(cmd_dict)
    return serialized

def serialize_input_event(event_type: str, key: str, player_id: int = 0) -> Dict[str, Any]:
    """Serialize input events for transmission"""
    return {
        'type': event_type,  # 'keydown' or 'keyup'
        'key': key,
        'player_id': player_id,
        'timestamp': 0  # Will be set by client
    }

class GameStateEncoder(json.JSONEncoder):
    """Custom JSON encoder for game state"""
    
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

def to_json(data: Dict[str, Any]) -> str:
    """Convert data to JSON string"""
    return json.dumps(data, cls=GameStateEncoder, separators=(',', ':'))

def from_json(json_str: str) -> Dict[str, Any]:
    """Parse JSON string to dictionary"""
    return json.loads(json_str)
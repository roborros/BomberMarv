export interface PlayerState {
    id: number;
    name: string;
    x: number;
    y: number;
    color: [number, number, number];
    alive: boolean;
    direction: [number, number];
    quad_damage: boolean;
    death_anim_time: number | null;
}

export interface BombState {
    x: number;
    y: number;
    start_time: number;
    fire_power: number;
    quad_damage: boolean;
}

export interface ExplosionState {
    cells: [number, number][];
    start_time: number;
    quad_damage: boolean;
}

export interface PowerUpState {
    x: number;
    y: number;
    type: string;
}

export interface CrushingWallsState {
    active: boolean;
    index: number;
}

export interface GameState {
    time: number;
    state: string;
    board: number[][];
    players: PlayerState[];
    bombs: BombState[];
    explosions: ExplosionState[];
    powerups: PowerUpState[];
    crushing_walls: CrushingWallsState;
    _net_metrics?: {
        host_fps_5s?: number;
        avg_input_apply_ms?: number;
    };
}

export interface ProtocolEnvelope {
    type: string;
    protocol?: number;
}

export interface ClientIdMessage extends ProtocolEnvelope {
    type: 'client_id';
    client_id: number;
}

export interface SlotListMessage extends ProtocolEnvelope {
    type: 'slot_list';
    slots: Record<string, boolean>;
    slot_reasons?: Record<string, 'local' | 'remote'>;
}

export interface RegistrationConfirmedMessage extends ProtocolEnvelope {
    type: 'registration_confirmed';
    client_id: number;
    slot: number;
    player_ids: number[];
    message?: string;
}

export interface RegistrationRejectedMessage extends ProtocolEnvelope {
    type: 'registration_rejected';
    message: string;
}

export interface GameStateMessage extends ProtocolEnvelope {
    type: 'gamestate';
    data: GameState;
    server_timestamp?: number;
    seq?: number;
}

export interface InputAckMessage extends ProtocolEnvelope {
    type: 'input_ack';
    client_id: number;
    original_timestamp?: number;
    server_timestamp: number;
}

export interface PongMessage extends ProtocolEnvelope {
    type: 'pong';
    server_timestamp?: number;
}

export interface ErrorMessage extends ProtocolEnvelope {
    type: 'error';
    message: string;
}

export type ServerMessage =
    | ClientIdMessage
    | SlotListMessage
    | RegistrationConfirmedMessage
    | RegistrationRejectedMessage
    | GameStateMessage
    | InputAckMessage
    | PongMessage
    | ErrorMessage;

export function isServerMessage(msg: unknown): msg is ServerMessage {
    if (typeof msg !== 'object' || msg === null) return false;
    const maybe = msg as { type?: unknown };
    return typeof maybe.type === 'string';
}

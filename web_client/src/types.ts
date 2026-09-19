export interface PlayerState {
    id: number;
    name: string;
    x: number;
    y: number;
    color: [number, number, number];
    alive: boolean;
    direction: [number, number];
    quad_damage: boolean;
    trophies?: number;
    death_time_rel_ms?: number | null;
    fire_power_at_death?: number | null;
    bomb_capacity_at_death?: number | null;
    death_anim_time: number | null;
    fire_power?: number;
    bomb_capacity?: number;
    walls_destroyed?: number;
    players_killed?: number;
    powerups_collected?: number;
    quad_damage_collected?: number;
    cells_walked?: number;
    total_walls_destroyed?: number;
    total_players_killed?: number;
    total_powerups_collected?: number;
    total_quad_damage_collected?: number;
    total_cells_walked?: number;
    team?: number;
    owner_client_id?: number | null;
    owner_client_player_id?: number | null;
    is_ai?: boolean;
    shield_until?: number;
    boss_lives_remaining?: number;
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

export interface BossFightWinner {
    name: string;
    is_ai: boolean;
    color: [number, number, number];
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
    boss_fight_winner?: BossFightWinner | null;
    local_player_count?: number
    grid_width?: number
    grid_height?: number
    _sim_tick?: number
    _net_metrics?: {
        clock?: string
        meaning?: string
        host_fps_5s?: number
        host_render_fps_5s?: number
        avg_input_apply_ms?: number
        input_apply_p50_ms?: number
        input_apply_p95_ms?: number
        input_apply_p99_ms?: number
        input_queue_delay_avg_ms?: number
        input_queue_delay_p50_ms?: number
        input_queue_delay_p95_ms?: number
        input_queue_delay_p99_ms?: number
        sim_step_avg_ms?: number
        sim_step_p95_ms?: number
        sim_tick?: number
        input_tick_reused?: number
        input_tick_buffered?: number
        input_tick_apply_lag_p95?: number
    }
    trophy_win_threshold?: number
    result_prompt?: string
    ai_count?: number
    _host_published_at_ms?: number;
}

export type BoardPatch = [number, number, number]

export interface PlayerPatch extends Partial<PlayerState> {
    id: number
}

export interface GameStateDelta extends Partial<GameState> {
    player_patches?: PlayerPatch[]
    player_removed?: number[]
    board_patches?: BoardPatch[]
}

export interface ProtocolEnvelope {
    type: string;
    protocol?: number;
}

export interface HelloAckMessage extends ProtocolEnvelope {
    type: 'hello_ack';
    server?: string;
    ws_version?: string;
    webrtc_offered?: boolean;
    webrtc_enabled?: boolean;
    rtc_codec?: 'json' | 'msgpack'
    encoding?: 'json' | 'msgpack'
    ws_codec?: 'json' | 'msgpack'
    metrics_clock?: string;
    strict_input_mode?: boolean;
    input_lead_ticks?: number;
    transport_active?: 'ws' | 'rtc';
}

export interface ClientIdMessage extends ProtocolEnvelope {
    type: 'client_id';
    client_id: number;
}

export interface SlotListMessage extends ProtocolEnvelope {
    type: 'slot_list';
    slots: Record<string, boolean>;
    slot_reasons?: Record<string, 'local' | 'remote'>;
    trophy_win_threshold?: number;
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
    tick_id?: number;
}

export interface GameStateDeltaMessage extends ProtocolEnvelope {
    type: 'gamestate_delta';
    base_seq: number;
    seq: number;
    server_timestamp?: number;
    tick_id?: number;
    delta: GameStateDelta;
}

export interface InputAckMessage extends ProtocolEnvelope {
    type: 'input_ack';
    client_id: number;
    original_timestamp?: number;
    server_timestamp: number;
    tick_id?: number;
    apply_tick_id?: number
    clock?: string
    rtt_clock?: string
}

export interface PongMessage extends ProtocolEnvelope {
    type: 'pong';
    server_timestamp?: number;
}

export interface ErrorMessage extends ProtocolEnvelope {
    type: 'error';
    message: string;
}

export interface StateKeepaliveMessage extends ProtocolEnvelope {
    type: 'state_keepalive'
    seq: number
    time?: number
    _sim_tick?: number
    _host_published_at_ms?: number
    server_timestamp?: number
    tick_id?: number
}

export interface NetMetricsMessage extends ProtocolEnvelope {
    type: 'net_metrics'
    metrics: NonNullable<GameState['_net_metrics']>
    clock?: string
    seq?: number
    server_timestamp?: number
}

export interface RtcOfferMessage extends ProtocolEnvelope {
    type: 'rtc_offer';
    sdp: string;
    sdp_type: 'offer';
}

export interface RtcAnswerMessage extends ProtocolEnvelope {
    type: 'rtc_answer';
    sdp: string;
    sdp_type: 'answer';
}

export interface RtcIceCandidatePayload {
    candidate?: string;
    sdpMid?: string | null;
    sdpMLineIndex?: number | null;
}

export interface RtcIceCandidateMessage extends ProtocolEnvelope {
    type: 'rtc_ice_candidate';
    candidate: RtcIceCandidatePayload;
}

export interface RtcReadyMessage extends ProtocolEnvelope {
    type: 'rtc_ready';
    transport?: 'ws' | 'rtc';
}

export interface RtcFailedMessage extends ProtocolEnvelope {
    type: 'rtc_failed';
    reason?: string;
}

export type ServerMessage =
    | ClientIdMessage
    | HelloAckMessage
    | SlotListMessage
    | RegistrationConfirmedMessage
    | RegistrationRejectedMessage
    | GameStateMessage
    | GameStateDeltaMessage
    | StateKeepaliveMessage
    | NetMetricsMessage
    | InputAckMessage
    | PongMessage
    | ErrorMessage
    | RtcOfferMessage
    | RtcIceCandidateMessage
    | RtcReadyMessage
    | RtcFailedMessage;

export function isServerMessage(msg: unknown): msg is ServerMessage {
    if (typeof msg !== 'object' || msg === null) return false;
    const maybe = msg as { type?: unknown };
    return typeof maybe.type === 'string';
}

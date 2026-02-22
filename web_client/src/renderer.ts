import type { GameState, PlayerState, BombState, ExplosionState, PowerUpState } from './types';

// Constants matching Python Game
const CELL_SIZE = 40; // Adjusted for browser viewing
const COLOR_BG = '#3C3C3C'; // (60, 60, 60)
const COLOR_INDESTRUCTIBLE = '#787878'; // (120, 120, 120)
const COLOR_DESTRUCTIBLE = '#C8C8C8'; // (200, 200, 200)

// Player colors - matching bm_params.py
const PLAYER_COLORS = [
    '#6496C8', // Light Blue (100, 150, 200)
    '#C89664', // Light Brown (200, 150, 100)
    '#96C864', // Light Green (150, 200, 100)
    '#C86496', // Light Pink  (200, 100, 150)
    '#64C896', // Light Teal  (100, 200, 150)
    '#9664C8'  // Light Purple (150, 100, 200)
];

const BOMB_COLOR = '#787878'; // (120, 120, 120)

export class Renderer {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private width: number = 0;
    private height: number = 0;

    // Interpolation state
    private lastState: GameState | null = null;
    private currentState: GameState | null = null;
    private lastStateTime: number = 0;
    private currentStateTime: number = 0;
    private interpolationDelayMs = 28;
    private lastArrivalIntervalMs = 16;

    constructor(canvas: HTMLCanvasElement) {
        this.canvas = canvas;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Could not get 2D context');
        this.ctx = context;
    }

    public render(state: GameState, serverTimestamp?: number, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number }) {
        const now = Date.now();

        // Update state history for interpolation
        if (state !== this.currentState) {
            this.lastState = this.currentState;
            this.lastStateTime = this.currentStateTime;
            this.currentState = state;
            const arrivalTime = typeof serverTimestamp === 'number' ? serverTimestamp : now;
            if (this.currentStateTime > 0) {
                const interval = Math.max(1, arrivalTime - this.currentStateTime);
                // Smooth observed network cadence.
                this.lastArrivalIntervalMs = this.lastArrivalIntervalMs * 0.85 + interval * 0.15;
                // Keep latency low on LAN/WLAN while absorbing jitter.
                this.interpolationDelayMs = Math.min(35, Math.max(20, this.lastArrivalIntervalMs * 1.5));
            }
            this.currentStateTime = arrivalTime;
        }

        // Update dimensions if needed based on board size
        if (state.board && state.board.length > 0) {
            const rows = state.board.length;
            const cols = state.board[0].length;
            const newWidth = cols * CELL_SIZE;
            const newHeight = rows * CELL_SIZE;

            if (this.width !== newWidth || this.height !== newHeight) {
                this.width = newWidth;
                this.height = newHeight;
                this.canvas.width = this.width;
                this.canvas.height = this.height;
            }
        }

        // Clear screen
        this.ctx.fillStyle = COLOR_BG;
        this.ctx.fillRect(0, 0, this.width, this.height);

        // Draw Board
        this.drawBoard(state.board);

        // Draw PowerUps
        state.powerups.forEach(p => this.drawPowerUp(p));

        // Draw Bombs
        state.bombs.forEach(b => this.drawBomb(b));

        // Draw Players
        const players = state.players;
        players.forEach(player => {
            // Find this player in last state for interpolation
            let prevPlayer: PlayerState | undefined;
            if (this.lastState) {
                prevPlayer = this.lastState.players.find(p => p.id === player.id);
            }
            this.drawPlayer(player, prevPlayer);
        });

        // Draw Explosions
        state.explosions.forEach(e => this.drawExplosion(e));

        // Draw UI/HUD (optional, could be HTML overlay)
        this.drawHUD(state, metrics);
    }

    private drawBoard(board: number[][]) {
        for (let y = 0; y < board.length; y++) {
            for (let x = 0; x < board[y].length; x++) {
                const cell = board[y][x];
                if (cell === 1) { // INDESTRUCTIBLE
                    this.ctx.fillStyle = COLOR_INDESTRUCTIBLE;
                    this.ctx.fillRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                    // Add bevel effect
                    this.ctx.strokeStyle = '#555';
                    this.ctx.lineWidth = 2;
                    this.ctx.strokeRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                } else if (cell === 2) { // DESTRUCTIBLE
                    this.ctx.fillStyle = COLOR_DESTRUCTIBLE;
                    this.ctx.fillRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                    // Add bevel effect
                    this.ctx.strokeStyle = '#999';
                    this.ctx.lineWidth = 2;
                    this.ctx.strokeRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);

                    // Detail lines
                    this.ctx.beginPath();
                    this.ctx.moveTo(x * CELL_SIZE + 5, y * CELL_SIZE + 5);
                    this.ctx.lineTo(x * CELL_SIZE + CELL_SIZE - 5, y * CELL_SIZE + CELL_SIZE - 5);
                    this.ctx.stroke();
                }
            }
        }
    }

    private drawPlayer(player: PlayerState, prevPlayer?: PlayerState) {
        if (!player.alive) return;

        const PYTHON_CELL_SIZE = 100;
        const SCALE = CELL_SIZE / PYTHON_CELL_SIZE;

        let px = player.x * SCALE;
        let py = player.y * SCALE;

        // Interpolation
        if (prevPlayer && this.lastStateTime > 0) {
            const now = Date.now();
            // Removed unused timeDiff

            // Simple approach: Interpolate from Prev -> Current based on elapsed time since 'current' arrived (but 'current' is our target).
            // Actually, for smoothness we want to be "between" frames.
            // But without knowing future frame, we can only interpolate between Last and Current.
            // If we are at 'now', and we received 'current' at 'currentStateTime'.
            // Ideally we render at 'now - delay'.
            // If 'now - delay' > 'currentStateTime', we are waiting for next frame (extrapolate or clamp).
            // If 'now - delay' < 'currentStateTime' but > 'lastStateTime', we interpolate.

            const renderTime = now - this.interpolationDelayMs;

            if (renderTime > this.lastStateTime && this.currentStateTime > this.lastStateTime) {
                // Determine phase
                // Normalized time between last and current? No, renderTime might be PAST current if delay is small.
                // Wait. lastStateTime < currentStateTime < now.
                // renderTime = now - 50ms.

                // If renderTime is between last and current:
                if (renderTime <= this.currentStateTime) {
                    const totalDuration = this.currentStateTime - this.lastStateTime;
                    const elapsed = renderTime - this.lastStateTime;
                    const alpha = elapsed / totalDuration;

                    const prevPx = prevPlayer.x * SCALE;
                    const prevPy = prevPlayer.y * SCALE;

                    px = prevPx + (px - prevPx) * alpha;
                    py = prevPy + (py - prevPy) * alpha;
                } else {
                    // renderTime > currentStateTime.
                    // We ran out of future buffer. Show current state (or extrapolate).
                    // Just show current.
                }
            }
        }

        const size = (PYTHON_CELL_SIZE * 0.85) * SCALE; // PLAYER_DRAW_SCALE = 0.85

        // Draw Shadow
        this.ctx.fillStyle = 'rgba(0,0,0,0.3)';
        this.ctx.beginPath();
        this.ctx.ellipse(px + size / 2, py + size - 5, size / 2, size / 4, 0, 0, Math.PI * 2);
        this.ctx.fill();

        // Draw Player Body
        const color = player.color ? `rgb(${player.color[0]},${player.color[1]},${player.color[2]})` : PLAYER_COLORS[player.id % PLAYER_COLORS.length];
        this.ctx.fillStyle = color;
        this.ctx.beginPath();
        // Backend pixels are already centered. Remove the + CELL_SIZE / 2 offset.
        this.ctx.arc(px, py, size / 2, 0, Math.PI * 2);
        this.ctx.fill();

        // Draw Outline
        this.ctx.strokeStyle = '#222';
        this.ctx.lineWidth = 2;
        this.ctx.stroke();

        // Eyes (direction)
        const dx = player.direction[0];
        const dy = player.direction[1];

        const eyeOffX = dx * 8;
        const eyeOffY = dy * 8;

        this.ctx.fillStyle = 'white';
        this.ctx.beginPath();
        this.ctx.arc(px + CELL_SIZE / 2 + eyeOffX - 6, py + CELL_SIZE / 2 + eyeOffY - 4, 4, 0, Math.PI * 2);
        this.ctx.arc(px + CELL_SIZE / 2 + eyeOffX + 6, py + CELL_SIZE / 2 + eyeOffY - 4, 4, 0, Math.PI * 2);
        this.ctx.fill();

        // Pupils
        this.ctx.fillStyle = 'black';
        this.ctx.beginPath();
        this.ctx.arc(px + CELL_SIZE / 2 + eyeOffX - 6 + dx * 2, py + CELL_SIZE / 2 + eyeOffY - 4 + dy * 2, 1.5, 0, Math.PI * 2);
        this.ctx.arc(px + CELL_SIZE / 2 + eyeOffX + 6 + dx * 2, py + CELL_SIZE / 2 + eyeOffY - 4 + dy * 2, 1.5, 0, Math.PI * 2);
        this.ctx.fill();

        // Determine name
        this.ctx.fillStyle = 'white';
        this.ctx.font = '10px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText(player.name || `P${player.id}`, px, py - size / 2 - 5);
    }

    private drawBomb(bomb: BombState) {
        const bx = bomb.x * CELL_SIZE;
        const by = bomb.y * CELL_SIZE;
        const size = (CELL_SIZE * 0.9);

        this.ctx.fillStyle = BOMB_COLOR;
        this.ctx.beginPath();
        this.ctx.arc(bx + CELL_SIZE / 2, by + CELL_SIZE / 2, size / 2, 0, Math.PI * 2);
        this.ctx.fill();

        // Pulse effect based on time?
        // For simple render just outline
        this.ctx.strokeStyle = 'black';
        this.ctx.lineWidth = 1;
        this.ctx.stroke();
    }

    private drawExplosion(explosion: ExplosionState) {
        // Removed unused SCALE
        this.ctx.fillStyle = 'rgba(255, 100, 50, 0.7)';
        explosion.cells.forEach(([gx, gy]) => {
            // These are grid coordinates!
            this.ctx.fillRect(gx * CELL_SIZE, gy * CELL_SIZE, CELL_SIZE, CELL_SIZE);
        });
    }

    private drawPowerUp(powerup: PowerUpState) {
        // powerup.x, powerup.y are grid coordinates
        const px = powerup.x * CELL_SIZE;
        const py = powerup.y * CELL_SIZE;
        const size = CELL_SIZE * 0.6;

        let color = 'yellow';
        let text = '?';

        if (powerup.type === 'fire') { color = 'orange'; text = 'F'; }
        else if (powerup.type === 'bomb') { color = 'gray'; text = 'B'; }
        else if (powerup.type === 'kick') { color = 'green'; text = 'K'; }
        else if (powerup.type === 'skull') { color = 'red'; text = 'S'; }
        else if (powerup.type === 'quad') { color = 'purple'; text = '4x'; }

        this.ctx.fillStyle = color;
        this.ctx.beginPath();
        this.ctx.arc(px + CELL_SIZE / 2, py + CELL_SIZE / 2, size / 2, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.fillStyle = 'white';
        this.ctx.font = 'bold 14px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(text, px + CELL_SIZE / 2, py + CELL_SIZE / 2);
    }

    private drawHUD(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number }) {
        this.ctx.fillStyle = 'white';
        this.ctx.font = '16px monospace';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(`State: ${state.state}`, 10, 20);
        this.ctx.fillText(`Time: ${(state.time / 1000).toFixed(1)}`, 10, 40);
        if (metrics?.latency5sMs !== undefined) {
            this.ctx.fillText(`Latency(5s): ${metrics.latency5sMs.toFixed(1)} ms`, 10, 60);
        }
        if (metrics?.fps5s !== undefined) {
            this.ctx.fillText(`Client FPS(5s): ${metrics.fps5s.toFixed(1)}`, 10, 80);
        }
        if (metrics?.hostFps5s !== undefined) {
            this.ctx.fillText(`Host FPS(5s): ${metrics.hostFps5s.toFixed(1)}`, 10, 100);
        }
    }
}

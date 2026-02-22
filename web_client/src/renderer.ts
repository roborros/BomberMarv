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
    private boardLayer: HTMLCanvasElement;
    private boardLayerCtx: CanvasRenderingContext2D;
    private boardSignature = '';
    private renderSamplesMs: number[] = [];

    constructor(canvas: HTMLCanvasElement) {
        this.canvas = canvas;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Could not get 2D context');
        this.ctx = context;
        this.ctx.imageSmoothingEnabled = true;
        this.boardLayer = document.createElement('canvas');
        const boardCtx = this.boardLayer.getContext('2d');
        if (!boardCtx) throw new Error('Could not create board layer context');
        this.boardLayerCtx = boardCtx;
    }

    public render(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number; hostRenderFps5s?: number; renderPipelineP95Ms?: number; presentDelayP95Ms?: number; decodeP95Ms?: number; }) {
        const renderStart = performance.now();
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
                this.boardLayer.width = this.width;
                this.boardLayer.height = this.height;
                this.boardSignature = '';
            }
        }

        const signature = this.computeBoardSignature(state.board);
        if (signature !== this.boardSignature) {
            this.boardSignature = signature;
            this.rebuildBoardLayer(state.board);
        }

        this.ctx.fillStyle = COLOR_BG;
        this.ctx.fillRect(0, 0, this.width, this.height);
        this.ctx.drawImage(this.boardLayer, 0, 0);

        state.powerups.forEach(p => this.drawPowerUp(p));
        state.bombs.forEach(b => this.drawBomb(b));
        state.players.forEach(player => this.drawPlayer(player));
        state.explosions.forEach(e => this.drawExplosion(e));
        const renderDurationMs = performance.now() - renderStart;
        this.renderSamplesMs.push(renderDurationMs);
        if (this.renderSamplesMs.length > 240) {
            this.renderSamplesMs = this.renderSamplesMs.slice(-240);
        }
        this.drawHUD(state, metrics, this.getRenderP95Ms());
    }

    private computeBoardSignature(board: number[][]): string {
        if (!board || board.length === 0) return 'empty';
        const flattened = board.flat();
        let hash = 2166136261;
        for (let i = 0; i < flattened.length; i++) {
            hash ^= (flattened[i] & 0xff);
            hash = Math.imul(hash, 16777619);
        }
        return `${board.length}x${board[0].length}:${hash >>> 0}`;
    }

    private rebuildBoardLayer(board: number[][]) {
        this.boardLayerCtx.fillStyle = COLOR_BG;
        this.boardLayerCtx.fillRect(0, 0, this.width, this.height);
        for (let y = 0; y < board.length; y++) {
            for (let x = 0; x < board[y].length; x++) {
                const cell = board[y][x];
                if (cell === 1) { // INDESTRUCTIBLE
                    this.boardLayerCtx.fillStyle = COLOR_INDESTRUCTIBLE;
                    this.boardLayerCtx.fillRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                    this.boardLayerCtx.strokeStyle = '#555';
                    this.boardLayerCtx.lineWidth = 2;
                    this.boardLayerCtx.strokeRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                } else if (cell === 2) { // DESTRUCTIBLE
                    this.boardLayerCtx.fillStyle = COLOR_DESTRUCTIBLE;
                    this.boardLayerCtx.fillRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                    this.boardLayerCtx.strokeStyle = '#999';
                    this.boardLayerCtx.lineWidth = 2;
                    this.boardLayerCtx.strokeRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);
                    this.boardLayerCtx.beginPath();
                    this.boardLayerCtx.moveTo(x * CELL_SIZE + 5, y * CELL_SIZE + 5);
                    this.boardLayerCtx.lineTo(x * CELL_SIZE + CELL_SIZE - 5, y * CELL_SIZE + CELL_SIZE - 5);
                    this.boardLayerCtx.stroke();
                }
            }
        }
    }

    private drawPlayer(player: PlayerState) {
        if (!player.alive) return;

        const PYTHON_CELL_SIZE = 100;
        const SCALE = CELL_SIZE / PYTHON_CELL_SIZE;

        let px = player.x * SCALE;
        let py = player.y * SCALE;

        const size = (PYTHON_CELL_SIZE * 0.85) * SCALE; // PLAYER_DRAW_SCALE = 0.85

        // Draw Shadow
        this.ctx.fillStyle = 'rgba(0,0,0,0.3)';
        this.ctx.beginPath();
        this.ctx.ellipse(px, py + size * 0.42, size * 0.45, size * 0.2, 0, 0, Math.PI * 2);
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
        this.ctx.arc(px + eyeOffX - 6, py + eyeOffY - 4, 4, 0, Math.PI * 2);
        this.ctx.arc(px + eyeOffX + 6, py + eyeOffY - 4, 4, 0, Math.PI * 2);
        this.ctx.fill();

        // Pupils
        this.ctx.fillStyle = 'black';
        this.ctx.beginPath();
        this.ctx.arc(px + eyeOffX - 6 + dx * 2, py + eyeOffY - 4 + dy * 2, 1.5, 0, Math.PI * 2);
        this.ctx.arc(px + eyeOffX + 6 + dx * 2, py + eyeOffY - 4 + dy * 2, 1.5, 0, Math.PI * 2);
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

    private getRenderP95Ms(): number {
        if (this.renderSamplesMs.length === 0) return 0;
        const sorted = [...this.renderSamplesMs].sort((a, b) => a - b);
        const idx = Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95));
        return sorted[idx];
    }

    private drawHUD(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number; hostRenderFps5s?: number; renderPipelineP95Ms?: number; presentDelayP95Ms?: number; decodeP95Ms?: number; }, renderP95Ms?: number) {
        this.ctx.fillStyle = 'white';
        this.ctx.font = '14px monospace';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(`State: ${state.state}`, 10, 20);
        this.ctx.fillText(`Time: ${(state.time / 1000).toFixed(1)}`, 10, 38);
        if (metrics?.latency5sMs !== undefined) {
            this.ctx.fillText(`Latency(5s): ${metrics.latency5sMs.toFixed(1)} ms`, 10, 56);
        }
        if (metrics?.fps5s !== undefined) {
            this.ctx.fillText(`Client FPS(5s): ${metrics.fps5s.toFixed(1)}`, 10, 74);
        }
        if (metrics?.hostFps5s !== undefined) {
            this.ctx.fillText(`Host Sim FPS(5s): ${metrics.hostFps5s.toFixed(1)}`, 10, 92);
        }
        if (metrics?.hostRenderFps5s !== undefined) {
            this.ctx.fillText(`Host Render FPS(5s): ${metrics.hostRenderFps5s.toFixed(1)}`, 10, 110);
        }
        if (metrics?.renderPipelineP95Ms !== undefined) {
            this.ctx.fillText(`RenderPipeline p95: ${metrics.renderPipelineP95Ms.toFixed(2)} ms`, 10, 128);
        }
        if (metrics?.presentDelayP95Ms !== undefined) {
            this.ctx.fillText(`PresentDelay p95: ${metrics.presentDelayP95Ms.toFixed(1)} ms`, 10, 146);
        }
        if (metrics?.decodeP95Ms !== undefined) {
            this.ctx.fillText(`Decode p95: ${metrics.decodeP95Ms.toFixed(2)} ms`, 10, 164);
        }
        if (renderP95Ms !== undefined) {
            this.ctx.fillText(`CanvasDraw p95: ${renderP95Ms.toFixed(2)} ms`, 10, 182);
        }
    }
}

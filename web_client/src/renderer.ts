import type { GameState, PlayerState, BombState, ExplosionState, PowerUpState } from './types';

// Constants matching Python host rendering
const CELL_SIZE = 100;
const COLOR_BG = '#3C3C3C'; // (60, 60, 60)
const COLOR_INDESTRUCTIBLE = '#787878'; // (120, 120, 120)
const COLOR_DESTRUCTIBLE = '#C8C8C8'; // (200, 200, 200)
const EXPLOSION_DURATION_MS = 400;
const FLAME_ARM_THICKNESS_RATIO = 0.9;

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
    private fireIcon: HTMLImageElement | null = null;
    private blastArm: HTMLImageElement | null = null;
    private blastArmQd: HTMLImageElement | null = null;
    private blastCenter: HTMLImageElement | null = null;
    private blastCenterQd: HTMLImageElement | null = null;
    private lastCanvasScale = 1;
    private avatarCache: Map<string, HTMLImageElement | null> = new Map();

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
        this.boardLayerCtx.imageSmoothingEnabled = true;
        this.loadSpriteAssets();
        window.addEventListener('resize', () => this.fitCanvasToViewport());
    }

    public render(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number; hostRenderFps5s?: number; renderPipelineP95Ms?: number; presentDelayP95Ms?: number; decodeP95Ms?: number; localCorrectionP95Px?: number; }): string {
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
                this.fitCanvasToViewport();
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
        state.explosions.forEach(e => this.drawExplosion(e, state.time));
        if (state.state === 'win' || state.state === 'champion') {
            this.drawWinStats(state);
        }
        const renderDurationMs = performance.now() - renderStart;
        this.renderSamplesMs.push(renderDurationMs);
        if (this.renderSamplesMs.length > 240) {
            this.renderSamplesMs = this.renderSamplesMs.slice(-240);
        }
        return this.buildDebugLine(state, metrics, this.getRenderP95Ms());
    }

    private fitCanvasToViewport() {
        if (this.width <= 0 || this.height <= 0) {
            return;
        }
        const horizontalPad = 40;
        const verticalPad = 240;
        const maxW = Math.max(320, window.innerWidth - horizontalPad);
        const maxH = Math.max(240, window.innerHeight - verticalPad);
        const scale = Math.min(maxW / this.width, maxH / this.height, 1);
        this.lastCanvasScale = scale;
        this.canvas.style.width = `${Math.floor(this.width * scale)}px`;
        this.canvas.style.height = `${Math.floor(this.height * scale)}px`;
    }

    private loadImage(src: string): HTMLImageElement {
        const img = new Image();
        img.decoding = 'async';
        img.src = src;
        return img;
    }

    private loadSpriteAssets() {
        this.fireIcon = this.loadImage('/img/fireup.png');
        this.blastArm = this.loadImage('/img/blast.png');
        this.blastArmQd = this.loadImage('/img/blast_qd.png');
        this.blastCenter = this.loadImage('/img/blast_centre.png');
        this.blastCenterQd = this.loadImage('/img/blast_centre_qd.png');
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

        const avatarKey = (player.name || '').trim();
        let avatarImg: HTMLImageElement | null = null;
        if (avatarKey) {
            if (!this.avatarCache.has(avatarKey)) {
                const img = new Image();
                img.src = `/img/avatars/${encodeURIComponent(avatarKey)}.png`;
                this.avatarCache.set(avatarKey, img);
            }
            avatarImg = this.avatarCache.get(avatarKey) ?? null;
        }

        if (avatarImg && avatarImg.complete && avatarImg.naturalWidth > 0) {
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.arc(px, py, size / 2, 0, Math.PI * 2);
            this.ctx.clip();
            this.ctx.drawImage(avatarImg, px - size / 2, py - size / 2, size, size);
            this.ctx.restore();
        } else {
            const color = player.color ? `rgb(${player.color[0]},${player.color[1]},${player.color[2]})` : PLAYER_COLORS[player.id % PLAYER_COLORS.length];
            this.ctx.fillStyle = color;
            this.ctx.beginPath();
            this.ctx.arc(px, py, size / 2, 0, Math.PI * 2);
            this.ctx.fill();
        }

        // Draw Outline
        this.ctx.strokeStyle = '#222';
        this.ctx.lineWidth = 2;
        this.ctx.stroke();

        // Eyes (direction)
        const dx = player.direction[0];
        const dy = player.direction[1];

        const eyeOffX = dx * (size * 0.16);
        const eyeOffY = dy * (size * 0.16);
        const eyeRadius = Math.max(4, size * 0.12);
        const pupilRadius = Math.max(1.5, size * 0.05);
        const eyeGap = size * 0.18;

        this.ctx.fillStyle = 'white';
        this.ctx.beginPath();
        this.ctx.arc(px + eyeOffX - eyeGap, py + eyeOffY - eyeGap * 0.7, eyeRadius, 0, Math.PI * 2);
        this.ctx.arc(px + eyeOffX + eyeGap, py + eyeOffY - eyeGap * 0.7, eyeRadius, 0, Math.PI * 2);
        this.ctx.fill();

        // Pupils
        this.ctx.fillStyle = 'black';
        this.ctx.beginPath();
        this.ctx.arc(px + eyeOffX - eyeGap + dx * 2, py + eyeOffY - eyeGap * 0.7 + dy * 2, pupilRadius, 0, Math.PI * 2);
        this.ctx.arc(px + eyeOffX + eyeGap + dx * 2, py + eyeOffY - eyeGap * 0.7 + dy * 2, pupilRadius, 0, Math.PI * 2);
        this.ctx.fill();

        // Determine name
        this.ctx.fillStyle = 'white';
        this.ctx.font = `${Math.max(14, Math.floor(size * 0.24))}px Arial`;
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

    private drawExplosion(explosion: ExplosionState, currentTimeMs: number) {
        if (!explosion.cells || explosion.cells.length === 0) {
            return;
        }

        const norm = Math.min(1, Math.max(0, (currentTimeMs - explosion.start_time) / EXPLOSION_DURATION_MS));
        let armFactor = 0;
        if (norm < 0.2) {
            armFactor = norm / 0.2;
        } else if (norm <= 0.7) {
            armFactor = 1;
        } else {
            armFactor = Math.max(0, 1 - ((norm - 0.7) / 0.3));
        }

        const [cx, cy] = explosion.cells[0];
        const centerPixelX = cx * CELL_SIZE + CELL_SIZE / 2;
        const centerPixelY = cy * CELL_SIZE + CELL_SIZE / 2;

        let upMax = 0;
        let downMax = 0;
        let leftMax = 0;
        let rightMax = 0;
        for (const [x, y] of explosion.cells) {
            if (x === cx && y < cy) upMax = Math.max(upMax, cy - y);
            else if (x === cx && y > cy) downMax = Math.max(downMax, y - cy);
            else if (y === cy && x < cx) leftMax = Math.max(leftMax, cx - x);
            else if (y === cy && x > cx) rightMax = Math.max(rightMax, x - cx);
        }

        const upLength = armFactor * upMax * CELL_SIZE;
        const downLength = armFactor * downMax * CELL_SIZE;
        const leftLength = armFactor * leftMax * CELL_SIZE;
        const rightLength = armFactor * rightMax * CELL_SIZE;

        const centerSprite = explosion.quad_damage ? this.blastCenterQd : this.blastCenter;
        const armSprite = explosion.quad_damage ? this.blastArmQd : this.blastArm;
        const thickness = CELL_SIZE * FLAME_ARM_THICKNESS_RATIO;

        if (centerSprite && centerSprite.complete && centerSprite.naturalWidth > 0) {
            const centerSize = thickness;
            this.ctx.drawImage(
                centerSprite,
                centerPixelX - centerSize / 2,
                centerPixelY - centerSize / 2,
                centerSize,
                centerSize,
            );
        } else {
            this.ctx.fillStyle = explosion.quad_damage ? 'rgba(85, 255, 255, 0.85)' : 'rgba(255, 110, 70, 0.85)';
            this.ctx.fillRect(centerPixelX - thickness / 2, centerPixelY - thickness / 2, thickness, thickness);
        }

        const drawArm = (dx: number, dy: number, length: number) => {
            if (length <= 0) return;
            if (armSprite && armSprite.complete && armSprite.naturalWidth > 0) {
                this.ctx.save();
                this.ctx.translate(centerPixelX, centerPixelY);
                this.ctx.rotate(Math.atan2(dy, dx));
                this.ctx.drawImage(armSprite, 0, -thickness / 2, length, thickness);
                this.ctx.restore();
            } else {
                this.ctx.fillStyle = explosion.quad_damage ? 'rgba(85, 255, 255, 0.75)' : 'rgba(255, 140, 65, 0.75)';
                const x = dx >= 0 ? centerPixelX : centerPixelX - length;
                const y = dy >= 0 ? centerPixelY : centerPixelY - length;
                if (Math.abs(dx) > 0) {
                    this.ctx.fillRect(x, centerPixelY - thickness / 2, length, thickness);
                } else {
                    this.ctx.fillRect(centerPixelX - thickness / 2, y, thickness, length);
                }
            }
        };

        drawArm(0, -1, upLength);
        drawArm(0, 1, downLength);
        drawArm(-1, 0, leftLength);
        drawArm(1, 0, rightLength);
    }

    private drawPowerUp(powerup: PowerUpState) {
        // powerup.x, powerup.y are grid coordinates
        const px = powerup.x * CELL_SIZE;
        const py = powerup.y * CELL_SIZE;
        const size = CELL_SIZE * 0.6;

        let color = 'yellow';
        let text = '?';

        if (powerup.type === 'fire') {
            const borderSize = size * 1.3;
            this.ctx.strokeStyle = 'rgb(0,255,255)';
            this.ctx.lineWidth = 3;
            this.ctx.strokeRect(
                px + (CELL_SIZE - borderSize) / 2,
                py + (CELL_SIZE - borderSize) / 2,
                borderSize,
                borderSize,
            );
            if (this.fireIcon && this.fireIcon.complete && this.fireIcon.naturalWidth > 0) {
                this.ctx.drawImage(
                    this.fireIcon,
                    px + (CELL_SIZE - size) / 2,
                    py + (CELL_SIZE - size) / 2,
                    size,
                    size,
                );
                return;
            }
            color = 'orange';
            text = 'F';
        } else if (powerup.type === 'bomb') { color = 'gray'; text = 'B'; }
        else if (powerup.type === 'kick') { color = 'green'; text = 'K'; }
        else if (powerup.type === 'skull') { color = 'red'; text = 'S'; }
        else if (powerup.type === 'quad' || powerup.type === 'quad_damage') { color = 'purple'; text = '4x'; }

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

    private drawWinStats(state: GameState) {
        const panelWidth = Math.min(this.width - 20, 980);
        const panelX = Math.max(10, (this.width - panelWidth) / 2);
        const panelY = Math.max(10, this.height - 200);
        this.ctx.fillStyle = 'rgba(12, 18, 28, 0.8)';
        this.ctx.fillRect(panelX, panelY, panelWidth, 180);
        this.ctx.strokeStyle = 'rgba(170, 200, 240, 0.7)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(panelX, panelY, panelWidth, 180);
        this.ctx.fillStyle = 'white';
        this.ctx.font = 'bold 16px monospace';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('Name       Team  Kills  Walls  Pups  Walked', panelX + 12, panelY + 22);
        this.ctx.font = '14px monospace';
        const sorted = [...state.players].sort((a, b) => (b.players_killed ?? 0) - (a.players_killed ?? 0));
        for (let i = 0; i < Math.min(sorted.length, 6); i++) {
            const p = sorted[i];
            const line = `${(p.name || `P${p.id}`).padEnd(10).slice(0, 10)} ${(p.team ?? 0).toString().padStart(4)} ${(p.players_killed ?? 0).toString().padStart(6)} ${(p.walls_destroyed ?? 0).toString().padStart(6)} ${(p.powerups_collected ?? 0).toString().padStart(5)} ${(p.cells_walked ?? 0).toString().padStart(7)}`;
            this.ctx.fillText(line, panelX + 12, panelY + 46 + i * 22);
        }
    }

    private buildDebugLine(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number; hostRenderFps5s?: number; renderPipelineP95Ms?: number; presentDelayP95Ms?: number; decodeP95Ms?: number; localCorrectionP95Px?: number; }, renderP95Ms?: number): string {
        const parts: string[] = [];
        parts.push(`State: ${state.state}`);
        parts.push(`Time: ${(state.time / 1000).toFixed(1)}`);
        if (metrics?.latency5sMs !== undefined) parts.push(`Latency(5s): ${metrics.latency5sMs.toFixed(1)} ms`);
        if (metrics?.fps5s !== undefined) parts.push(`Client FPS(5s): ${metrics.fps5s.toFixed(1)}`);
        if (metrics?.hostFps5s !== undefined) parts.push(`Host Sim FPS(5s): ${metrics.hostFps5s.toFixed(1)}`);
        if (metrics?.hostRenderFps5s !== undefined) parts.push(`Host Render FPS(5s): ${metrics.hostRenderFps5s.toFixed(1)}`);
        if (metrics?.renderPipelineP95Ms !== undefined) parts.push(`RenderPipeline p95: ${metrics.renderPipelineP95Ms.toFixed(2)} ms`);
        if (metrics?.presentDelayP95Ms !== undefined) parts.push(`PresentDelay p95: ${metrics.presentDelayP95Ms.toFixed(1)} ms`);
        if (metrics?.decodeP95Ms !== undefined) parts.push(`Decode p95: ${metrics.decodeP95Ms.toFixed(2)} ms`);
        if (metrics?.localCorrectionP95Px !== undefined) parts.push(`LocalCorr p95: ${metrics.localCorrectionP95Px.toFixed(1)} px`);
        if (renderP95Ms !== undefined) parts.push(`CanvasDraw p95: ${renderP95Ms.toFixed(2)} ms`);
        parts.push(`Scale: ${(this.lastCanvasScale * 100).toFixed(0)}%`);
        return parts.join(' | ');
    }
}

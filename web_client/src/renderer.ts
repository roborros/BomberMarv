import type { GameState, PlayerState, BombState, ExplosionState, PowerUpState } from './types';
import { computeBoardSignature } from './boardHash';
import { isPlayerInPlannedBlast, explosionArmPixelLength } from './explosionVisual';
import { buildWinStatRows } from './winStats';
import { computeCanvasBackingStore } from './canvasScale';
import { BOSS_COLOR, BOSS_NAME, BOMBER_TOM_COLOR, BOMBER_TOM_NAME, BOMBER_TOM_QUOTE, MARV_KILLER_TITLE, bossResultTitle, championBossCardRect, inviteQuoteLines, isMarvKillerWin, showsBomberTomInvite } from './championChallenge';

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
    '#9664C8', // Light Purple (150, 100, 200)
    '#DC5A46', // Coral (220, 90, 70)
    '#50A0DC'  // Sky (80, 160, 220)
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
    private qdIcon: HTMLImageElement | null = null;
    private blastArm: HTMLImageElement | null = null;
    private blastArmQd: HTMLImageElement | null = null;
    private blastCenter: HTMLImageElement | null = null;
    private blastCenterQd: HTMLImageElement | null = null;
    private lastCanvasScale = 1;
    private worldToBackingX = 1;
    private worldToBackingY = 1;
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

    public render(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number; hostRenderFps5s?: number; renderPipelineP95Ms?: number; presentDelayP95Ms?: number; decodeP95Ms?: number; localCorrectionP95Px?: number; queueDelayP95Ms?: number; }): string {
        const renderStart = performance.now();
        if (state.board && state.board.length > 0) {
            const rows = state.board.length;
            const cols = state.board[0].length;
            const newWidth = cols * CELL_SIZE;
            const newHeight = rows * CELL_SIZE;

            if (this.width !== newWidth || this.height !== newHeight) {
                this.width = newWidth;
                this.height = newHeight;
                this.boardSignature = '';
            }
            this.applyCanvasBacking();
        }

        const signature = computeBoardSignature(state.board);
        if (signature !== this.boardSignature) {
            this.boardSignature = signature;
            this.rebuildBoardLayer(state.board);
        }

        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        this.ctx.fillStyle = COLOR_BG;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.drawImage(this.boardLayer, 0, 0);
        this.ctx.setTransform(this.worldToBackingX, 0, 0, this.worldToBackingY, 0, 0);
        this.ctx.imageSmoothingEnabled = true;

        state.powerups.forEach(p => this.drawPowerUp(p));
        state.bombs.forEach(b => this.drawBomb(b, state.time));
        state.players.forEach(player => this.drawPlayer(player, state));
        state.explosions.forEach(e => this.drawExplosion(e, state.time));
        if (state.state === 'get_ready') {
            this.drawGetReady();
        }
        if (state.state === 'champion') {
            this.drawChampionChallenge(state);
            this.drawWinStats(state);
        } else if (state.state === 'win' || state.state === 'boss_result') {
            this.drawWinStats(state);
            if (state.state === 'boss_result' && isMarvKillerWin(state.boss_fight_winner?.title)) {
                this.drawMarvKillerBanner(state);
            } else if (state.state === 'boss_result' && showsBomberTomInvite(state.result_prompt)) {
                this.drawBrabiInvite(state);
            }
        }
        this.drawLeavePrompt(state);
        const renderDurationMs = performance.now() - renderStart;
        this.renderSamplesMs.push(renderDurationMs);
        if (this.renderSamplesMs.length > 240) {
            this.renderSamplesMs = this.renderSamplesMs.slice(-240);
        }
        return this.buildDebugLine(state, metrics, this.getRenderP95Ms());
    }

    private applyCanvasBacking() {
        if (this.width <= 0 || this.height <= 0) {
            return;
        }
        const store = computeCanvasBackingStore({
            worldWidth: this.width,
            worldHeight: this.height,
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            devicePixelRatio: window.devicePixelRatio || 1,
        });
        this.lastCanvasScale = store.cssScale;
        this.worldToBackingX = store.worldToBackingX;
        this.worldToBackingY = store.worldToBackingY;
        this.canvas.style.width = `${store.cssWidth}px`;
        this.canvas.style.height = `${store.cssHeight}px`;
        if (this.canvas.width !== store.backingWidth || this.canvas.height !== store.backingHeight) {
            this.canvas.width = store.backingWidth;
            this.canvas.height = store.backingHeight;
            this.boardLayer.width = store.backingWidth;
            this.boardLayer.height = store.backingHeight;
            this.boardSignature = '';
            this.ctx.imageSmoothingEnabled = true;
            this.boardLayerCtx.imageSmoothingEnabled = true;
        }
    }

    private fitCanvasToViewport() {
        this.applyCanvasBacking();
    }

    private loadImage(src: string): HTMLImageElement {
        const img = new Image();
        img.decoding = 'async';
        img.src = src;
        return img;
    }

    private loadSpriteAssets() {
        this.fireIcon = this.loadImage('/img/fireup.png');
        this.qdIcon = this.loadImage('/img/qd.png');
        this.blastArm = this.loadImage('/img/blast.png');
        this.blastArmQd = this.loadImage('/img/blast_qd.png');
        this.blastCenter = this.loadImage('/img/blast_centre.png');
        this.blastCenterQd = this.loadImage('/img/blast_centre_qd.png');
    }

    private rebuildBoardLayer(board: number[][]) {
        this.boardLayerCtx.setTransform(this.worldToBackingX, 0, 0, this.worldToBackingY, 0, 0);
        this.boardLayerCtx.imageSmoothingEnabled = true;
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
                    // Brick pattern (host-style) - clamp to cell bounds to avoid overlap
                    const cellLeft = x * CELL_SIZE;
                    const cellTop = y * CELL_SIZE;
                    const brickWidth = CELL_SIZE / 3;
                    const brickHeight = CELL_SIZE / 2;
                    const mortarColor = '#505050';
                    this.boardLayerCtx.strokeStyle = mortarColor;
                    this.boardLayerCtx.lineWidth = 1;
                    for (let row = 0; row < 2; row++) {
                        const offset = row % 2 === 1 ? brickWidth / 2 : 0;
                        const by = cellTop + row * brickHeight;
                        let bx = cellLeft + offset;
                        while (bx < cellLeft + CELL_SIZE) {
                            const w = Math.min(brickWidth, cellLeft + CELL_SIZE - bx);
                            this.boardLayerCtx.strokeRect(bx, by, w, brickHeight);
                            bx += brickWidth;
                        }
                    }
                }
            }
        }
    }

    private drawPlayer(player: PlayerState, state: GameState) {
        if (!player.alive) return;

        const currentTimeMs = state.time;
        const PYTHON_CELL_SIZE = 100;
        const SCALE = CELL_SIZE / PYTHON_CELL_SIZE;

        let px = player.x * SCALE;
        let py = player.y * SCALE;

        const drawScale = player.draw_scale && player.draw_scale > 0 ? player.draw_scale : 1;
        const size = (PYTHON_CELL_SIZE * 0.85) * SCALE * drawScale; // PLAYER_DRAW_SCALE = 0.85
        const [dx, dy] = player.direction;

        if (player.sprite === 'brabi') {
            this.drawBrabiGlow(px, py, size / 2, currentTimeMs);
        }

        const scared = isPlayerInPlannedBlast(player, state.bombs || [], state.board || [])

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

        // Alternating feet (1.5x larger, animate only when moving)
        const isMoving = dx !== 0 || dy !== 0;
        const legOffset = isMoving ? 6 * Math.sin(currentTimeMs / 150) : 0;
        const footSize = 6;
        const legColor = player.color
            ? `rgb(${Math.floor(player.color[0] / 2)},${Math.floor(player.color[1] / 2)},${Math.floor(player.color[2] / 2)})`
            : '#333';
        this.ctx.fillStyle = legColor;
        this.ctx.fillRect(px - size / 4 - footSize / 2, py + size / 2 - footSize / 2 + legOffset, footSize, footSize);
        this.ctx.fillRect(px + size / 4 - footSize / 2, py + size / 2 - footSize / 2 - legOffset, footSize, footSize);

        // Eyes (direction) - bigger when scared
        const eyeOffX = dx * (size * 0.16);
        const eyeOffY = dy * (size * 0.16);
        let eyeRadius = Math.max(4, size * 0.12);
        if (scared) eyeRadius *= 1.5;
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

        // Glasses when quad damage is active
        if (player.quad_damage) {
            const leftEyeX = px + eyeOffX - eyeGap;
            const rightEyeX = px + eyeOffX + eyeGap;
            const eyeY = py + eyeOffY - eyeGap * 0.7;
            const lensR = Math.max(8, eyeRadius * 1.8);
            const frameW = Math.max(2, lensR / 4);
            this.ctx.strokeStyle = 'rgb(0, 255, 255)';
            this.ctx.lineWidth = frameW;
            this.ctx.beginPath();
            this.ctx.arc(leftEyeX, eyeY, lensR, 0, Math.PI * 2);
            this.ctx.arc(rightEyeX, eyeY, lensR, 0, Math.PI * 2);
            this.ctx.stroke();
            this.ctx.beginPath();
            this.ctx.moveTo(leftEyeX + lensR, eyeY);
            this.ctx.lineTo(rightEyeX - lensR, eyeY);
            this.ctx.stroke();
        }

        // Mouth: line by default, circle when scared
        const mouthY = py + eyeGap * 0.8;
        this.ctx.fillStyle = 'rgb(40, 40, 40)';
        if (scared) {
            const mouthR = Math.max(2, size * 0.06);
            this.ctx.beginPath();
            this.ctx.arc(px, mouthY, mouthR, 0, Math.PI * 2);
            this.ctx.fill();
        } else {
            const mouthW = size * 0.25;
            this.ctx.fillRect(px - mouthW, mouthY - 1, mouthW * 2, 2);
        }

        if (player.sprite === 'cleaver') {
            const chopping = (player.cleaver_swing_until ?? 0) > currentTimeMs;
            this.drawCleaver(px, py, size / 2, currentTimeMs, isMoving || chopping);
        }

        if (player.quad_damage) {
            const pulse = 1 + 0.1 * Math.sin(2 * Math.PI * (currentTimeMs / 500));
            const rectSize = (size + 10) * pulse;
            this.ctx.strokeStyle = 'rgb(0, 255, 255)';
            this.ctx.lineWidth = 4;
            this.ctx.strokeRect(px - rectSize / 2, py - rectSize / 2, rectSize, rectSize);
        }
        const shieldUntil = player.shield_until ?? 0;
        if (shieldUntil > currentTimeMs) {
            const pulse = 1 + 0.08 * Math.sin(2 * Math.PI * (currentTimeMs / 280));
            const shieldR = (size / 2 + 10) * pulse;
            this.ctx.strokeStyle = 'rgb(210, 230, 255)';
            this.ctx.lineWidth = 4;
            this.ctx.beginPath();
            this.ctx.arc(px, py, shieldR, 0, Math.PI * 2);
            this.ctx.stroke();
            this.ctx.strokeStyle = 'rgb(130, 180, 255)';
            this.ctx.lineWidth = 2;
            this.ctx.beginPath();
            this.ctx.arc(px, py, Math.max(1, shieldR - 6), 0, Math.PI * 2);
            this.ctx.stroke();
        }

        if (player.name) {
            this.ctx.fillStyle = 'white';
            const nameSize = Math.max(13, Math.min(26, Math.floor(size * 0.26)));
            this.ctx.font = `${nameSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.fillText(player.name, px, py - size / 2 - 5);
        }
        const voiceUntil = player.voice_until ?? 0;
        if (voiceUntil > currentTimeMs) {
            this.ctx.fillStyle = 'rgb(255, 230, 160)';
            this.ctx.font = `bold ${Math.max(16, Math.floor(size * 0.28))}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.fillText('Fresh meat!', px, py - size / 2 - 28);
        }
    }

    private drawBrabiGlow(px: number, py: number, radius: number, now: number) {
        const period = 1400;
        const phase = (now % period) / period;
        if (phase > 0.42) return;
        const strength = Math.sin((phase / 0.42) * Math.PI);
        const glowR = radius * (1.2 + 0.9 * strength);
        this.ctx.save();
        this.ctx.fillStyle = `rgba(40, 255, 110, ${0.18 + 0.45 * strength})`;
        this.ctx.beginPath();
        this.ctx.arc(px, py, glowR, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = `rgba(210, 255, 220, ${0.35 + 0.5 * strength})`;
        this.ctx.lineWidth = 3;
        this.ctx.beginPath();
        this.ctx.arc(px, py, Math.max(2, glowR * 0.55), 0, Math.PI * 2);
        this.ctx.stroke();
        this.ctx.restore();
    }

    private drawCleaver(px: number, py: number, radius: number, now: number, moving: boolean) {
        const base = 0.18;
        const swing = moving ? Math.sin(now / 80) * 0.38 : (Math.floor(now / 3200) % 2 === 0 && (now % 3200) < 460 ? Math.sin(now / 70) * 0.5 : 0.16);
        const angle = base + swing;
        const handX = px + radius * 0.88;
        const handY = py + radius * 0.02;
        const rot = (x: number, y: number) => ({
            x: handX + x * Math.cos(angle) - y * Math.sin(angle),
            y: handY + x * Math.sin(angle) + y * Math.cos(angle),
        });
        const poly = (pts: { x: number; y: number }[], fill: string, stroke?: string, width = 2) => {
            this.ctx.beginPath();
            this.ctx.moveTo(pts[0].x, pts[0].y);
            for (const p of pts.slice(1)) this.ctx.lineTo(p.x, p.y);
            this.ctx.closePath();
            this.ctx.fillStyle = fill;
            this.ctx.fill();
            if (stroke) {
                this.ctx.strokeStyle = stroke;
                this.ctx.lineWidth = width;
                this.ctx.stroke();
            }
        };
        const fistR = Math.max(3, radius * 0.18);
        this.ctx.fillStyle = 'rgb(48, 48, 54)';
        this.ctx.beginPath();
        this.ctx.arc(handX, handY, fistR, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgb(24, 24, 28)';
        this.ctx.lineWidth = 1;
        this.ctx.stroke();
        const handleLen = radius * 0.42;
        const bladeW = radius * 1.28;
        const bladeH = radius * 0.86;
        const grip = Math.max(2.2, radius * 0.07);
        poly([
            rot(0, -grip * 0.42), rot(handleLen, -grip * 0.42), rot(handleLen, grip * 0.42), rot(0, grip * 0.42),
        ], 'rgb(110, 68, 36)', 'rgb(62, 36, 18)', 1);
        const bx0 = handleLen * 0.78;
        poly([
            rot(bx0, -bladeH * 0.26),
            rot(bx0 + bladeW * 0.18, -bladeH * 0.58),
            rot(bx0 + bladeW, -bladeH * 0.46),
            rot(bx0 + bladeW, bladeH * 0.36),
            rot(bx0 + bladeW * 0.08, bladeH * 0.16),
        ], 'rgb(176, 184, 192)', 'rgb(52, 56, 64)', Math.max(1, radius * 0.045));
        this.ctx.strokeStyle = 'rgb(226, 230, 236)';
        this.ctx.lineWidth = Math.max(1, radius * 0.04);
        this.ctx.beginPath();
        const shineA = rot(bx0 + bladeW * 0.16, -bladeH * 0.34);
        const shineB = rot(bx0 + bladeW * 0.78, -bladeH * 0.42);
        this.ctx.moveTo(shineA.x, shineA.y);
        this.ctx.lineTo(shineB.x, shineB.y);
        this.ctx.stroke();
        poly([
            rot(bx0 + bladeW * 0.22, -bladeH * 0.08),
            rot(bx0 + bladeW * 0.58, -bladeH * 0.30),
            rot(bx0 + bladeW * 0.84, -bladeH * 0.06),
            rot(bx0 + bladeW * 0.70, bladeH * 0.18),
            rot(bx0 + bladeW * 0.34, bladeH * 0.10),
        ], 'rgb(132, 16, 20)');
        poly([
            rot(bx0 + bladeW * 0.48, -bladeH * 0.02),
            rot(bx0 + bladeW * 0.76, bladeH * 0.08),
            rot(bx0 + bladeW * 0.62, bladeH * 0.22),
            rot(bx0 + bladeW * 0.40, bladeH * 0.06),
        ], 'rgb(78, 8, 12)');
        this.ctx.fillStyle = 'rgb(132, 16, 20)';
        for (const [ox, oy, scale] of [
            [bx0 + bladeW * 0.70, bladeH * 0.42, 0.11],
            [bx0 + bladeW * 0.92, bladeH * 0.34, 0.08],
            [bx0 + bladeW * 0.48, bladeH * 0.30, 0.07],
        ] as Array<[number, number, number]>) {
            const drop = rot(ox, oy);
            const tail = rot(ox - bladeW * 0.02, oy - bladeH * 0.16);
            const sideA = rot(ox - radius * 0.06, oy);
            const sideB = rot(ox + radius * 0.05, oy - bladeH * 0.02);
            this.ctx.beginPath();
            this.ctx.moveTo(tail.x, tail.y);
            this.ctx.lineTo(sideA.x, sideA.y);
            this.ctx.lineTo(drop.x, drop.y);
            this.ctx.lineTo(sideB.x, sideB.y);
            this.ctx.closePath();
            this.ctx.fill();
            this.ctx.beginPath();
            this.ctx.arc(drop.x, drop.y, Math.max(2, radius * scale), 0, Math.PI * 2);
            this.ctx.fill();
        }
    }

    private drawBomb(bomb: BombState, currentTimeMs: number) {
        const bx = bomb.x * CELL_SIZE;
        const by = bomb.y * CELL_SIZE;
        const cx = bx + CELL_SIZE / 2;
        const cy = by + CELL_SIZE / 2;

        const elapsed = currentTimeMs - bomb.start_time;
        const pulse = 1 + 0.1 * Math.sin(2 * Math.PI * (elapsed / 300));
        const bombRadius = (CELL_SIZE * 0.9 / 2) * pulse;

        this.ctx.fillStyle = BOMB_COLOR;
        this.ctx.beginPath();
        this.ctx.arc(cx, cy, bombRadius, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.strokeStyle = '#505050';
        this.ctx.lineWidth = 1;
        this.ctx.stroke();

        // Fuse (burning rope) near top-left
        const fuseOffset = bombRadius * 0.6;
        const fuseX = cx - fuseOffset * 0.5;
        const fuseY = cy - fuseOffset * 0.9;
        const fuseRadius = Math.max(2, bombRadius / 3);
        this.ctx.fillStyle = 'rgb(255, 200, 150)';
        this.ctx.beginPath();
        this.ctx.arc(fuseX, fuseY, fuseRadius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgb(255, 200, 150)';
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

        const upLength = explosionArmPixelLength(armFactor, upMax, CELL_SIZE);
        const downLength = explosionArmPixelLength(armFactor, downMax, CELL_SIZE);
        const leftLength = explosionArmPixelLength(armFactor, leftMax, CELL_SIZE);
        const rightLength = explosionArmPixelLength(armFactor, rightMax, CELL_SIZE);

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
                const isHorizontal = Math.abs(dx) > Math.abs(dy);
                if (isHorizontal) {
                    this.ctx.scale(-1, 1);
                    this.ctx.drawImage(armSprite, -length, -thickness / 2, length, thickness);
                } else {
                    this.ctx.scale(1, -1);
                    this.ctx.drawImage(armSprite, 0, -thickness / 2, length, thickness);
                }
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
        const px = powerup.x * CELL_SIZE;
        const py = powerup.y * CELL_SIZE;
        const cx = px + CELL_SIZE / 2;
        const cy = py + CELL_SIZE / 2;

        // Teal border for all bonuses (cell-sized)
        this.ctx.strokeStyle = 'rgb(0,255,255)';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(px, py, CELL_SIZE, CELL_SIZE);

        if (powerup.type === 'fire') {
            const fireSize = CELL_SIZE / 1.3;
            const fireOffset = (CELL_SIZE - fireSize) / 2;
            if (this.fireIcon && this.fireIcon.complete && this.fireIcon.naturalWidth > 0) {
                this.ctx.drawImage(this.fireIcon, px + fireOffset, py + fireOffset, fireSize, fireSize);
            } else {
                this.ctx.fillStyle = 'orange';
                this.ctx.beginPath();
                this.ctx.arc(cx, cy, fireSize * 0.3, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.fillStyle = 'white';
                this.ctx.font = 'bold 28px Arial';
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this.ctx.fillText('F', cx, cy);
            }
            return;
        }

        if (powerup.type === 'bomb') {
            this.drawMiniBomb(cx, cy, CELL_SIZE * 0.25 * 1.3);
            return;
        }

        if (powerup.type === 'quad' || powerup.type === 'quad_damage') {
            const qdSize = CELL_SIZE - 20;
            const qdOffset = (CELL_SIZE - qdSize) / 2;
            if (this.qdIcon && this.qdIcon.complete && this.qdIcon.naturalWidth > 0) {
                this.ctx.drawImage(this.qdIcon, px + qdOffset, py + qdOffset, qdSize, qdSize);
            } else {
                this.ctx.fillStyle = 'purple';
                this.ctx.beginPath();
                this.ctx.arc(cx, cy, CELL_SIZE * 0.3, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.fillStyle = 'white';
                this.ctx.font = 'bold 28px Arial';
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this.ctx.fillText('4x', cx, cy);
            }
            return;
        }

        let color = 'yellow';
        let text = '?';
        if (powerup.type === 'kick') { color = 'green'; text = 'K'; }
        else if (powerup.type === 'skull') { color = 'red'; text = 'S'; }

        this.ctx.fillStyle = color;
        this.ctx.beginPath();
        this.ctx.arc(cx, cy, CELL_SIZE * 0.3, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.fillStyle = 'white';
        this.ctx.font = 'bold 28px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(text, cx, cy);
    }

    private drawMiniBomb(cx: number, cy: number, bombRadius: number) {
        this.ctx.fillStyle = BOMB_COLOR;
        this.ctx.beginPath();
        this.ctx.arc(cx, cy, bombRadius, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = '#505050';
        this.ctx.lineWidth = 1;
        this.ctx.stroke();
        const fuseOffset = bombRadius * 0.6;
        const fuseX = cx - fuseOffset * 0.5;
        const fuseY = cy - fuseOffset * 0.9;
        const fuseRadius = Math.max(2, bombRadius / 3);
        this.ctx.fillStyle = 'rgb(255, 200, 150)';
        this.ctx.beginPath();
        this.ctx.arc(fuseX, fuseY, fuseRadius, 0, Math.PI * 2);
        this.ctx.fill();
    }

    private getRenderP95Ms(): number {
        if (this.renderSamplesMs.length === 0) return 0;
        const sorted = [...this.renderSamplesMs].sort((a, b) => a - b);
        const idx = Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95));
        return sorted[idx];
    }

    private winHeaderLines(label: string): string[] {
        if (label === 'Death Time (s)') return ['Death', 'Time (s)'];
        if (label === 'Walls Exploded') return ['Walls', 'Exploded'];
        if (label === 'Cells Walked') return ['Cells', 'Walked'];
        return [label];
    }

    private setUiFont(size: number, bold = false) {
        this.ctx.font = `${bold ? 'bold ' : ''}${size}px Arial, sans-serif`;
    }

    private fitCanvasText(text: string, maxWidth: number): string {
        if (this.ctx.measureText(text).width <= maxWidth) return text;
        const ellipsis = '…';
        if (this.ctx.measureText(ellipsis).width > maxWidth) return '';
        let lo = 0;
        let hi = text.length;
        let best = ellipsis;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            const candidate = text.slice(0, mid) + ellipsis;
            if (this.ctx.measureText(candidate).width <= maxWidth) {
                best = candidate;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return best;
    }

    private fillClippedText(text: string, x: number, y: number, width: number, height: number) {
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(x, y, Math.max(0, width), Math.max(0, height));
        this.ctx.clip();
        this.ctx.fillText(text, x, y);
        this.ctx.restore();
    }

    private drawTrophyIcon(x: number, y: number, size: number) {
        this.ctx.fillStyle = 'rgb(212, 175, 55)';
        this.ctx.beginPath();
        this.ctx.ellipse(x + size / 2, y + size * 0.3, size * 0.5, size * 0.3, 0, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.fillRect(x + size * 0.2, y + size * 0.5, size * 0.6, size * 0.3);
        this.ctx.fillRect(x + size * 0.3, y + size * 0.85, size * 0.4, size * 0.15);
    }

    private drawChampionChallenge(state: GameState) {
        this.drawBossInvite(state, {
            name: BOSS_NAME,
            color: BOSS_COLOR,
            quoteLines: inviteQuoteLines('Finally a worthy challenger, come and fight me!'),
            stats: 'x1.4  ·  Fire 2  ·  Bombs 2  ·  +1 life',
            sprite: 'cleaver',
            drawScale: 1,
            backdrop: 'rgb(28, 28, 34)',
            ring: 'rgb(90, 90, 104)',
            radiusScale: 1,
        });
    }

    private drawBrabiInvite(state: GameState) {
        this.drawBossInvite(state, {
            name: BOMBER_TOM_NAME,
            color: BOMBER_TOM_COLOR,
            quoteLines: inviteQuoteLines(BOMBER_TOM_QUOTE),
            stats: 'x2  ·  Fire 5  ·  Bombs 5  ·  +2 lives',
            sprite: 'brabi',
            drawScale: 1.5,
            backdrop: 'rgb(16, 42, 28)',
            ring: 'rgb(36, 200, 84)',
            radiusScale: 1,
        });
    }

    private drawBossInvite(state: GameState, invite: {
        name: string
        color: [number, number, number]
        quoteLines: string[]
        stats: string
        sprite: string
        drawScale: number
        backdrop: string
        ring: string
        radiusScale: number
    }) {
        const w = this.width;
        const h = this.height;
        const card = championBossCardRect(w, h);
        this.ctx.fillStyle = 'rgb(24, 28, 38)';
        this.roundRect(card.x, card.y, card.w, card.h, 14);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgb(196, 209, 228)';
        this.ctx.lineWidth = 2;
        this.roundRect(card.x, card.y, card.w, card.h, 14);
        this.ctx.stroke();

        const bossR = Math.max(16, Math.floor(Math.min(card.w, card.h) * 0.16 * invite.radiusScale));
        const bossX = card.x + card.w / 2;
        const bossY = card.y + 12 + bossR;
        this.ctx.fillStyle = invite.backdrop;
        this.ctx.beginPath();
        this.ctx.arc(bossX, bossY, bossR * 1.18, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.strokeStyle = invite.ring;
        this.ctx.lineWidth = 2;
        this.ctx.stroke();
        const portraitState: GameState = { ...state, bombs: [], explosions: [] };
        this.ctx.save();
        this.ctx.translate(bossX, bossY);
        const portraitScale = Math.max(0.55, Math.min(0.85, bossR / 28));
        this.ctx.scale(portraitScale, portraitScale);
        this.drawPlayer({
            id: 998,
            name: '',
            x: 0,
            y: 0,
            color: invite.color,
            alive: true,
            direction: [0, 1],
            quad_damage: false,
            death_anim_time: null,
            sprite: invite.sprite,
            draw_scale: invite.drawScale,
        }, portraitState);
        this.ctx.restore();

        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'top';
        const nameSize = Math.max(28, Math.floor(card.h * 0.1));
        const quoteSize = Math.max(22, Math.floor(card.h * 0.07));
        const statSize = Math.max(20, Math.floor(card.h * 0.065));
        this.setUiFont(nameSize, true);
        this.ctx.fillStyle = 'rgb(236, 240, 248)';
        this.ctx.fillText(invite.name, bossX, bossY + bossR + 8, card.w - 24);

        this.setUiFont(quoteSize, true);
        this.ctx.fillStyle = 'rgb(210, 214, 230)';
        let quoteY = bossY + bossR + nameSize + 10;
        for (const line of invite.quoteLines) {
            this.ctx.fillText(line, bossX, quoteY, card.w - 28);
            quoteY += quoteSize + 6;
        }

        this.setUiFont(statSize);
        this.ctx.fillStyle = 'rgb(186, 196, 210)';
        this.ctx.fillText(invite.stats, bossX, card.y + card.h - statSize - 16, card.w - 24);
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'alphabetic';
    }

    private drawMarvKillerBanner(state: GameState) {
        const w = this.width;
        const h = this.height;
        const cardW = Math.min(920, Math.max(480, Math.floor(w * 0.62)));
        const cardH = Math.min(250, Math.max(168, Math.floor(h * 0.26)));
        const x = Math.floor((w - cardW) / 2);
        const y = Math.max(14, Math.floor(h * 0.03));
        this.ctx.fillStyle = 'rgb(28, 20, 8)';
        this.roundRect(x, y, cardW, cardH, 18);
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgb(232, 196, 74)';
        this.ctx.lineWidth = 3;
        this.roundRect(x, y, cardW, cardH, 18);
        this.ctx.stroke();
        const trophy = Math.max(26, Math.min(44, Math.floor(cardH / 6)));
        this.drawTrophyIcon(x + cardW / 2 - trophy / 2, y + 14, trophy);

        const name = state.boss_fight_winner?.name || 'Champion';
        const titleSize = Math.max(36, Math.min(64, Math.floor(cardH / 4)));
        const nameSize = Math.max(22, Math.min(34, Math.floor(cardH / 8)));
        const lineSize = Math.max(18, Math.min(26, Math.floor(cardH / 10)));
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'top';
        this.setUiFont(titleSize, true);
        this.ctx.fillStyle = 'rgb(255, 214, 90)';
        this.ctx.fillText(MARV_KILLER_TITLE, x + cardW / 2, y + 18 + trophy, cardW - 32);
        this.setUiFont(nameSize, true);
        this.ctx.fillStyle = 'rgb(248, 244, 230)';
        this.ctx.fillText(name, x + cardW / 2, y + 24 + trophy + titleSize, cardW - 32);
        this.setUiFont(lineSize);
        this.ctx.fillStyle = 'rgb(232, 214, 170)';
        this.ctx.fillText(`defeated ${BOSS_NAME} and ${BOMBER_TOM_NAME}.`, x + cardW / 2, y + cardH - lineSize - 16, cardW - 32);
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'alphabetic';
    }

    private roundRect(x: number, y: number, width: number, height: number, radius: number) {
        const r = Math.min(radius, width / 2, height / 2);
        this.ctx.beginPath();
        this.ctx.moveTo(x + r, y);
        this.ctx.arcTo(x + width, y, x + width, y + height, r);
        this.ctx.arcTo(x + width, y + height, x, y + height, r);
        this.ctx.arcTo(x, y + height, x, y, r);
        this.ctx.arcTo(x, y, x + width, y, r);
        this.ctx.closePath();
    }

    private drawWinStats(state: GameState) {
        const columnsSpec: Array<{ key: string; label: string }> = [
            { key: 'name', label: 'Player' },
            { key: 'wins', label: 'WINS' },
            { key: 'death', label: 'Death Time (s)' },
            { key: 'flames', label: 'Flames' },
            { key: 'bombs', label: 'Bombs' },
            { key: 'kills', label: 'Kills' },
            { key: 'walls', label: 'Walls Exploded' },
            { key: 'pups', label: 'Pickups' },
            { key: 'qds', label: 'QDs' },
            { key: 'walked', label: 'Cells Walked' },
        ];
        const players = state.players.slice(0, 8);
        const nPlayers = Math.max(1, players.length);
        const rows = buildWinStatRows(state.players);
        const cellColors: Record<string, string> = {
            flames: 'rgb(255, 220, 160)',
            bombs: 'rgb(160, 220, 255)',
            kills: 'rgb(255, 180, 180)',
            walls: 'rgb(220, 200, 170)',
            pups: 'rgb(180, 255, 180)',
            qds: 'rgb(100, 220, 255)',
            walked: 'rgb(180, 220, 255)',
        };

        const pad = 16;
        const panelWidth = Math.max(320, this.width - 20);
        const panelX = Math.max(10, (this.width - panelWidth) / 2);
        const tableWidth = panelWidth - pad * 2;
        const maxPanelH = Math.floor(this.height * 0.52);

        type Col = { key: string; label: string; lines: string[]; x: number; width: number };
        const measure = (fontSize: number, force = false): Col[] | null => {
            this.setUiFont(fontSize);
            const innerPad = Math.max(8, Math.floor(fontSize / 4));
            const nameCap = Math.max(Math.floor(tableWidth * 0.22), this.ctx.measureText('Player').width + innerPad);
            const minName = this.ctx.measureText('Mmmmmmmmmm').width + innerPad;
            const trophySize = Math.max(12, Math.min(24, Math.floor(fontSize * 0.7)));
            const minWidths: number[] = [];
            for (const spec of columnsSpec) {
                const lines = this.winHeaderLines(spec.label);
                const headerW = Math.max(...lines.map(line => this.ctx.measureText(line).width));
                let contentW = 0;
                if (spec.key === 'name') {
                    contentW = Math.min(nameCap, Math.max(0, ...rows.map(r => this.ctx.measureText(r.name).width)));
                } else if (spec.key === 'wins') {
                    const maxT = Math.max(0, ...rows.map(r => r.trophies));
                    contentW = maxT > 0 ? maxT * (trophySize + 4) : trophySize;
                } else {
                    contentW = Math.max(0, ...rows.map(r => {
                        const value = spec.key === 'death' ? r.death
                            : spec.key === 'flames' ? r.flames
                            : spec.key === 'bombs' ? r.bombs
                            : spec.key === 'kills' ? r.kills
                            : spec.key === 'walls' ? r.walls
                            : spec.key === 'pups' ? r.pups
                            : spec.key === 'qds' ? r.qds
                            : spec.key === 'walked' ? r.walked
                            : '';
                        return this.ctx.measureText(value).width;
                    }));
                }
                minWidths.push(Math.max(headerW, contentW) + innerPad);
            }
            const minGap = Math.max(16, Math.floor(fontSize / 3));
            const reservedGaps = minGap * (columnsSpec.length - 1);
            let overflow = minWidths.reduce((a, b) => a + b, 0) + reservedGaps - tableWidth;
            if (overflow > 0) {
                const shrink = Math.min(overflow, Math.max(0, minWidths[0] - minName));
                minWidths[0] -= shrink;
                overflow -= shrink;
                if (overflow > 0) {
                    if (!force) return null;
                    const interior = Math.max(1, tableWidth - reservedGaps);
                    const scale = interior / Math.max(1, minWidths.reduce((a, b) => a + b, 0));
                    for (let i = 0; i < minWidths.length; i++) minWidths[i] = Math.max(16, minWidths[i] * scale);
                }
            }
            let extra = tableWidth - minWidths.reduce((a, b) => a + b, 0) - reservedGaps;
            if (extra > 0) {
                const nameBonus = extra * 0.35;
                minWidths[0] += nameBonus;
                extra -= nameBonus;
            }
            const gapExtra = columnsSpec.length > 1 && extra > 0 ? extra / (columnsSpec.length - 1) : 0;
            const cols: Col[] = [];
            let x = 0;
            columnsSpec.forEach((spec, i) => {
                cols.push({
                    key: spec.key,
                    label: spec.label,
                    lines: this.winHeaderLines(spec.label),
                    x,
                    width: minWidths[i],
                });
                x += minWidths[i];
                if (i < columnsSpec.length - 1) x += minGap + gapExtra;
            });
            return cols;
        };

        const winnerPlayer = players.find(p => p.alive) || null
        let winnerLabel = 'No one wins!'
        if (state.state === 'boss_result') {
            const bossWinner = state.boss_fight_winner
            winnerLabel = isMarvKillerWin(bossWinner?.title)
                ? 'You win'
                : bossResultTitle(!!bossWinner, !!bossWinner?.is_ai)
        } else if (state.state === 'champion' && winnerPlayer) {
            winnerLabel = `Champion: ${winnerPlayer.name}`
        } else if (winnerPlayer) {
            winnerLabel = `${winnerPlayer.name} wins!`
        }
        const winnerSize = Math.min(56, Math.max(28, Math.floor(this.height * 0.04)));
        const winnerH = winnerSize + 12;
        const captionSize = Math.max(16, Math.min(22, Math.floor(this.height * 0.016)));
        const captionH = captionSize + 10;

        let fontSize = 16;
        let columns: Col[] = [];
        let headerH = 36;
        let rowH = 24;
        let trophySize = 12;
        for (let size = 36; size >= 16; size -= 2) {
            const cols = measure(size);
            if (!cols) continue;
            const maxLines = Math.max(...cols.map(c => c.lines.length));
            const nextHeaderH = Math.floor(size * 1.12) * maxLines + 10;
            const nextTrophy = Math.max(12, Math.min(24, Math.floor(size * 0.7)));
            const nextRowH = Math.max(Math.floor(size * 1.55), nextTrophy + 10);
            fontSize = size;
            columns = cols;
            headerH = nextHeaderH;
            rowH = nextRowH;
            trophySize = nextTrophy;
            if (winnerH + captionH + nextHeaderH + nPlayers * nextRowH + pad * 2 <= maxPanelH) {
                break;
            }
        }
        if (columns.length === 0) {
            columns = measure(16, true) || [];
            fontSize = 16;
            headerH = 36;
            rowH = 24;
            trophySize = 12;
        }
        const neededH = pad + winnerH + captionH + headerH + nPlayers * rowH + pad;
        if (neededH > maxPanelH) {
            rowH = Math.max(18, Math.floor((maxPanelH - winnerH - captionH - headerH - pad * 2) / nPlayers));
        }

        this.setUiFont(winnerSize, true);
        const fittedWinner = this.fitCanvasText(winnerLabel, tableWidth);
        const panelHeight = Math.min(maxPanelH, pad + winnerH + captionH + headerH + nPlayers * rowH + pad);
        const panelY = Math.max(10, this.height - panelHeight - 10);

        this.ctx.fillStyle = 'rgba(12, 18, 28, 0.88)';
        this.ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
        this.ctx.strokeStyle = 'rgba(170, 200, 240, 0.7)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';

        this.setUiFont(winnerSize, true);
        const threshold = state.trophy_win_threshold ?? 3
        const prompt = state.result_prompt ? `   ·   ${state.result_prompt}` : ''
        const killerWin = state.state === 'boss_result' && isMarvKillerWin(state.boss_fight_winner?.title)
        const killerName = state.boss_fight_winner?.name || 'Champion'
        const caption = killerWin
            ? `${killerName} earns the title ${MARV_KILLER_TITLE}.   ·   ${state.result_prompt || 'Enter: back to the lobby'}`
            : state.state === 'boss_result'
            ? (state.result_prompt || 'Enter: back to the lobby')
            : `Match totals until ${threshold} trophies${prompt}`
        this.ctx.fillStyle = killerWin
            ? 'rgb(255, 214, 90)'
            : state.state === 'boss_result'
            ? (state.boss_fight_winner?.is_ai ? 'rgb(255, 96, 88)' : state.boss_fight_winner ? 'rgb(88, 220, 120)' : 'rgb(220, 224, 232)')
            : (winnerPlayer && winnerPlayer.color.length >= 3
                ? `rgb(${winnerPlayer.color[0]}, ${winnerPlayer.color[1]}, ${winnerPlayer.color[2]})`
                : 'white')
        this.fillClippedText(fittedWinner, panelX + pad, panelY + pad, tableWidth, winnerH);
        this.setUiFont(captionSize);
        this.ctx.fillStyle = 'rgb(186, 196, 210)';
        this.fillClippedText(caption, panelX + pad, panelY + pad + winnerH, tableWidth, captionH)

        const tableTop = panelY + pad + winnerH + captionH;
        const lineH = Math.floor(fontSize * 1.12);
        this.setUiFont(fontSize);
        this.ctx.fillStyle = 'rgb(200, 200, 200)';
        for (const col of columns) {
            let lineY = tableTop;
            for (const line of col.lines) {
                this.fillClippedText(line, panelX + pad + col.x, lineY, col.width, lineH);
                lineY += lineH;
            }
        }
        this.ctx.strokeStyle = 'rgba(170, 200, 240, 0.45)';
        this.ctx.beginPath();
        this.ctx.moveTo(panelX + pad, tableTop + headerH - 4);
        this.ctx.lineTo(panelX + pad + tableWidth, tableTop + headerH - 4);
        this.ctx.stroke();

        for (let i = 0; i < rows.length; i++) {
            const row = rows[i];
            const rowY = tableTop + headerH + i * rowH;
            const textY = rowY + Math.max(0, (rowH - fontSize) / 2);
            for (const col of columns) {
                const x = panelX + pad + col.x;
                if (col.key === 'wins') {
                    const iconY = rowY + Math.max(0, (rowH - trophySize) / 2);
                    for (let j = 0; j < row.trophies; j++) {
                        const iconX = x + j * (trophySize + 4);
                        if (iconX + trophySize > x + col.width) break;
                        this.drawTrophyIcon(iconX, iconY, trophySize);
                    }
                    continue;
                }
                const bold = col.key === 'name' || !!row.bold[col.key];
                this.setUiFont(fontSize, bold);
                if (col.key === 'name') {
                    this.ctx.fillStyle = `rgb(${row.color[0]}, ${row.color[1]}, ${row.color[2]})`;
                    this.fillClippedText(this.fitCanvasText(row.name, Math.max(12, col.width - 4)), x, textY, col.width, rowH);
                    continue;
                }
                this.ctx.fillStyle = col.key === 'death' ? row.deathColor : (cellColors[col.key] || 'white');
                const value = col.key === 'death' ? row.death
                    : col.key === 'flames' ? row.flames
                    : col.key === 'bombs' ? row.bombs
                    : col.key === 'kills' ? row.kills
                    : col.key === 'walls' ? row.walls
                    : col.key === 'pups' ? row.pups
                    : col.key === 'qds' ? row.qds
                    : col.key === 'walked' ? row.walked
                    : '';
                this.fillClippedText(value, x, textY, col.width, rowH);
            }
        }
    }

    private drawGetReady() {
        const bannerH = Math.max(56, Math.min(120, Math.floor(this.height * 0.10)));
        const y = Math.floor((this.height - bannerH) / 2);
        this.ctx.save();
        this.ctx.fillStyle = 'rgba(12, 10, 18, 0.82)';
        this.ctx.fillRect(0, y, this.width, bannerH);
        this.ctx.fillStyle = 'rgb(212, 175, 55)';
        this.ctx.fillRect(0, y, this.width, 2);
        this.ctx.fillRect(0, y + bannerH - 2, this.width, 2);
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        const size = Math.max(28, Math.min(64, Math.floor(bannerH * 0.48)));
        this.ctx.font = `bold ${size}px "Comic Sans MS", "Comic Sans", cursive`;
        this.ctx.fillStyle = 'rgb(236, 120, 168)';
        this.ctx.fillText('Get Ready!', this.width / 2, y + bannerH / 2);
        this.ctx.restore();
    }

    private drawLeavePrompt(state: GameState) {
        const prompt = state.leave_prompt;
        if (!prompt?.open) return;
        const w = this.width;
        const h = this.height;
        this.ctx.save();
        this.ctx.setTransform(this.worldToBackingX, 0, 0, this.worldToBackingY, 0, 0);
        this.ctx.fillStyle = 'rgba(8, 10, 16, 0.72)';
        this.ctx.fillRect(0, 0, w, h);
        const panelW = Math.min(720, Math.max(420, w * 0.52));
        const panelH = Math.min(280, Math.max(200, h * 0.28));
        const panelX = (w - panelW) / 2;
        const panelY = (h - panelH) / 2;
        this.roundRect(panelX, panelY, panelW, panelH, 16);
        this.ctx.fillStyle = 'rgb(28, 34, 46)';
        this.ctx.fill();
        this.ctx.strokeStyle = 'rgb(196, 209, 228)';
        this.ctx.lineWidth = 2;
        this.ctx.stroke();
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.setUiFont(Math.min(36, Math.max(24, panelH / 7)), true);
        this.ctx.fillStyle = 'rgb(238, 244, 255)';
        this.ctx.fillText(prompt.title || 'Leave game?', w / 2, panelY + panelH * 0.28);
        this.setUiFont(Math.min(20, Math.max(14, panelH / 12)));
        this.ctx.fillStyle = 'rgb(164, 178, 198)';
        this.ctx.fillText('Host: arrows select  ·  Enter confirm  ·  Esc resume', w / 2, panelY + panelH * 0.46);
        const btnW = Math.min(160, Math.max(110, panelW * 0.28));
        const btnH = Math.min(56, Math.max(40, panelH * 0.22));
        const gap = 24;
        const noX = w / 2 - gap / 2 - btnW;
        const yesX = w / 2 + gap / 2;
        const btnY = panelY + panelH - btnH - 28;
        this.drawLeaveButton('NO', noX, btnY, btnW, btnH, prompt.choice !== 'yes');
        this.drawLeaveButton('YES', yesX, btnY, btnW, btnH, prompt.choice === 'yes');
        this.ctx.restore();
    }

    private drawLeaveButton(label: string, x: number, y: number, w: number, h: number, selected: boolean) {
        this.roundRect(x, y, w, h, 12);
        if (selected) {
            this.ctx.fillStyle = label === 'YES' ? 'rgb(176, 72, 78)' : 'rgb(86, 168, 118)';
        } else {
            this.ctx.fillStyle = 'rgb(46, 56, 70)';
        }
        this.ctx.fill();
        this.ctx.strokeStyle = selected ? 'rgb(230, 240, 232)' : 'rgb(90, 108, 132)';
        this.ctx.lineWidth = selected ? 2 : 1;
        this.ctx.stroke();
        this.setUiFont(Math.min(28, Math.max(18, h * 0.45)), true);
        this.ctx.fillStyle = selected && label === 'YES' ? 'rgb(255, 236, 236)' : selected ? 'rgb(22, 32, 28)' : 'rgb(210, 220, 232)';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(label, x + w / 2, y + h / 2);
    }

    private buildDebugLine(state: GameState, metrics?: { latency5sMs?: number; fps5s?: number; hostFps5s?: number; hostRenderFps5s?: number; renderPipelineP95Ms?: number; presentDelayP95Ms?: number; decodeP95Ms?: number; localCorrectionP95Px?: number; queueDelayP95Ms?: number; }, renderP95Ms?: number): string {
        const parts: string[] = [];
        parts.push(`State: ${state.state}`);
        parts.push(`Time: ${(state.time / 1000).toFixed(1)}`);
        if (metrics?.latency5sMs !== undefined) parts.push(`RTT(5s): ${metrics.latency5sMs.toFixed(1)} ms`);
        if (metrics?.queueDelayP95Ms !== undefined) parts.push(`QueueDelay p95: ${metrics.queueDelayP95Ms.toFixed(1)} ms`);
        if (metrics?.fps5s !== undefined) parts.push(`Client FPS(5s): ${metrics.fps5s.toFixed(1)}`);
        if (metrics?.hostFps5s !== undefined) parts.push(`Host Sim FPS(5s): ${metrics.hostFps5s.toFixed(1)}`);
        if (metrics?.hostRenderFps5s !== undefined) parts.push(`Host Render FPS(5s): ${metrics.hostRenderFps5s.toFixed(1)}`);
        if (metrics?.renderPipelineP95Ms !== undefined) parts.push(`RenderPipeline p95: ${metrics.renderPipelineP95Ms.toFixed(2)} ms`);
        if (metrics?.presentDelayP95Ms !== undefined) parts.push(`PresentAge p95: ${metrics.presentDelayP95Ms.toFixed(1)} ms`);
        if (metrics?.decodeP95Ms !== undefined) parts.push(`Decode p95: ${metrics.decodeP95Ms.toFixed(2)} ms`);
        if (metrics?.localCorrectionP95Px !== undefined) parts.push(`LocalCorr p95: ${metrics.localCorrectionP95Px.toFixed(1)} px`);
        if (renderP95Ms !== undefined) parts.push(`CanvasDraw p95: ${renderP95Ms.toFixed(2)} ms`);
        parts.push(`Scale: ${(this.lastCanvasScale * 100).toFixed(0)}%`);
        return parts.join(' | ');
    }
}

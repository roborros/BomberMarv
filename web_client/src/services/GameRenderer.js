/**
 * Canvas-based game renderer for BomberMarv web client
 * Renders game state received from WebSocket server
 */
class GameRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', {
      alpha: false,
      desynchronized: true
    });
    
    // Game constants (will be updated from server)
    this.constants = {
      CELL_SIZE: 100,
      GRID_WIDTH: 15,
      GRID_HEIGHT: 15,
      BASE_WIDTH: 1500,
      BASE_HEIGHT: 1500,
      BOMB_PULSE_AMPLITUDE: 0.1,
      BOMB_PULSE_SPEED: 300.0,
      BOMB_BASE_RADIUS: 45,
      EXPLOSION_DURATION: 400,
      FLAME_ARM_THICKNESS_RATIO: 0.9,
      SHOW_PLAYER_DIRECTIONS: true
    };

    // Colors (matching Python constants)
    this.colors = {
      BG: [60, 60, 60],
      INDESTRUCTIBLE: [128, 128, 128],
      DESTRUCTIBLE: [139, 69, 19],
      BOMB_FILL: [64, 64, 64],
      BOMB_OUTLINE: [255, 255, 255],
      FUSE: [255, 100, 0],
      EXPLOSION_NORMAL: [255, 200, 0],
      EXPLOSION_QUAD: [255, 100, 255]
    };

    // FPS measurement for web
    this.fpsEnabled = false;
    this.lastFpsTime = performance.now();
    this.frameCount = 0;
    this.currentFps = 0;
  }

  render(gameState) {
    if (!gameState) return;

    // Update constants from server
    if (gameState.constants) {
      this.constants = { ...this.constants, ...gameState.constants };
      // Adopt authoritative colors from server if provided
      if (gameState.constants.COLORS) {
        const c = gameState.constants.COLORS;
        this.colors = {
          BG: c.BG || this.colors.BG,
          INDESTRUCTIBLE: c.INDESTRUCTIBLE || this.colors.INDESTRUCTIBLE,
          DESTRUCTIBLE: c.DESTRUCTIBLE || this.colors.DESTRUCTIBLE,
          BOMB_FILL: c.BOMB_FILL || this.colors.BOMB_FILL,
          BOMB_OUTLINE: c.BOMB_OUTLINE || this.colors.BOMB_OUTLINE,
          FUSE: c.FUSE || this.colors.FUSE,
          EXPLOSION_NORMAL: this.colors.EXPLOSION_NORMAL,
          EXPLOSION_QUAD: this.colors.EXPLOSION_QUAD,
        };
      }
    }

    // Clear canvas
    this.fillBackground(this.colors.BG);

    // Render based on game state
    switch (gameState.game_state) {
      case 'startup':
        this.renderStartupScreen(gameState);
        break;
      case 'game_prep':
        this.renderGamePrepScreen(gameState);
        break;
      case 'get_ready':
        this.renderGameScreen(gameState);
        this.renderGetReadyOverlay();
        break;
      case 'playing':
        this.renderGameScreen(gameState);
        break;
      case 'win':
        this.renderWinScreen(gameState);
        break;
      case 'champion':
        this.renderChampionScreen(gameState);
        break;
      default:
        this.renderGameScreen(gameState);
    }

    // FPS overlay (web)
    if (this.fpsEnabled) {
      this.frameCount += 1;
      const now = performance.now();
      if (now - this.lastFpsTime >= 1000) {
        this.currentFps = this.frameCount;
        this.frameCount = 0;
        this.lastFpsTime = now;
      }
      this.drawText(`FPS: ${this.currentFps}`, 10, 10, 16, [255, 255, 255]);
    }
  }

  // Utility methods
  fillBackground(color) {
    this.ctx.fillStyle = this.rgbToString(color);
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  rgbToString(rgb) {
    return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
  }

  drawRect(x, y, width, height, fillColor, borderWidth = 0, borderColor = null) {
    this.ctx.fillStyle = this.rgbToString(fillColor);
    this.ctx.fillRect(x, y, width, height);

    if (borderWidth > 0 && borderColor) {
      this.ctx.strokeStyle = this.rgbToString(borderColor);
      this.ctx.lineWidth = borderWidth;
      this.ctx.strokeRect(x, y, width, height);
    }
  }

  drawCircle(x, y, radius, fillColor, borderWidth = 0, borderColor = null) {
    this.ctx.beginPath();
    this.ctx.arc(x, y, radius, 0, 2 * Math.PI);
    this.ctx.fillStyle = this.rgbToString(fillColor);
    this.ctx.fill();

    if (borderWidth > 0 && borderColor) {
      this.ctx.strokeStyle = this.rgbToString(borderColor);
      this.ctx.lineWidth = borderWidth;
      this.ctx.stroke();
    }
  }

  drawText(text, x, y, fontSize, color, center = false, fontFamily = 'Arial') {
    this.ctx.fillStyle = this.rgbToString(color);
    this.ctx.font = `${fontSize}px ${fontFamily}`;
    
    if (center) {
      this.ctx.textAlign = 'center';
      this.ctx.textBaseline = 'middle';
    } else {
      this.ctx.textAlign = 'left';
      this.ctx.textBaseline = 'top';
    }
    
    this.ctx.fillText(text, x, y);
  }

  drawLine(x1, y1, x2, y2, color, width = 1) {
    this.ctx.beginPath();
    this.ctx.moveTo(x1, y1);
    this.ctx.lineTo(x2, y2);
    this.ctx.strokeStyle = this.rgbToString(color);
    this.ctx.lineWidth = width;
    this.ctx.stroke();
  }

  // Game rendering methods
  renderGameScreen(gameState) {
    this.renderBoard(gameState.board);
    this.renderPowerups(gameState.powerups);
    this.renderBombs(gameState.bombs, gameState.current_time);
    this.renderExplosions(gameState.explosions, gameState.current_time);
    this.renderPlayers(gameState.players);
  }

  renderBoard(board) {
    if (!board) return;

    for (let y = 0; y < board.length; y++) {
      for (let x = 0; x < board[y].length; x++) {
        const cellX = x * this.constants.CELL_SIZE;
        const cellY = y * this.constants.CELL_SIZE;
        const cellType = board[y][x];

        switch (cellType) {
          case 0: // EMPTY
            this.drawRect(cellX, cellY, this.constants.CELL_SIZE, this.constants.CELL_SIZE, this.colors.BG);
            break;
          case 1: // INDESTRUCTIBLE
            this.drawRect(cellX, cellY, this.constants.CELL_SIZE, this.constants.CELL_SIZE, 
                         this.colors.INDESTRUCTIBLE, 1, [80, 80, 80]);
            break;
          case 2: // DESTRUCTIBLE
            this.drawRect(cellX, cellY, this.constants.CELL_SIZE, this.constants.CELL_SIZE, 
                         this.colors.DESTRUCTIBLE);
            this.drawBrickPattern(cellX, cellY, this.constants.CELL_SIZE, this.constants.CELL_SIZE);
            break;
        }
      }
    }
  }

  drawBrickPattern(x, y, width, height) {
    const brickHeight = height / 4;
    const brickWidth = width / 3;
    const mortarColor = [80, 80, 80];
    const rows = 2;

    for (let row = 0; row < rows; row++) {
      const offset = row % 2 === 1 ? brickWidth / 2 : 0;
      const rowY = y + row * (height / rows);
      let brickX = x + offset;

      while (brickX < x + width) {
        this.drawRect(brickX, rowY, brickWidth, height / rows, this.colors.DESTRUCTIBLE, 1, mortarColor);
        brickX += brickWidth;
      }
    }
  }

  renderPlayers(players) {
    if (!players) return;

    players.forEach(player => {
      if (!player.alive && player.death_animation_time <= 0) return;

      const x = player.pos.x;
      const y = player.pos.y;
      const radius = player.draw_radius;

      if (player.alive) {
        // Main body
        this.drawCircle(x, y, radius, player.color);

        // Eyes
        const eyeRadius = Math.max(1, radius / 8);
        const eyeOffsetX = radius / 3;
        const eyeOffsetY = radius / 3;
        this.drawCircle(x - eyeOffsetX, y - eyeOffsetY, eyeRadius, [0, 0, 0]);
        this.drawCircle(x + eyeOffsetX, y - eyeOffsetY, eyeRadius, [0, 0, 0]);

        // Animated legs
        const legWidth = radius / 3;
        const legHeight = radius / 4;
        const legOffset = Math.sin(player.animation_time / 150.0) * 6;
        const legColor = [player.color[0] / 2, player.color[1] / 2, player.color[2] / 2];

        this.drawRect(x - radius/2 - legWidth/2, y + radius - 2 + legOffset, 
                     legWidth, legHeight, legColor);
        this.drawRect(x + radius/2 - legWidth/2, y + radius - 2 - legOffset, 
                     legWidth, legHeight, legColor);

        // Quad damage effect
        if (player.quad_damage) {
          const elapsed = Date.now() - player.quad_damage_start_time;
          const pulse = 1 + 0.1 * Math.sin(2 * Math.PI * (elapsed / 500.0));
          const rectSize = (2 * radius + 10) * pulse;
          this.drawRect(x - rectSize/2, y - rectSize/2, rectSize, rectSize, 
                       [0, 0, 0], 4, [0, 255, 255]);
        }

        // Player name
        this.drawText(player.name, x, y - radius - 10, 16, [255, 255, 255], true);
      } else {
        // Death animation
        const alpha = player.death_animation_time / 1000.0;
        const deathColor = [255 * alpha, 0, 0];
        this.drawCircle(x, y, radius, deathColor);
      }
    });
  }

  renderBombs(bombs, currentTime) {
    if (!bombs) return;

    bombs.forEach(bomb => {
      const centerX = bomb.x * this.constants.CELL_SIZE + this.constants.CELL_SIZE / 2;
      const centerY = bomb.y * this.constants.CELL_SIZE + this.constants.CELL_SIZE / 2;

      const elapsed = currentTime - bomb.start_time;
      const pulse = 1 + this.constants.BOMB_PULSE_AMPLITUDE * 
                   Math.sin(2 * Math.PI * (elapsed / this.constants.BOMB_PULSE_SPEED));
      const bombRadius = this.constants.BOMB_BASE_RADIUS * pulse;

      // Main bomb body
      this.drawCircle(centerX, centerY, bombRadius, this.colors.BOMB_FILL, 2, this.colors.BOMB_OUTLINE);

      // Fuse
      const fuseRadius = Math.max(2, bombRadius / 3);
      const fuseOffset = bombRadius * 0.6;
      this.drawCircle(centerX, centerY - fuseOffset, fuseRadius, this.colors.FUSE);
    });
  }

  renderExplosions(explosions, currentTime) {
    if (!explosions) return;

    explosions.forEach(explosion => {
      const norm = Math.min((currentTime - explosion.start_time) / this.constants.EXPLOSION_DURATION, 1);
      
      let armFactor;
      if (norm < 0.2) {
        armFactor = norm / 0.2;
      } else if (norm <= 0.7) {
        armFactor = 1;
      } else {
        armFactor = (1 - (norm - 0.7) / 0.3);
      }

      const [cx, cy] = explosion.cells[0];
      const centerPixelX = cx * this.constants.CELL_SIZE + this.constants.CELL_SIZE / 2;
      const centerPixelY = cy * this.constants.CELL_SIZE + this.constants.CELL_SIZE / 2;

      // Calculate arm lengths
      const upMax = Math.max(...explosion.cells
        .filter(([x, y]) => x === cx && y < cy)
        .map(([x, y]) => cy - y), 0);
      const downMax = Math.max(...explosion.cells
        .filter(([x, y]) => x === cx && y > cy)
        .map(([x, y]) => y - cy), 0);
      const leftMax = Math.max(...explosion.cells
        .filter(([x, y]) => y === cy && x < cx)
        .map(([x, y]) => cx - x), 0);
      const rightMax = Math.max(...explosion.cells
        .filter(([x, y]) => y === cy && x > cx)
        .map(([x, y]) => x - cx), 0);

      const explosionColor = explosion.quad_damage ? 
        this.colors.EXPLOSION_QUAD : this.colors.EXPLOSION_NORMAL;

      // Draw center
      const centerSize = this.constants.CELL_SIZE * this.constants.FLAME_ARM_THICKNESS_RATIO;
      this.drawRect(centerPixelX - centerSize/2, centerPixelY - centerSize/2, 
                   centerSize, centerSize, explosionColor);

      // Draw arms
      const armThickness = this.constants.CELL_SIZE * this.constants.FLAME_ARM_THICKNESS_RATIO;

      if (upMax > 0) {
        const armLength = armFactor * upMax * this.constants.CELL_SIZE;
        this.drawRect(centerPixelX - armThickness/2, centerPixelY - armLength, 
                     armThickness, armLength, explosionColor);
      }

      if (downMax > 0) {
        const armLength = armFactor * downMax * this.constants.CELL_SIZE;
        this.drawRect(centerPixelX - armThickness/2, centerPixelY, 
                     armThickness, armLength, explosionColor);
      }

      if (leftMax > 0) {
        const armLength = armFactor * leftMax * this.constants.CELL_SIZE;
        this.drawRect(centerPixelX - armLength, centerPixelY - armThickness/2, 
                     armLength, armThickness, explosionColor);
      }

      if (rightMax > 0) {
        const armLength = armFactor * rightMax * this.constants.CELL_SIZE;
        this.drawRect(centerPixelX, centerPixelY - armThickness/2, 
                     armLength, armThickness, explosionColor);
      }
    });
  }

  renderPowerups(powerups) {
    if (!powerups) return;

    powerups.forEach(powerup => {
      const centerX = powerup.x * this.constants.CELL_SIZE + this.constants.CELL_SIZE / 2;
      const centerY = powerup.y * this.constants.CELL_SIZE + this.constants.CELL_SIZE / 2;
      const size = this.constants.CELL_SIZE - 20;

      // Border
      this.drawRect(centerX - size/2, centerY - size/2, size, size, 
                   [0, 0, 0], 4, [0, 255, 255]);

      switch (powerup.type) {
        case 'bomb':
          const bombR = size / 3;
          this.drawCircle(centerX, centerY, bombR, this.colors.BOMB_FILL, 2, this.colors.BOMB_OUTLINE);
          const fuseR = Math.max(2, bombR / 3);
          this.drawCircle(centerX, centerY - bombR * 0.6, fuseR, this.colors.FUSE);
          break;

        case 'fire':
          this.drawCircle(centerX, centerY, size/3, [255, 100, 0]);
          this.drawCircle(centerX - 5, centerY - 5, size/4, [255, 200, 0]);
          this.drawCircle(centerX + 5, centerY - 5, size/4, [255, 150, 0]);
          break;

        case 'quad_damage':
          this.drawText('QD', centerX, centerY, 20, [255, 0, 255], true);
          break;
      }
    });
  }

  renderStartupScreen(gameState) {
    this.fillBackground(this.colors.BG);
    
    // Logo placeholder
    const logoX = this.constants.BASE_WIDTH / 2 - 200;
    const logoY = this.constants.BASE_HEIGHT / 4 - 100;
    this.drawRect(logoX, logoY, 400, 200, [100, 100, 100], 2, [200, 200, 200]);
    
    // Game title
    this.drawText('BomberMarv', this.constants.BASE_WIDTH / 2, this.constants.BASE_HEIGHT / 2, 
                 90, [255, 255, 255], true, 'Arial Black');
    
    // Instructions
    this.drawText('Press Enter to start the game', this.constants.BASE_WIDTH / 2, 
                 this.constants.BASE_HEIGHT - 50, 32, [255, 255, 255], true);
  }

  renderGamePrepScreen(gameState) {
    this.fillBackground(this.colors.BG);
    
    this.drawText('Game Setup', this.constants.BASE_WIDTH / 2, 60, 48, [255, 255, 255], true);
    
    let y = 150;
    if (gameState.players) {
      gameState.players.forEach((player, i) => {
        this.drawText(`Player ${i+1}: ${player.name}`, 100, y, 32, player.color);
        y += 50;
      });
    }
    
    this.drawText('Press Enter to start', this.constants.BASE_WIDTH / 2, 
                 this.constants.BASE_HEIGHT - 100, 32, [255, 255, 255], true);
  }

  renderGetReadyOverlay() {
    this.drawText('Get Ready!', this.constants.BASE_WIDTH / 2, 
                 this.constants.BASE_HEIGHT - 500, 90, [180, 60, 120], true, 'Arial Black');
  }

  renderWinScreen(gameState) {
    this.renderStartupScreen(gameState);
    // Add win-specific rendering here
  }

  renderChampionScreen(gameState) {
    this.renderStartupScreen(gameState);
    // Add champion-specific rendering here
  }
}

export default GameRenderer;
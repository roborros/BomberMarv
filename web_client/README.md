# BomberMarv Web Client

React-based web frontend for the BomberMarv multiplayer game.

## Features

- **Real-time multiplayer** via WebSocket connection
- **Canvas-based rendering** for high performance
- **Mobile support** with touch controls
- **Keyboard controls** (WASD + Space)
- **Responsive design** that scales to fit screen

## Installation

1. Install Node.js (version 14 or higher)
2. Install dependencies:
   ```bash
   cd web_client
   npm install
   ```

## Development

Start the development server:
```bash
npm run dev
```

This will start the React development server on `http://localhost:3000`

## Production Build

Build for production:
```bash
npm run build
```

The built files will be in the `dist/` directory.

## Usage

1. Make sure the Python game server is running with web support:
   ```bash
   python pyBomberMarv_dual.py
   ```

2. Open your browser and navigate to:
   - Development: `http://localhost:3000`
   - Production: `http://localhost:8080` (served by Python HTTP server)

## Controls

### Desktop
- **WASD** - Move player
- **Space** - Place bomb

### Mobile
- Use the touch controls at the bottom of the screen
- **Arrows** - Move player
- **💣** - Place bomb

## Architecture

The web client connects to the Python game server via WebSocket and receives:
- **Game state updates** - Player positions, bombs, explosions, board state
- **Drawing commands** - Low-level rendering instructions (optional)

The client renders the game using HTML5 Canvas for optimal performance.

## Connection

- **WebSocket**: `ws://localhost:8765` - Game state and input
- **HTTP**: `http://localhost:8080` - Static file serving

## Browser Compatibility

- Chrome/Edge 80+
- Firefox 75+
- Safari 13+
- Mobile browsers with WebGL support
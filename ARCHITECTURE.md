# BomberMarv Architecture Documentation

## Overview
BomberMarv is a multiplayer Bomberman-style game with a hybrid architecture supporting both local pygame-based gameplay and web-based remote clients through WebSocket streaming.

## System Architecture

### High-Level Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    BomberMarv System                        │
├─────────────────────────────────────────────────────────────┤
│  Frontend Layer                                             │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │  Local PyGame   │    │     Web Client (HTML/JS)       │ │
│  │   Interface     │    │  - WebSocket Connection         │ │
│  │                 │    │  - JPEG Stream Display         │ │
│  │                 │    │  - Key Input Handling          │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Communication Layer                                        │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │ Local Events    │    │    WebSocket Server             │ │
│  │ (pygame events) │    │  - Frame Streaming (Port 8765) │ │
│  │                 │    │  - Input Processing             │ │
│  │                 │    │  - HTTP Server (Port 8080)     │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Backend/Game Engine Layer                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Core Game Engine                           │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │ │
│  │  │Game Logic   │ │   Physics   │ │   Rendering     │   │ │
│  │  │- Game State │ │- Collisions │ │- PyGame Surface │   │ │
│  │  │- Players    │ │- Movement   │ │- JPEG Encoding  │   │ │
│  │  │- Bombs      │ │- Grid Logic │ │- UI Drawing     │   │ │
│  │  │- Explosions │ │             │ │                 │   │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack Separation

### Backend Technologies
- **Python 3.x** - Core runtime
- **PyGame** - Game engine, graphics, and local input handling
- **asyncio/websockets** - WebSocket server for remote clients
- **aiohttp** - HTTP server for serving web client
- **TurboJPEG** - High-performance JPEG encoding for frame streaming
- **NumPy** - Image data processing
- **multiprocessing** - Process isolation between game and web server
- **PIL (Pillow)** - Image processing utilities
- **psutil** - Process management

### Frontend Technologies
#### Local Client (PyGame)
- **PyGame** - Native window management and rendering
- **Direct event handling** - Keyboard/mouse input

#### Web Client
- **HTML5** - Basic page structure
- **JavaScript (ES6+)** - Client-side logic
- **WebSocket API** - Real-time communication
- **Canvas/Image APIs** - Frame display
- **Fetch API** - Version information retrieval

## Backend/Frontend Separation

### Clear Separation Points

#### 1. **Process Boundary**
- **Backend Process**: Main game engine (`pyBomberMarv.py`)
- **WebSocket Server Process**: Communication layer (`ws_stream_server.py`)
- **Inter-process communication**: Multiprocessing queues
  - `frame_queue`: Backend → WebSocket server (JPEG frames)
  - `input_queue`: WebSocket server → Backend (player input)

#### 2. **Network Boundary**
- **Protocol**: WebSocket over TCP
- **Ports**: 
  - 8765 (WebSocket for game streaming)
  - 8080 (HTTP for client serving)
- **Data Format**: 
  - Frames: Binary JPEG data
  - Input: JSON messages

#### 3. **Responsibility Separation**

**Backend Responsibilities:**
- Game state management
- Physics simulation
- Collision detection
- Player logic
- Bomb/explosion mechanics
- Score tracking
- Rendering to surface
- Frame encoding

**Frontend Responsibilities:**
- Input capture and transmission
- Frame decoding and display
- FPS monitoring
- Connection management
- User interface overlays

## Core Module Architecture

### 1. **Main Game Module** (`pyBomberMarv.py`)
**Purpose**: Application entry point and orchestration
```python
# Key Functions:
- main loop coordination
- WebSocket server process management
- Frame encoding and streaming
- Input queue processing
```

### 2. **Game Classes** (`bm_classes.py`)
**Purpose**: Core game entities and logic
```python
# Key Classes:
- Game: Main game state manager
- Player: Player entities with movement/combat
- Bomb: Explosive entities with timers
- Explosion: Damage area effects
- PowerUp: Collectible items
- Screen: Display surface management
```

### 3. **WebSocket Server** (`ws_stream_server.py`)
**Purpose**: Network communication layer
```python
# Key Functions:
- WebSocket connection management
- Frame streaming to clients
- Input event processing
- HTTP client serving
- Player ID assignment
```

### 4. **Rendering Engine** (`bm_drawing.py`)
**Purpose**: Graphics and UI rendering
```python
# Key Functions:
- Game screen composition
- Entity drawing (players, bombs, explosions)
- UI screens (startup, game prep, win)
- Visual effects and animations
```

### 5. **Physics/Collision** (`lib_collisions.py`, `lib_grid.py`)
**Purpose**: Game physics and spatial logic
```python
# Key Functions:
- Circle-rectangle collision detection
- Grid-based movement
- Maze generation
- Safe zone clearing
```

### 6. **Configuration** (`bm_params.py`)
**Purpose**: Game constants and settings
```python
# Key Constants:
- Game dimensions and scaling
- Player/bomb parameters
- Colors and visual settings
- Control mappings
```

### 7. **Audio System** (`bm_sounds.py`)
**Purpose**: Sound effect management
```python
# Key Assets:
- Explosion sounds
- Bonus collection sounds
- Death sounds
- Quad damage effects
```

## Function Call Graph

### Main Game Loop Flow
```
pyBomberMarv.main()
├── kill_existing_ws_server_processes()
├── start_ws_server_with_queue()
│   └── ws_stream_server.run_server_with_queue()
├── Game.__init__()
├── Game.init_game()
├── Screen.__init__()
└── Main Loop:
    ├── Game.tick()
    │   ├── clock.tick(FPS)
    │   └── pygame.time.get_ticks()
    ├── Game.handle_window_events()
    │   └── pygame.event.get()
    ├── input_queue processing
    │   └── Game.handle_web_key_event()
    ├── State-based rendering:
    │   ├── Screen.draw_startup()
    │   ├── Screen.draw_game_prep()
    │   ├── draw_game_screen()
    │   │   ├── draw_board()
    │   │   ├── draw_powerups()
    │   │   ├── draw_bombs()
    │   │   ├── draw_explosions()
    │   │   └── draw_players()
    │   ├── draw_title_page()
    │   └── draw_champion_screen()
    ├── Game.update() [if playing]
    │   ├── Player.update() [for each player]
    │   │   ├── movement processing
    │   │   ├── collision detection
    │   │   └── bomb dropping
    │   ├── Bomb.update() [for each bomb]
    │   ├── explosion processing
    │   └── powerup collection
    ├── save_surface_as_jpeg()
    └── frame_queue.put()
```

### WebSocket Server Flow
```
ws_stream_server.run_server_with_queue()
├── frame_updater() [background thread]
│   └── frame_queue.get()
├── start_http_server() [background thread]
│   └── aiohttp web server
└── WebSocket handling:
    ├── stream_frames() [per client]
    │   ├── player ID assignment
    │   ├── input processing
    │   │   └── input_queue.put()
    │   └── frame transmission
    └── connection management
```

### Input Processing Flow
```
Input Sources:
├── Local (PyGame):
│   ├── pygame.event.get()
│   └── Game.handle_window_events()
└── Remote (WebSocket):
    ├── WebSocket.recv()
    ├── input_queue.put()
    ├── input_queue.get()
    └── Game.handle_web_key_event()
        └── Player.update(web_keys)
            └── browser_key_to_pygame()
```

### Rendering Pipeline
```
Rendering Flow:
├── Game state determines screen type
├── Screen-specific drawing functions
├── Entity rendering:
│   ├── Board rendering (grid-based)
│   ├── Entity rendering (position-based)
│   └── UI overlay rendering
├── PyGame surface composition
├── JPEG encoding (TurboJPEG)
└── Frame distribution:
    ├── Local display (pygame.display.flip)
    └── Remote streaming (WebSocket)
```

## Game State Management

### State Machine
```
States:
├── "startup" → "game_prep" → "get_ready" → "playing" → "win" → "champion"
│                     ↑                                      ↓
│                     └──────── game restart ←──────────────┘
│
└── State Transitions:
    ├── Enter key: startup → game_prep
    ├── Enter key: game_prep/win/champion → get_ready
    ├── Timer: get_ready → playing
    ├── Win condition: playing → win
    └── Trophy threshold: win → champion
```

## Data Flow Architecture

### Frame Streaming
```
Backend → WebSocket Server → Web Client
Game Surface → JPEG Bytes → Binary WebSocket → Image Display
```

### Input Processing
```
Web Client → WebSocket Server → Backend
Key Events → JSON Messages → Input Queue → Game Logic
```

### Process Communication
```
Main Process ←→ WebSocket Process
├── frame_queue (Backend → WebSocket)
└── input_queue (WebSocket → Backend)
```

## Key Design Patterns

### 1. **Observer Pattern**
- Input events propagated through queue system
- Multiple clients can observe same game state

### 2. **State Pattern**
- Game state machine with distinct behavior per state
- Screen rendering varies by current state

### 3. **Component Pattern**
- Game entities (Player, Bomb, Explosion) as discrete components
- Modular update and rendering systems

### 4. **Producer-Consumer Pattern**
- Frame production (game engine) and consumption (WebSocket clients)
- Input production (web clients) and consumption (game engine)

## Performance Considerations

### Frame Rate Management
- Target 60 FPS for game logic
- 30 FPS for WebSocket streaming
- Frame dropping in WebSocket queue to prevent lag

### Memory Management
- Single frame buffering in WebSocket queue
- JPEG compression for bandwidth efficiency
- Surface reuse in rendering pipeline

### Concurrency
- Process isolation between game and network
- Async WebSocket handling for multiple clients
- Thread-safe queue communication

## Security Considerations

### Input Validation
- Key mapping validation through `browser_key_to_pygame()`
- Player ID assignment and validation
- Bounded input queues

### Network Security
- Local network binding (no external exposure by default)
- WebSocket connection limits
- Input sanitization

## Extensibility Points

### Adding New Game Features
1. Extend game entities in `bm_classes.py`
2. Add rendering in `bm_drawing.py`
3. Update parameters in `bm_params.py`

### Adding New Client Types
1. Implement WebSocket client protocol
2. Handle frame decoding (JPEG)
3. Implement input JSON format

### Scaling Considerations
1. Multiple game instances (different ports)
2. Game server clustering
3. Database integration for persistent scores

This architecture provides a clean separation between game logic, rendering, and network communication while maintaining high performance for real-time multiplayer gameplay.
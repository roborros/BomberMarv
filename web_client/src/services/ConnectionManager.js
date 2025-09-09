// WebSocket connection manager for BomberMarv game

class ConnectionManager {
  constructor() {
    this.socket = null;
    this.eventListeners = {};
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
  }

  connect(url = 'ws://localhost:8765') {
    if (this.socket) {
      this.socket.disconnect();
    }

    this.emit('connecting');

    // Connect to raw WebSocket server
    this.connectWebSocket(url);
  }

  connectWebSocket(url) {
    try {
      this.socket = new WebSocket(url);

      this.socket.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.emit('connect');
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleMessage(data);
        } catch (error) {
          console.error('Error parsing message:', error);
        }
      };

      this.socket.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        this.emit('disconnect');
        this.attemptReconnect();
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.emit('error', error);
      };

    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.emit('error', error);
      this.attemptReconnect();
    }
  }

  handleMessage(data) {
    switch (data.type) {
      case 'connection_confirmed':
        console.log('Connection confirmed:', data.message);
        break;

      case 'game_state_update':
        this.emit('gameState', data.data);
        break;

      case 'draw_commands':
        this.emit('drawCommands', data.data);
        break;

      case 'pong':
        // Handle ping/pong for connection health
        break;

      default:
        console.log('Unknown message type:', data.type);
    }
  }

  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
      
      setTimeout(() => {
        this.connect();
      }, this.reconnectDelay * this.reconnectAttempts);
    } else {
      console.log('Max reconnect attempts reached');
      this.emit('maxReconnectAttemptsReached');
    }
  }

  sendInput(eventType, key, playerId = 0) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      // Normalize key names for server/browser differences
      const normalizedKey = (key || '').toLowerCase();
      const inputEvent = {
        type: 'input_event',
        event_type: eventType,
        key: normalizedKey,
        player_id: playerId,
        timestamp: Date.now(),
      };

      this.socket.send(JSON.stringify(inputEvent));
    }
  }

  ping() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'ping',
        timestamp: Date.now()
      }));
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  // Event emitter methods
  on(event, callback) {
    if (!this.eventListeners[event]) {
      this.eventListeners[event] = [];
    }
    this.eventListeners[event].push(callback);
  }

  emit(event, data) {
    if (this.eventListeners[event]) {
      this.eventListeners[event].forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in event listener for ${event}:`, error);
        }
      });
    }
  }

  off(event, callback) {
    if (this.eventListeners[event]) {
      this.eventListeners[event] = this.eventListeners[event].filter(cb => cb !== callback);
    }
  }
}

export default ConnectionManager;
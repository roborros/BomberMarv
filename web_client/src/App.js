import React, { useState, useEffect } from 'react';
import GameCanvas from './components/GameCanvas';
import ConnectionManager from './services/ConnectionManager';

function App() {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [gameState, setGameState] = useState(null);
  const [connectionManager] = useState(() => new ConnectionManager());
  const [showFps, setShowFps] = useState(false);

  useEffect(() => {
    // Set up connection event listeners
    connectionManager.on('connect', () => {
      setConnectionStatus('connected');
      console.log('Connected to game server');
    });

    connectionManager.on('disconnect', () => {
      setConnectionStatus('disconnected');
      console.log('Disconnected from game server');
    });

    connectionManager.on('connecting', () => {
      setConnectionStatus('connecting');
      console.log('Connecting to game server...');
    });

    connectionManager.on('gameState', (state) => {
      setGameState(state);
    });

    connectionManager.on('error', (error) => {
      console.error('Connection error:', error);
      setConnectionStatus('disconnected');
    });

    // Connect to server
    connectionManager.connect();

    // Cleanup on unmount
    return () => {
      connectionManager.disconnect();
    };
  }, [connectionManager]);

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'connected';
      case 'connecting': return 'connecting';
      default: return 'disconnected';
    }
  };

  const getStatusText = () => {
    switch (connectionStatus) {
      case 'connected': return 'Connected';
      case 'connecting': return 'Connecting...';
      default: return 'Disconnected';
    }
  };

  return (
    <div className="game-container">
      <div className={`connection-status ${getStatusColor()}`}>
        {getStatusText()}
      </div>
      <div style={{ position: 'absolute', top: 8, right: 8 }}>
        <label style={{ color: '#fff', userSelect: 'none' }}>
          <input type="checkbox" checked={showFps} onChange={(e) => setShowFps(e.target.checked)} /> Show FPS
        </label>
      </div>
      
      <GameCanvas 
        gameState={gameState}
        connectionManager={connectionManager}
        isConnected={connectionStatus === 'connected'}
        showFps={showFps}
      />
      
      <div className="controls-overlay">
        <div>Desktop: WASD + Space</div>
        <div>Mobile: Touch controls below</div>
      </div>
      
      <div className="mobile-controls">
        <button className="control-btn" data-key="w">↑</button>
        <button className="control-btn" data-key="s">↓</button>
        <button className="control-btn" data-key="a">←</button>
        <button className="control-btn" data-key="d">→</button>
        <button className="control-btn" data-key=" ">💣</button>
      </div>
    </div>
  );
}

export default App;
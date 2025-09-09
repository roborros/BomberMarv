import React, { useRef, useEffect, useState, useCallback } from 'react';
import GameRenderer from '../services/GameRenderer';

const GameCanvas = ({ gameState, connectionManager, isConnected }) => {
  const canvasRef = useRef(null);
  const rendererRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 1500, height: 1500 });
  const keysPressed = useRef(new Set());

  // Initialize renderer
  useEffect(() => {
    if (canvasRef.current && !rendererRef.current) {
      rendererRef.current = new GameRenderer(canvasRef.current);
    }
  }, []);

  // Handle game state updates
  useEffect(() => {
    if (gameState && rendererRef.current) {
      // Update canvas dimensions if needed
      const constants = gameState.constants;
      if (constants) {
        const newWidth = constants.BASE_WIDTH;
        const newHeight = constants.BASE_HEIGHT;
        
        if (newWidth !== dimensions.width || newHeight !== dimensions.height) {
          setDimensions({ width: newWidth, height: newHeight });
        }
      }

      // Render the game state
      rendererRef.current.render(gameState);
    }
  }, [gameState, dimensions]);

  // Handle keyboard input
  const handleKeyDown = useCallback((event) => {
    if (!isConnected) return;

    const key = event.key && event.key.length ? event.key.toLowerCase() : '';
    
    // Prevent default for game keys
    if (['w', 'a', 's', 'd', ' ', 'enter', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
      event.preventDefault();
    }

    // Only send if not already pressed (prevent key repeat)
    if (key && !keysPressed.current.has(key)) {
      keysPressed.current.add(key);
      connectionManager.sendInput('keydown', key);
    }
  }, [isConnected, connectionManager]);

  const handleKeyUp = useCallback((event) => {
    if (!isConnected) return;

    const key = event.key && event.key.length ? event.key.toLowerCase() : '';
    
    if (key && keysPressed.current.has(key)) {
      keysPressed.current.delete(key);
      connectionManager.sendInput('keyup', key);
    }
  }, [isConnected, connectionManager]);

  // Handle mobile touch controls
  const handleMobileControl = useCallback((key, isPress) => {
    if (!isConnected) return;

    if (isPress && !keysPressed.current.has(key)) {
      keysPressed.current.add(key);
      connectionManager.sendInput('keydown', key);
    } else if (!isPress && keysPressed.current.has(key)) {
      keysPressed.current.delete(key);
      connectionManager.sendInput('keyup', key);
    }
  }, [isConnected, connectionManager]);

  // Set up event listeners
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    // Mobile touch controls
    const mobileButtons = document.querySelectorAll('.control-btn');
    mobileButtons.forEach(button => {
      const key = button.getAttribute('data-key');
      
      const handleTouchStart = (e) => {
        e.preventDefault();
        handleMobileControl(key, true);
      };
      
      const handleTouchEnd = (e) => {
        e.preventDefault();
        handleMobileControl(key, false);
      };

      button.addEventListener('touchstart', handleTouchStart);
      button.addEventListener('touchend', handleTouchEnd);
      button.addEventListener('mousedown', handleTouchStart);
      button.addEventListener('mouseup', handleTouchEnd);
    });

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      
      // Cleanup mobile controls
      mobileButtons.forEach(button => {
        button.removeEventListener('touchstart', () => {});
        button.removeEventListener('touchend', () => {});
        button.removeEventListener('mousedown', () => {});
        button.removeEventListener('mouseup', () => {});
      });
    };
  }, [handleKeyDown, handleKeyUp, handleMobileControl]);

  // Handle window focus/blur to reset key states
  useEffect(() => {
    const handleBlur = () => {
      // Release all keys when window loses focus
      keysPressed.current.forEach(key => {
        connectionManager.sendInput('keyup', key);
      });
      keysPressed.current.clear();
    };

    window.addEventListener('blur', handleBlur);
    return () => window.removeEventListener('blur', handleBlur);
  }, [connectionManager]);

  // Scale canvas to fit screen while maintaining aspect ratio
  const getCanvasStyle = () => {
    const maxWidth = window.innerWidth - 40;
    const maxHeight = window.innerHeight - 100;
    
    const scaleX = maxWidth / dimensions.width;
    const scaleY = maxHeight / dimensions.height;
    const scale = Math.min(scaleX, scaleY, 1); // Don't upscale
    
    return {
      width: dimensions.width * scale,
      height: dimensions.height * scale,
    };
  };

  return (
    <canvas
      ref={canvasRef}
      className="game-canvas"
      width={dimensions.width}
      height={dimensions.height}
      style={getCanvasStyle()}
      tabIndex={0} // Make canvas focusable
    />
  );
};

export default GameCanvas;
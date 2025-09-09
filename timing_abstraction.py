"""
Timing abstraction layer using time.perf_counter() for millisecond precision.
This provides a clean interface that can be easily swapped between different timing backends.
Currently uses time.perf_counter() as the backend, but can be easily replaced with other timing sources.
"""

import time
from typing import Optional
from abc import ABC, abstractmethod

class TimingBackend(ABC):
    """Abstract base class for timing backends"""
    
    @abstractmethod
    def get_ticks(self) -> int:
        """Get current time in milliseconds"""
        pass
    
    @abstractmethod
    def create_clock(self) -> 'GameClock':
        """Create a game clock for frame rate control"""
        pass

class PerfCounterTimingBackend(TimingBackend):
    """time.perf_counter() based timing backend"""
    
    def __init__(self):
        self.start_time = time.perf_counter()
    
    def get_ticks(self) -> int:
        """Get current time in milliseconds using perf_counter"""
        return int((time.perf_counter() - self.start_time) * 1000)
    
    def create_clock(self) -> 'GameClock':
        """Create a game clock"""
        return GameClock(self)

class GameClock:
    """Game clock for frame rate control, similar to pygame.time.Clock"""
    
    def __init__(self, timing_backend: TimingBackend):
        self.timing_backend = timing_backend
        self.last_tick_time = 0
        self.target_fps = 60
        self.frame_count = 0
        self.fps_start_time = self.timing_backend.get_ticks()
    
    def tick(self, fps: Optional[int] = None) -> int:
        """
        Control frame rate and return milliseconds since last tick.
        Similar to pygame.time.Clock.tick()
        """
        if fps is not None:
            self.target_fps = fps
        
        current_time = self.timing_backend.get_ticks()
        
        if self.last_tick_time == 0:
            # First tick
            dt = 0
        else:
            dt = current_time - self.last_tick_time
        
        # Frame rate limiting
        if self.target_fps > 0:
            target_frame_time = 1000 / self.target_fps  # milliseconds per frame
            if dt < target_frame_time:
                sleep_time = (target_frame_time - dt) / 1000  # convert to seconds
                if sleep_time > 0:
                    time.sleep(sleep_time)
                dt = target_frame_time
        
        self.last_tick_time = self.timing_backend.get_ticks()
        self.frame_count += 1
        
        return int(dt)
    
    def get_fps(self) -> float:
        """Get current FPS"""
        current_time = self.timing_backend.get_ticks()
        if current_time - self.fps_start_time > 0:
            return (self.frame_count * 1000) / (current_time - self.fps_start_time)
        return 0.0
    
    def get_time(self) -> int:
        """Get time since clock creation in milliseconds"""
        return self.timing_backend.get_ticks()

class TimeManager:
    """Main timing manager that uses the configured backend"""
    
    def __init__(self, backend: TimingBackend = None):
        self.backend = backend or PerfCounterTimingBackend()
        self._clock: Optional[GameClock] = None
    
    def set_backend(self, backend: TimingBackend):
        """Switch to a different timing backend"""
        self.backend = backend
        self._clock = None  # Reset clock when backend changes
    
    def get_ticks(self) -> int:
        """Get current time in milliseconds"""
        return self.backend.get_ticks()
    
    def create_clock(self) -> GameClock:
        """Create a new game clock"""
        return self.backend.create_clock()
    
    def get_clock(self) -> GameClock:
        """Get or create the default clock"""
        if self._clock is None:
            self._clock = self.create_clock()
        return self._clock

# Global timing manager instance
timing_manager = TimeManager()

# Convenience functions that use the global timing manager
def get_ticks() -> int:
    """Get current time in milliseconds"""
    return timing_manager.get_ticks()

def Clock(fps: int = 60) -> GameClock:
    """Create a game clock, similar to pygame.time.Clock()"""
    return timing_manager.create_clock()

def set_timing_backend(backend: TimingBackend):
    """Switch to a different timing backend"""
    timing_manager.set_backend(backend)

# Example of how to switch backends:
# 
# # Switch to a different timing backend
# from timing_abstraction import set_timing_backend, PerfCounterTimingBackend
# set_timing_backend(PerfCounterTimingBackend())
#
# # Create custom timing backend
# class CustomTimingBackend(TimingBackend):
#     def get_ticks(self): return int(time.time() * 1000)
#     def create_clock(self): return GameClock(self)
# set_timing_backend(CustomTimingBackend())

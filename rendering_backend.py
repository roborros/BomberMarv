"""
Abstract rendering backend interface for BomberMarv
Supports multiple rendering targets: pygame, web canvas, etc.
"""
from abc import ABC, abstractmethod
from typing import Tuple, List, Optional, Any
from dataclasses import dataclass

# Color type alias
Color = Tuple[int, int, int]
Position = Tuple[float, float]
Size = Tuple[int, int]

@dataclass
class DrawCommand:
    """Base class for drawing commands that can be serialized"""
    pass

@dataclass
class DrawRect(DrawCommand):
    x: float
    y: float
    width: float
    height: float
    color: Color
    border_width: int = 0
    border_color: Optional[Color] = None

@dataclass
class DrawCircle(DrawCommand):
    x: float
    y: float
    radius: float
    color: Color
    border_width: int = 0
    border_color: Optional[Color] = None

@dataclass
class DrawText(DrawCommand):
    text: str
    x: float
    y: float
    font_name: str
    font_size: int
    color: Color
    center: bool = False

@dataclass
class DrawImage(DrawCommand):
    image_name: str
    x: float
    y: float
    width: Optional[float] = None
    height: Optional[float] = None
    alpha: float = 1.0

@dataclass
class DrawLine(DrawCommand):
    x1: float
    y1: float
    x2: float
    y2: float
    color: Color
    width: int = 1

@dataclass
class FillBackground(DrawCommand):
    color: Color

class RenderingBackend(ABC):
    """Abstract base class for rendering backends"""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.commands: List[DrawCommand] = []
    
    @abstractmethod
    def init(self) -> bool:
        """Initialize the rendering backend"""
        pass
    
    @abstractmethod
    def clear(self):
        """Clear the screen/surface"""
        pass
    
    @abstractmethod
    def present(self):
        """Present/display the rendered frame"""
        pass
    
    @abstractmethod
    def shutdown(self):
        """Cleanup resources"""
        pass
    
    # Drawing primitives
    def fill_background(self, color: Color):
        """Fill background with solid color"""
        cmd = FillBackground(color)
        self.commands.append(cmd)
        self._fill_background(cmd)
    
    def draw_rect(self, x: float, y: float, width: float, height: float, 
                  color: Color, border_width: int = 0, border_color: Optional[Color] = None):
        """Draw a rectangle"""
        cmd = DrawRect(x, y, width, height, color, border_width, border_color)
        self.commands.append(cmd)
        self._draw_rect(cmd)
    
    def draw_circle(self, x: float, y: float, radius: float, color: Color, 
                    border_width: int = 0, border_color: Optional[Color] = None):
        """Draw a circle"""
        cmd = DrawCircle(x, y, radius, color, border_width, border_color)
        self.commands.append(cmd)
        self._draw_circle(cmd)
    
    def draw_text(self, text: str, x: float, y: float, font_name: str, 
                  font_size: int, color: Color, center: bool = False):
        """Draw text"""
        cmd = DrawText(text, x, y, font_name, font_size, color, center)
        self.commands.append(cmd)
        self._draw_text(cmd)
    
    def draw_image(self, image_name: str, x: float, y: float, 
                   width: Optional[float] = None, height: Optional[float] = None, alpha: float = 1.0):
        """Draw an image"""
        cmd = DrawImage(image_name, x, y, width, height, alpha)
        self.commands.append(cmd)
        self._draw_image(cmd)
    
    def draw_line(self, x1: float, y1: float, x2: float, y2: float, 
                  color: Color, width: int = 1):
        """Draw a line"""
        cmd = DrawLine(x1, y1, x2, y2, color, width)
        self.commands.append(cmd)
        self._draw_line(cmd)
    
    def get_commands(self) -> List[DrawCommand]:
        """Get all drawing commands for this frame"""
        return self.commands.copy()
    
    def clear_commands(self):
        """Clear the command buffer"""
        self.commands.clear()
    
    # Abstract methods that backends must implement
    @abstractmethod
    def _fill_background(self, cmd: FillBackground):
        pass
    
    @abstractmethod
    def _draw_rect(self, cmd: DrawRect):
        pass
    
    @abstractmethod
    def _draw_circle(self, cmd: DrawCircle):
        pass
    
    @abstractmethod
    def _draw_text(self, cmd: DrawText):
        pass
    
    @abstractmethod
    def _draw_image(self, cmd: DrawImage):
        pass
    
    @abstractmethod
    def _draw_line(self, cmd: DrawLine):
        pass

class WebRenderingBackend(RenderingBackend):
    """Rendering backend that only collects commands for web transmission"""
    
    def init(self) -> bool:
        return True
    
    def clear(self):
        self.clear_commands()
    
    def present(self):
        # Commands are sent via WebSocket, nothing to do here
        pass
    
    def shutdown(self):
        pass
    
    # Web backend doesn't actually draw, just collects commands
    def _fill_background(self, cmd: FillBackground):
        pass
    
    def _draw_rect(self, cmd: DrawRect):
        pass
    
    def _draw_circle(self, cmd: DrawCircle):
        pass
    
    def _draw_text(self, cmd: DrawText):
        pass
    
    def _draw_image(self, cmd: DrawImage):
        pass
    
    def _draw_line(self, cmd: DrawLine):
        pass
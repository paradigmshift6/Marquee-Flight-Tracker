"""Renderer package — adaptive layout engine and frame painter for LED matrix."""

from .engine import LayoutEngine
from .painter import FramePainter

__all__ = ["LayoutEngine", "FramePainter"]

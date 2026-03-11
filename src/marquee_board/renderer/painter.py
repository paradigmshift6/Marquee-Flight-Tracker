"""Frame painter — renders a FrameLayout to a PIL Image.

Takes the positioned elements from the layout engine and draws them
onto an RGB PIL Image at the exact pixel dimensions of the LED matrix.
"""

import logging
from typing import Tuple

from PIL import Image, ImageDraw

from .engine import FrameLayout, TextElement, IconElement, RectElement
from .fonts import FontManager
from .icons import get_icon
from . import colors

logger = logging.getLogger(__name__)


class FramePainter:
    """Renders a FrameLayout to a PIL Image."""

    def __init__(self, width: int = 64, height: int = 64):
        self.width = width
        self.height = height
        self._fonts = FontManager()

    def paint(self, layout: FrameLayout) -> Image.Image:
        """Render all elements in the layout to an RGB PIL Image."""
        img = Image.new("RGB", (self.width, self.height), colors.BG_COLOR)
        draw = ImageDraw.Draw(img)

        for element in layout.elements:
            if isinstance(element, RectElement):
                self._draw_rect(draw, element)
            elif isinstance(element, TextElement):
                self._draw_text(draw, img, element)
            elif isinstance(element, IconElement):
                self._draw_icon(img, element)

        return img

    def _draw_rect(self, draw: ImageDraw.ImageDraw, el: RectElement):
        draw.rectangle(
            [el.x, el.y, el.x + el.w - 1, el.y + el.h - 1],
            fill=el.color,
        )

    def _draw_text(self, draw: ImageDraw.ImageDraw, img: Image.Image, el: TextElement):
        font = self._fonts.get(el.font_name)
        # Clip text to image bounds
        draw.text((el.x, el.y), el.text, fill=el.color, font=font)

    def _draw_icon(self, img: Image.Image, el: IconElement):
        icon_data = get_icon(el.icon_name, el.size)
        if not icon_data:
            return

        for row_idx, row in enumerate(icon_data):
            for col_idx, pixel in enumerate(row):
                if pixel != (0, 0, 0):
                    px = el.x + col_idx
                    py = el.y + row_idx
                    if 0 <= px < self.width and 0 <= py < self.height:
                        img.putpixel((px, py), pixel)

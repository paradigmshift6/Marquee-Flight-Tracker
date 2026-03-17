"""Frame painter — renders a FrameLayout to a PIL Image.

Takes the positioned elements from the layout engine and draws them
onto an RGB PIL Image at the exact pixel dimensions of the LED matrix.
Text elements support optional max_width constraints with truncation
("..") or time-based horizontal scrolling for long content.

LED legibility note
-------------------
TrueType fonts rendered via Pillow produce anti-aliased intermediate-
grey pixels.  On a physical LED matrix every pixel is distinctly lit,
so those grey values appear as dim halos that make text look blurry.
All text is therefore rendered to a greyscale scratch surface first,
hard-thresholded at 50% brightness, and then painted onto the frame
with the target colour.  The result is clean, binary on/off pixels.
"""

import logging
import time as _time
from typing import Tuple

from PIL import Image, ImageDraw

from .engine import FrameLayout, TextElement, IconElement, RectElement
from .fonts import FontManager
from .icons import get_icon
from . import colors

logger = logging.getLogger(__name__)

# Scroll tuning
_SCROLL_PAUSE = 2.0    # seconds to pause at each end
_SCROLL_SPEED = 22.0   # pixels per second


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
                self._draw_text(img, element)
            elif isinstance(element, IconElement):
                self._draw_icon(img, element)

        return img

    def _draw_rect(self, draw: ImageDraw.ImageDraw, el: RectElement):
        draw.rectangle(
            [el.x, el.y, el.x + el.w - 1, el.y + el.h - 1],
            fill=el.color,
        )

    def _draw_text(self, img: Image.Image, el: TextElement):
        font = self._fonts.get(el.font_name)

        # No width constraint → draw full text (clips at image edge naturally)
        if el.max_width is None or el.max_width <= 0:
            self._render_sharp(img, el.x, el.y, el.text, font, el.color)
            return

        text_w = self._fonts.text_width(el.text, el.font_name)

        # Fits within constraint → draw normally
        if text_w <= el.max_width:
            self._render_sharp(img, el.x, el.y, el.text, font, el.color)
            return

        if el.scroll:
            self._draw_scrolling_text(img, el, font, text_w)
        else:
            self._draw_truncated_text(img, el, font)

    @staticmethod
    def _render_sharp(
        img: Image.Image,
        x: int,
        y: int,
        text: str,
        font,
        color: tuple,
    ):
        """Paint text with binary (non-antialiased) pixels for crisp LED output.

        Renders via a greyscale scratch image then hard-thresholds at 128 so
        every glyph pixel is either fully on (255) or fully off (0).  This
        eliminates the dim anti-aliasing halos that TrueType rendering
        produces on physical LED matrices.
        """
        if not text:
            return
        # Render text onto a same-size greyscale scratch canvas
        tmp = Image.new("L", img.size, 0)
        ImageDraw.Draw(tmp).text((x, y), text, fill=255, font=font)
        # Threshold: keep pixels above 40 to preserve thin strokes that
        # TrueType anti-aliasing renders at lower brightness at small sizes.
        # 127 cuts too aggressively and breaks character shapes; 40 eliminates
        # the faint halo (0-39) while keeping all meaningful glyph pixels.
        alpha = tmp.point(lambda p: 255 if p > 40 else 0)
        colored = Image.new("RGB", img.size, color[:3])
        img.paste(colored, mask=alpha)

    def _draw_truncated_text(
        self,
        img: Image.Image,
        el: TextElement,
        font,
    ):
        """Truncate text with '..' to fit within max_width, rendered sharply."""
        ellipsis = ".."
        ew = self._fonts.text_width(ellipsis, el.font_name)
        truncated = el.text
        while (
            len(truncated) > 1
            and self._fonts.text_width(truncated, el.font_name) + ew > el.max_width
        ):
            truncated = truncated[:-1]
        self._render_sharp(
            img, el.x, el.y, truncated.rstrip() + ellipsis, font, el.color
        )

    def _draw_scrolling_text(
        self,
        img: Image.Image,
        el: TextElement,
        font,
        text_w: int,
    ):
        """Render text with time-based horizontal scrolling.

        Cycle: pause at start → scroll left → pause at end → scroll right.
        Uses wall-clock time so each frame request gets the right offset
        without any stored state.
        """
        overflow = text_w - el.max_width
        scroll_dur = overflow / _SCROLL_SPEED
        cycle = _SCROLL_PAUSE + scroll_dur + _SCROLL_PAUSE + scroll_dur
        t = _time.time() % cycle

        if t < _SCROLL_PAUSE:
            offset = 0
        elif t < _SCROLL_PAUSE + scroll_dur:
            frac = (t - _SCROLL_PAUSE) / scroll_dur
            offset = int(frac * overflow)
        elif t < _SCROLL_PAUSE + scroll_dur + _SCROLL_PAUSE:
            offset = overflow
        else:
            frac = (t - 2 * _SCROLL_PAUSE - scroll_dur) / scroll_dur
            offset = int(overflow * (1 - frac))

        offset = max(0, min(offset, overflow))

        pad = 4

        # Use the full image height as scratch canvas height (same strategy as
        # _render_sharp).  Drawing at (0, el.y) means the character pixels land
        # at the correct vertical position without needing an accurate text_h
        # measurement — getbbox() on BDF bitmap fonts can return a tight bounding
        # box that clips descenders/ascenders when used as a canvas height.
        tmp_gray = Image.new("L", (text_w + pad, img.height), 0)
        ImageDraw.Draw(tmp_gray).text((0, el.y), el.text, fill=255, font=font)
        # Match the threshold used by _render_sharp (40) so scrolling and static
        # text have identical stroke fidelity.
        alpha_full = tmp_gray.point(lambda p: 255 if p > 40 else 0)

        # Crop only horizontally to the visible window; preserve full height
        crop_right = min(offset + el.max_width, text_w + pad)
        alpha_crop = alpha_full.crop((offset, 0, crop_right, img.height))

        colored = Image.new("RGB", alpha_crop.size, el.color[:3])
        img.paste(colored, (el.x, 0), alpha_crop)

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

"""Font manager for bitmap rendering on LED matrices.

Uses Pillow's built-in bitmap fonts at small pixel sizes. Optionally loads
BDF/PCF bitmap fonts if available for pixel-perfect rendering.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import ImageFont

logger = logging.getLogger(__name__)

# Font directory for optional custom BDF fonts
_FONT_DIR = Path(__file__).parent / "bdf_fonts"

# Pillow built-in truetype sizes that work well on LED matrices
_BUILTIN_SIZES = {
    "tiny": 8,
    "small": 10,
    "medium": 12,
    "large": 16,
}


class FontManager:
    """Loads and caches fonts for the frame painter."""

    def __init__(self):
        self._cache: Dict[str, ImageFont.ImageFont] = {}
        self._default = ImageFont.load_default()

    def get(self, name: str = "small") -> ImageFont.ImageFont:
        """Get a font by logical name (tiny, small, medium, large).

        Falls back to Pillow's default bitmap font if nothing else works.
        """
        if name in self._cache:
            return self._cache[name]

        font = self._try_load(name)
        self._cache[name] = font
        return font

    def measure(self, text: str, font_name: str = "small") -> Tuple[int, int]:
        """Return (width, height) of rendered text."""
        font = self.get(font_name)
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def text_width(self, text: str, font_name: str = "small") -> int:
        return self.measure(text, font_name)[0]

    def _try_load(self, name: str) -> ImageFont.ImageFont:
        # Try BDF font first
        bdf_path = _FONT_DIR / f"{name}.bdf"
        if bdf_path.exists():
            try:
                font = ImageFont.load(str(bdf_path))
                logger.debug("Loaded BDF font: %s", bdf_path)
                return font
            except Exception:
                logger.debug("Failed to load BDF font %s", bdf_path)

        # Fall back to Pillow truetype at appropriate size
        size = _BUILTIN_SIZES.get(name, 10)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size)
            return font
        except (OSError, IOError):
            pass

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
            return font
        except (OSError, IOError):
            pass

        # Last resort: Pillow default bitmap font
        return self._default

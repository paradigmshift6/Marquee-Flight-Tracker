"""Font manager for bitmap rendering on LED matrices.

Prefers BDF bitmap fonts from the rpi-rgb-led-matrix library for pixel-perfect,
alias-free rendering on physical LED panels. Falls back to TrueType (with
threshold rendering) when BDF sources are not available (e.g. Mac dev).

BDF conversion flow
-------------------
PIL cannot load `.bdf` files directly.  The correct path is:
  1. ``PIL.BdfFontFile.BdfFontFile(fp).save(stem)``  → writes ``stem.pil`` + ``stem.pbm``
  2. ``ImageFont.load("stem.pil")``                  → loads the binary bitmap font

Converted fonts are cached in a ``bdf_cache/`` subdirectory next to this file so
the conversion only happens once per installation.
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import BdfFontFile, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BDF source discovery
# ---------------------------------------------------------------------------

# Logical name → BDF filename (in rpi-rgb-led-matrix/fonts/)
_BDF_NAMES: Dict[str, str] = {
    "tiny":   "5x7.bdf",
    "small":  "6x10.bdf",
    "medium": "7x13.bdf",
    "large":  "9x15.bdf",
}

# Known locations of BDF font files.  The bundled directory ships with the
# package and is checked first so the fonts always load regardless of
# external rpi-rgb-led-matrix install or file-permission quirks.
_BDF_SEARCH_DIRS: List[Path] = [
    Path(__file__).parent / "bdf_fonts",          # bundled (always present)
    Path("/home/levi/rpi-rgb-led-matrix/fonts"),
    Path("/usr/share/rpi-rgb-led-matrix/fonts"),
    Path("/opt/rpi-rgb-led-matrix/fonts"),
]

# Where converted .pil / .pbm files are cached
_CACHE_DIR = Path(__file__).parent / "bdf_cache"

# ---------------------------------------------------------------------------
# TrueType fallback sizes (used on Mac / CI where no BDF fonts exist)
# ---------------------------------------------------------------------------
_TRUETYPE_SIZES: Dict[str, int] = {
    "tiny":   8,
    "small":  10,
    "medium": 12,
    "large":  16,
}

_TRUETYPE_SEARCH: List[str] = [
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


# ---------------------------------------------------------------------------
# FontManager
# ---------------------------------------------------------------------------

class FontManager:
    """Loads and caches fonts for the frame painter.

    On a Raspberry Pi with rpi-rgb-led-matrix installed the logical names
    map to BDF bitmap fonts for crisp, alias-free text.  On a development
    machine without those fonts it falls back to TrueType.
    """

    def __init__(self):
        self._cache: Dict[str, ImageFont.ImageFont] = {}
        self._is_bdf: Dict[str, bool] = {}  # name → True if BDF (purely binary, no AA)
        self._default = ImageFont.load_default()
        self._bdf_source_dir: Optional[Path] = _find_bdf_source_dir()
        if self._bdf_source_dir:
            logger.info("BDF font source directory: %s", self._bdf_source_dir)
        else:
            logger.info("No BDF font source directory found; will use TrueType fallback")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str = "small") -> ImageFont.ImageFont:
        """Return a font by logical name (tiny, small, medium, large)."""
        if name in self._cache:
            return self._cache[name]
        font = self._load(name)
        self._cache[name] = font
        return font

    def is_binary(self, name: str = "small") -> bool:
        """True if the font for *name* is a BDF bitmap (purely binary pixels).

        When True the painter can skip the greyscale threshold step and
        draw text directly — faster and pixel-perfect.
        """
        self.get(name)  # ensure loaded
        return self._is_bdf.get(name, False)

    def measure(self, text: str, font_name: str = "small") -> Tuple[int, int]:
        """Return (width, height) of rendered *text*."""
        font = self.get(font_name)
        try:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            # Pillow < 9.2 or default bitmap font
            w, h = font.getsize(text)  # type: ignore[attr-defined]
            return w, h

    def text_width(self, text: str, font_name: str = "small") -> int:
        return self.measure(text, font_name)[0]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self, name: str) -> ImageFont.ImageFont:
        # 1. Try BDF → PIL conversion path (binary, no anti-aliasing)
        if self._bdf_source_dir:
            font = self._load_bdf(name)
            if font is not None:
                self._is_bdf[name] = True
                return font

        # 2. TrueType fallback (anti-aliased, needs threshold)
        font = self._load_truetype(name)
        if font is not None:
            self._is_bdf[name] = False
            return font

        # 3. Absolute last resort
        logger.warning("Using Pillow default bitmap font for '%s'", name)
        self._is_bdf[name] = False
        return self._default

    def _load_bdf(self, name: str) -> Optional[ImageFont.ImageFont]:
        """Convert (if needed) and load a BDF font.  Returns None on failure."""
        bdf_filename = _BDF_NAMES.get(name)
        if not bdf_filename:
            return None

        assert self._bdf_source_dir is not None
        bdf_path = self._bdf_source_dir / bdf_filename
        # Python 3.13 changed Path.exists() to raise PermissionError instead of
        # returning False.  Treat any OSError as "not accessible".
        try:
            bdf_exists = bdf_path.exists()
        except OSError:
            bdf_exists = False
        if not bdf_exists:
            logger.debug("BDF source not accessible: %s", bdf_path)
            return None

        pil_path = _ensure_converted(bdf_path, name)
        if pil_path is None:
            return None

        try:
            font = ImageFont.load(str(pil_path))
            logger.debug("Loaded BDF bitmap font '%s' from %s", name, pil_path)
            return font
        except Exception as exc:
            logger.warning("Failed to load converted PIL font %s: %s", pil_path, exc)
            return None

    def _load_truetype(self, name: str) -> Optional[ImageFont.ImageFont]:
        size = _TRUETYPE_SIZES.get(name, 10)
        for path in _TRUETYPE_SEARCH:
            try:
                font = ImageFont.truetype(path, size)
                logger.debug("Loaded TrueType font '%s' @ %dpx from %s", name, size, path)
                return font
            except (OSError, IOError):
                continue
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _find_bdf_source_dir() -> Optional[Path]:
    """Return the first directory in _BDF_SEARCH_DIRS that contains BDF files."""
    for d in _BDF_SEARCH_DIRS:
        try:
            if d.is_dir() and any(d.glob("*.bdf")):
                return d
        except OSError:
            continue
    return None


def _ensure_converted(bdf_path: Path, name: str) -> Optional[Path]:
    """Convert *bdf_path* to a Pillow PIL font if not already cached.

    Returns the path to the ``.pil`` file, or None on failure.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Cannot create BDF cache dir %s: %s", _CACHE_DIR, exc)
        # Fall back to a temp dir for this run
        try:
            tmp = Path(tempfile.mkdtemp(prefix="marquee_bdf_"))
        except OSError:
            return None
        return _convert_bdf(bdf_path, tmp / name)

    return _convert_bdf(bdf_path, _CACHE_DIR / name)


def _convert_bdf(bdf_path: Path, stem: Path) -> Optional[Path]:
    """Run BdfFontFile conversion.  *stem* is the path without extension.

    PIL writes ``{stem}.pil`` and ``{stem}.pbm``.
    Returns path to ``.pil`` on success, None on failure.
    """
    pil_path = stem.with_suffix(".pil")

    # Already converted?
    if pil_path.exists() and pil_path.stat().st_size > 0:
        return pil_path

    try:
        with open(bdf_path, "rb") as fp:
            bdf = BdfFontFile.BdfFontFile(fp)
            bdf.save(str(stem))
        logger.info("Converted BDF font %s → %s", bdf_path.name, pil_path)
        return pil_path
    except Exception as exc:
        logger.warning("BDF conversion failed for %s: %s", bdf_path, exc)
        return None

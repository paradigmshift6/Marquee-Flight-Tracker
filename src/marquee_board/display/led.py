"""LED matrix display backend using rpi-rgb-led-matrix (hzeller).

Only works on Raspberry Pi with a HUB75 LED panel connected.
The rgbmatrix library is imported lazily so the rest of the app
can run on any platform (web simulator, terminal, etc.).
"""

import logging
from typing import Dict, List

from .base import DisplayBackend

logger = logging.getLogger(__name__)


class LEDDisplay(DisplayBackend):
    def __init__(
        self,
        width: int = 64,
        height: int = 64,
        brightness: int = 80,
        gpio_slowdown: int = 4,
    ):
        self._width = width
        self._height = height
        self._brightness = brightness
        self._gpio_slowdown = gpio_slowdown
        self._matrix = None
        self._engine = None
        self._painter = None

    def start(self) -> None:
        # Initialize renderer
        from ..renderer.engine import LayoutEngine
        from ..renderer.painter import FramePainter

        self._engine = LayoutEngine(self._width, self._height)
        self._painter = FramePainter(self._width, self._height)

        # Initialize LED matrix hardware
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions

            options = RGBMatrixOptions()
            options.rows = self._height
            options.cols = self._width
            options.brightness = self._brightness
            options.gpio_slowdown = self._gpio_slowdown
            options.hardware_mapping = "regular"

            self._matrix = RGBMatrix(options=options)
            logger.info(
                "LED matrix initialized (%dx%d, brightness=%d)",
                self._width, self._height, self._brightness,
            )
        except ImportError:
            logger.error(
                "rpi-rgb-led-matrix not installed. "
                "Install with: pip install marquee-board[led]"
            )
            raise
        except Exception as e:
            logger.error("Failed to initialize LED matrix: %s", e)
            raise

    def update(
        self,
        grouped: Dict[str, List[str]],
        display_names: Dict[str, str],
        **kwargs,
    ) -> None:
        if not self._matrix or not self._engine or not self._painter:
            return

        messages = kwargs.get("structured", [])
        layout = self._engine.layout(messages)
        img = self._painter.paint(layout)

        # Push PIL Image to the LED matrix
        self._matrix.SetImage(img)

    def stop(self) -> None:
        if self._matrix:
            self._matrix.Clear()
            logger.info("LED matrix cleared")

import logging
import signal
import time
from typing import Dict, List

from .config import AppConfig
from .display.base import DisplayBackend
from .providers.base import MarqueeMessage, MarqueeProvider

logger = logging.getLogger(__name__)


class MarqueeBoardApp:
    def __init__(self, config: AppConfig):
        self._config = config
        self._providers: List[MarqueeProvider] = []
        self._display = self._build_display(config)
        self._running = False
        self._init_providers(config)

    def run(self):
        """Main loop: poll all providers, collect messages, update display."""
        for p in self._providers:
            p.start()
        self._display.start()
        self._running = True

        signal.signal(signal.SIGINT, lambda *_: self._shutdown())
        signal.signal(signal.SIGTERM, lambda *_: self._shutdown())

        logger.info(
            "Marquee Board started with %d provider(s): %s",
            len(self._providers),
            ", ".join(p.name for p in self._providers),
        )

        while self._running:
            try:
                grouped: Dict[str, List[str]] = {}
                display_names: Dict[str, str] = {}
                all_messages: List[MarqueeMessage] = []

                for provider in self._providers:
                    messages = provider.fetch_messages()
                    grouped[provider.name] = [m.text for m in messages]
                    display_names[provider.name] = provider.display_name
                    all_messages.extend(messages)

                self._display.update(
                    grouped, display_names, structured=all_messages
                )

            except Exception:
                logger.exception("Error in main loop")

            time.sleep(2)

    def _init_providers(self, config: AppConfig):
        if config.flights.enabled:
            from .providers.flights import FlightProvider
            self._providers.append(FlightProvider(config))

        if config.weather.enabled:
            try:
                from .providers.weather import WeatherProvider
                self._providers.append(WeatherProvider(config))
            except Exception as e:
                logger.warning("Weather provider unavailable: %s", e)

        if config.calendar.enabled:
            try:
                from .providers.calendar import CalendarProvider
                self._providers.append(CalendarProvider(config))
            except Exception as e:
                logger.warning("Calendar provider unavailable: %s", e)

    def _build_display(self, config: AppConfig) -> DisplayBackend:
        backend = config.display.backend

        if backend == "terminal":
            from .display.terminal import TerminalDisplay
            return TerminalDisplay(
                scroll_speed=config.display.scroll_speed,
                idle_message=config.display.idle_message,
            )
        elif backend == "web":
            from .display.web import WebDisplay
            return WebDisplay(
                host=config.web.host,
                port=config.web.port,
                idle_message=config.display.idle_message,
                renderer_width=config.renderer.width,
                renderer_height=config.renderer.height,
            )
        elif backend == "led":
            from .display.led import LEDDisplay
            return LEDDisplay(
                width=config.renderer.width,
                height=config.renderer.height,
                brightness=config.renderer.brightness,
                gpio_slowdown=config.renderer.gpio_slowdown,
            )
        else:
            raise ValueError(f"Unknown display backend: {backend}")

    def _shutdown(self):
        logger.info("Shutting down...")
        self._running = False
        for p in self._providers:
            p.stop()
        self._display.stop()

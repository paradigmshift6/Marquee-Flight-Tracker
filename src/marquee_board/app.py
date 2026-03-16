import logging
import signal
import time
from datetime import datetime
from typing import Dict, List

from .config import AppConfig
from .display.base import DisplayBackend
from .providers.base import MarqueeMessage, MarqueeProvider

logger = logging.getLogger(__name__)


class MarqueeBoardApp:
    def __init__(self, config: AppConfig, config_path: str = "config.yaml"):
        self._config = config
        self._config_path = config_path
        self._providers: List[MarqueeProvider] = []
        self._display = self._build_display(config)
        self._running = False
        self._sleeping = False
        self._init_providers(config)

    def run(self):
        """Main loop: poll all providers, collect messages, update display."""
        for p in self._providers:
            p.start()
        self._display.start()
        self._running = True

        # Signal handlers only set the flag; cleanup happens after the loop.
        signal.signal(signal.SIGINT, lambda *_: setattr(self, '_running', False))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, '_running', False))

        logger.info(
            "Marquee Board started with %d provider(s): %s",
            len(self._providers),
            ", ".join(p.name for p in self._providers),
        )

        try:
            while self._running:
                try:
                    if not self._is_active():
                        if not self._sleeping:
                            logger.info("Outside active hours — entering sleep mode")
                            self._sleeping = True
                            self._display.update({}, {}, structured=[])
                        time.sleep(30)
                        continue

                    if self._sleeping:
                        logger.info("Active hours — waking up")
                        self._sleeping = False

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
        finally:
            self._cleanup()

    def _cleanup(self):
        """Stop all providers and display. Safe to call multiple times."""
        logger.info("Shutting down...")
        for p in self._providers:
            try:
                p.stop()
            except Exception:
                logger.debug("Error stopping provider %s", p.name, exc_info=True)
        try:
            self._display.stop()
        except Exception:
            logger.debug("Error stopping display", exc_info=True)

    def _is_active(self) -> bool:
        """Check if current time is within configured active hours."""
        sched = self._config.schedule
        if not sched.enabled:
            return True

        try:
            start = datetime.strptime(sched.active_start, "%H:%M").time()
            end = datetime.strptime(sched.active_end, "%H:%M").time()
        except ValueError:
            logger.warning("Invalid schedule times, staying active")
            return True

        now = datetime.now().time()

        if start <= end:
            # Normal range, e.g. 06:30 - 18:00
            return start <= now <= end
        else:
            # Overnight range, e.g. 22:00 - 06:00
            return now >= start or now <= end

    def _init_providers(self, config: AppConfig):
        if config.flights.enabled:
            try:
                from .providers.flights import FlightProvider
                self._providers.append(FlightProvider(config))
            except Exception as e:
                logger.warning("Flight provider unavailable: %s", e)

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
                config=config,
                config_path=self._config_path,
            )
        elif backend == "led":
            from .display.led import LEDDisplay
            return LEDDisplay(
                width=config.renderer.width,
                height=config.renderer.height,
                brightness=config.renderer.brightness,
                gpio_slowdown=config.renderer.gpio_slowdown,
                hardware_mapping=config.renderer.hardware_mapping,
            )
        else:
            raise ValueError(f"Unknown display backend: {backend}")

    def _shutdown(self):
        """Legacy entry point — just sets the flag; cleanup is in _cleanup()."""
        self._running = False

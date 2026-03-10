import logging
import signal
import time
from pathlib import Path
from typing import List

from .config import AppConfig
from .display.base import DisplayBackend
from .display.terminal import TerminalDisplay
from .fetcher import OpenSkyFetcher
from .formatter import format_flight
from .geo import compute_bounding_box, haversine
from .models import EnrichedFlight, RawAircraftState

logger = logging.getLogger(__name__)


class FlightTrackerApp:
    def __init__(self, config: AppConfig):
        self._config = config
        self._bbox = compute_bounding_box(
            config.location.latitude,
            config.location.longitude,
            config.location.radius_miles,
        )
        self._fetcher = OpenSkyFetcher(
            self._bbox,
            min_interval=config.polling.interval_seconds,
            client_id=config.opensky.client_id,
            client_secret=config.opensky.client_secret,
            username=config.opensky.username,
            password=config.opensky.password,
        )
        self._enricher = None  # Set up in _init_enrichment
        self._display = self._build_display(config)
        self._running = False

    def run(self):
        """Main loop: fetch, enrich, format, display. Repeat."""
        self._init_enrichment()
        self._display.start()
        self._running = True

        signal.signal(signal.SIGINT, lambda *_: self._shutdown())
        signal.signal(signal.SIGTERM, lambda *_: self._shutdown())

        lat = self._config.location.latitude
        lon = self._config.location.longitude
        logger.info(
            "Flight Tracker started. Watching skies at (%.4f, %.4f) "
            "with %.1f mile radius",
            lat, lon, self._config.location.radius_miles,
        )

        while self._running:
            try:
                raw_states = self._fetcher.fetch()

                # Filter: airborne, above min altitude, below max
                filtered = self._filter_states(raw_states)

                # Enrich each flight
                flights = [self._enrich(s) for s in filtered]

                # Only show aircraft within the configured radius
                radius = self._config.location.radius_miles
                flights = [
                    f for f in flights
                    if f.distance_miles is not None
                    and f.distance_miles <= radius
                ]

                # Sort by distance (closest first)
                flights.sort(key=lambda f: f.distance_miles or float("inf"))

                # Format for display
                messages = [format_flight(f) for f in flights]

                self._display.update(messages)

                if flights:
                    logger.info("Tracking %d aircraft", len(flights))
                else:
                    logger.debug("No aircraft in range")

            except Exception:
                logger.exception("Error in main loop")

            time.sleep(self._config.polling.interval_seconds)

    def _filter_states(self, states: List[RawAircraftState]) -> List[RawAircraftState]:
        min_alt = self._config.polling.min_altitude_feet
        max_alt = self._config.polling.max_altitude_feet
        approach_only = self._config.polling.approach_only
        result = []
        for s in states:
            if s.on_ground:
                continue
            if s.baro_altitude is None:
                continue
            alt_feet = s.baro_altitude * 3.28084
            if alt_feet < min_alt or alt_feet > max_alt:
                continue

            # Approach-only mode: only show descending aircraft
            if approach_only:
                # vertical_rate is in m/s from OpenSky; negative = descending
                if s.vertical_rate is None or s.vertical_rate >= 0:
                    continue

            result.append(s)
        return result

    def _enrich(self, state: RawAircraftState) -> EnrichedFlight:
        """Enrich a raw state into a display-ready flight."""
        # If we have the full enrichment pipeline, use it
        if self._enricher:
            return self._enricher.enrich(state)

        # Basic enrichment (no external databases)
        alt_feet = int(state.baro_altitude * 3.28084) if state.baro_altitude else None
        speed_knots = int(state.velocity * 1.94384) if state.velocity else None

        distance = None
        if state.latitude and state.longitude:
            distance = haversine(
                self._config.location.latitude,
                self._config.location.longitude,
                state.latitude,
                state.longitude,
            )

        return EnrichedFlight(
            icao24=state.icao24,
            callsign=state.callsign,
            flight_number=state.callsign,
            altitude_feet=alt_feet,
            speed_knots=speed_knots,
            heading=state.true_track,
            vertical_rate_fpm=(
                int(state.vertical_rate * 196.85)
                if state.vertical_rate else None
            ),
            distance_miles=distance,
            on_ground=state.on_ground,
        )

    def _init_enrichment(self):
        """Try to initialize the full enrichment pipeline."""
        try:
            from .enrichment.enricher import FlightEnricher
            cache_dir = Path(self._config.enrichment.cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)

            self._enricher = FlightEnricher(
                cache_dir=cache_dir,
                observer_lat=self._config.location.latitude,
                observer_lon=self._config.location.longitude,
                fetcher=self._fetcher,
                local_airport=self._config.location.local_airport,
            )
            logger.info("Enrichment pipeline initialized")
        except Exception as e:
            logger.warning(
                "Enrichment unavailable, using basic mode: %s", e
            )
            self._enricher = None

    def _build_display(self, config: AppConfig) -> DisplayBackend:
        backend = config.display.backend

        if backend == "terminal":
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
            )
        else:
            raise ValueError(f"Unknown display backend: {backend}")

    def _shutdown(self):
        logger.info("Shutting down...")
        self._running = False
        self._display.stop()
        self._fetcher.close()

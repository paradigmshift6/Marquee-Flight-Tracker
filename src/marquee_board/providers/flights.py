"""Flight tracking provider — wraps existing OpenSky fetcher + enrichment pipeline."""
import logging
import time
from pathlib import Path
from typing import List, Optional

from .base import MarqueeMessage, MarqueeProvider, Priority
from ..config import AppConfig
from ..fetcher import OpenSkyFetcher
from ..formatter import format_flight
from ..geo import compute_bounding_box, haversine
from ..models import EnrichedFlight, RawAircraftState

logger = logging.getLogger(__name__)


class FlightProvider(MarqueeProvider):
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
        self._enricher = None
        self._last_fetch: float = 0.0
        self._cached_messages: List[MarqueeMessage] = []

    @property
    def name(self) -> str:
        return "flights"

    @property
    def display_name(self) -> str:
        return "Nearby Aircraft"

    def start(self) -> None:
        self._init_enrichment()
        lat = self._config.location.latitude
        lon = self._config.location.longitude
        logger.info(
            "Flight provider started. Watching skies at (%.4f, %.4f) "
            "with %.1f mile radius",
            lat, lon, self._config.location.radius_miles,
        )

    def fetch_messages(self) -> List[MarqueeMessage]:
        now = time.monotonic()
        interval = self._config.polling.interval_seconds
        if self._cached_messages and (now - self._last_fetch) < interval:
            return self._cached_messages

        try:
            raw_states = self._fetcher.fetch()
            filtered = self._filter_states(raw_states)
            flights = [self._enrich(s) for s in filtered]

            radius = self._config.location.radius_miles
            flights = [
                f for f in flights
                if f.distance_miles is not None and f.distance_miles <= radius
            ]
            flights.sort(key=lambda f: f.distance_miles or float("inf"))

            self._cached_messages = [
                MarqueeMessage(
                    text=format_flight(f),
                    category="flights",
                    priority=Priority.URGENT,
                    data={
                        "flight_number": f.flight_number or f.callsign or "???",
                        "route_dep": getattr(f, "origin_airport", None) or "",
                        "route_arr": getattr(f, "destination_airport", None) or "",
                        "altitude_feet": f.altitude_feet,
                        "distance_miles": f.distance_miles,
                        "aircraft_type": getattr(f, "aircraft_type", None) or "",
                    },
                )
                for f in flights
            ]
            self._last_fetch = now

            if flights:
                logger.info("Tracking %d aircraft", len(flights))
            else:
                logger.debug("No aircraft in range")

        except Exception:
            logger.exception("Error fetching flights")

        return self._cached_messages

    def stop(self) -> None:
        self._fetcher.close()

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
            if approach_only:
                if s.vertical_rate is None or s.vertical_rate >= 0:
                    continue
            result.append(s)
        return result

    def _enrich(self, state: RawAircraftState) -> EnrichedFlight:
        if self._enricher:
            return self._enricher.enrich(state)

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
                int(state.vertical_rate * 196.85) if state.vertical_rate else None
            ),
            distance_miles=distance,
            on_ground=state.on_ground,
        )

    def _init_enrichment(self):
        try:
            from ..enrichment.enricher import FlightEnricher
            cache_dir = Path(self._config.enrichment.cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._enricher = FlightEnricher(
                cache_dir=cache_dir,
                observer_lat=self._config.location.latitude,
                observer_lon=self._config.location.longitude,
                fetcher=self._fetcher,
                local_airport=self._config.location.local_airport,
            )
            logger.info("Flight enrichment pipeline initialized")
        except Exception as e:
            logger.warning("Flight enrichment unavailable, using basic mode: %s", e)
            self._enricher = None

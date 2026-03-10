"""Orchestrates all enrichment sources to produce EnrichedFlight objects."""
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..geo import haversine
from ..models import EnrichedFlight, RawAircraftState
from .aircraft_db import AircraftDB
from .airline_db import AirlineDB
from .airport_db import AirportDB
from .route_resolver import RouteResolver

if TYPE_CHECKING:
    from ..fetcher import OpenSkyFetcher

logger = logging.getLogger(__name__)


class FlightEnricher:
    def __init__(
        self,
        cache_dir: Path,
        observer_lat: float,
        observer_lon: float,
        fetcher: Optional["OpenSkyFetcher"] = None,
        local_airport: Optional[str] = None,
    ):
        self._observer_lat = observer_lat
        self._observer_lon = observer_lon
        self._local_airport = local_airport  # ICAO code e.g. "KSLC"

        self._aircraft_db = AircraftDB(cache_dir)
        self._airline_db = AirlineDB(cache_dir)
        self._airport_db = AirportDB(cache_dir)
        self._route_resolver = RouteResolver(
            cache_dir=cache_dir,
            airport_db=self._airport_db,
            fetcher=fetcher,
        )

    def enrich(self, state: RawAircraftState) -> EnrichedFlight:
        # 1. Aircraft type
        aircraft_info = self._aircraft_db.lookup(state.icao24)

        # 2. Airline from callsign
        airline = None
        flight_number = state.callsign
        if state.callsign:
            icao_code, flight_num = self._airline_db.parse_callsign(state.callsign)
            if icao_code:
                airline = self._airline_db.lookup_icao(icao_code)
                # Build IATA-style flight number (e.g., "UA1234")
                if airline and airline.iata_code:
                    flight_number = f"{airline.iata_code}{flight_num}"
                else:
                    flight_number = f"{icao_code}{flight_num}"

        # 3. Route
        route = None
        if state.callsign:
            route = self._route_resolver.resolve(state.callsign, state.icao24)

        # 3b. Infer arrival/departure using local airport proximity
        if route and self._local_airport:
            local = self._local_airport
            local_info = self._airport_db.lookup(local)
            local_iata = local_info.iata if local_info else None

            dep_icao = route.departure_icao
            arr_icao = route.arrival_icao

            if dep_icao and not arr_icao and dep_icao != local:
                # Departure is NOT local airport, aircraft is near us → arriving here
                route.arrival_icao = local
                route.arrival_iata = local_iata
                route.arrival_city = local_info.city if local_info else None
            elif dep_icao and not arr_icao and dep_icao == local:
                # Departing from local airport, destination unknown — leave as-is
                pass
            elif not dep_icao and arr_icao and arr_icao != local:
                # Arrival is NOT local airport but aircraft is near us → departing from here
                route.departure_icao = local
                route.departure_iata = local_iata
                route.departure_city = local_info.city if local_info else None

        # 4. Unit conversions
        alt_feet = int(state.baro_altitude * 3.28084) if state.baro_altitude else None
        speed_knots = int(state.velocity * 1.94384) if state.velocity else None
        vrate_fpm = (
            int(state.vertical_rate * 196.85)
            if state.vertical_rate else None
        )

        # 5. Distance from observer
        distance = None
        if state.latitude is not None and state.longitude is not None:
            distance = haversine(
                self._observer_lat, self._observer_lon,
                state.latitude, state.longitude,
            )

        return EnrichedFlight(
            icao24=state.icao24,
            callsign=state.callsign,
            airline_name=airline.name if airline else None,
            flight_number=flight_number,
            aircraft_info=aircraft_info,
            route=route,
            altitude_feet=alt_feet,
            speed_knots=speed_knots,
            heading=state.true_track,
            vertical_rate_fpm=vrate_fpm,
            distance_miles=distance,
            on_ground=state.on_ground,
        )

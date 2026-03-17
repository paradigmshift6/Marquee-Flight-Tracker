"""Resolve flight routes (origin/destination) from callsigns.

Uses a tiered approach:
1. Memory cache (instant)
2. Disk cache from previous resolutions
3. OpenSky /flights/aircraft endpoint (most reliable, needs auth)
4. OpenSky /routes endpoint (needs auth, spotty coverage)
5. Historical departures from local airport (same callsign = same route daily)
6. Graceful degradation (no route)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..models import RouteInfo

if TYPE_CHECKING:
    from ..fetcher import OpenSkyFetcher
    from .airport_db import AirportDB

logger = logging.getLogger(__name__)


class RouteResolver:
    def __init__(
        self,
        cache_dir: Path,
        airport_db: "AirportDB",
        fetcher: Optional["OpenSkyFetcher"] = None,
        cache_ttl_hours: int = 24,
        local_airport: Optional[str] = None,
    ):
        self._cache_dir = cache_dir
        self._airport_db = airport_db
        self._fetcher = fetcher
        self._cache_ttl = cache_ttl_hours * 3600
        self._local_airport = local_airport
        self._memory_cache: dict[str, RouteInfo] = {}
        self._disk_cache = self._load_disk_cache()
        self._failed_lookups: dict[str, float] = {}  # callsign -> timestamp
        self._fail_cooldown = 600  # Don't retry failed lookups for 10 min
        # Historical callsign→arrival mapping from local airport departures
        self._historical_routes: dict[str, str] = {}  # callsign -> arrival ICAO
        self._historical_loaded: float = 0.0

    def resolve(self, callsign: str, icao24: str) -> Optional[RouteInfo]:
        # Memory cache (instant)
        if callsign in self._memory_cache:
            return self._memory_cache[callsign]

        # Disk cache
        if callsign in self._disk_cache:
            entry = self._disk_cache[callsign]
            age = time.time() - entry.get("_cached_at", 0)
            if age < self._cache_ttl:
                route = self._entry_to_route(entry)
                self._memory_cache[callsign] = route
                return route

        # Don't retry recently failed lookups
        if callsign in self._failed_lookups:
            if time.time() - self._failed_lookups[callsign] < self._fail_cooldown:
                return None

        route = None  # partial result from tier 1

        if self._fetcher and self._fetcher.authenticated:
            # Tier 1: OpenSky /flights/aircraft (most reliable)
            route = self._try_opensky_flights(callsign, icao24)

            # Complete route — cache and return immediately
            if route and route.departure_icao and route.arrival_icao:
                self._cache_route(callsign, route)
                return route

            # Tier 2: OpenSky /routes endpoint (spotty coverage)
            routes_route = self._try_opensky_routes(callsign)
            if routes_route:
                # Merge: prefer /routes for a complete picture, but keep
                # any data from /flights/aircraft that /routes missed.
                if route:
                    if not routes_route.departure_icao:
                        routes_route.departure_icao = route.departure_icao
                        routes_route.departure_iata = route.departure_iata
                        routes_route.departure_city = route.departure_city
                    if not routes_route.arrival_icao:
                        routes_route.arrival_icao = route.arrival_icao
                        routes_route.arrival_iata = route.arrival_iata
                        routes_route.arrival_city = route.arrival_city
                self._cache_route(callsign, routes_route)
                return routes_route

            # Tier 3: Historical departures from local airport.
            # Completed flights from previous days have arrival data,
            # and most commercial flights fly the same route daily.
            if self._local_airport:
                hist_route = self._try_historical_departures(callsign)
                if hist_route:
                    # Merge with any partial tier-1 data
                    if route and not hist_route.departure_icao:
                        hist_route.departure_icao = route.departure_icao
                        hist_route.departure_iata = route.departure_iata
                        hist_route.departure_city = route.departure_city
                    self._cache_route(callsign, hist_route)
                    return hist_route

        # Accept partial route if nothing else worked
        if route:
            self._cache_route(callsign, route)
            return route

        # Mark as failed; prune expired entries to prevent unbounded growth
        self._failed_lookups[callsign] = time.time()
        self._prune_failed_lookups()
        return None

    def _prune_failed_lookups(self) -> None:
        """Remove cooldown entries that have already expired."""
        cutoff = time.time() - self._fail_cooldown
        expired = [k for k, v in self._failed_lookups.items() if v < cutoff]
        for k in expired:
            del self._failed_lookups[k]

    def _try_opensky_flights(self, callsign: str, icao24: str) -> Optional[RouteInfo]:
        """Try the /flights/aircraft endpoint — returns departure/arrival airports."""
        flights = self._fetcher.fetch_flights_by_aircraft(icao24)
        if not flights:
            return None

        # Find the most recent flight matching this callsign
        best = None
        for f in flights:
            fc = (f.get("callsign") or "").strip()
            if fc == callsign:
                if best is None or f.get("lastSeen", 0) > best.get("lastSeen", 0):
                    best = f

        # If no exact callsign match, use the most recent flight for this aircraft
        if best is None and flights:
            flights_sorted = sorted(flights, key=lambda x: x.get("lastSeen", 0), reverse=True)
            best = flights_sorted[0]

        if best is None:
            return None

        dep_icao = best.get("estDepartureAirport")
        arr_icao = best.get("estArrivalAirport")

        if not dep_icao and not arr_icao:
            return None

        dep_airport = self._airport_db.lookup(dep_icao) if dep_icao else None
        arr_airport = self._airport_db.lookup(arr_icao) if arr_icao else None

        logger.info(
            "Resolved route via /flights/aircraft: %s → %s (%s)",
            dep_icao or "???",
            arr_icao or "???",
            callsign,
        )

        return RouteInfo(
            departure_icao=dep_icao,
            departure_iata=dep_airport.iata if dep_airport else None,
            departure_city=dep_airport.city if dep_airport else None,
            arrival_icao=arr_icao,
            arrival_iata=arr_airport.iata if arr_airport else None,
            arrival_city=arr_airport.city if arr_airport else None,
        )

    def _try_opensky_routes(self, callsign: str) -> Optional[RouteInfo]:
        data = self._fetcher.fetch_routes(callsign)
        if not data:
            return None

        route_list = data.get("route", [])
        if len(route_list) < 2:
            return None

        dep_icao = route_list[0]
        arr_icao = route_list[-1]

        dep_airport = self._airport_db.lookup(dep_icao)
        arr_airport = self._airport_db.lookup(arr_icao)

        return RouteInfo(
            departure_icao=dep_icao,
            departure_iata=dep_airport.iata if dep_airport else None,
            departure_city=dep_airport.city if dep_airport else None,
            arrival_icao=arr_icao,
            arrival_iata=arr_airport.iata if arr_airport else None,
            arrival_city=arr_airport.city if arr_airport else None,
        )

    # --- Tier 3: Historical departure lookup ---

    def _try_historical_departures(self, callsign: str) -> Optional[RouteInfo]:
        """Look up route from historical departure data.

        Most commercial flights fly the same route daily.  By checking
        completed flights from the local airport in the previous 1-2 days,
        we can find the likely arrival airport for callsigns currently in
        the air.
        """
        # Refresh historical data every 6 hours
        if time.time() - self._historical_loaded > 6 * 3600:
            self._load_historical_departures()

        arr_icao = self._historical_routes.get(callsign)
        if not arr_icao:
            return None

        dep_icao = self._local_airport
        dep_airport = self._airport_db.lookup(dep_icao) if dep_icao else None
        arr_airport = self._airport_db.lookup(arr_icao)

        logger.info(
            "Resolved route via historical departures: %s → %s (%s)",
            dep_icao or "???",
            arr_icao,
            callsign,
        )

        return RouteInfo(
            departure_icao=dep_icao,
            departure_iata=dep_airport.iata if dep_airport else None,
            departure_city=dep_airport.city if dep_airport else None,
            arrival_icao=arr_icao,
            arrival_iata=arr_airport.iata if arr_airport else None,
            arrival_city=arr_airport.city if arr_airport else None,
        )

    def _load_historical_departures(self):
        """Fetch recent departures from local airport, build callsign→arrival map."""
        if not self._fetcher or not self._local_airport:
            return

        now = int(time.time())
        # OpenSky allows querying across at most 2 calendar-day partitions.
        # Query previous ~24h to stay within the 2-partition limit.
        begin = now - 86400
        end = now

        logger.info(
            "Loading historical departures from %s ...", self._local_airport
        )
        flights = self._fetcher.fetch_departures(
            self._local_airport, begin, end
        )

        if not flights:
            logger.info("No historical departures returned (may retry)")
            # Use a short backoff (5 min) so we retry soon if rate-limited,
            # instead of waiting the full 6 hours.
            self._historical_loaded = time.time() - 6 * 3600 + 300
            return

        mapping: dict[str, str] = {}
        for f in flights:
            cs = (f.get("callsign") or "").strip()
            arr = f.get("estArrivalAirport")
            if cs and arr:
                # Keep the most recent entry per callsign
                mapping[cs] = arr

        self._historical_routes = mapping
        self._historical_loaded = time.time()
        logger.info(
            "Loaded %d historical routes from %s (%d departures total)",
            len(mapping),
            self._local_airport,
            len(flights),
        )

    def _cache_route(self, callsign: str, route: RouteInfo):
        self._memory_cache[callsign] = route
        self._disk_cache[callsign] = {
            "dep_icao": route.departure_icao,
            "dep_iata": route.departure_iata,
            "dep_city": route.departure_city,
            "arr_icao": route.arrival_icao,
            "arr_iata": route.arrival_iata,
            "arr_city": route.arrival_city,
            "_cached_at": time.time(),
        }
        self._save_disk_cache()

    def _entry_to_route(self, entry: dict) -> RouteInfo:
        return RouteInfo(
            departure_icao=entry.get("dep_icao"),
            departure_iata=entry.get("dep_iata"),
            departure_city=entry.get("dep_city"),
            arrival_icao=entry.get("arr_icao"),
            arrival_iata=entry.get("arr_iata"),
            arrival_city=entry.get("arr_city"),
        )

    def _load_disk_cache(self) -> dict:
        cache_file = self._cache_dir / "route_cache.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_disk_cache(self):
        cache_file = self._cache_dir / "route_cache.json"
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(self._disk_cache, indent=2))
        except OSError as e:
            logger.warning("Failed to save route cache: %s", e)

import logging
import time
from typing import List, Optional

import httpx

from .models import BoundingBox, RawAircraftState

logger = logging.getLogger(__name__)

OPENSKY_BASE = "https://opensky-network.org/api"
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)

# Refresh token 5 minutes before expiry
TOKEN_REFRESH_MARGIN = 300


class OpenSkyFetcher:
    def __init__(
        self,
        bbox: BoundingBox,
        min_interval: float = 10.0,
        timeout: float = 15.0,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._bbox = bbox
        self._min_interval = min_interval
        self._timeout = timeout
        self._last_request_time: float = 0.0
        self._backoff: float = 0.0

        # OAuth2 credentials
        self._client_id = client_id
        self._client_secret = client_secret
        self._use_oauth2 = bool(client_id and client_secret)

        # Legacy basic auth
        self._use_basic = bool(username and password) and not self._use_oauth2
        basic_auth = (username, password) if self._use_basic else None

        self._client = httpx.Client(timeout=timeout, auth=basic_auth)

        # OAuth2 token state
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def authenticated(self) -> bool:
        return self._use_oauth2 or self._use_basic

    def fetch(self) -> List[RawAircraftState]:
        """Fetch current aircraft states within the bounding box."""
        self._enforce_rate_limit()

        params = {
            "lamin": self._bbox.lat_min,
            "lomin": self._bbox.lon_min,
            "lamax": self._bbox.lat_max,
            "lomax": self._bbox.lon_max,
        }

        try:
            headers = self._auth_headers()
            resp = self._client.get(
                f"{OPENSKY_BASE}/states/all",
                params=params,
                headers=headers,
            )
            self._last_request_time = time.monotonic()

            if resp.status_code == 401 and self._use_oauth2:
                # Token may have expired, force refresh and retry
                logger.debug("Got 401, refreshing OAuth2 token and retrying")
                self._access_token = None
                headers = self._auth_headers()
                resp = self._client.get(
                    f"{OPENSKY_BASE}/states/all",
                    params=params,
                    headers=headers,
                )

            if resp.status_code == 429:
                self._backoff = min(max(self._backoff * 2, 30), 300)
                logger.warning("Rate limited. Backing off %.0fs", self._backoff)
                return []

            resp.raise_for_status()
            self._backoff = 0.0
            data = resp.json()

        except httpx.TimeoutException:
            logger.warning("OpenSky request timed out")
            return []
        except httpx.HTTPStatusError as e:
            logger.warning("OpenSky HTTP error: %s", e)
            return []
        except httpx.RequestError as e:
            logger.warning("OpenSky request failed: %s", e)
            return []

        states = data.get("states") or []
        results = []
        for s in states:
            if len(s) < 14:
                logger.debug("Skipping short state vector (%d elements)", len(s))
                continue
            callsign = s[1].strip() if s[1] else None
            if not callsign:
                continue
            results.append(self._parse_state(s, callsign))

        return results

    def fetch_routes(self, callsign: str) -> Optional[dict]:
        """Fetch route info for a callsign (requires authentication)."""
        if not self.authenticated:
            return None

        try:
            headers = self._auth_headers()
            resp = self._client.get(
                f"{OPENSKY_BASE}/routes",
                params={"callsign": callsign},
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.debug("Route lookup failed for %s: %s", callsign, e)

        return None

    def fetch_flights_by_aircraft(self, icao24: str) -> Optional[list]:
        """Fetch recent flights for an aircraft by ICAO24 hex address.

        Uses /flights/aircraft endpoint which returns estDepartureAirport
        and estArrivalAirport — more reliable than /routes.
        """
        if not self.authenticated:
            return None

        now = int(time.time())
        begin = now - 86400  # Last 24 hours

        try:
            headers = self._auth_headers()
            resp = self._client.get(
                f"{OPENSKY_BASE}/flights/aircraft",
                params={
                    "icao24": icao24.lower(),
                    "begin": begin,
                    "end": now,
                },
                headers=headers,
            )
            if resp.status_code == 200:
                flights = resp.json()
                if flights:
                    return flights
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.debug("Flight lookup failed for %s: %s", icao24, e)

        return None

    def fetch_departures(self, airport: str, begin: int, end: int) -> Optional[list]:
        """Fetch departures from an airport in a time window.

        Returns a list of flight dicts with estDepartureAirport and
        estArrivalAirport.  Completed flights usually have both.
        """
        if not self.authenticated:
            return None

        try:
            headers = self._auth_headers()
            resp = self._client.get(
                f"{OPENSKY_BASE}/flights/departure",
                params={
                    "airport": airport,
                    "begin": begin,
                    "end": end,
                },
                headers=headers,
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                logger.warning("Rate limited on departure lookup for %s", airport)
            else:
                logger.debug(
                    "Departure lookup %s returned %d: %s",
                    airport, resp.status_code, resp.text[:200],
                )
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.debug("Departure lookup failed for %s: %s", airport, e)

        return None

    # --- OAuth2 token management ---

    def _auth_headers(self) -> dict:
        """Return Authorization header if authenticated."""
        if self._use_oauth2:
            token = self._get_token()
            if token:
                return {"Authorization": f"Bearer {token}"}
        # Basic auth is handled by httpx's auth= parameter
        return {}

    def _get_token(self) -> Optional[str]:
        """Get a valid OAuth2 access token, refreshing if needed."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        logger.info("Requesting new OAuth2 token from OpenSky...")
        try:
            resp = self._client.post(
                OPENSKY_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            token_data = resp.json()

            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 1800)  # default 30 min
            self._token_expires_at = time.time() + expires_in - TOKEN_REFRESH_MARGIN

            logger.info(
                "OAuth2 token acquired (expires in %d min)",
                expires_in // 60,
            )
            return self._access_token

        except httpx.HTTPStatusError as e:
            logger.error("OAuth2 token request failed: %s", e)
            logger.error("Response: %s", e.response.text)
            return None
        except Exception as e:
            logger.error("OAuth2 token request error: %s", e)
            return None

    def ready_to_fetch(self) -> bool:
        """True if enough time has passed since the last request (incl. backoff).

        Callers should check this before calling fetch() and return cached data
        immediately when False, avoiding any sleep in the main loop.
        """
        wait = self._min_interval + self._backoff
        return (time.monotonic() - self._last_request_time) >= wait

    def _enforce_rate_limit(self):
        wait = self._min_interval + self._backoff
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < wait:
            time.sleep(wait - elapsed)

    @staticmethod
    def _parse_state(s: list, callsign: str) -> RawAircraftState:
        return RawAircraftState(
            icao24=s[0],
            callsign=callsign,
            origin_country=s[2],
            longitude=s[5],
            latitude=s[6],
            baro_altitude=s[7],
            on_ground=s[8],
            velocity=s[9],
            true_track=s[10],
            vertical_rate=s[11],
            geo_altitude=s[13],
            squawk=s[14] if len(s) > 14 else None,
            category=s[17] if len(s) > 17 else None,
        )

    def close(self):
        self._client.close()

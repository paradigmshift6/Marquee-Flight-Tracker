from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class LocationConfig:
    latitude: float = 0.0
    longitude: float = 0.0
    radius_miles: float = 5.0
    local_airport: Optional[str] = None  # ICAO code e.g. "KSLC" — used to infer arrivals


@dataclass
class PollingConfig:
    interval_seconds: float = 12.0
    min_altitude_feet: float = 500.0
    max_altitude_feet: float = 45000.0
    approach_only: bool = False  # Only show descending aircraft (on approach)


@dataclass
class DisplayConfig:
    backend: str = "terminal"
    scroll_speed: float = 0.08
    cycle_interval: float = 8.0
    idle_message: str = "Scanning the skies..."


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 5000


@dataclass
class OpenSkyConfig:
    # OAuth2 client credentials (new method)
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    # Legacy basic auth (deprecated March 2026)
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class EnrichmentConfig:
    cache_dir: str = "data"
    cache_ttl_hours: int = 168  # 1 week


@dataclass
class AppConfig:
    location: LocationConfig = field(default_factory=LocationConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    web: WebConfig = field(default_factory=WebConfig)
    opensky: OpenSkyConfig = field(default_factory=OpenSkyConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)


def load_config(path: str) -> AppConfig:
    """Load config from a YAML file, falling back to defaults."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    config = AppConfig()

    if loc := raw.get("location"):
        config.location = LocationConfig(
            latitude=loc.get("latitude", 0.0),
            longitude=loc.get("longitude", 0.0),
            radius_miles=loc.get("radius_miles", 5.0),
            local_airport=loc.get("local_airport"),
        )

    if poll := raw.get("polling"):
        config.polling = PollingConfig(
            interval_seconds=max(poll.get("interval_seconds", 12.0), 10.0),
            min_altitude_feet=poll.get("min_altitude_feet", 500.0),
            max_altitude_feet=poll.get("max_altitude_feet", 45000.0),
            approach_only=poll.get("approach_only", False),
        )

    if disp := raw.get("display"):
        config.display = DisplayConfig(
            backend=disp.get("backend", "terminal"),
            scroll_speed=disp.get("scroll_speed", 0.08),
            cycle_interval=disp.get("cycle_interval", 8.0),
            idle_message=disp.get("idle_message", "Scanning the skies..."),
        )

    if web := raw.get("web"):
        config.web = WebConfig(
            host=web.get("host", "0.0.0.0"),
            port=web.get("port", 5000),
        )

    if osky := raw.get("opensky"):
        config.opensky = OpenSkyConfig(
            client_id=osky.get("client_id"),
            client_secret=osky.get("client_secret"),
            username=osky.get("username"),
            password=osky.get("password"),
        )

    if enr := raw.get("enrichment"):
        config.enrichment = EnrichmentConfig(
            cache_dir=enr.get("cache_dir", "data"),
            cache_ttl_hours=enr.get("cache_ttl_hours", 168),
        )

    if config.location.latitude == 0.0 and config.location.longitude == 0.0:
        raise ValueError("You must set your latitude and longitude in the config file.")

    return config

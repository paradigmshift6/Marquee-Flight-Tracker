import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import re

import yaml


def _parse_yaml_time(value, default: str = "06:30") -> str:
    """Safely convert a YAML time value to 'HH:MM' string.

    PyYAML interprets unquoted ``06:30`` as the integer 390 (sexagesimal).
    This helper normalises ints, floats and strings back to ``HH:MM``.
    """
    if isinstance(value, int):
        # YAML sexagesimal: 06:30 → 390 (6*60+30)
        hours, minutes = divmod(value, 60)
        return f"{hours:02d}:{minutes:02d}"
    s = str(value).strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", s):
        return s
    return default


@dataclass
class LocationConfig:
    latitude: float = 0.0
    longitude: float = 0.0
    radius_miles: float = 5.0
    local_airport: Optional[str] = None


@dataclass
class PollingConfig:
    interval_seconds: float = 12.0
    min_altitude_feet: float = 500.0
    max_altitude_feet: float = 45000.0
    approach_only: bool = False


@dataclass
class DisplayConfig:
    backend: str = "terminal"
    scroll_speed: float = 0.08
    cycle_interval: float = 8.0
    idle_message: str = "No data yet..."


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 5000


@dataclass
class OpenSkyConfig:
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class EnrichmentConfig:
    cache_dir: str = "data"
    cache_ttl_hours: int = 168


@dataclass
class FlightsConfig:
    enabled: bool = True


@dataclass
class WeatherConfig:
    enabled: bool = False
    api_key: Optional[str] = None
    poll_interval: float = 300.0
    units: str = "imperial"  # "imperial" or "metric"


@dataclass
class CalendarConfig:
    enabled: bool = False
    credentials_file: str = "credentials.json"
    token_file: str = "data/calendar_token.json"
    calendar_id: str = "primary"
    lookahead_hours: int = 24
    poll_interval: float = 60.0


@dataclass
class ScheduleConfig:
    enabled: bool = False
    active_start: str = "06:30"   # HH:MM local time
    active_end: str = "18:00"


@dataclass
class RendererConfig:
    width: int = 64
    height: int = 64
    brightness: int = 80
    gpio_slowdown: int = 4
    hardware_mapping: str = "adafruit-hat"  # "regular" | "adafruit-hat" | "adafruit-hat-pwm"


@dataclass
class AppConfig:
    location: LocationConfig = field(default_factory=LocationConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    web: WebConfig = field(default_factory=WebConfig)
    opensky: OpenSkyConfig = field(default_factory=OpenSkyConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    flights: FlightsConfig = field(default_factory=FlightsConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    renderer: RendererConfig = field(default_factory=RendererConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)


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
            idle_message=disp.get("idle_message", "No data yet..."),
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

    if fl := raw.get("flights"):
        config.flights = FlightsConfig(
            enabled=fl.get("enabled", True),
        )

    if wx := raw.get("weather"):
        config.weather = WeatherConfig(
            enabled=wx.get("enabled", False),
            api_key=wx.get("api_key"),
            poll_interval=wx.get("poll_interval", 300.0),
            units=wx.get("units", "imperial"),
        )

    if cal := raw.get("calendar"):
        config.calendar = CalendarConfig(
            enabled=cal.get("enabled", False),
            credentials_file=cal.get("credentials_file", "credentials.json"),
            token_file=cal.get("token_file", "data/calendar_token.json"),
            calendar_id=cal.get("calendar_id", "primary"),
            lookahead_hours=cal.get("lookahead_hours", 24),
            poll_interval=cal.get("poll_interval", 60.0),
        )

    if rend := raw.get("renderer"):
        config.renderer = RendererConfig(
            width=rend.get("width", 64),
            height=rend.get("height", 64),
            brightness=rend.get("brightness", 80),
            gpio_slowdown=rend.get("gpio_slowdown", 4),
            hardware_mapping=rend.get("hardware_mapping", "adafruit-hat"),
        )

    if sched := raw.get("schedule"):
        config.schedule = ScheduleConfig(
            enabled=sched.get("enabled", False),
            active_start=_parse_yaml_time(sched.get("active_start", "06:30"), "06:30"),
            active_end=_parse_yaml_time(sched.get("active_end", "18:00"), "18:00"),
        )

    return config


def config_to_dict(config: AppConfig) -> dict:
    """Convert an AppConfig to a plain dict suitable for JSON/YAML."""
    return dataclasses.asdict(config)


def save_config(path: str, config: Union[AppConfig, dict]) -> None:
    """Write config to a YAML file.  Accepts AppConfig or a plain dict."""
    if isinstance(config, AppConfig):
        data = config_to_dict(config)
    else:
        data = config

    # Ensure schedule times survive a YAML round-trip as quoted strings.
    # PyYAML interprets unquoted "06:30" as the integer 390 (sexagesimal),
    # so we normalise to HH:MM first, then wrap in a YAML literal string.
    if "schedule" in data:
        for key in ("active_start", "active_end"):
            if key in data["schedule"] and data["schedule"][key] is not None:
                time_str = _parse_yaml_time(data["schedule"][key])
                # yaml.scalarstring is only in ruamel; use a representer instead
                data["schedule"][key] = time_str

    # Custom representer to force-quote strings that look like sexagesimal
    class _QuotedDumper(yaml.SafeDumper):
        pass

    def _str_representer(dumper, value):
        if re.fullmatch(r"\d{1,2}:\d{2}", value):
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="'")
        return dumper.represent_scalar("tag:yaml.org,2002:str", value)

    _QuotedDumper.add_representer(str, _str_representer)

    with open(path, "w") as f:
        yaml.dump(data, f, Dumper=_QuotedDumper, default_flow_style=False, sort_keys=False)

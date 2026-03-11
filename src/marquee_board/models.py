from dataclasses import dataclass
from typing import Optional


@dataclass
class BoundingBox:
    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float


@dataclass
class RawAircraftState:
    """Direct mapping of one OpenSky state vector."""
    icao24: str
    callsign: Optional[str]
    origin_country: str
    longitude: Optional[float]
    latitude: Optional[float]
    baro_altitude: Optional[float]  # meters
    on_ground: bool
    velocity: Optional[float]  # m/s
    true_track: Optional[float]
    vertical_rate: Optional[float]
    geo_altitude: Optional[float]  # meters
    squawk: Optional[str]
    category: Optional[int]


@dataclass
class AircraftInfo:
    """Enrichment data from the aircraft database."""
    icao24: str
    registration: Optional[str] = None
    typecode: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    operator: Optional[str] = None
    operator_icao: Optional[str] = None
    operator_iata: Optional[str] = None


@dataclass
class AirlineInfo:
    """Airline lookup result."""
    name: str
    icao_code: str
    iata_code: Optional[str] = None
    callsign_name: Optional[str] = None  # radio callsign e.g. "SPEEDBIRD"


@dataclass
class AirportInfo:
    """Airport lookup result."""
    icao: str
    iata: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None


@dataclass
class RouteInfo:
    """Origin and destination for a flight."""
    departure_icao: Optional[str] = None
    departure_iata: Optional[str] = None
    departure_city: Optional[str] = None
    arrival_icao: Optional[str] = None
    arrival_iata: Optional[str] = None
    arrival_city: Optional[str] = None


@dataclass
class EnrichedFlight:
    """A fully enriched flight ready for display."""
    icao24: str
    callsign: Optional[str]
    airline_name: Optional[str] = None
    flight_number: Optional[str] = None
    aircraft_info: Optional[AircraftInfo] = None
    route: Optional[RouteInfo] = None
    altitude_feet: Optional[int] = None
    speed_knots: Optional[int] = None
    heading: Optional[float] = None
    vertical_rate_fpm: Optional[int] = None
    distance_miles: Optional[float] = None
    on_ground: bool = False

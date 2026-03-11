import math

from .models import BoundingBox


def compute_bounding_box(lat: float, lon: float, radius_miles: float) -> BoundingBox:
    """Compute a bounding box around a center point.

    Uses the approximation that 1 degree latitude ~ 69 miles,
    and adjusts longitude for the cosine of the latitude.
    """
    lat_delta = radius_miles / 69.0
    lon_delta = radius_miles / (69.0 * math.cos(math.radians(lat)))
    return BoundingBox(
        lat_min=lat - lat_delta,
        lon_min=lon - lon_delta,
        lat_max=lat + lat_delta,
        lon_max=lon + lon_delta,
    )


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

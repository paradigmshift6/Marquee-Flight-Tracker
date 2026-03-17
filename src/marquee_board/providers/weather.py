"""Weather provider using OpenWeatherMap API."""
import logging
import time
from typing import List, Optional

import httpx

from .base import MarqueeMessage, MarqueeProvider, Priority
from ..config import AppConfig

logger = logging.getLogger(__name__)

OPENWEATHERMAP_BASE = "https://api.openweathermap.org/data/2.5"

# Compass directions for wind bearing
COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _wind_direction(degrees: float) -> str:
    idx = round(degrees / 22.5) % 16
    return COMPASS[idx]


class WeatherProvider(MarqueeProvider):
    def __init__(self, config: AppConfig):
        self._api_key = config.weather.api_key
        if not self._api_key:
            raise ValueError("Weather provider requires an api_key in config")

        self._lat = config.location.latitude
        self._lon = config.location.longitude
        self._units = config.weather.units
        self._poll_interval = config.weather.poll_interval
        self._client = httpx.Client(timeout=15.0)
        self._last_fetch: float = 0.0
        self._cached_messages: List[MarqueeMessage] = []

    @property
    def name(self) -> str:
        return "weather"

    @property
    def display_name(self) -> str:
        return "Weather"

    def start(self) -> None:
        logger.info("Weather provider started (OpenWeatherMap, %s)", self._units)

    def fetch_messages(self) -> List[MarqueeMessage]:
        now = time.monotonic()
        if self._cached_messages and (now - self._last_fetch) < self._poll_interval:
            return self._cached_messages

        try:
            messages = []

            # Current weather
            current_text, current_data = self._fetch_current()
            if current_text:
                messages.append(MarqueeMessage(
                    text=current_text,
                    category="weather",
                    priority=Priority.MEDIUM,
                    data=current_data,
                ))

            # Forecast summary
            forecast_text, forecast_data = self._fetch_forecast()
            if forecast_text:
                messages.append(MarqueeMessage(
                    text=forecast_text,
                    category="weather",
                    priority=Priority.MEDIUM,
                    data=forecast_data,
                ))

            self._cached_messages = messages
            self._last_fetch = now

        except Exception:
            logger.exception("Error fetching weather")

        return self._cached_messages

    def stop(self) -> None:
        self._client.close()

    def _fetch_current(self):
        try:
            resp = self._client.get(
                f"{OPENWEATHERMAP_BASE}/weather",
                params={
                    "lat": self._lat,
                    "lon": self._lon,
                    "appid": self._api_key,
                    "units": self._units,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning("Current weather fetch failed: %s", e)
            return None, {}

        try:
            temp = round(data["main"]["temp"])
            desc = data["weather"][0]["description"].title()
            wind_speed = round(data["wind"]["speed"])
            wind_deg = data["wind"].get("deg", 0)
            wind_dir = _wind_direction(wind_deg)
            humidity = data["main"]["humidity"]
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("Unexpected current weather response structure: %s", e)
            return None, {}

        temp_unit = "\u00b0F" if self._units == "imperial" else "\u00b0C"
        speed_unit = "mph" if self._units == "imperial" else "m/s"

        text = (
            f"{temp}{temp_unit}  {desc}  "
            f"Wind: {wind_speed}{speed_unit} {wind_dir}  "
            f"Humidity: {humidity}%"
        )

        structured = {
            "temp": temp,
            "temp_unit": temp_unit,
            "condition": desc,
            "wind_speed": f"{wind_speed}{speed_unit}",
            "wind_dir": wind_dir,
            "humidity": humidity,
        }

        return text, structured

    def _fetch_forecast(self):
        try:
            resp = self._client.get(
                f"{OPENWEATHERMAP_BASE}/forecast",
                params={
                    "lat": self._lat,
                    "lon": self._lon,
                    "appid": self._api_key,
                    "units": self._units,
                    "cnt": 8,  # next 24 hours (3-hour intervals)
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning("Forecast fetch failed: %s", e)
            return None, {}

        items = data.get("list", [])
        if not items:
            return None, {}

        temp_unit = "\u00b0F" if self._units == "imperial" else "\u00b0C"

        try:
            # Find high/low and dominant condition over the forecast window
            temps = [item["main"]["temp"] for item in items]
            hi = round(max(temps))
            lo = round(min(temps))

            # Most common weather condition
            conditions = [item["weather"][0]["description"] for item in items]
            dominant = max(set(conditions), key=conditions.count).title()
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning("Unexpected forecast response structure: %s", e)
            return None, {}

        text = f"Next 24h: {lo}{temp_unit} - {hi}{temp_unit}  {dominant}"

        structured = {
            "hi": f"{hi}{temp_unit}",
            "lo": f"{lo}{temp_unit}",
            "condition": dominant,
        }

        return text, structured

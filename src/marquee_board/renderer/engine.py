"""Adaptive layout engine for LED matrix display.

Takes structured MarqueeMessages and produces a FrameLayout — a list
of positioned elements (text, icons, rectangles) that the painter renders.
All coordinates reference self.width / self.height so layouts scale to
any matrix size (64x32, 64x64, 128x64, etc.).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..providers.base import MarqueeMessage, Priority
from . import colors

logger = logging.getLogger(__name__)


# ── Frame element types ─────────────────────────────────

@dataclass
class TextElement:
    x: int
    y: int
    text: str
    font_name: str = "small"
    color: Tuple[int, int, int] = colors.WHITE


@dataclass
class IconElement:
    x: int
    y: int
    icon_name: str
    size: int = 8  # 8 or 5


@dataclass
class RectElement:
    x: int
    y: int
    w: int
    h: int
    color: Tuple[int, int, int] = colors.SEPARATOR_COLOR


@dataclass
class FrameLayout:
    """Complete rendered frame description."""
    elements: List[Any] = field(default_factory=list)
    width: int = 64
    height: int = 64


class LayoutEngine:
    """Picks the best layout based on available content and priority."""

    def __init__(self, width: int = 64, height: int = 64):
        self.width = width
        self.height = height

    def layout(self, messages: List[MarqueeMessage]) -> FrameLayout:
        """Produce a FrameLayout from the current set of messages."""
        frame = FrameLayout(width=self.width, height=self.height)

        # Sort messages by priority descending
        by_priority = sorted(messages, key=lambda m: m.priority, reverse=True)

        # Categorize available content
        flights = [m for m in by_priority if m.category == "flights"]
        calendar_events = [m for m in by_priority if m.category == "calendar"]
        weather = [m for m in by_priority if m.category == "weather"]

        urgent_events = [
            m for m in calendar_events if m.priority >= Priority.URGENT
        ]

        # --- Smart adaptive layout selection ---
        if flights and urgent_events:
            self._layout_split(frame, flights[0], urgent_events[0], weather)
        elif flights:
            self._layout_flight_full(frame, flights[0], weather)
        elif urgent_events:
            self._layout_calendar_full(frame, urgent_events[0], weather)
        elif calendar_events:
            self._layout_calendar_ambient(frame, calendar_events[0], weather)
        elif weather:
            self._layout_weather_full(frame, weather)
        else:
            self._layout_idle(frame)

        return frame

    # ── Layout modes ────────────────────────────────────

    def _layout_split(
        self,
        frame: FrameLayout,
        flight: MarqueeMessage,
        event: MarqueeMessage,
        weather: List[MarqueeMessage],
    ):
        """Split screen: flight on top, calendar event on bottom."""
        mid_y = self.height // 2

        # Top half: flight
        self._draw_flight_section(frame, flight, y_start=0, y_end=mid_y)

        # Separator line
        frame.elements.append(
            RectElement(0, mid_y, self.width, 1, colors.SEPARATOR_COLOR)
        )

        # Bottom half: calendar event
        self._draw_calendar_section(frame, event, y_start=mid_y + 1, y_end=self.height)

    def _layout_flight_full(
        self,
        frame: FrameLayout,
        flight: MarqueeMessage,
        weather: List[MarqueeMessage],
    ):
        """Full screen flight display."""
        self._draw_flight_section(frame, flight, y_start=0, y_end=self.height - 10)

        # Bottom strip: weather summary if available
        if weather:
            self._draw_weather_strip(frame, weather[0], y_start=self.height - 10)
        else:
            self._draw_clock_strip(frame, y_start=self.height - 9)

    def _layout_calendar_full(
        self,
        frame: FrameLayout,
        event: MarqueeMessage,
        weather: List[MarqueeMessage],
    ):
        """Full screen calendar event (urgent)."""
        self._draw_calendar_section(frame, event, y_start=0, y_end=self.height - 10)

        if weather:
            self._draw_weather_strip(frame, weather[0], y_start=self.height - 10)
        else:
            self._draw_clock_strip(frame, y_start=self.height - 9)

    def _layout_calendar_ambient(
        self,
        frame: FrameLayout,
        event: MarqueeMessage,
        weather: List[MarqueeMessage],
    ):
        """Non-urgent calendar + weather + clock."""
        # Clock at top
        self._draw_clock_section(frame, y_start=0, y_end=14)

        # Weather in middle
        if weather:
            self._draw_weather_section(frame, weather, y_start=14, y_end=40)

        # Calendar event at bottom
        self._draw_calendar_section(frame, event, y_start=40, y_end=self.height)

    def _layout_weather_full(
        self,
        frame: FrameLayout,
        weather: List[MarqueeMessage],
    ):
        """Clock + full weather display (no flights or events)."""
        self._draw_clock_section(frame, y_start=0, y_end=14)
        self._draw_weather_section(frame, weather, y_start=14, y_end=self.height)

    def _layout_idle(self, frame: FrameLayout):
        """Nothing to show — display clock and date."""
        now = datetime.now()
        time_str = now.strftime("%-I:%M")
        ampm = now.strftime("%p").lower()
        date_str = now.strftime("%a %b %-d")

        # Large centered clock
        frame.elements.append(
            TextElement(
                x=self.width // 2 - 20,
                y=self.height // 2 - 14,
                text=time_str,
                font_name="large",
                color=colors.CLOCK_COLOR,
            )
        )
        frame.elements.append(
            TextElement(
                x=self.width // 2 + 14,
                y=self.height // 2 - 10,
                text=ampm,
                font_name="tiny",
                color=colors.DIM_WHITE,
            )
        )
        # Date below
        frame.elements.append(
            TextElement(
                x=self.width // 2 - 20,
                y=self.height // 2 + 4,
                text=date_str,
                font_name="small",
                color=colors.DIM_AMBER,
            )
        )

    # ── Section renderers ───────────────────────────────

    def _draw_flight_section(
        self,
        frame: FrameLayout,
        flight: MarqueeMessage,
        y_start: int,
        y_end: int,
    ):
        """Render a flight info section."""
        d = flight.data
        y = y_start + 1

        # Icon + flight number
        frame.elements.append(IconElement(1, y, "plane", size=8))

        flight_num = d.get("flight_number", "???")
        frame.elements.append(
            TextElement(11, y, flight_num, "small", colors.FLIGHT_COLOR)
        )

        y += 10

        # Route
        dep = d.get("route_dep", "")
        arr = d.get("route_arr", "")
        if dep and arr:
            route_text = f"{dep}->{arr}"
        elif dep or arr:
            route_text = dep or arr
        else:
            route_text = ""
        if route_text:
            frame.elements.append(
                TextElement(2, y, route_text, "small", colors.WHITE)
            )
            y += 10

        # Altitude + aircraft type
        alt = d.get("altitude_feet")
        aircraft = d.get("aircraft_type", "")
        alt_str = f"{alt:,}ft" if alt else ""
        info_parts = [p for p in [alt_str, aircraft] if p]
        if info_parts:
            frame.elements.append(
                TextElement(2, y, "  ".join(info_parts), "tiny", colors.DIM_CYAN)
            )
            y += 9

        # Distance
        dist = d.get("distance_miles")
        if dist is not None:
            frame.elements.append(
                TextElement(2, y, f"{dist:.1f} mi away", "tiny", colors.DIM_WHITE)
            )

    def _draw_calendar_section(
        self,
        frame: FrameLayout,
        event: MarqueeMessage,
        y_start: int,
        y_end: int,
    ):
        """Render a calendar event section."""
        d = event.data
        y = y_start + 1

        # Icon + "NEXT UP" label
        frame.elements.append(IconElement(1, y, "calendar", size=8))

        minutes = d.get("minutes_until")
        if minutes is not None and minutes < 60:
            label = f"IN {minutes} MIN"
            label_color = colors.RED if minutes < 10 else colors.ORANGE
        elif minutes is not None:
            hours = minutes // 60
            label = f"IN {hours}H"
            label_color = colors.CALENDAR_COLOR
        else:
            label = "NEXT UP"
            label_color = colors.CALENDAR_COLOR

        frame.elements.append(
            TextElement(11, y, label, "tiny", label_color)
        )
        y += 10

        # Event name
        summary = d.get("summary", event.text)
        # Truncate if too long for display
        max_chars = self.width // 5  # rough estimate
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1] + "."
        frame.elements.append(
            TextElement(2, y, summary, "small", colors.WHITE)
        )
        y += 10

        # Time
        start_time = d.get("start_time", "")
        if start_time:
            frame.elements.append(
                TextElement(2, y, start_time, "tiny", colors.DIM_GREEN)
            )

    def _draw_weather_section(
        self,
        frame: FrameLayout,
        weather: List[MarqueeMessage],
        y_start: int,
        y_end: int,
    ):
        """Render full weather section."""
        if not weather:
            return
        d = weather[0].data
        y = y_start + 1

        # Weather icon
        condition = d.get("condition", "").lower()
        icon_name = self._weather_icon(condition)
        frame.elements.append(IconElement(1, y, icon_name, size=8))

        # Temperature
        temp = d.get("temp", "")
        unit = d.get("temp_unit", "F")
        temp_str = f"{temp}{unit}" if temp != "" else ""
        frame.elements.append(
            TextElement(11, y, temp_str, "medium", colors.WEATHER_COLOR)
        )
        y += 11

        # Condition text
        cond_text = d.get("condition", "")
        if cond_text:
            frame.elements.append(
                TextElement(2, y, cond_text, "tiny", colors.DIM_AMBER)
            )
            y += 9

        # Wind
        wind_speed = d.get("wind_speed")
        wind_dir = d.get("wind_dir", "")
        if wind_speed is not None:
            wind_text = f"Wind: {wind_speed} {wind_dir}"
            frame.elements.append(
                TextElement(2, y, wind_text, "tiny", colors.DIM_WHITE)
            )
            y += 9

        # Hi/Lo from forecast (second weather message)
        if len(weather) > 1:
            fd = weather[1].data
            hi = fd.get("hi", "")
            lo = fd.get("lo", "")
            if hi and lo:
                frame.elements.append(
                    TextElement(2, y, f"H:{hi} L:{lo}", "tiny", colors.DIM_AMBER)
                )

    def _draw_weather_strip(
        self,
        frame: FrameLayout,
        weather: MarqueeMessage,
        y_start: int,
    ):
        """Compact single-line weather at the bottom."""
        d = weather.data
        frame.elements.append(
            RectElement(0, y_start, self.width, 1, colors.SEPARATOR_COLOR)
        )
        temp = d.get("temp", "")
        unit = d.get("temp_unit", "F")
        condition = d.get("condition", "")
        text = f"{temp}{unit} {condition}" if temp != "" else condition
        frame.elements.append(
            TextElement(2, y_start + 2, text, "tiny", colors.WEATHER_COLOR)
        )

    def _draw_clock_section(
        self,
        frame: FrameLayout,
        y_start: int,
        y_end: int,
    ):
        """Render clock at the top of the display."""
        now = datetime.now()
        time_str = now.strftime("%-I:%M")
        ampm = now.strftime("%p").lower()

        frame.elements.append(IconElement(1, y_start + 1, "clock", size=8))
        frame.elements.append(
            TextElement(11, y_start + 1, time_str, "medium", colors.CLOCK_COLOR)
        )
        frame.elements.append(
            TextElement(11 + len(time_str) * 7 + 2, y_start + 3, ampm, "tiny", colors.DIM_WHITE)
        )

    def _draw_clock_strip(self, frame: FrameLayout, y_start: int):
        """Compact clock line at the bottom."""
        now = datetime.now()
        time_str = now.strftime("%-I:%M %p").lower()
        frame.elements.append(
            RectElement(0, y_start, self.width, 1, colors.SEPARATOR_COLOR)
        )
        frame.elements.append(
            TextElement(2, y_start + 2, time_str, "tiny", colors.DIM_WHITE)
        )

    @staticmethod
    def _weather_icon(condition: str) -> str:
        """Pick an icon name from a weather condition string."""
        c = condition.lower()
        if "rain" in c or "drizzle" in c or "shower" in c:
            return "rain"
        if "cloud" in c or "overcast" in c:
            return "cloud"
        return "sun"

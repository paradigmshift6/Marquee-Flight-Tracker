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
from .icons import condition_to_icon

logger = logging.getLogger(__name__)


# ── Frame element types ─────────────────────────────────

@dataclass
class TextElement:
    x: int
    y: int
    text: str
    font_name: str = "small"
    color: Tuple[int, int, int] = colors.WHITE
    max_width: Optional[int] = None  # px limit; painter truncates or scrolls
    scroll: bool = False              # True → scroll instead of truncate


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
        # Split layout needs ~16 px per half; skip it on short (32 px) panels
        # and fall through to flight-full which handles the single-section case.
        if flights and urgent_events and self.height > 32:
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
        strip_h = 12 if self.height <= 32 else 13  # extra margin on short panels
        self._draw_flight_section(frame, flight, y_start=0, y_end=self.height - strip_h)

        # Bottom strip: weather summary if available
        if weather:
            self._draw_weather_strip(frame, weather[0], y_start=self.height - strip_h)
        else:
            self._draw_clock_strip(frame, y_start=self.height - strip_h)

    def _layout_calendar_full(
        self,
        frame: FrameLayout,
        event: MarqueeMessage,
        weather: List[MarqueeMessage],
    ):
        """Full screen calendar event (urgent)."""
        strip_h = 12 if self.height <= 32 else 13  # extra margin on short panels
        self._draw_calendar_section(frame, event, y_start=0, y_end=self.height - strip_h)

        if weather:
            self._draw_weather_strip(frame, weather[0], y_start=self.height - strip_h)
        else:
            self._draw_clock_strip(frame, y_start=self.height - strip_h)

    def _layout_calendar_ambient(
        self,
        frame: FrameLayout,
        event: MarqueeMessage,
        weather: List[MarqueeMessage],
    ):
        """Non-urgent calendar + weather + clock."""
        # Clock at top
        self._draw_clock_section(frame, y_start=0, y_end=14)

        # Weather in middle — only on tall panels (64x64+).
        # On short panels (64x32), skip weather here so the calendar event
        # has enough vertical room to actually render.
        if weather and self.height >= 48:
            weather_end = min(self.height - 20, 44)
            self._draw_weather_section(frame, weather, y_start=14, y_end=weather_end)
            cal_start = weather_end
        else:
            cal_start = 14

        # Calendar event — gets full remaining space
        self._draw_calendar_section(frame, event, y_start=cal_start, y_end=self.height)

    def _layout_weather_full(
        self,
        frame: FrameLayout,
        weather: List[MarqueeMessage],
    ):
        """Clock + full weather display (no flights or events)."""
        self._draw_clock_section(frame, y_start=0, y_end=14)
        self._draw_weather_section(frame, weather, y_start=14, y_end=self.height)

    def _layout_idle(self, frame: FrameLayout):
        """Nothing to show — display a dim clock and date, properly centred."""
        now = datetime.now()
        time_str = now.strftime("%-I:%M")
        ampm    = now.strftime("%p").lower()
        date_str = now.strftime("%a %b %-d")

        # ── Measure widths (matches BDF font cell widths exactly) ──────────
        time_w = self._approx_text_width(time_str, "large")   # 9 px/char
        ampm_w = self._approx_text_width(ampm, "tiny")        # 5 px/char
        date_w = self._approx_text_width(date_str, "small")   # 6 px/char

        # Total width of "HH:MM am" row (time + 2 px gap + am/pm)
        row_w = time_w + 2 + ampm_w

        # Horizontal: centre the time row; centre the date independently
        clock_x = max(1, (self.width - row_w) // 2)
        ampm_x  = clock_x + time_w + 2
        date_x  = max(1, (self.width - date_w) // 2)

        # Vertical: stack [time row 15px] [2px gap] [date 10px] = 27px block
        block_h = 15 + 2 + 10
        time_y  = max(0, (self.height - block_h) // 2)
        date_y  = time_y + 17

        # ── Elements ───────────────────────────────────────────────────────
        frame.elements.append(
            TextElement(
                x=clock_x, y=time_y,
                text=time_str, font_name="large",
                color=colors.SLEEP_CLOCK_COLOR,
                max_width=self.width - clock_x,
            )
        )
        # am/pm sits slightly lower to baseline-align with the large glyphs
        frame.elements.append(
            TextElement(
                x=ampm_x, y=time_y + 7,
                text=ampm, font_name="tiny",
                color=colors.SLEEP_DATE_COLOR,
                max_width=max(1, self.width - ampm_x),
            )
        )
        frame.elements.append(
            TextElement(
                x=date_x, y=date_y,
                text=date_str, font_name="small",
                color=colors.SLEEP_DATE_COLOR,
                max_width=self.width - date_x,
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
        """Render a flight info section, clipping content to y_end."""
        d = flight.data
        y = y_start + 1

        # Icon + flight number (row 1 — always draw if section has any height)
        frame.elements.append(IconElement(1, y, "plane", size=8))
        flight_num = d.get("flight_number", "???")
        frame.elements.append(
            TextElement(11, y, flight_num, "small", colors.FLIGHT_COLOR,
                        max_width=self.width - 11)
        )
        y += 10

        # Route (row 2 — only if it fits within y_end)
        dep = d.get("route_dep", "")
        arr = d.get("route_arr", "")
        if dep and arr:
            route_text = f"{dep}->{arr}"
        elif dep or arr:
            route_text = dep or arr
        else:
            route_text = ""
        if route_text and y + 9 <= y_end:
            frame.elements.append(
                TextElement(2, y, route_text, "small", colors.WHITE,
                            max_width=self.width - 2)
            )
            y += 10

        # Altitude + aircraft type (row 3 — only if it fits within y_end)
        alt = d.get("altitude_feet")
        aircraft = d.get("aircraft_type", "")
        alt_str = f"{alt:,}ft" if alt else ""
        info_parts = [p for p in [alt_str, aircraft] if p]
        if info_parts and y + 7 <= y_end:
            frame.elements.append(
                TextElement(2, y, "  ".join(info_parts), "tiny", colors.DIM_CYAN,
                            max_width=self.width - 2)
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
        available_height = y_end - y_start

        # Icon + time / countdown header
        frame.elements.append(IconElement(1, y, "calendar", size=8))

        minutes = d.get("minutes_until")
        start_time = d.get("start_time", "")

        if minutes is not None and minutes < 60:
            label = f"{start_time}  in {minutes}m" if start_time else f"IN {minutes} MIN"
            label_color = colors.RED if minutes < 10 else colors.ORANGE
        elif minutes is not None:
            hours = minutes // 60
            label = f"{start_time}  {hours}h" if start_time else f"IN {hours}H"
            label_color = colors.CALENDAR_COLOR
        else:
            label = start_time or "NEXT UP"
            label_color = colors.CALENDAR_COLOR

        frame.elements.append(
            TextElement(11, y, label, "tiny", label_color,
                        max_width=self.width - 11)
        )

        # Header advance: tighter on short sections to leave room for event text
        section_h = y_end - y_start
        header_h = 8 if section_h < 22 else 9
        y += header_h

        # Event name — word-wrap if it fits, otherwise scroll the full text.
        summary = d.get("summary", event.text)
        max_line_px = self.width - 4  # 2px margin each side
        # Use tighter line height when the remaining area is small (short panels)
        available = y_end - y
        line_height = 8 if available < 20 else 9

        lines = self._word_wrap(summary, max_line_px, "tiny")
        max_lines = max(1, available // line_height)

        if len(lines) <= max_lines:
            # Fits completely — render static word-wrapped lines
            for line in lines:
                frame.elements.append(
                    TextElement(2, y, line, "tiny", colors.WHITE)
                )
                y += line_height
        else:
            # Too long to show fully — scroll the full text on a single line so
            # nothing is lost.  The painter pauses at each end before scrolling,
            # so the text sits still most of the time ("occasionally" scrolling).
            frame.elements.append(
                TextElement(2, y, summary, "tiny", colors.WHITE,
                            max_width=max_line_px, scroll=True)
            )

    def _draw_weather_section(
        self,
        frame: FrameLayout,
        weather: List[MarqueeMessage],
        y_start: int,
        y_end: int,
    ):
        """Render full weather section (respects y_end boundary)."""
        if not weather:
            return
        d = weather[0].data
        y = y_start + 1
        line_h = 9  # height of a tiny-font line

        # Weather icon + temperature (always drawn)
        condition = d.get("condition", "").lower()
        icon_name = condition_to_icon(condition)
        frame.elements.append(IconElement(1, y, icon_name, size=8))

        temp = d.get("temp", "")
        unit = d.get("temp_unit", "F")
        temp_str = f"{temp}{unit}" if temp != "" else ""
        frame.elements.append(
            TextElement(11, y, temp_str, "medium", colors.WEATHER_COLOR,
                        max_width=self.width - 11)
        )
        y += 11

        # Condition text (scrolls if long, e.g. "Thunderstorms with Heavy Rain")
        cond_text = d.get("condition", "")
        if cond_text and y + line_h <= y_end:
            frame.elements.append(
                TextElement(2, y, cond_text, "tiny", colors.DIM_AMBER,
                            max_width=self.width - 2, scroll=True)
            )
            y += line_h

        # Wind
        wind_speed = d.get("wind_speed")
        wind_dir = d.get("wind_dir", "")
        if wind_speed is not None and y + line_h <= y_end:
            wind_text = f"Wind: {wind_speed} {wind_dir}"
            frame.elements.append(
                TextElement(2, y, wind_text, "tiny", colors.DIM_WHITE,
                            max_width=self.width - 2)
            )
            y += line_h

        # Hi/Lo from forecast (second weather message)
        if len(weather) > 1 and y + line_h <= y_end:
            fd = weather[1].data
            hi = fd.get("hi", "")
            lo = fd.get("lo", "")
            if hi and lo:
                frame.elements.append(
                    TextElement(2, y, f"H:{hi} L:{lo}", "tiny", colors.DIM_AMBER,
                                max_width=self.width - 2)
                )

    def _draw_weather_strip(
        self,
        frame: FrameLayout,
        weather: MarqueeMessage,
        y_start: int,
    ):
        """Compact single-line weather at the bottom: icon + temp."""
        d = weather.data
        frame.elements.append(
            RectElement(0, y_start, self.width, 1, colors.SEPARATOR_COLOR)
        )

        # Weather condition icon (5x5) — replaces condition text to save space
        condition = d.get("condition", "")
        icon_name = condition_to_icon(condition)
        icon_y = y_start + 3  # vertically center 5px icon in the 12px strip
        frame.elements.append(IconElement(2, icon_y, icon_name, size=5))

        # Temperature text after icon
        temp = d.get("temp", "")
        unit = d.get("temp_unit", "F")
        text_x = 9  # 2px pad + 5px icon + 2px gap
        if temp != "":
            frame.elements.append(
                TextElement(text_x, y_start + 2, f"{temp}{unit}", "tiny",
                            colors.WEATHER_COLOR, max_width=self.width - text_x)
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

        ampm_x = 11 + self._approx_text_width(time_str, "medium") + 2

        frame.elements.append(IconElement(1, y_start + 1, "clock", size=8))
        frame.elements.append(
            TextElement(11, y_start + 1, time_str, "medium", colors.CLOCK_COLOR,
                        max_width=self.width - 11)
        )
        frame.elements.append(
            TextElement(ampm_x, y_start + 3, ampm, "tiny", colors.DIM_WHITE,
                        max_width=max(1, self.width - ampm_x))
        )

    def _draw_clock_strip(self, frame: FrameLayout, y_start: int):
        """Compact clock line at the bottom."""
        now = datetime.now()
        time_str = now.strftime("%-I:%M %p").lower()
        frame.elements.append(
            RectElement(0, y_start, self.width, 1, colors.SEPARATOR_COLOR)
        )
        frame.elements.append(
            TextElement(2, y_start + 2, time_str, "tiny", colors.DIM_WHITE,
                        max_width=self.width - 2)
        )

    @staticmethod
    def _approx_text_width(text: str, font_name: str = "small") -> int:
        """Approximate pixel width of text for the given logical font.

        Uses average character widths measured from DejaVuSans at each
        size.  These are intentionally slight overestimates so word-wrap
        avoids overflow rather than allowing it.
        """
        _CHAR_W = {
            "tiny":   5,   # DejaVuSans 8 px  ≈ 5 px/char
            "small":  6,   # DejaVuSans 10 px ≈ 6 px/char
            "medium": 7,   # DejaVuSans 12 px ≈ 7 px/char
            "large":  9,   # DejaVuSans 16 px ≈ 9 px/char
        }
        return len(text) * _CHAR_W.get(font_name, 6)

    @classmethod
    def _word_wrap(cls, text: str, max_px: int, font_name: str = "small") -> list:
        """Split text into lines that fit within max_px width."""
        words = text.split()
        if not words:
            return [""]

        lines = []
        current = words[0]

        for word in words[1:]:
            test = current + " " + word
            if cls._approx_text_width(test, font_name) <= max_px:
                current = test
            else:
                lines.append(current)
                current = word

        lines.append(current)
        return lines


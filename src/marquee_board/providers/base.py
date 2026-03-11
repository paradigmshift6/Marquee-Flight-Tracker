from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List


class Priority(IntEnum):
    """Content priority for the adaptive layout engine."""
    LOW = 0        # clock, date fallback
    MEDIUM = 10    # weather (always-available ambient info)
    HIGH = 20      # calendar event < 2 hours away
    URGENT = 30    # flight overhead, calendar < 30 min


@dataclass
class MarqueeMessage:
    """A single message from a provider.

    ``text`` is used by the legacy terminal/scrolling display.
    ``data`` carries structured fields for the renderer layout engine.
    ``priority`` tells the layout engine how important this message is.
    """
    text: str
    category: str
    priority: int = Priority.MEDIUM
    data: Dict[str, Any] = field(default_factory=dict)


class MarqueeProvider(ABC):
    """Base class for all marquee data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider key (e.g., 'flights', 'weather', 'calendar')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for section headers."""

    @abstractmethod
    def start(self) -> None:
        """Initialize resources (called once before the main loop)."""

    @abstractmethod
    def fetch_messages(self) -> List[MarqueeMessage]:
        """Return current messages. Providers manage their own poll interval
        internally — this may return cached results if the interval hasn't elapsed."""

    @abstractmethod
    def stop(self) -> None:
        """Clean up resources."""

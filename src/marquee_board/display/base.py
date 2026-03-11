from abc import ABC, abstractmethod
from typing import Dict, List


class DisplayBackend(ABC):
    @abstractmethod
    def start(self) -> None:
        """Initialize the display."""

    @abstractmethod
    def update(
        self,
        grouped: Dict[str, List[str]],
        display_names: Dict[str, str],
        **kwargs,
    ) -> None:
        """Update the display with grouped messages from providers.

        Args:
            grouped: {provider_name: [message_strings]}
            display_names: {provider_name: human_readable_name}
            **kwargs: Additional data (e.g. ``structured`` list of MarqueeMessage)
        """

    @abstractmethod
    def stop(self) -> None:
        """Clean up resources."""

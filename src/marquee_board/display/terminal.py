import threading
import time
from typing import Dict, List, Optional

from rich.live import Live
from rich.text import Text
from rich.panel import Panel

from .base import DisplayBackend


class TerminalDisplay(DisplayBackend):
    def __init__(
        self,
        scroll_speed: float = 0.08,
        idle_message: str = "No data yet...",
        width: int = 60,
    ):
        self._scroll_speed = scroll_speed
        self._idle_message = idle_message
        self._width = width
        self._messages: List[str] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._scroll_loop, daemon=True)
        self._thread.start()

    def update(
        self,
        grouped: Dict[str, List[str]],
        display_names: Dict[str, str],
        **kwargs,
    ) -> None:
        # Flatten all provider messages into one interleaved list
        flat = []
        for name, msgs in grouped.items():
            flat.extend(msgs)
        with self._lock:
            self._messages = flat

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _scroll_loop(self):
        msg_idx = 0
        offset = 0

        with Live(refresh_per_second=12, transient=False) as live:
            while self._running:
                with self._lock:
                    msgs = self._messages.copy()

                if not msgs:
                    live.update(Panel(
                        Text(self._idle_message, style="dim italic"),
                        title="[bold cyan]Marquee Board[/]",
                        width=self._width + 4,
                        border_style="cyan",
                    ))
                    time.sleep(0.5)
                    continue

                current = msgs[msg_idx % len(msgs)]
                padded = " " * self._width + current + " " * self._width
                window = padded[offset:offset + self._width]

                live.update(Panel(
                    Text(window, style="bold green"),
                    title="[bold cyan]Marquee Board[/]",
                    subtitle=f"[dim]{len(msgs)} items[/]",
                    width=self._width + 4,
                    border_style="cyan",
                ))

                offset += 1
                if offset > len(current) + self._width:
                    offset = 0
                    msg_idx += 1

                time.sleep(self._scroll_speed)

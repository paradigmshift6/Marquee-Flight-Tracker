"""Google Calendar provider using OAuth2 browser flow.

Uses google-auth + requests directly instead of google-api-python-client
to avoid the httplib2 SSL compatibility issues on Python 3.13 + sudo.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from .base import MarqueeMessage, MarqueeProvider, Priority
from ..config import AppConfig

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
_CALENDAR_API = "https://www.googleapis.com/calendar/v3/calendars/{}/events"


class CalendarProvider(MarqueeProvider):
    def __init__(self, config: AppConfig):
        self._credentials_file = config.calendar.credentials_file
        self._token_file = config.calendar.token_file
        self._calendar_id = config.calendar.calendar_id
        self._lookahead_hours = config.calendar.lookahead_hours
        self._poll_interval = config.calendar.poll_interval
        self._session = None
        self._last_fetch: float = 0.0
        self._cached_messages: List[MarqueeMessage] = []

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def display_name(self) -> str:
        return "Upcoming Events"

    def start(self) -> None:
        self._session = self._build_session()
        logger.info("Calendar provider started (calendar: %s)", self._calendar_id)

    def fetch_messages(self) -> List[MarqueeMessage]:
        now = time.monotonic()
        if self._cached_messages and (now - self._last_fetch) < self._poll_interval:
            return self._cached_messages

        if not self._session:
            return self._cached_messages

        try:
            messages = self._fetch_events()
            self._cached_messages = messages
            self._last_fetch = now
        except Exception:
            logger.exception("Error fetching calendar events")

        return self._cached_messages

    def stop(self) -> None:
        pass

    def _build_session(self):
        """Build an authorized requests session using google-auth (no httplib2)."""
        try:
            from google.auth.transport.requests import Request, AuthorizedSession
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            logger.error(
                "Calendar provider requires google-auth-oauthlib. "
                "Install with: pip install marquee-board[calendar]"
            )
            return None

        creds = None
        token_path = Path(self._token_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds_path = Path(self._credentials_file)
                if not creds_path.exists():
                    logger.error(
                        "Google Calendar credentials file not found: %s. "
                        "Download it from the Google Cloud Console.",
                        self._credentials_file,
                    )
                    return None

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())

        session = AuthorizedSession(creds)
        # certifi's cacert.pem is sometimes absent in venvs built under sudo.
        # Fall back to the system CA bundle (always present on Debian/Pi OS).
        _SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"
        try:
            import certifi
            ca_bundle = certifi.where()
            import os
            if not os.path.exists(ca_bundle):
                raise FileNotFoundError(ca_bundle)
        except Exception:
            ca_bundle = _SYSTEM_CA
        session.verify = ca_bundle
        return session

    def _fetch_events(self) -> List[MarqueeMessage]:
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(hours=self._lookahead_hours)

        url = _CALENDAR_API.format(self._calendar_id)
        response = self._session.get(
            url,
            params={
                "timeMin": now.isoformat(),
                "timeMax": time_max.isoformat(),
                "maxResults": 10,
                "singleEvents": True,
                "orderBy": "startTime",
            },
        )
        response.raise_for_status()
        events = response.json().get("items", [])

        messages = []
        for event in events:
            msg = self._build_message(event, now)
            if msg:
                messages.append(msg)

        return messages

    def _build_message(self, event: dict, now: datetime) -> Optional[MarqueeMessage]:
        summary = event.get("summary", "Untitled")
        all_day = False
        minutes_until = None
        time_str = ""

        start = event.get("start", {})
        if "dateTime" in start:
            dt = datetime.fromisoformat(start["dateTime"])
            time_str = dt.strftime("%-I:%M %p")
            delta = dt.replace(tzinfo=timezone.utc if dt.tzinfo is None else dt.tzinfo) - now
            # Skip events that have already started (> 1 min ago)
            if delta.total_seconds() < -60:
                return None
            minutes_until = max(0, int(delta.total_seconds() / 60))
            relative = self._relative_time(delta)
        elif "date" in start:
            time_str = "All day"
            all_day = True
            relative = ""
        else:
            return None

        # Build legacy text
        parts = [time_str, summary]
        if relative:
            parts.append(f"({relative})")
        text = "  ".join(parts)

        # Determine priority based on urgency
        if minutes_until is not None and minutes_until < 30:
            priority = Priority.URGENT
        elif minutes_until is not None and minutes_until < 120:
            priority = Priority.HIGH
        else:
            priority = Priority.MEDIUM

        data = {
            "summary": summary,
            "start_time": time_str,
            "minutes_until": minutes_until,
            "all_day": all_day,
        }

        return MarqueeMessage(
            text=text,
            category="calendar",
            priority=priority,
            data=data,
        )

    @staticmethod
    def _relative_time(delta: timedelta) -> str:
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 0:
            return "now"
        if total_minutes < 1:
            return "now"
        if total_minutes < 60:
            return f"in {total_minutes} min"
        hours = total_minutes // 60
        if hours < 24:
            return f"in {hours}h"
        days = hours // 24
        return f"in {days}d"

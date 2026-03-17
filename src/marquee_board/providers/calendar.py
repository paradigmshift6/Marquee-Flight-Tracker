"""Google Calendar provider using OAuth2 browser flow.

Uses google-auth + requests directly instead of google-api-python-client
to avoid the httplib2 SSL compatibility issues on Python 3.13 + sudo.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

# certifi's cacert.pem can be missing in venvs partially built under sudo.
# Set REQUESTS_CA_BUNDLE to the system CA bundle as a fallback — this is
# checked by requests at the lowest level (before session.verify).
_SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"
if "REQUESTS_CA_BUNDLE" not in os.environ:
    try:
        import certifi
        _ca = certifi.where()
        if not os.path.isfile(_ca):
            raise FileNotFoundError(_ca)
    except Exception:
        if os.path.isfile(_SYSTEM_CA):
            os.environ["REQUESTS_CA_BUNDLE"] = _SYSTEM_CA
            logging.getLogger(__name__).debug(
                "certifi CA bundle missing; using system CA: %s", _SYSTEM_CA
            )

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
            import requests as req_lib
            from google.auth.transport.requests import Request, AuthorizedSession
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            logger.error(
                "Calendar provider requires google-auth-oauthlib. "
                "Install with: pip install marquee-board[calendar]"
            )
            return None

        # Resolve a working CA bundle — certifi's can be broken in sudo venvs
        ca_bundle = self._find_ca_bundle()

        # Auth request session (used internally for token refresh)
        auth_sess = req_lib.Session()
        auth_sess.verify = ca_bundle
        auth_request = Request(session=auth_sess)

        creds = None
        token_path = Path(self._token_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired:
                if creds.refresh_token:
                    creds.refresh(auth_request)
                else:
                    # Token exists but has no refresh_token — it can't be silently
                    # renewed.  Running the browser flow on a headless Pi would hang.
                    logger.error(
                        "Calendar token at '%s' is expired and has no refresh_token. "
                        "Delete it and re-authorize on a machine with a browser: "
                        "  rm %s  && python -m marquee_board -c config.yaml",
                        self._token_file, self._token_file,
                    )
                    return None
            else:
                # No token at all — need a browser-based OAuth2 flow.
                creds_path = Path(self._credentials_file)
                if not creds_path.exists():
                    logger.error(
                        "Google Calendar credentials file not found: %s. "
                        "Download it from the Google Cloud Console.",
                        self._credentials_file,
                    )
                    return None

                # On headless systems (no DISPLAY / Wayland), run_local_server()
                # will start a local HTTP server but webbrowser.open() silently
                # fails — the service would hang waiting for a redirect that
                # never comes.  Detect this and fail fast with a clear message.
                import sys as _sys
                _headless = (
                    os.name != "nt"
                    and not os.environ.get("DISPLAY")
                    and not os.environ.get("WAYLAND_DISPLAY")
                    and not _sys.stdin.isatty()
                )
                if _headless:
                    logger.error(
                        "No Google Calendar token found and no browser is available. "
                        "Authorize on a machine with a browser first, then copy "
                        "%s to this device.",
                        self._token_file,
                    )
                    return None

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())

        session = AuthorizedSession(creds, auth_request=auth_request)
        session.verify = ca_bundle
        return session

    @staticmethod
    def _find_ca_bundle() -> str:
        """Return path to a working CA certificate bundle."""
        # Prefer system CA bundle (always works on Debian/Pi OS)
        for path in (
            "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu/Pi OS
            "/etc/pki/tls/certs/ca-bundle.crt",     # RHEL/Fedora
        ):
            if os.path.isfile(path):
                return path
        # Fallback to certifi
        try:
            import certifi
            ca = certifi.where()
            if os.path.isfile(ca):
                return ca
        except Exception:
            pass
        return True  # Let requests figure it out

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

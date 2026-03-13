import io
import os
import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory, Response

from .base import DisplayBackend

logger = logging.getLogger(__name__)

STATIC_DIR = Path(
    os.environ.get("MARQUEE_STATIC_DIR")
    or str(Path(__file__).resolve().parent.parent.parent.parent / "static")
)

# Fields that should be masked when serving config via the API
SENSITIVE_FIELDS = {
    ("opensky", "client_secret"),
    ("opensky", "password"),
    ("weather", "api_key"),
}
MASK_VALUE = "********"


class WebDisplay(DisplayBackend):
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        idle_message: str = "No data yet...",
        renderer_width: int = 64,
        renderer_height: int = 64,
        config=None,
        config_path: str = "config.yaml",
    ):
        self._host = host
        self._port = int(os.environ.get("PORT", port))
        self._idle_message = idle_message
        self._sections: List[dict] = []
        self._structured_messages: list = []
        self._mock_hold = False  # When True, update() won't overwrite mock data
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        # Settings support
        self._config = config
        self._config_path = config_path
        self._settings_lock = threading.Lock()

        # Renderer
        self._renderer_width = renderer_width
        self._renderer_height = renderer_height
        self._engine = None
        self._painter = None
        self._init_renderer()

        self._app = Flask(__name__, static_folder=str(STATIC_DIR))
        self._setup_routes()

    def _init_renderer(self):
        try:
            from ..renderer.engine import LayoutEngine
            from ..renderer.painter import FramePainter
            self._engine = LayoutEngine(self._renderer_width, self._renderer_height)
            self._painter = FramePainter(self._renderer_width, self._renderer_height)
            logger.info(
                "Renderer initialized (%dx%d)",
                self._renderer_width, self._renderer_height,
            )
        except Exception as e:
            logger.warning("Renderer unavailable (Pillow missing?): %s", e)

    def _setup_routes(self):
        @self._app.route("/")
        def index():
            return send_from_directory(str(STATIC_DIR), "marquee.html")

        @self._app.route("/simulator")
        def simulator():
            return send_from_directory(str(STATIC_DIR), "simulator.html")

        @self._app.route("/api/messages")
        def messages():
            with self._lock:
                sections = [s.copy() for s in self._sections]
            return jsonify({
                "sections": sections,
                "idle_message": self._idle_message,
            })

        @self._app.route("/api/frame")
        def frame():
            """Render the current state as a PNG image at LED matrix resolution."""
            if not self._engine or not self._painter:
                return Response("Renderer not available", status=503)

            with self._lock:
                msgs = list(self._structured_messages)

            layout = self._engine.layout(msgs)
            img = self._painter.paint(layout)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            return Response(
                buf.getvalue(),
                mimetype="image/png",
                headers={"Cache-Control": "no-store"},
            )

        @self._app.route("/api/frame/config")
        def frame_config():
            return jsonify({
                "width": self._renderer_width,
                "height": self._renderer_height,
            })

        # Keep legacy endpoint for backwards compatibility
        @self._app.route("/api/flights")
        def flights():
            with self._lock:
                for s in self._sections:
                    if s["name"] == "flights":
                        return jsonify({
                            "flights": s["messages"],
                            "idle_message": self._idle_message,
                        })
            return jsonify({"flights": [], "idle_message": self._idle_message})

        @self._app.route("/api/mock", methods=["POST"])
        def inject_mock():
            """Inject mock data for testing all layout modes."""
            from ..providers.base import MarqueeMessage, Priority

            mode = (request.args.get("mode") or "flight").lower()
            msgs = []

            if mode in ("flight", "all", "split"):
                msgs.append(MarqueeMessage(
                    text="UAL1234 SFO->SLC 35,000ft B738 1.2mi",
                    category="flights",
                    priority=Priority.URGENT,
                    data={
                        "flight_number": "UAL1234",
                        "route_dep": "SFO",
                        "route_arr": "SLC",
                        "altitude_feet": 35000,
                        "distance_miles": 1.2,
                        "aircraft_type": "B738",
                    },
                ))

            if mode in ("calendar", "urgent_cal", "all", "split"):
                mins = 12 if mode in ("urgent_cal", "split") else 45
                msgs.append(MarqueeMessage(
                    text=f"1:30 PM  Team Standup  (in {mins} min)",
                    category="calendar",
                    priority=Priority.URGENT if mins < 30 else Priority.HIGH,
                    data={
                        "summary": "Team Standup",
                        "start_time": "1:30 PM",
                        "minutes_until": mins,
                        "all_day": False,
                    },
                ))

            if mode in ("weather", "all", "split"):
                msgs.append(MarqueeMessage(
                    text="42°F  Partly Cloudy  Wind: 8mph NW",
                    category="weather",
                    priority=Priority.MEDIUM,
                    data={
                        "temp": 42,
                        "temp_unit": "°F",
                        "condition": "Partly Cloudy",
                        "wind_speed": "8mph",
                        "wind_dir": "NW",
                        "humidity": 55,
                    },
                ))
                msgs.append(MarqueeMessage(
                    text="Next 24h: 28°F - 45°F  Cloudy",
                    category="weather",
                    priority=Priority.MEDIUM,
                    data={
                        "hi": "45°F",
                        "lo": "28°F",
                        "condition": "Cloudy",
                    },
                ))

            if mode == "idle":
                msgs = []
                with self._lock:
                    self._structured_messages = msgs
                    self._mock_hold = False
            else:
                with self._lock:
                    self._structured_messages = msgs
                    self._mock_hold = True

            return jsonify({"ok": True, "mode": mode, "count": len(msgs)})

        # --- Settings UI ---

        @self._app.route("/settings")
        def settings_page():
            return send_from_directory(str(STATIC_DIR), "settings.html")

        @self._app.route("/api/settings")
        def get_settings():
            from ..config import config_to_dict
            if not self._config:
                return jsonify({"error": "Config not available"}), 503
            with self._settings_lock:
                data = config_to_dict(self._config)
            # Mask sensitive fields
            for section_key, field_key in SENSITIVE_FIELDS:
                if section_key in data and field_key in data[section_key]:
                    val = data[section_key][field_key]
                    data[section_key][field_key] = MASK_VALUE if val else ""
            return jsonify(data)

        @self._app.route("/api/settings", methods=["POST"])
        def save_settings():
            from ..config import config_to_dict, save_config

            payload = request.get_json()
            if not payload:
                return jsonify({"error": "No JSON body"}), 400

            with self._settings_lock:
                # Start from current config as base
                current_dict = config_to_dict(self._config)

                # Merge submitted values over current config
                for section_key, section_val in payload.items():
                    if section_key.startswith("_"):
                        continue  # skip meta keys like _restart
                    if section_key not in current_dict:
                        continue
                    if not isinstance(section_val, dict):
                        continue
                    for field_key, field_val in section_val.items():
                        if field_key not in current_dict[section_key]:
                            continue
                        # Preserve existing sensitive values if masked
                        if (section_key, field_key) in SENSITIVE_FIELDS:
                            if field_val == MASK_VALUE or field_val == "":
                                continue
                        current_dict[section_key][field_key] = field_val

                # Save to disk
                try:
                    save_config(self._config_path, current_dict)
                except Exception as e:
                    return jsonify({"error": f"Failed to save: {e}"}), 500

            do_restart = payload.get("_restart", False)

            if do_restart:
                def _delayed_exit():
                    import time as _time
                    import sys
                    _time.sleep(1)
                    logger.info("Restarting after settings change...")
                    sys.exit(0)
                threading.Thread(target=_delayed_exit, daemon=True).start()

            return jsonify({
                "saved": True,
                "restart_required": True,
                "restarting": do_restart,
            })

        @self._app.route("/static/<path:filename>")
        def static_files(filename):
            return send_from_directory(str(STATIC_DIR), filename)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=lambda: self._app.run(
                host=self._host,
                port=self._port,
                debug=False,
                use_reloader=False,
            ),
            daemon=True,
        )
        self._thread.start()
        logger.info("Web marquee running at http://%s:%d", self._host, self._port)
        logger.info("LED simulator at http://%s:%d/simulator", self._host, self._port)
        logger.info("Settings page at http://%s:%d/settings", self._host, self._port)

    def update(
        self,
        grouped: Dict[str, List[str]],
        display_names: Dict[str, str],
        **kwargs,
    ) -> None:
        sections = []
        for name, msgs in grouped.items():
            sections.append({
                "name": name,
                "display_name": display_names.get(name, name),
                "messages": msgs,
            })
        with self._lock:
            self._sections = sections
            if not self._mock_hold:
                self._structured_messages = kwargs.get("structured", [])

    def stop(self) -> None:
        pass

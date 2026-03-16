"""Entry point: python -m marquee_board"""
# Fix certifi CA bundle BEFORE requests is imported by any dependency.
# On Pi, venvs built under sudo can have a broken certifi with no cacert.pem.
import os as _os
if "REQUESTS_CA_BUNDLE" not in _os.environ:
    _sys_ca = "/etc/ssl/certs/ca-certificates.crt"
    try:
        import certifi as _certifi
        if not _os.path.isfile(_certifi.where()):
            raise FileNotFoundError
    except Exception:
        if _os.path.isfile(_sys_ca):
            _os.environ["REQUESTS_CA_BUNDLE"] = _sys_ca

import argparse
import logging
from pathlib import Path

from .config import load_config, save_config, AppConfig
from .app import MarqueeBoardApp

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Marquee Board - A smart adaptive LED matrix display"
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--display",
        choices=["terminal", "web", "led"],
        help="Override display backend from config (led requires Raspberry Pi)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config_path = args.config

    # First-run: create a default config if the file doesn't exist
    if not Path(config_path).exists():
        default = AppConfig()
        default.display.backend = "web"
        save_config(config_path, default)
        logger.info(
            "Created default config at %s — visit /settings to configure",
            config_path,
        )

    config = load_config(config_path)
    if args.display:
        config.display.backend = args.display

    # If location isn't set, force web backend so user can configure via browser
    if config.location.latitude == 0.0 and config.location.longitude == 0.0:
        logger.warning(
            "Location not configured — visit /settings to complete setup"
        )
        config.display.backend = "web"

    app = MarqueeBoardApp(config, config_path=config_path)
    app.run()


if __name__ == "__main__":
    main()

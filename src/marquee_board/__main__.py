"""Entry point: python -m marquee_board"""
import argparse
import logging

from .config import load_config
from .app import MarqueeBoardApp


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

    config = load_config(args.config)
    if args.display:
        config.display.backend = args.display

    app = MarqueeBoardApp(config)
    app.run()


if __name__ == "__main__":
    main()

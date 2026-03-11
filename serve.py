"""Standalone launcher for preview tooling."""
import os
import sys

# Add paths so system python can find all packages
base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(base, "src"))
sys.path.insert(0, os.path.join(base, ".venv", "lib", "python3.9", "site-packages"))

os.environ.setdefault("PORT", "5050")

from marquee_board.__main__ import main

sys.argv = [
    "serve.py",
    "-c", os.path.join(base, "config.yaml"),
    "--display", "web",
]
main()

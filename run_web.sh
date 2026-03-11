#!/bin/bash
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src:$PWD/.venv/lib/python3.9/site-packages"
export PORT="${PORT:-5050}"
exec /usr/bin/python3 -m marquee_board -c config.yaml --display web

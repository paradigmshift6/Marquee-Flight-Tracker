#!/usr/bin/env bash
# start-marquee.sh — Auto-update and launch Marquee Board on Raspberry Pi
# Called by systemd (marquee-board.service) or manually.
set -euo pipefail

MARQUEE_DIR="/home/levi/marquee-board"
VENV_PYTHON="$MARQUEE_DIR/.venv/bin/python"
VENV_PIP="$MARQUEE_DIR/.venv/bin/pip"
LOG_TAG="marquee-start"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

cd "$MARQUEE_DIR"

# ── 1. Pull latest code ────────────────────────────────
log "Checking for updates..."
# Fetch with a timeout so a network outage doesn't block boot forever
if timeout 30 git fetch origin main 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)

    if [ "$LOCAL" != "$REMOTE" ]; then
        log "Update available ($LOCAL -> $REMOTE), pulling..."
        git pull --ff-only origin main || {
            log "WARNING: git pull failed (local changes?), continuing with current version"
        }
        UPDATED=true
    else
        log "Already up to date."
        UPDATED=false
    fi
else
    log "WARNING: git fetch failed (no network?), continuing with current version"
    UPDATED=false
fi

# ── 2. Reinstall package if code was updated ───────────
if [ "$UPDATED" = true ]; then
    log "Installing updated package..."
    "$VENV_PIP" install --quiet -e . 2>&1 || {
        log "WARNING: pip install failed, continuing with previous install"
    }
fi

# ── 3. Ensure data directory exists and is writable ────
mkdir -p "$MARQUEE_DIR/data"

# ── 4. Ensure system CA bundle is available ────────────
export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"

# ── 5. Launch the app (needs root for GPIO/LED matrix) ─
log "Starting Marquee Board..."
exec sudo -E "$VENV_PYTHON" -m marquee_board -c config.yaml

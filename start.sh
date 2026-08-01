#!/usr/bin/env bash
# xDrive launcher — Linux (Arch and friends)
#
#   ./start.sh          run the server in this terminal + open a browser tab
#   ./start.sh --app    desktop-app mode: server in the background, xDrive
#                       opens as a native window (used by the launcher entry)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${XDRIVE_PORT:-8484}"
URL="http://127.0.0.1:${PORT}"
APP_MODE=0
if [ "${1:-}" = "--app" ]; then
    APP_MODE=1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found. Install it with:  sudo pacman -S python"
    exit 1
fi

# Keep Ollama's model store on this drive if the user hasn't set it already.
if [ -z "${OLLAMA_MODELS:-}" ] && [ -d "models/ollama" ]; then
    export OLLAMA_MODELS="$(pwd)/models/ollama"
fi

# Offer to start Ollama if it's installed but not running.
if command -v ollama >/dev/null 2>&1; then
    if ! curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "Starting Ollama (models dir: ${OLLAMA_MODELS:-default})..."
        nohup ollama serve >/dev/null 2>&1 &
        sleep 2
    fi
fi

# (kiwix-serve is managed by the xDrive server itself: started at boot when
# library/*.zim exist, restarted when new knowledge finishes downloading.)

server_up() {
    curl -sf -m 2 "$URL/api/status" >/dev/null 2>&1
}

native_window_available() {
    python3 - >/dev/null 2>&1 <<'PY'
import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("WebKit2", "4.1")
except ValueError:
    gi.require_version("WebKit2", "4.0")
PY
}

# Open xDrive as a native GTK window; fall back to a browser if the
# GTK/WebKit stack isn't installed (see scripts/setup-arch.sh).
open_app_window() {
    if native_window_available; then
        nohup python3 xdrive/window.py "$URL" >/dev/null 2>&1 &
        return 0
    fi
    local browser
    for browser in chromium chromium-browser google-chrome-stable \
                   google-chrome brave brave-browser vivaldi-stable \
                   microsoft-edge-stable; do
        if command -v "$browser" >/dev/null 2>&1; then
            nohup "$browser" --app="$URL" >/dev/null 2>&1 &
            return 0
        fi
    done
    if command -v firefox >/dev/null 2>&1; then
        nohup firefox --new-window "$URL" >/dev/null 2>&1 &
        return 0
    fi
    xdg-open "$URL" >/dev/null 2>&1 || echo "Open $URL in your browser."
}

# If a server is already running but was started from older code than what
# is now on disk (e.g. after an update), kill it so the fresh code loads —
# otherwise fixes stay dormant and the app looks broken forever.
kill_stale_server() {
    server_up || return 0
    local disk running
    disk="$(git rev-parse HEAD 2>/dev/null | cut -c1-12 || true)"
    [ -n "$disk" ] || return 0
    running="$(curl -sf -m 2 "$URL/api/status" |
        sed -n 's/.*"running_commit": "\([0-9a-f]*\)".*/\1/p')"
    if [ "$running" != "$disk" ]; then
        echo "Running server is outdated (${running:-unknown} vs $disk) — restarting it..."
        # bracket keeps this pattern from matching the shell running it
        pkill -f "[x]drive/server.py" 2>/dev/null || true
        sleep 1
    fi
}

if [ "$APP_MODE" = "1" ]; then
    kill_stale_server
    if ! server_up; then
        nohup python3 xdrive/server.py >/dev/null 2>&1 &
        for _ in $(seq 1 40); do
            server_up && break
            sleep 0.25
        done
    fi
    open_app_window
    exit 0
fi

kill_stale_server

# Terminal mode: open the UI in the default browser once the server is up.
( sleep 1.5; xdg-open "$URL" >/dev/null 2>&1 || true ) &

exec python3 xdrive/server.py

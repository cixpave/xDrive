#!/usr/bin/env bash
# xDrive launcher — Linux (Arch and friends)
#
#   ./start.sh          run the server in this terminal + open a browser tab
#   ./start.sh --app    desktop-app mode: server in the background, xDrive
#                       opens in its own window (used by the launcher entry)
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

# Serve the offline knowledge base (Wikipedia, dev docs) if present.
KIWIX_BIN=""
if command -v kiwix-serve >/dev/null 2>&1; then
    KIWIX_BIN="kiwix-serve"
elif [ -x "tools/kiwix/kiwix-serve" ]; then
    KIWIX_BIN="tools/kiwix/kiwix-serve"
fi
if [ -n "$KIWIX_BIN" ] && ls library/*.zim >/dev/null 2>&1; then
    if ! curl -sf -m 2 http://127.0.0.1:8181/catalog/v2/entries >/dev/null 2>&1; then
        echo "Starting knowledge base (kiwix-serve, library/)..."
        nohup "$KIWIX_BIN" --port 8181 library/*.zim >/dev/null 2>&1 &
    fi
fi

server_up() {
    curl -sf -m 2 "$URL/api/status" >/dev/null 2>&1
}

# Open xDrive in its own window (chromium app mode), falling back to a tab.
open_app_window() {
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

if [ "$APP_MODE" = "1" ]; then
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

# Terminal mode: open the UI in the default browser once the server is up.
( sleep 1.5; xdg-open "$URL" >/dev/null 2>&1 || true ) &

exec python3 xdrive/server.py

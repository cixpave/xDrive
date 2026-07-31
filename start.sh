#!/usr/bin/env bash
# xDrive launcher — Linux (Arch and friends)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${XDRIVE_PORT:-8484}"

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

# Open the UI in the default browser once the server is up.
( sleep 1.5; xdg-open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 || true ) &

exec python3 xdrive/server.py

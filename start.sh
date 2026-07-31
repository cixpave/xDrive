#!/usr/bin/env bash
# Ember launcher — Linux (Arch and friends)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${EMBER_PORT:-8484}"

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

# Open the UI in the default browser once the server is up.
( sleep 1.5; xdg-open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 || true ) &

exec python3 ember/server.py

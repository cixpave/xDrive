#!/usr/bin/env bash
# Download a recommended model lineup to this drive (requires internet ONCE).
# ~112 GB for the core set; see docs/MODELS.md for the full 5TB plan.
set -euo pipefail
cd "$(dirname "$0")/.."

export OLLAMA_MODELS="${OLLAMA_MODELS:-$(pwd)/models/ollama}"
mkdir -p "$OLLAMA_MODELS"
echo "Models will be stored in: $OLLAMA_MODELS"

if ! command -v ollama >/dev/null 2>&1; then
    echo "Error: ollama not installed. Run ./scripts/setup-arch.sh first."
    exit 1
fi

# Make sure the server is running with our models dir.
if ! curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    nohup ollama serve >/dev/null 2>&1 &
    sleep 3
fi

CORE_MODELS=(
    "qwen2.5-coder:14b"   # daily-driver coding model, 40+ languages (~9 GB)
    "qwen2.5:14b"         # daily-driver general model (~9 GB)
    "deepseek-r1:14b"     # step-by-step reasoning model (~9 GB)
    "qwen2.5-coder:32b"   # heavy coding model (~20 GB)
    "deepseek-r1:32b"     # heavy reasoning model (~20 GB)
    "llama3.3:70b"        # heavy general model (~43 GB)
    "qwen2.5:3b"          # fast lightweight fallback (~2 GB)
)

for m in "${CORE_MODELS[@]}"; do
    echo "── pulling $m ─────────────────────────────"
    ollama pull "$m"
done

echo
echo "All core models downloaded. xDrive is now fully offline-capable."
echo "See docs/MODELS.md for optional extras to fill out the 5TB drive."

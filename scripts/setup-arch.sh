#!/usr/bin/env bash
# One-time setup on Arch Linux (needs internet ONCE; xDrive runs offline after).
# Installs Python + Ollama and points Ollama's model store at this drive.
set -euo pipefail
cd "$(dirname "$0")/.."
DRIVE_DIR="$(pwd)"

echo "── xDrive setup (Arch Linux) ──────────────────────────"
echo "Drive location: $DRIVE_DIR"

sudo pacman -S --needed --noconfirm python ollama

mkdir -p "$DRIVE_DIR/models/ollama"

# Make the model store on this drive the default for your user.
PROFILE="$HOME/.config/environment.d/xdrive.conf"
mkdir -p "$(dirname "$PROFILE")"
echo "OLLAMA_MODELS=$DRIVE_DIR/models/ollama" > "$PROFILE"
export OLLAMA_MODELS="$DRIVE_DIR/models/ollama"

# If Ollama runs as a systemd service, point the service at the drive too.
if systemctl list-unit-files ollama.service >/dev/null 2>&1; then
    sudo mkdir -p /etc/systemd/system/ollama.service.d
    printf '[Service]\nEnvironment="OLLAMA_MODELS=%s"\n' "$DRIVE_DIR/models/ollama" |
        sudo tee /etc/systemd/system/ollama.service.d/xdrive.conf >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable --now ollama || true
fi

echo
echo "Done. Next steps:"
echo "  1. Download models while you still have internet:"
echo "       ./scripts/pull-models.sh"
echo "  2. Launch xDrive any time (works offline):"
echo "       ./start.sh"

#!/usr/bin/env bash
# One-time setup on Arch Linux (needs internet ONCE; xDrive runs offline after).
# Installs Python + Ollama and points Ollama's model store at this drive.
set -euo pipefail
cd "$(dirname "$0")/.."
DRIVE_DIR="$(pwd)"

echo "── xDrive setup (Arch Linux) ──────────────────────────"
echo "Drive location: $DRIVE_DIR"

sudo pacman -S --needed --noconfirm python ollama python-gobject gtk3

# WebKitGTK gives xDrive a native app window (no browser involved).
sudo pacman -S --needed --noconfirm webkit2gtk-4.1 ||
    sudo pacman -S --needed --noconfirm webkit2gtk ||
    echo "note: webkit2gtk not installed — xDrive will open in a browser window instead"

# kiwix-serve hosts the offline knowledge base (Wikipedia, dev docs).
if ! sudo pacman -S --needed --noconfirm kiwix-tools 2>/dev/null; then
    echo "kiwix-tools not in repos — fetching static binary to tools/kiwix/"
    mkdir -p "$DRIVE_DIR/tools/kiwix"
    curl -L "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-x86_64.tar.gz" |
        tar -xz --strip-components=1 -C "$DRIVE_DIR/tools/kiwix"
fi

mkdir -p "$DRIVE_DIR/models/ollama" "$DRIVE_DIR/library"

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

# Put xDrive in the desktop application launcher.
"$DRIVE_DIR/scripts/install-desktop.sh" || true

echo
echo "Done. Next steps (while you still have internet):"
echo "  1. Download models:               ./scripts/pull-models.sh"
echo "  2. Download Wikipedia + dev docs: ./scripts/pull-knowledge.sh"
echo "  3. Launch xDrive any time (works offline):"
echo "       ./start.sh"

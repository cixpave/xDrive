#!/usr/bin/env bash
# Register xDrive in the desktop application launcher (Arch / any
# freedesktop-compliant DE: GNOME, KDE, XFCE, Hyprland+rofi, ...).
#
#   ./scripts/install-desktop.sh            install or update the entry
#   ./scripts/install-desktop.sh --remove   uninstall it
#
# The entry points at this drive's absolute path — if you ever mount the
# drive somewhere else, just re-run this script.
set -euo pipefail
cd "$(dirname "$0")/.."
DRIVE_DIR="$(pwd)"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
DESKTOP_FILE="$APPS_DIR/xdrive.desktop"
ICON_FILE="$ICON_DIR/xdrive.svg"

refresh_caches() {
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database "$APPS_DIR" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 &&
        gtk-update-icon-cache -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
}

if [ "${1:-}" = "--remove" ]; then
    rm -f "$DESKTOP_FILE" "$ICON_FILE"
    refresh_caches
    echo "xDrive removed from the application launcher."
    exit 0
fi

mkdir -p "$APPS_DIR" "$ICON_DIR"
cp assets/xdrive.svg "$ICON_FILE"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=xDrive
GenericName=Offline AI Terminal
Comment=Offline AI assistant — code, chat, agent tools, and Wikipedia, 100% local
Exec="$DRIVE_DIR/start.sh" --app
Path=$DRIVE_DIR
Icon=xdrive
Terminal=false
Categories=Development;Utility;
Keywords=AI;LLM;assistant;offline;chat;code;terminal;wikipedia;
StartupNotify=true
EOF

refresh_caches

echo "Installed: $DESKTOP_FILE"
echo "Icon:      $ICON_FILE"
echo
echo "xDrive now appears in your application launcher — search for \"xDrive\"."
echo "(If it doesn't show up immediately, log out and back in once.)"

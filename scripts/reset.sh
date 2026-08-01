#!/usr/bin/env bash
# Wipe xDrive runtime state and start over.
#
#   ./scripts/reset.sh              chats, workspace, settings  (keeps models + books)
#   ./scripts/reset.sh --books      also delete downloaded ZIMs in library/
#   ./scripts/reset.sh --models     also delete model weights in models/
#   ./scripts/reset.sh --everything all of the above — back to a fresh clone
#
# Always stops any running xDrive/kiwix processes first, so nothing holds
# stale state or old code.
set -uo pipefail
cd "$(dirname "$0")/.."

WIPE_BOOKS=0
WIPE_MODELS=0
for arg in "$@"; do
    case "$arg" in
        --books)      WIPE_BOOKS=1 ;;
        --models)     WIPE_MODELS=1 ;;
        --everything) WIPE_BOOKS=1; WIPE_MODELS=1 ;;
        *) echo "unknown option: $arg"; exit 1 ;;
    esac
done

echo "This will delete:"
echo "  · all chat sessions and the agent workspace (data/)"
echo "  · settings (config.json)"
[ "$WIPE_BOOKS"  = "1" ] && echo "  · all downloaded knowledge (library/)"
[ "$WIPE_MODELS" = "1" ] && echo "  · all model weights (models/)"
printf "\nType YES to continue: "
read -r reply
[ "$reply" = "YES" ] || { echo "aborted."; exit 1; }

echo "Stopping xDrive…"
# brackets keep these patterns from matching the shell running them
pkill -f "[x]drive/server.py" 2>/dev/null || true
pkill -f "[k]iwix-serve" 2>/dev/null || true
sleep 1

rm -rf data config.json
[ "$WIPE_BOOKS"  = "1" ] && rm -rf library
[ "$WIPE_MODELS" = "1" ] && rm -rf models

echo
echo "Done — xDrive is back to a clean state."
echo "Launch it again from your application launcher, or run ./start.sh"

#!/usr/bin/env bash
# Download the offline knowledge base to this drive (requires internet ONCE).
#
#   ./scripts/pull-knowledge.sh          core set  (~103 GB: full Wikipedia,
#                                        Arch Wiki, docs for ~17 languages/tools)
#   ./scripts/pull-knowledge.sh --full   adds Stack Overflow, Wiktionary,
#                                        Wikibooks (~+180 GB)
#
# Everything lands in library/ as ZIM files, served locally by kiwix-serve.
# Downloads are resumable — re-run the script if a download is interrupted.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p library

BASE="https://download.kiwix.org/zim"

CORE=(
    # ── all of Wikipedia (English, full text + images) ~102 GB
    "wikipedia/wikipedia_en_all_maxi.zim"
    # ── Arch Wiki ~30 MB
    "other/archlinux_en_all_maxi.zim"
    # ── programming language & tool docs (DevDocs), tens of MB each
    "devdocs/devdocs_en_python.zim"
    "devdocs/devdocs_en_javascript.zim"
    "devdocs/devdocs_en_typescript.zim"
    "devdocs/devdocs_en_node.zim"
    "devdocs/devdocs_en_html.zim"
    "devdocs/devdocs_en_css.zim"
    "devdocs/devdocs_en_c.zim"
    "devdocs/devdocs_en_cpp.zim"
    "devdocs/devdocs_en_rust.zim"
    "devdocs/devdocs_en_go.zim"
    "devdocs/devdocs_en_openjdk.zim"
    "devdocs/devdocs_en_bash.zim"
    "devdocs/devdocs_en_git.zim"
    "devdocs/devdocs_en_docker.zim"
    "devdocs/devdocs_en_postgresql.zim"
    "devdocs/devdocs_en_react.zim"
    "devdocs/devdocs_en_rails.zim"
)

FULL=(
    # ── all of Stack Overflow ~75 GB
    "stack_exchange/stackoverflow.com_en_all.zim"
    # ── English dictionary ~7 GB
    "wiktionary/wiktionary_en_all_nopic.zim"
    # ── textbooks ~4 GB
    "wikibooks/wikibooks_en_all_maxi.zim"
)

LIST=("${CORE[@]}")
if [ "${1:-}" = "--full" ]; then
    LIST+=("${FULL[@]}")
fi

# Kiwix only hosts dated snapshots (name_YYYY-MM.zim), so resolve the
# newest file from the directory listing before downloading.
resolve_latest() {
    local rel="$1" folder stem
    folder="${rel%/*}"
    stem="$(basename "$rel" .zim)"
    curl -sL --max-time 60 "$BASE/$folder/" |
        grep -o "href=\"${stem}_[0-9][0-9][0-9][0-9]-[0-9][0-9]\.zim\"" |
        sed 's/^href="//; s/"$//' | sort | tail -1
}

failed=0
for rel in "${LIST[@]}"; do
    stem="$(basename "$rel" .zim)"
    if ls "library/${stem}"*.zim >/dev/null 2>&1; then
        echo "── $stem already installed — skipping"
        continue
    fi
    echo "── $rel ─────────────────────────────"
    folder="${rel%/*}"
    latest="$(resolve_latest "$rel")"
    if [ -z "$latest" ]; then
        echo "!! could not find $stem on the download server"
        failed=1
        continue
    fi
    # -C - resumes partial downloads if you re-run the script.
    if ! curl -L -C - --fail --retry 3 -o "library/$latest" "$BASE/$folder/$latest"; then
        echo "!! failed: $latest (re-run this script to resume)"
        failed=1
    fi
done

echo
if [ "$failed" = "0" ]; then
    echo "Knowledge base complete: $(du -sh library 2>/dev/null | cut -f1) in library/"
else
    echo "Some downloads failed — re-run this script to resume them."
fi
echo "Restart xDrive (./start.sh) and the knowledge base mounts automatically."

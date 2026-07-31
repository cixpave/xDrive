# Download the offline knowledge base to this drive (requires internet ONCE).
#
#   powershell -ExecutionPolicy Bypass -File scripts\pull-knowledge.ps1
#       core set (~103 GB: full Wikipedia, Arch Wiki, docs for ~17 languages)
#   powershell -ExecutionPolicy Bypass -File scripts\pull-knowledge.ps1 -Full
#       adds Stack Overflow, Wiktionary, Wikibooks (~+180 GB)
#
# Everything lands in library\ as ZIM files, served locally by kiwix-serve.
# Downloads are resumable — re-run the script if a download is interrupted.
param([switch]$Full)

$ErrorActionPreference = "Continue"
$DriveDir = Split-Path -Parent $PSScriptRoot
Set-Location $DriveDir
New-Item -ItemType Directory -Force -Path "library" | Out-Null

$Base = "https://download.kiwix.org/zim"

$Core = @(
    "wikipedia/wikipedia_en_all_maxi.zim",       # all of Wikipedia ~102 GB
    "other/archlinux_en_all_maxi.zim",           # Arch Wiki
    "devdocs/devdocs_en_python.zim",
    "devdocs/devdocs_en_javascript.zim",
    "devdocs/devdocs_en_typescript.zim",
    "devdocs/devdocs_en_node.zim",
    "devdocs/devdocs_en_html.zim",
    "devdocs/devdocs_en_css.zim",
    "devdocs/devdocs_en_c.zim",
    "devdocs/devdocs_en_cpp.zim",
    "devdocs/devdocs_en_rust.zim",
    "devdocs/devdocs_en_go.zim",
    "devdocs/devdocs_en_java.zim",
    "devdocs/devdocs_en_bash.zim",
    "devdocs/devdocs_en_git.zim",
    "devdocs/devdocs_en_docker.zim",
    "devdocs/devdocs_en_postgresql.zim",
    "devdocs/devdocs_en_react.zim",
    "devdocs/devdocs_en_rails.zim"
)

$Extra = @(
    "stack_exchange/stackoverflow.com_en_all.zim",  # all of Stack Overflow ~75 GB
    "wiktionary/wiktionary_en_all_maxi.zim",
    "wikibooks/wikibooks_en_all_maxi.zim"
)

$List = $Core
if ($Full) { $List += $Extra }

$failed = $false
foreach ($rel in $List) {
    $out = Join-Path "library" (Split-Path -Leaf $rel)
    Write-Host "-- $rel -----------------------------"
    # curl.exe ships with Windows 10+; -C - resumes partial downloads.
    curl.exe -L -C - --fail --retry 3 -o $out "$Base/$rel"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!! failed: $rel (re-run this script to resume)"
        $failed = $true
    }
}

Write-Host ""
if (-not $failed) {
    Write-Host "Knowledge base complete in library\"
} else {
    Write-Host "Some downloads failed - re-run this script to resume them."
}
Write-Host "Restart xDrive (start.bat) and the knowledge base mounts automatically."

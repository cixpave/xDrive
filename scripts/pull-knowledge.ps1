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
    "devdocs/devdocs_en_openjdk.zim",
    "devdocs/devdocs_en_bash.zim",
    "devdocs/devdocs_en_git.zim",
    "devdocs/devdocs_en_docker.zim",
    "devdocs/devdocs_en_postgresql.zim",
    "devdocs/devdocs_en_react.zim",
    "devdocs/devdocs_en_rails.zim"
)

$Extra = @(
    "stack_exchange/stackoverflow.com_en_all.zim",  # all of Stack Overflow ~75 GB
    "wiktionary/wiktionary_en_all_nopic.zim",
    "wikibooks/wikibooks_en_all_maxi.zim"
)

$List = $Core
if ($Full) { $List += $Extra }

# Kiwix only hosts dated snapshots (name_YYYY-MM.zim), so resolve the
# newest file from the directory listing before downloading.
function Resolve-Latest($rel) {
    $folder = Split-Path -Parent $rel
    $stem = [IO.Path]::GetFileNameWithoutExtension($rel)
    $listing = curl.exe -sL --max-time 60 "$Base/$folder/"
    $matches = [regex]::Matches($listing, "href=""($([regex]::Escape($stem))_\d{4}-\d{2}\.zim)""")
    if ($matches.Count -eq 0) { return $null }
    return ($matches | ForEach-Object { $_.Groups[1].Value } | Sort-Object)[-1]
}

$failed = $false
foreach ($rel in $List) {
    $stem = [IO.Path]::GetFileNameWithoutExtension($rel)
    if (Get-ChildItem "library" -Filter "$stem*.zim" -ErrorAction SilentlyContinue) {
        Write-Host "-- $stem already installed - skipping"
        continue
    }
    Write-Host "-- $rel -----------------------------"
    $folder = Split-Path -Parent $rel
    $latest = Resolve-Latest $rel
    if (-not $latest) {
        Write-Host "!! could not find $stem on the download server"
        $failed = $true
        continue
    }
    # curl.exe ships with Windows 10+; -C - resumes partial downloads.
    curl.exe -L -C - --fail --retry 3 -o (Join-Path "library" $latest) "$Base/$folder/$latest"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!! failed: $latest (re-run this script to resume)"
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

# One-time setup on Windows (needs internet ONCE; xDrive runs offline after).
# Installs Python + Ollama and points Ollama's model store at this drive.
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1

$ErrorActionPreference = "Stop"
$DriveDir = Split-Path -Parent $PSScriptRoot
Set-Location $DriveDir

Write-Host "-- xDrive setup (Windows) ------------------------------"
Write-Host "Drive location: $DriveDir"

# Python
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Python..."
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
}

# Ollama
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Ollama..."
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
}

# kiwix-serve hosts the offline knowledge base (Wikipedia, dev docs).
if (-not (Test-Path "$DriveDir\tools\kiwix\kiwix-serve.exe")) {
    Write-Host "Fetching kiwix-tools to tools\kiwix\ ..."
    New-Item -ItemType Directory -Force -Path "$DriveDir\tools\kiwix" | Out-Null
    $zip = "$env:TEMP\kiwix-tools.zip"
    curl.exe -L -o $zip "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_win-i686.zip"
    Expand-Archive -Path $zip -DestinationPath "$env:TEMP\kiwix-tools" -Force
    Get-ChildItem "$env:TEMP\kiwix-tools" -Recurse -Filter "*.exe" |
        Copy-Item -Destination "$DriveDir\tools\kiwix" -Force
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
}

# Keep all models on this drive.
New-Item -ItemType Directory -Force -Path "$DriveDir\models\ollama" | Out-Null
New-Item -ItemType Directory -Force -Path "$DriveDir\library" | Out-Null
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "$DriveDir\models\ollama", "User")
$env:OLLAMA_MODELS = "$DriveDir\models\ollama"

Write-Host ""
Write-Host "Done. Next steps (while you still have internet):"
Write-Host "  1. Close and reopen your terminal (so OLLAMA_MODELS takes effect)."
Write-Host "  2. Download models:"
Write-Host "       powershell -ExecutionPolicy Bypass -File scripts\pull-models.ps1"
Write-Host "  3. Download Wikipedia + dev docs:"
Write-Host "       powershell -ExecutionPolicy Bypass -File scripts\pull-knowledge.ps1"
Write-Host "  4. Launch xDrive any time (works offline): double-click start.bat"

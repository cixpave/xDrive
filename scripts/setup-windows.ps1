# One-time setup on Windows (needs internet ONCE; Ember runs offline after).
# Installs Python + Ollama and points Ollama's model store at this drive.
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1

$ErrorActionPreference = "Stop"
$DriveDir = Split-Path -Parent $PSScriptRoot
Set-Location $DriveDir

Write-Host "-- Ember setup (Windows) ------------------------------"
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

# Keep all models on this drive.
New-Item -ItemType Directory -Force -Path "$DriveDir\models\ollama" | Out-Null
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "$DriveDir\models\ollama", "User")
$env:OLLAMA_MODELS = "$DriveDir\models\ollama"

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Close and reopen your terminal (so OLLAMA_MODELS takes effect)."
Write-Host "  2. Download models while you still have internet:"
Write-Host "       powershell -ExecutionPolicy Bypass -File scripts\pull-models.ps1"
Write-Host "  3. Launch Ember any time (works offline): double-click start.bat"

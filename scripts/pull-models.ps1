# Download a recommended model lineup to this drive (requires internet ONCE).
# ~112 GB for the core set; see docs/MODELS.md for the full 5TB plan.
$ErrorActionPreference = "Stop"
$DriveDir = Split-Path -Parent $PSScriptRoot
Set-Location $DriveDir

if (-not $env:OLLAMA_MODELS) { $env:OLLAMA_MODELS = "$DriveDir\models\ollama" }
New-Item -ItemType Directory -Force -Path $env:OLLAMA_MODELS | Out-Null
Write-Host "Models will be stored in: $env:OLLAMA_MODELS"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Error: ollama not installed. Run scripts\setup-windows.ps1 first."
    exit 1
}

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
} catch {
    Start-Process -WindowStyle Minimized ollama serve
    Start-Sleep -Seconds 3
}

$CoreModels = @(
    "qwen2.5-coder:14b",   # daily-driver coding model, 40+ languages (~9 GB)
    "qwen2.5:14b",         # daily-driver general model (~9 GB)
    "deepseek-r1:14b",     # step-by-step reasoning model (~9 GB)
    "qwen2.5-coder:32b",   # heavy coding model (~20 GB)
    "deepseek-r1:32b",     # heavy reasoning model (~20 GB)
    "llama3.3:70b",        # heavy general model (~43 GB)
    "qwen2.5:3b"           # fast lightweight fallback (~2 GB)
)

foreach ($m in $CoreModels) {
    Write-Host "-- pulling $m -----------------------------"
    ollama pull $m
}

Write-Host ""
Write-Host "All core models downloaded. xDrive is now fully offline-capable."
Write-Host "See docs\MODELS.md for optional extras to fill out the 5TB drive."

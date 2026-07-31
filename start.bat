@echo off
rem xDrive launcher — Windows
setlocal
cd /d "%~dp0"

if not defined XDRIVE_PORT set XDRIVE_PORT=8484

rem Find a Python interpreter (py launcher first, then python).
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (
    where python >nul 2>nul && set PY=python
)
if not defined PY (
    echo Error: Python 3 not found. Install it from https://python.org
    echo (or run scripts\setup-windows.ps1 on a machine with internet once).
    pause
    exit /b 1
)

rem Keep Ollama's model store on this drive if present.
if exist "models\ollama" if not defined OLLAMA_MODELS (
    set "OLLAMA_MODELS=%cd%\models\ollama"
)

rem Start Ollama if installed but not running.
where ollama >nul 2>nul
if %errorlevel%==0 (
    curl -sf -m 2 http://127.0.0.1:11434/api/tags >nul 2>nul
    if errorlevel 1 (
        echo Starting Ollama...
        start "" /min ollama serve
        timeout /t 3 /nobreak >nul
    )
)

start "" "http://127.0.0.1:%XDRIVE_PORT%"
%PY% xdrive\server.py
pause

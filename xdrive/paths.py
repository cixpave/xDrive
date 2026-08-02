"""Portable filesystem layout for source and packaged xDrive builds.

The Windows executable treats the directory containing ``xDrive.exe`` as the
drive root.  Runtime files never use the current working directory or a user
profile, so moving the portable folder to another drive keeps all state with
it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def drive_root() -> Path:
    override = os.environ.get("XDRIVE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Return the read-only application resource directory.

    PyInstaller places bundled resources under ``sys._MEIPASS``.  Source
    checkouts keep them beside the Python package.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled).resolve() if bundled else drive_root()


ROOT = drive_root()
RESOURCE_ROOT = resource_root()
WEB_DIR = RESOURCE_ROOT / "web"
ASSETS_DIR = RESOURCE_ROOT / "assets"
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
LIBRARY_DIR = ROOT / "library"
TOOLS_DIR = ROOT / "tools"
RUNTIME_DIR = ROOT / ".xdrive-runtime"


def prepare_portable_environment() -> None:
    """Direct application and child-process writable state to the drive."""
    for path in (DATA_DIR, MODELS_DIR, LIBRARY_DIR, TOOLS_DIR, RUNTIME_DIR):
        path.mkdir(parents=True, exist_ok=True)

    temp = RUNTIME_DIR / "temp"
    profile = RUNTIME_DIR / "profile"
    appdata = profile / "AppData" / "Roaming"
    local_appdata = profile / "AppData" / "Local"
    for path in (temp, profile, appdata, local_appdata):
        path.mkdir(parents=True, exist_ok=True)

    # These values are inherited by Edge, Ollama, Kiwix, and agent commands.
    # They are process-local and do not alter the Windows user's settings.
    portable_vars = {
        "XDRIVE_ROOT": str(ROOT),
        "OLLAMA_MODELS": str(MODELS_DIR / "ollama"),
        "TEMP": str(temp),
        "TMP": str(temp),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local_appdata),
    }
    for key, value in portable_vars.items():
        os.environ[key] = value


def relative_to_drive(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())

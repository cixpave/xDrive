"""Windows helpers for the drive-contained desktop distribution."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

try:
    from xdrive.paths import DATA_DIR, MODELS_DIR, ROOT, RUNTIME_DIR, TOOLS_DIR
except ModuleNotFoundError:  # supports direct execution from xdrive/
    from paths import DATA_DIR, MODELS_DIR, ROOT, RUNTIME_DIR, TOOLS_DIR  # type: ignore


OLLAMA_WINDOWS_URL = os.environ.get(
    "XDRIVE_OLLAMA_URL",
    "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip",
)
KIWIX_WINDOWS_URL = os.environ.get(
    "XDRIVE_KIWIX_URL",
    "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_win-i686.zip",
)
PORTABLE_OLLAMA_HOST = "127.0.0.1:11435"
PORTABLE_OLLAMA_URL = f"http://{PORTABLE_OLLAMA_HOST}"


def portable_ollama_binary() -> Path:
    return TOOLS_DIR / "ollama" / "ollama.exe"


def portable_kiwix_binary() -> Path:
    return TOOLS_DIR / "kiwix" / "kiwix-serve.exe"


def ollama_binary() -> str | None:
    portable = portable_ollama_binary()
    if portable.is_file():
        return str(portable)
    # Keep existing source-checkout behavior on Linux/macOS.  Packaged Windows
    # builds deliberately avoid a profile-installed runtime because it may
    # place models and logs outside the portable drive.
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return shutil.which("ollama")
    return None


def start_ollama() -> subprocess.Popen | None:
    binary = ollama_binary()
    if not binary:
        return None
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = str(MODELS_DIR / "ollama")
    env["OLLAMA_HOST"] = PORTABLE_OLLAMA_HOST
    (MODELS_DIR / "ollama").mkdir(parents=True, exist_ok=True)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(
            [binary, "serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except OSError:
        return None


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for info in archive.infolist():
        target = (destination / info.filename).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe archive path: {info.filename}")
    archive.extractall(destination)


def install_portable_ollama(
    progress: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Download and unpack Ollama beside xDrive.exe.

    ``progress`` receives downloaded bytes, total bytes, and a short status.
    The partial download remains on the drive and is replaced atomically.
    """
    destination = TOOLS_DIR / "ollama"
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = RUNTIME_DIR / "ollama-windows-amd64.zip.part"

    request = urllib.request.Request(
        OLLAMA_WINDOWS_URL,
        headers={"User-Agent": "xDrive-portable"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with archive_path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total, "downloading portable Ollama")

    if progress:
        progress(done, total, "unpacking portable Ollama")
    with zipfile.ZipFile(archive_path) as archive:
        _safe_extract(archive, destination)
    archive_path.unlink(missing_ok=True)

    binary = portable_ollama_binary()
    if not binary.is_file():
        # Some release archives contain one top-level directory.
        candidates = list(destination.rglob("ollama.exe"))
        if not candidates:
            raise FileNotFoundError("ollama.exe was not found in the downloaded archive")
        source_root = candidates[0].parent
        for item in source_root.iterdir():
            target = destination / item.name
            if item.resolve() == target.resolve():
                continue
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
    return binary


def install_portable_kiwix(
    progress: Callable[[int, int, str], None] | None = None,
) -> Path:
    destination = TOOLS_DIR / "kiwix"
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = RUNTIME_DIR / "kiwix-tools.zip.part"
    request = urllib.request.Request(
        KIWIX_WINDOWS_URL,
        headers={"User-Agent": "xDrive-portable"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with archive_path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total, "downloading offline knowledge reader")
    if progress:
        progress(done, total, "unpacking offline knowledge reader")
    with zipfile.ZipFile(archive_path) as archive:
        _safe_extract(archive, destination)
    archive_path.unlink(missing_ok=True)

    binary = portable_kiwix_binary()
    if not binary.is_file():
        candidates = list(destination.rglob("kiwix-serve.exe"))
        if not candidates:
            raise FileNotFoundError("kiwix-serve.exe was not found in the downloaded archive")
        source_root = candidates[0].parent
        for item in source_root.iterdir():
            target = destination / item.name
            if item.resolve() == target.resolve():
                continue
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
    return binary


def find_edge() -> Path | None:
    candidates = []
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(key)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    # Windows 11 includes Edge.  This final lookup also supports managed PCs
    # where the executable is exposed through PATH.
    found = shutil.which("msedge")
    if found:
        candidates.append(Path(found))
    return next((path for path in candidates if path.is_file()), None)


def launch_edge_app(url: str) -> subprocess.Popen:
    edge = find_edge()
    if edge is None:
        raise FileNotFoundError("Microsoft Edge is required on Windows 11")
    profile = DATA_DIR / "edge-profile"
    cache = DATA_DIR / "edge-cache"
    profile.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(edge),
            f"--app={url}",
            f"--user-data-dir={profile}",
            f"--disk-cache-dir={cache}",
            "--no-first-run",
            "--disable-sync",
            "--disable-background-mode",
            "--disable-component-update",
        ],
        cwd=ROOT,
    )

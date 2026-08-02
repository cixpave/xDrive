"""Windows 11 entry point for the portable xDrive executable."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
import urllib.error
import urllib.request

try:
    from xdrive.paths import ROOT, prepare_portable_environment
    from xdrive.portable_runtime import launch_edge_app
    from xdrive import server
except ModuleNotFoundError:  # supports ``python xdrive/desktop.py``
    from paths import ROOT, prepare_portable_environment  # type: ignore
    from portable_runtime import launch_edge_app  # type: ignore
    import server  # type: ignore


def message_box(message: str, title: str = "xDrive") -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    else:
        print(f"{title}: {message}", file=sys.stderr)


def wait_for_server(url: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/setup", timeout=1) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.2)
    return False


def main() -> int:
    prepare_portable_environment()
    cfg = server.load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8484))
    url = f"http://{host}:{port}"

    thread = threading.Thread(target=server.main, name="xdrive-server", daemon=True)
    thread.start()
    if not wait_for_server(url):
        message_box(
            f"xDrive could not start its local service on port {port}.\n\n"
            f"Close any other xDrive window and try again.\n"
            f"Portable drive: {ROOT}"
        )
        return 1

    try:
        window = launch_edge_app(url)
    except OSError as exc:
        message_box(
            "xDrive needs Microsoft Edge, which is included with Windows 11.\n\n"
            f"Details: {exc}"
        )
        return 1

    try:
        return window.wait()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""xDrive native desktop window (GTK + WebKitGTK — no Chromium needed).

Opens the locally served UI in a real application window. Requires the
system packages `python-gobject`, `gtk3`, and `webkit2gtk-4.1` (or the
older `webkit2gtk`) — installed by scripts/setup-arch.sh.

Exit code 2 means the GTK/WebKit stack is unavailable, which the launcher
uses to fall back to a browser window.
"""

import signal
import sys
from pathlib import Path

try:
    import gi

    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("WebKit2", "4.1")
    except ValueError:
        gi.require_version("WebKit2", "4.0")
    from gi.repository import Gtk, WebKit2
except (ImportError, ValueError) as exc:
    sys.stderr.write(f"[xDrive] native window unavailable: {exc}\n")
    sys.exit(2)

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8484"
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def main():
    window = Gtk.Window(title="xDrive — Offline AI Terminal")
    window.set_default_size(1440, 900)
    icon = ASSETS / "xdrive.svg"
    if icon.exists():
        try:
            window.set_icon_from_file(str(icon))
        except Exception:  # noqa: BLE001 — missing SVG pixbuf loader is fine
            pass

    settings = WebKit2.Settings()
    settings.set_enable_developer_extras(True)   # right-click → inspect
    settings.set_enable_write_console_messages_to_stdout(False)
    view = WebKit2.WebView.new_with_settings(settings)
    view.load_uri(URL)

    # keep target=_blank links (kiwix reader, article links) working by
    # opening them in the default browser instead of a dead-end subview
    def on_create(_view, nav_action, *_args):
        uri = nav_action.get_request().get_uri()
        Gtk.show_uri_on_window(window, uri, 0)
        return None

    view.connect("create", on_create)

    window.add(view)
    window.connect("destroy", Gtk.main_quit)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

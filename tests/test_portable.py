import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from xdrive import paths, portable_runtime, server


class PortablePathsTests(unittest.TestCase):
    def test_environment_override_selects_drive_root(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {"XDRIVE_ROOT": temp}):
                self.assertEqual(paths.drive_root(), Path(temp).resolve())

    def test_archive_extraction_rejects_drive_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            memory = io.BytesIO()
            with zipfile.ZipFile(memory, "w") as archive:
                archive.writestr("../outside.txt", "no")
            memory.seek(0)
            with zipfile.ZipFile(memory) as archive:
                with self.assertRaises(ValueError):
                    portable_runtime._safe_extract(archive, Path(temp))


class SetupRoutingTests(unittest.TestCase):
    def _get_root(self, complete):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.json"
            config.write_text(json.dumps({"setup_complete": complete}), encoding="utf-8")
            with mock.patch.object(server, "CONFIG_PATH", config):
                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    port = httpd.server_address[1]
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
                        return response.read().decode("utf-8")
                finally:
                    httpd.shutdown()
                    httpd.server_close()

    def test_first_launch_serves_setup_landing_page(self):
        self.assertIn("PORTABLE WINDOWS 11 SETUP", self._get_root(False))

    def test_completed_setup_serves_terminal(self):
        self.assertIn("Offline AI Terminal", self._get_root(True))


if __name__ == "__main__":
    unittest.main()

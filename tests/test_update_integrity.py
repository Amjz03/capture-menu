"""Offline updater regression tests. Never launch an executable or use the network."""
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
from PySide6 import QtWidgets
from capturemenu import updates, version, windows

DATA = b"disposable installer fixture, not an executable"
DIGEST = "sha256:" + hashlib.sha256(DATA).hexdigest()
URL = f"https://github.com/{version.REPO}/releases/download/v9.9.9/CaptureMenu-Setup.exe"


class Response(io.BytesIO):
    def geturl(self):
        return URL


def fails(call):
    try:
        call()
    except (ValueError, RuntimeError, OSError):
        return
    raise AssertionError("unsafe operation was accepted")


with tempfile.TemporaryDirectory() as folder:
    out = Path(folder) / "Setup.exe"
    def download(data=DATA, size=len(DATA), digest=DIGEST, url=URL, progress=None):
        with patch("urllib.request.urlopen", return_value=Response(data)):
            updates.download_update(url, size, out, progress, digest=digest)

    progress = []
    download(progress=progress.append)
    assert out.read_bytes() == DATA and progress == [99]
    assert list(Path(folder).glob("*.part")) == []
    print("verified download PASS")

    # A stale destination is never promoted as the result of a failed download.
    for data in (DATA[:-1], DATA + b"x", b"X" * len(DATA)):
        out.write_bytes(b"old")
        fails(lambda: download(data=data))
        assert out.read_bytes() == b"old" and not list(Path(folder).glob("*.part"))
    for digest in (None, "", "sha256:abc", "md5:" + "0" * 64, "sha256:" + "g" * 64):
        with patch("urllib.request.urlopen") as network:
            fails(lambda: updates.download_update(URL, len(DATA), out, digest=digest))
            network.assert_not_called()
    for size in (0, -1, None, True, "5"):
        fails(lambda: download(size=size))
    for url in (URL.replace("https:", "http:"), URL.replace("github.com", "evil.example"),
                URL.replace(version.REPO, "other/repo"), "file:///tmp/setup.exe"):
        fails(lambda: download(url=url))
    print("length, digest and source validation PASS")

    class Interrupted(Response):
        def read(self, n):
            if self.tell():
                raise OSError("connection interrupted")
            return super().read(3)
    with patch("urllib.request.urlopen", return_value=Interrupted(DATA)):
        fails(lambda: updates.download_update(URL, len(DATA), out, digest=DIGEST))
    def broken_progress(pct):
        raise RuntimeError("callback failed")
    fails(lambda: download(progress=broken_progress))
    with patch("os.replace", side_effect=OSError("destination locked")):
        fails(download)
    with patch.object(Response, "geturl", return_value="http://example.com/Setup.exe"):
        fails(download)
    assert not list(Path(folder).glob("*.part")) and out.read_bytes() == b"old"
    print("failed download cleanup PASS")

    with patch.object(windows, "launch_outside") as launch, patch.object(QtWidgets.QApplication, "quit") as quit_app:
        out.write_bytes(b"X" * len(DATA))
        fails(lambda: updates.run_update_installer(out, size=len(DATA), digest=DIGEST))
        launch.assert_not_called(); quit_app.assert_not_called()
        out.write_bytes(DATA)
        launch.side_effect = OSError("launch refused")
        fails(lambda: updates.run_update_installer(out, size=len(DATA), digest=DIGEST))
        quit_app.assert_not_called()
        launch.side_effect = None
        updates.run_update_installer(out, size=len(DATA), digest=DIGEST)
        quit_app.assert_called_once()
    print("prelaunch verification and launch failure PASS (launch mocked)")

    payload = {"tag_name": "v9.9.9", "assets": [{"name": "CaptureMenu-Setup.exe",
               "browser_download_url": URL, "size": len(DATA), "digest": DIGEST}]}
    with patch("urllib.request.urlopen", return_value=Response(json.dumps(payload).encode())):
        assert updates.latest_release()["digest"] == DIGEST
    del payload["assets"][0]["digest"]
    with patch("urllib.request.urlopen", return_value=Response(json.dumps(payload).encode())):
        assert updates.latest_release()["digest"] is None
    print("release digest metadata PASS")

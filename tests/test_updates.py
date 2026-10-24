# Updates happen only when asked: Settings -> Updates checks GitHub, a second press downloads Setup.exe
# and hands it to the installer. Usage: test_updates.py REPO [--online]   (--online also asks GitHub for real)
import sys, tempfile, time, hashlib
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, preferences, runtime, ui_settings, updates, version
from PySide6 import QtWidgets
app = QtWidgets.QApplication([])
repo = Path(sys.argv[1])

assert version.APP_VERSION == (repo / "VERSION").read_text().strip().lstrip("v"), "APP_VERSION and VERSION differ"
assert updates.version_tuple("v0.0.10") > updates.version_tuple("0.0.9") > updates.version_tuple("0.0.3")
print("version PASS")

root = Path(tempfile.mkdtemp())
preferences.STATE_PATH = root / "state.json"
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root / "Clips")))
s = ui_settings.Settings(ctl)
s.restart = lambda: None
installed = []
s.install = lambda path, **kwargs: installed.append(path)


def wait(state, seconds=10):
    end = time.time() + seconds
    while s.update["state"] != state and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    assert s.update["state"] == state, s.update


s.open((1920, 1080))
assert "_update" not in s.values() and not s.changes()          # not a setting, never "unsaved"
assert s.update_row.text() == f"Version {version.APP_VERSION}"

# nothing newer
updates.latest_release = lambda timeout=10: {"version": version.APP_VERSION, "page": "p", "url": "u", "size": 3}
s.update_row.activate()
wait("latest")
assert s.update_row.text() == "Up to date" and not installed

# a newer version: the first press only says so, the second downloads and installs
release = {"version": "9.9.9", "page": "p", "url": "https://x/Setup.exe", "size": 5,
           "digest": "sha256:" + hashlib.sha256(b"setup").hexdigest()}
updates.latest_release = lambda timeout=10: dict(release)
s.update = {"state": "idle"}
s.update_row.activate()
wait("available")
assert s.update_row.text() == "Version 9.9.9 is available" and not installed


def fake_download(url, size, out, on_progress=None, *, digest):
    for pct in (10, 60, 99):
        on_progress(pct)
    out.write_bytes(b"setup")


updates.download_update = fake_download
runtime.FROZEN = True            # the installed app; the Python version opens the download page instead
s.update_row.activate()
wait("ready")
assert installed and installed[0].name == "CaptureMenu-Setup.exe" and installed[0].read_bytes() == b"setup"

# Missing integrity metadata never reaches a downloader or the installer.
s.update = dict(release, state="available", digest=None)
with patch.object(updates, "download_update") as download:
    s.update_row.activate()
    wait("error")
    download.assert_not_called()
assert len(installed) == 1

# Download and launch failures leave the UI retryable, without stale installers.
with patch.object(updates, "download_update", side_effect=OSError("interrupted")):
    s.update = dict(release, state="available")
    s.update_row.activate()
    wait("error")
assert len(installed) == 1
def launch_failed(path, **kwargs):
    raise OSError("launch refused")
s.install = launch_failed
s.update = dict(release, state="available")
s.update_row.activate()
wait("error")
assert len(installed) == 1
installed[0].unlink(); installed[0].parent.rmdir()
print("missing digest and update failure UI PASS")

# no internet
def offline(timeout=10):
    raise OSError("no network")


updates.latest_release = offline
s.update = {"state": "idle"}
s.update_row.activate()
wait("error")
assert "try again" in s._update_describe()
print("updates flow PASS")

if "--online" in sys.argv:
    import importlib
    real = importlib.reload(updates)
    rel = real.latest_release()
    assert updates.version_tuple(rel["version"]) >= (0, 0, 1) and rel["url"].endswith("CaptureMenu-Setup.exe") and rel["size"] > 10e6, rel
    print(f"github PASS: latest {rel['version']}, {rel['size'] / 1e6:.0f} MB")

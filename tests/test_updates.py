# Updates happen only when asked: Settings -> Updates checks GitHub, a second press downloads Setup.exe
# and hands it to the installer. Usage: test_updates.py REPO [--online]   (--online also asks GitHub for real)
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets
app = QtWidgets.QApplication([])
repo = Path(sys.argv[1])

assert cm.APP_VERSION == (repo / "VERSION").read_text().strip().lstrip("v"), "APP_VERSION and VERSION differ"
assert cm.version_tuple("v0.0.10") > cm.version_tuple("0.0.9") > cm.version_tuple("0.0.3")
print("version PASS")

root = Path(tempfile.mkdtemp())
cm.STATE_PATH = root / "state.json"
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root / "Clips")))
s = cm.Settings(ctl)
s.restart = lambda: None
installed = []
s.install = installed.append


def wait(state, seconds=10):
    end = time.time() + seconds
    while s.update["state"] != state and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    assert s.update["state"] == state, s.update


s.open((1920, 1080))
assert "_update" not in s.values() and not s.changes()          # not a setting, never "unsaved"
assert s.update_row.text() == f"Version {cm.APP_VERSION}"

# nothing newer
cm.latest_release = lambda timeout=10: {"version": cm.APP_VERSION, "page": "p", "url": "u", "size": 3}
s.update_row.activate()
wait("latest")
assert s.update_row.text() == "Up to date" and not installed

# a newer version: the first press only says so, the second downloads and installs
cm.latest_release = lambda timeout=10: {"version": "9.9.9", "page": "p", "url": "https://x/Setup.exe", "size": 5}
s.update = {"state": "idle"}
s.update_row.activate()
wait("available")
assert s.update_row.text() == "Version 9.9.9 is available" and not installed


def fake_download(url, size, out, on_progress=None):
    for pct in (10, 60, 99):
        on_progress(pct)
    out.write_bytes(b"setup")


cm.download_update = fake_download
cm.FROZEN = True            # the installed app; the Python version opens the download page instead
s.update_row.activate()
wait("ready")
assert installed and installed[0].name == "CaptureMenu-Setup-9.9.9.exe" and installed[0].read_bytes() == b"setup"

# no internet
def offline(timeout=10):
    raise OSError("no network")


cm.latest_release = offline
s.update = {"state": "idle"}
s.update_row.activate()
wait("error")
assert "try again" in s._update_describe()
print("updates flow PASS")

if "--online" in sys.argv:
    import importlib
    real = importlib.reload(cm)
    rel = real.latest_release()
    assert real.version_tuple(rel["version"]) >= (0, 0, 1) and rel["url"].endswith("CaptureMenu-Setup.exe") and rel["size"] > 10e6, rel
    print(f"github PASS: latest {rel['version']}, {rel['size'] / 1e6:.0f} MB")

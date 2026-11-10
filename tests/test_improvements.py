"""The review fixes: a save is never turned away by a trim, a broken config.json never stops the app,
many captures delete with one write, work in progress is finished before a restart, an old clips folder
stays in the gallery, and a recording left running says so."""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore, QtWidgets
from capturemenu import capture_controller, input_devices, preferences

app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
preferences.CONFIG_PATH = tmp / "config.json"
preferences.STATE_PATH = tmp / "state.json"


def wait(cond, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


made = []


def controller(**cfg):
    with patch.object(capture_controller.Controller, "_remake_hdr_thumbs"):
        ctl = capture_controller.Controller(dict(preferences.DEFAULTS, **{"clips_dir": str(tmp / "Clips"), **cfg}))
    ctl.check_storage = lambda: None
    made.append(ctl)        # kept: its worker threads may still be letting go of it
    return ctl


# ---- 1) a trim or sound change that's running never turns a save away (and the other way round)
ctl = controller()
notices = []
ctl.toast.connect(lambda text, kind: notices.append((text, kind)))
saved, release = [], threading.Event()
ctl._save_clip = lambda seconds, game: saved.append((seconds, game))
ctl._trim = lambda *a: release.wait(5)
ctl.trim(tmp / "a.mp4", 0, 1000, False)
assert wait(ctl._edits.locked) and ctl.working()
ctl.save_clip(30, "Game")
assert wait(lambda: saved == [(30, "Game")]), "the save ran while the trim was still going"
failed = []
ctl.job_failed.connect(failed.append)
ctl.trim(tmp / "b.mp4", 0, 1000, False)          # a second trim waits its turn, and says which
assert wait(lambda: failed == [str(tmp / "b.mp4")]) and "trim or sound change" in notices[-1][0], notices
release.set()
assert wait(lambda: not ctl.working())
print("a save during a trim PASS")

# ---- 2) when_idle: work being written is finished before a restart or Quit
gate, ran = threading.Event(), []
ctl._share = lambda *a: gate.wait(5)
ctl.share(tmp / "a.mp4", "phone", False)
assert wait(ctl.working)
ctl.when_idle(lambda: ran.append(1), "wait for it")
app.processEvents()
assert ran == [] and notices[-1] == ("wait for it", "info"), "not while a copy is being made"
gate.set()
assert wait(lambda: ran == [1])
ctl.when_idle(lambda: ran.append(2))
assert ran == [1, 2], "nothing running: at once"
print("restart and Quit wait for work in progress PASS")

# ---- 3) config.json: a typo, a wrong kind of value or odd keys never stop the app
preferences.CONFIG_PATH.write_text('{"obs_password": "se\\"cret", "obs_port": 4460, "fps": 120,}')   # trailing comma
cfg = preferences.load_config()
assert preferences.CONFIG_PROBLEM == "unreadable" and cfg["fps"] == 60
assert cfg["obs_password"] == 'se"cret' and cfg["obs_port"] == 4460, "OBS is still reachable"
assert (tmp / "config.broken.json").exists(), "the file as it was is kept"
preferences.save_config({"fps": 30})
assert json.loads(preferences.CONFIG_PATH.read_text()) == {"obs_password": 'se"cret', "obs_port": 4460, "fps": 30}
preferences.CONFIG_PATH.write_text(json.dumps({"fps": "fast", "buffer_minutes": "45", "durations_seconds": "x",
                                               "sounds": "yes", "hotkey": "alt+", "library_dirs": ["D:/Old"]}))
cfg = preferences.load_config()
assert sorted(preferences.CONFIG_PROBLEM) == ["durations_seconds", "fps", "sounds"], preferences.CONFIG_PROBLEM
assert cfg["fps"] == 60 and cfg["buffer_minutes"] == 45 and cfg["sounds"] is True and cfg["library_dirs"] == ["D:/Old"]
assert cfg["durations_seconds"] == preferences.DEFAULTS["durations_seconds"]
assert not input_devices.Hotkey(cfg["hotkey"], lambda: "").valid() and input_devices.Hotkey("ctrl+f9", lambda: "").valid()
preferences.CONFIG_PATH.write_text(json.dumps({"fps": 120}))
assert preferences.load_config()["fps"] == 120 and preferences.CONFIG_PROBLEM is None
print("a broken config.json PASS")

# ---- 4) many captures: one write of state.json and one library_changed, not one per capture
ctl = controller()
files = [ctl.clips_dir / "Game" / f"Clip_{i}.mp4" for i in range(6)]
files[0].parent.mkdir(parents=True, exist_ok=True)
for f in files:
    f.write_bytes(b"x")
    ctl.toggle_favorite(f)
    ctl.set_meta(f, f"title {f.stem}", "")
ctl.recent = list(files)
changes, writes = [], []
ctl.library_changed.connect(lambda: changes.append(1))
real_write = preferences._write_state
with patch.object(preferences, "_write_state", side_effect=lambda s: (writes.append(1), real_write(s))), \
     patch.object(QtCore.QFile, "moveToTrash", side_effect=lambda p: (Path(p).unlink(), (True, ""))[1]):
    assert ctl.delete_many(files[:5]) == (5, 5)
app.processEvents()
assert len(writes) == 1 and len(changes) == 1, (writes, changes)
state = preferences.load_state()
assert state["favorites"] == [str(Path("Game") / "Clip_5.mp4")] and list(state["meta"]) == state["favorites"]
assert ctl.recent == files[5:]
print("deleting many captures PASS")

# ---- 5) a new clips folder: the old one stays in the gallery, favorites and titles with it
old, new = ctl.clips_dir, tmp / "Other drive" / "Clips"
moved_in = new / "Game" / "Clip_new.mp4"
moved_in.parent.mkdir(parents=True)
moved_in.write_bytes(b"x")
preferences.rekey_library(old, new)
state = preferences.load_state()
assert state["favorites"] == [str(files[5])] and list(state["meta"]) == [str(files[5])], state
ctl2 = controller(clips_dir=str(new), library_dirs=[str(old), str(tmp / "unplugged drive")])
assert ctl2.roots == [new, old], ctl2.roots
assert set(ctl2.all_captures()) == {files[5], moved_in}
assert ctl2.is_favorite(files[5]) and ctl2.title_of(files[5]) == "title Clip_5" and not ctl2.is_favorite(moved_in)
preferences.rekey_library(new, old)            # and back again: the same keys as before
assert preferences.load_state()["favorites"] == [str(Path("Game") / "Clip_5.mp4")]
print("the old clips folder stays in the gallery PASS")

# ---- 6) a recording left running says so every half hour
ctl = controller()
notices = []
ctl.toast.connect(lambda text, kind: notices.append((text, kind)))
preferences.update_state(lambda s: s.update(recording={"since": time.time() - 10 * 60, "game": "Game"}))
ctl._remind_recording()
assert notices == [], "not in the first half hour"
preferences.update_state(lambda s: s.update(recording={"since": time.time() - 31 * 60, "game": "Game"}))
ctl._remind_recording(); ctl._remind_recording()
assert len(notices) == 1 and notices[0][1] == "rec" and "31:00" in notices[0][0], notices
preferences.update_state(lambda s: s.update(recording={"since": time.time() - 61 * 60, "game": "Game"}))
ctl._remind_recording()
assert len(notices) == 2
preferences.update_state(lambda s: s.pop("recording"))
ctl._remind_recording()
assert ctl._reminded == 0
print("a long recording reminds PASS")

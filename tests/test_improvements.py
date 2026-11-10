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

# ---- 7) shortcuts go by the key, not by what the keyboard layout types with it
from PySide6 import QtGui
from PySide6.QtCore import Qt
from capturemenu import ui_gallery, ui_menu, ui_settings, ui_viewer


def press(key, vk=0, mods=Qt.NoModifier):
    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, mods, 0, vk, 0)


arabic_s, arabic_bracket = 0x0633, 0x062C          # what the S and [ keys type on an Arabic layout
assert input_devices.latin_key(press(arabic_s, 0x53), on_windows=True) == Qt.Key_S
assert input_devices.latin_key(press(arabic_bracket, 0xDB), on_windows=True) == Qt.Key_BracketLeft
assert input_devices.latin_key(press(0x0648, 0xBC), on_windows=True) == Qt.Key_Comma
assert input_devices.latin_key(press(Qt.Key_T, 0x54), on_windows=True) == Qt.Key_T
assert input_devices.latin_key(press(Qt.Key_Left, 0x25), on_windows=True) == Qt.Key_Left
assert input_devices.latin_key(press(arabic_s), on_windows=True) == arabic_s, "the controller's keys have no code"
print("keys in any keyboard layout PASS")

# ---- 8) Settings: a click on a row's name doesn't change it; small settings save without a restart;
#         the extra shortcuts can be set, can't repeat another one, and Backspace turns them off
preferences.CONFIG_PATH.write_text(json.dumps({"hotkey": "alt+c"}))
ctl = controller()
ctl.cfg.update(preferences.load_config(), clips_dir=str(tmp / "Clips"))
s = ui_settings.Settings(ctl); s.encoder = "nvenc_av1"
restarts, applied = [], []
s.restart = lambda: restarts.append(1)
s.applied.connect(applied.append)
s.resize(1000, 900)
s.open((2560, 1440)); app.processEvents()
rows = {r.key: r for r in s.rows}
fps = rows["fps"]


def click(row, x):
    pos = QtCore.QPointF(x, row.height() / 2)
    QtWidgets.QApplication.sendEvent(row, QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, pos, row.mapToGlobal(pos),
                                                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


click(fps, 60)
assert fps.value == 60, "a click on the name leaves the value alone"
click(fps, fps._value_rect().center().x())
assert fps.value == 120, "the value changes it"
fps.set_value(60, emit=True)
rows["sounds"].activate(); rows["storage_warn_gb"].step(1)
s.save()
assert restarts == [] and not s.isVisible() and applied == [{"sounds": False, "storage_warn_gb": 500}], applied
assert json.loads(preferences.CONFIG_PATH.read_text())["sounds"] is False and ctl.cfg["sounds"] is False
s.open((2560, 1440)); app.processEvents()
shot = rows["hotkey_screenshot"]
assert shot.text() == "Off"
shot.setFocus(); shot.activate(); assert shot.listening
QtWidgets.QApplication.sendEvent(shot, press(Qt.Key_C, 0x43, Qt.AltModifier))
assert shot.listening and shot.value == "", "Alt + C opens the menu already"
QtWidgets.QApplication.sendEvent(shot, press(Qt.Key_F10, 0x79, Qt.ControlModifier))
assert not shot.listening and shot.value == "ctrl+f10" and shot.text() == "Ctrl + F10", shot.text()
shot.activate(); QtWidgets.QApplication.sendEvent(shot, press(Qt.Key_Backspace))
assert not shot.listening and shot.value == ""
main_key = rows["hotkey"]; main_key.setFocus(); main_key.activate()
QtWidgets.QApplication.sendEvent(main_key, press(Qt.Key_Backspace))
assert main_key.listening and main_key.value == "alt+c", "the menu's own shortcut can't be turned off"
s.close_settings()
print("settings: clicks, no restart, extra shortcuts PASS")

# ---- 9) trimming: the controller steps a frame and a second; the bar and the gallery
viewer = ui_viewer.Viewer(ctl)
menu = ui_menu.Menu(ctl, viewer)
viewer.show(); viewer.trimming = True
keys = {b: input_devices.pad_key(b, menu, viewer) for b in (input_devices.L1, input_devices.R1, input_devices.UP,
                                                             input_devices.DOWN, 6)}
assert list(keys.values()) == [Qt.Key_Comma, Qt.Key_Period, Qt.Key_Up, Qt.Key_Down, Qt.Key_P], keys
viewer.trimming = False; viewer.hide()
shots = []
ctl.screenshot = lambda game: shots.append(game)
menu.shoot("Elden Ring")
assert wait(lambda: shots == ["Elden Ring"]), "the screenshot shortcut takes the shot for the game in front"

gallery = ui_gallery.Gallery(ctl, viewer)
only = ctl.clips_dir / "Game" / "Screenshot_only.png"
only.parent.mkdir(parents=True, exist_ok=True); only.write_bytes(b"x")
gallery.resize(1600, 900); gallery.open(); app.processEvents()
assert gallery.items and not gallery.marked
gallery.grid.setFocus(); gallery.delete_marked()
assert gallery.marked == {gallery.items[0]} and gallery.del_btn.property("danger"), "Del picks the capture and asks"
gallery.close_gallery()
print("trim steps, screenshot shortcut, Del in the gallery PASS")

# ---- 10) the gallery: search, "Show", sizes from one walk of the folders
ctl = controller()
game = ctl.clips_dir / "Elden Ring"
game.mkdir(parents=True, exist_ok=True)
boss, shot, rec = game / "Clip_2026-01-01_10-00-00_30s.mp4", game / "Screenshot_2026-01-01.png", game / "Recording_2026.mp4"
for f, size in ((boss, 3000), (shot, 2000), (rec, 1000)):
    f.write_bytes(b"x" * size)
ctl.set_meta(boss, "Boss down", "first try")
assert set(ctl.all_captures()) >= {boss, shot, rec} and ctl.size_of(boss) == 3000 and ctl.modified_of(shot) > 0
assert not any(".thumbs" in p.parts or "Shared" in p.parts for p in ctl.all_captures())
with patch.object(Path, "stat", side_effect=AssertionError("the walk already knows the sizes")):
    assert ctl.size_of(rec) == 1000
gallery = ui_gallery.Gallery(ctl, ui_viewer.Viewer(ctl))
gallery.resize(1600, 900); gallery.open("Elden Ring"); app.processEvents()
assert set(gallery.items) == {boss, shot, rec}
gallery.search.setText("boss"); assert gallery.items == [boss], "by title"
gallery.search.setText("FIRST try"); assert gallery.items == [boss], "by note, any case"
gallery.search.setText("elden screenshot"); assert gallery.items == [shot], "game and file name, every word"
gallery.search.setText("nothing like it"); assert gallery.items == [] and "0" in gallery.info.text()
gallery.search.setText("")
seen = []
for _ in range(4):
    gallery.next_kind(); seen.append((gallery.kind, set(gallery.items)))
assert seen == [("clips", {boss}), ("shots", {shot}), ("recordings", {rec}), ("all", {boss, shot, rec})], seen
gallery.search.setText("boss"); gallery.close_gallery(); assert gallery.search.text() == ""
print("gallery search and Show PASS")

# ---- 11) notices: an error isn't covered by a smaller notice, and the bar says it again once
from capturemenu import ui_notices
toast = ui_notices.Toast()
toast.ERROR_MS = 400
toast.show_message("OBS can't start recording · open OBS to see why", "error")
toast.show_message("Controller connected · DualSense", "ok")
assert "OBS can't start recording" in toast.title.text(), "the error stays"
assert wait(lambda: "Controller connected" in toast.title.text(), 3), "the smaller notice follows it"
menu = ui_menu.Menu(ctl, ui_viewer.Viewer(ctl))
menu.note_problem("Saved", "ok"); menu._show_problem(); assert menu.problem_label.isHidden()
menu.note_problem("OBS can't start recording · open OBS to see why", "error")
menu.show_menu("Game"); app.processEvents()
assert not menu.problem_label.isHidden() and "OBS can't start recording" in menu.problem_label.text()
menu.hide_menu(); menu.show_menu("Game"); app.processEvents()
assert menu.problem_label.isHidden(), "said once"
menu.hide_menu()
print("errors stay and are repeated in the bar PASS")

# ---- 12) the low-space notice follows its setting, once a day
ctl = controller(low_space_gb=0)
notices = []
ctl.toast.connect(lambda text, kind: notices.append(text))
del ctl.check_storage                      # the real one
with patch("shutil.disk_usage", return_value=type("U", (), {"free": 3 * 1024 ** 3})()):
    ctl.check_storage(); assert wait(lambda: ctl.last_storage) and ctl.last_storage["low"] is False and notices == []
    ctl.cfg["low_space_gb"] = 20
    ctl.check_storage(); assert wait(lambda: ctl.last_storage["low"] and len(notices) == 1), notices
    again = controller(low_space_gb=20); del again.check_storage
    again.toast.connect(lambda text, kind: notices.append(text))
    again.check_storage(); assert wait(lambda: again.last_storage.get("low")) and len(notices) == 1, "once a day"
print("low-space warning PASS")

# ---- 13) a long explanation gets a second line instead of being cut
from capturemenu import ui_widgets
row = ui_widgets.SettingRow("x", "Name", "bool", describe=lambda v: "short" if v else "a very long explanation " * 8)
row.resize(700, row.H); row.set_value(True); assert row.height() == row.H
row.set_value(False); assert row.height() > row.H
print("two-line explanations PASS")

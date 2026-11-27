"""Save recent: a clip moved earlier ends where it was asked to (not at the save), the pictures of the last minutes
are made once per finished file and kept, and a preview picture comes from the file that holds that moment."""
import sys, threading, time, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from capturemenu import capture_controller, input_devices, media, obs_client, preferences, ui_menu, ui_theme, ui_viewer

app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
obs_client.BUFFER_DIR = tmp / "Buffer"; obs_client.BUFFER_DIR.mkdir()
preferences.STATE_PATH = tmp / "state.json"
C = capture_controller.Controller


class FakeObs:
    def buffer_active(self): return True
    def split(self): pass


with patch.object(C, "_remake_hdr_thumbs"):
    ctl = C(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips"), buffer_minutes=30))
ctl.obs = FakeObs(); ctl.check_storage = lambda: None
done = []
ctl._done = lambda text, path: done.append((text, path))
now = 100_000.0
capture_controller.time.time = lambda: now
seg = lambda name, start, end: (obs_client.BUFFER_DIR / name, start, end)
segs = [seg(f"{i}.mp4", now - 600 + 60 * i, now - 540 + 60 * i) for i in range(10)]    # ten 1-minute files
for s in segs:
    s[0].write_bytes(b"x")
live = seg("live.mp4", now, now + 1)
C._segments = classmethod(lambda cls: segs + [live])
ctl._finished_segments = lambda: segs

joins = []
def fake_join(files, inpoint, out, outpoint=None):
    joins.append(([f.name for f in files], round(inpoint, 1), None if outpoint is None else round(outpoint, 1)))
    out.write_bytes(b"clip")
with patch.object(media, "join", fake_join), patch.object(media, "media_duration", lambda p: 60.0):
    # the last minute, as before: up to now, no end point
    ctl._save_clip(60, "Game")
    assert joins[-1] == (["9.mp4"], 0.0, None), joins[-1]
    # the same minute moved 2 minutes earlier: it ends 2 minutes ago, in file 7
    ctl._save_clip(60, "Game", until=now - 120)
    files, inpoint, outpoint = joins[-1]
    assert files == ["7.mp4"] and inpoint == 0.0 and outpoint is None, joins[-1]
    # 90 seconds ending 1:30 ago: file 7 (it starts 3:00 ago) and the first 30 s of file 8
    ctl._save_clip(90, "Game", until=now - 90)
    files, inpoint, outpoint = joins[-1]
    assert files == ["7.mp4", "8.mp4"] and inpoint == 0.0 and outpoint == 30.0, joins[-1]
    # a start before the oldest file is clamped to it
    ctl._save_clip(900, "Game", until=now - 300)
    assert joins[-1][0][0] == "0.mp4" and joins[-1][1] == 0.0, joins[-1]
assert len(done) == 4
print("save a clip moved earlier PASS")

# pictures: one per finished file, made once; none for the file OBS is still writing
made = []
def fake_frame(src, at_s, out, height=360):
    made.append((src.name, at_s)); out.write_bytes(b"jpg"); return True
got = []
ctl.buffer_frames.connect(lambda items: got.append(items))
with patch.object(media, "buffer_frame", fake_frame):
    ctl.load_buffer_frames()
    end = time.monotonic() + 5
    while (not got or got[-1][-2][2] is None) and time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)
    while ctl._framing.locked() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)
    app.processEvents()
    last = got[-1]
    assert len(last) == 11 and last[-1][2] is None, "the file being written has no picture"
    assert all(p is not None and p.exists() for _, _, p in last[:-1])
    assert sorted(made) == sorted((s[0].name, 0.0) for s in segs), made
    made.clear(); ctl.load_buffer_frames()
    end = time.monotonic() + 5
    while ctl._framing.locked() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)
    assert made == [], "kept: not made again"
    # a file that's gone takes its picture with it
    segs.pop(0)
    ctl.load_buffer_frames()
    end = time.monotonic() + 5
    while ctl._framing.locked() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)
    assert not (ctl.buffer_frames_dir() / "0.jpg").exists()
print("pictures of the last minutes PASS")

# a preview picture comes from the file that holds that moment, that far in
previews = []
ctl.buffer_preview.connect(lambda when, path: previews.append((when, path)))
with patch.object(media, "buffer_frame", fake_frame):
    made.clear()
    ctl.buffer_picture_at(now - 150)          # 2:30 ago: file 7 starts 3:00 ago, so 30 s in
    end = time.monotonic() + 5
    while not previews and time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)
    assert made == [("7.mp4", 30.0)] and previews[-1][0] == now - 150, (made, previews)
print("preview picture PASS")

# ---- the screen: lengths, moving the clip earlier, and what Save then asks for
ui_theme.MOTION_MS = 0
ctl.load_buffer_frames = lambda: None
ctl.buffer_picture_at = lambda when: None
menu = ui_menu.Menu(ctl, ui_viewer.Viewer(ctl))
menu.show_menu("Game")
held = 19 * 60 + 20
st = {"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": held * 1000, "recording": False,
      "record_ms": 0, "mic_muted": False}
menu._on_status(st)
assert menu.options[0] == 15 and menu.options[-1] is None, "shortest first, Everything last"
menu.open_picker(); app.processEvents()
assert menu.picking and menu.pick_len == 60 and menu.chips[menu.options.index(60)].hasFocus()
assert menu.chips[-1].text().endswith("19:20"), "Everything says how much is kept"
assert menu.chips[menu.options.index(1800)].dimmed, "30 min isn't recorded yet"
saves = []
ctl.save_clip = lambda seconds, game, until=None: saves.append((seconds, game, until))   # until only when moved
def key(k):
    QtWidgets.QApplication.sendEvent(QtWidgets.QApplication.focusWidget() or menu,
                                     QtGui.QKeyEvent(QtCore.QEvent.KeyPress, k, Qt.NoModifier))
    app.processEvents()
for _ in range(3):
    key(Qt.Key_BracketLeft)
assert menu.pick_shift == 30, menu.pick_shift
start, end = menu._selection()
assert abs(end - (menu._pick_now - 30)) < 0.01 and abs(start - (end - 60)) < 0.01
assert "ends 00:30 ago" in menu.pick_summary.text(), menu.pick_summary.text()
key(Qt.Key_BracketRight)
assert menu.pick_shift == 20
key(Qt.Key_Right)          # 3 min: the shift stays as long as it fits
assert menu.pick_len == 180 and menu.pick_shift == 20
menu.pick_shift = 10_000; menu._clamp_shift()
assert menu.pick_shift == held - 180, "never before the oldest kept moment"
menu.pick_shift = 20
key(Qt.Key_Return)
assert saves[-1][0] == 180 and saves[-1][1] == "Game" and abs(saves[-1][2] - (menu._pick_now - 20)) < 0.01, saves
def reopen():      # Save closed the bar: open it and the lengths again (the test window can't take the focus back)
    menu.show_menu("Game"); menu._on_status(st); menu.open_picker(); app.processEvents()
# Everything can't move; with no shift a save ends now, as always
reopen()
menu._choose(None); menu._shift(menu.SHIFT_STEP)
assert menu.pick_len is None and menu.pick_shift == 0
menu._save(menu.pick_len)
assert saves[-1] == (None, "Game", None), saves[-1]
reopen()
menu._choose(60)
menu._save(60)
assert saves[-1] == (60, "Game", None), "unmoved: up to now"
# a click on the strip moves the clip there
reopen(); menu._choose(60)
menu._move_to(menu._pick_now - 300)
assert menu.pick_shift == 300
# a click on a length only picks it; a second click on the same one saves
reopen(); n = len(saves)
menu.chips[menu.options.index(300)].click(); app.processEvents()
assert len(saves) == n and menu.pick_len == 300 and "click again" in menu.pick_summary.text(), "one click doesn't save"
menu.chips[menu.options.index(60)].click()
assert len(saves) == n and menu.pick_len == 60, "another length: picked, still not saved"
menu.chips[menu.options.index(60)].click()
assert saves[-1][0] == 60, "the second click on it saves"
# the controller's L1 / R1 move it while choosing; otherwise R1 trims the latest as before
menu.show_menu("Game"); menu._on_status(st); menu.open_picker()
assert input_devices.pad_key(input_devices.L1, menu, menu.viewer) == Qt.Key_BracketLeft
assert input_devices.pad_key(input_devices.R1, menu, menu.viewer) == Qt.Key_BracketRight
menu.close_picker()
assert input_devices.pad_key(input_devices.R1, menu, menu.viewer) == Qt.Key_T
menu.hide_menu()
print("save recent screen PASS")

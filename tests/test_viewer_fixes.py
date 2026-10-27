# Viewer fixes from the QA report: a click on the seek bar jumps there (RUNTIME-SEEK); T / V / E from "only the
# video" bring the page back with the panel (QA13-01); fast clicks on Delete delete once, no false error (QA15-03).
import sys, os, time, tempfile, subprocess
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, language, preferences, ui_viewer
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

app = QtWidgets.QApplication([])
preferences.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp()) / "Game"; root.mkdir()
clips = []
for i in range(3):
    p = root / f"Clip_2026-10-27_1{i}-00-00_30s.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-f", "lavfi",
                    "-i", "sine=f=400", "-map", "0", "-map", "1", "-map", "1", "-map", "1", "-t", "8", "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(p)], check=True)
    clips.append(p)
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root.parent)))
ctl.refresh_status = lambda: None


def wait(cond, s=10):
    end = time.time() + s
    while not cond() and time.time() < end:
        app.processEvents(); time.sleep(0.02)
    return cond()


for lang in ("en", "ar"):
    language.set_language(lang)
    v = ui_viewer.Viewer(ctl)
    v.resize(1600, 900); v.show()
    v.open(list(clips), 0)
    assert wait(lambda: v.player is not None and v.player.duration() > 7000), "the clip loads"
    v.player.pause(); v.player.setPosition(500); wait(lambda: abs(v.player.position() - 500) < 100, 3)

    # a click on the bar at 80% moves there (the bar runs left to right in Arabic too, like any player)
    s = v.slider
    x = int(s.width() * 0.8)
    QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, QPoint(x, s.height() // 2))
    assert wait(lambda: v.player.position() > 5000, 3), (lang, v.player.position())
    print(lang, "seek click PASS", v.player.position())

    # only the video, then T / V / E: the panel shows with the page around it
    for k, flag, panel in ((Qt.Key_T, "trimming", v.trim_panel), (Qt.Key_V, "sounding", v.sound_panel),
                           (Qt.Key_E, "sharing", v.share_panel)):
        v.toggle_full(); assert v.full
        QTest.keyClick(v, k); app.processEvents()
        assert getattr(v, flag) and not v.full and panel.isVisible() and v.footer.isVisible(), (lang, flag)
        QTest.keyClick(v, Qt.Key_Escape); app.processEvents()
        assert not getattr(v, flag), (lang, flag)
    print(lang, "full + T/V/E PASS")
    v.close_viewer(); app.processEvents()

# three fast clicks on Delete: the clip goes once, the next one stays, no "couldn't delete"
deleted, shown = [], []
ctl.delete = lambda p: (deleted.append(p), True)[-1]       # counts the deletes; the files stay
v = ui_viewer.Viewer(ctl)
v._show_msg = lambda *a: shown.append(a)
v.resize(1600, 900); v.show()
v.open(list(clips), 0); wait(lambda: v.player is not None and v.player.duration() > 0)
for _ in range(3):
    QTest.mouseClick(v.del_btn, Qt.LeftButton)
wait(lambda: deleted, 3)
for _ in range(30):
    app.processEvents(); time.sleep(0.02)
assert deleted == [clips[0]] and not shown and clips[1].exists() and v.current == clips[1], (deleted, shown, v.current)
v.close_viewer(); app.processEvents()
print("delete once PASS")

# ---- results belong to the request that asked (QA07-002, QA17-001, QA09-001, QA09-002, QA17-002, QA06-01/02)
import threading
from capturemenu import media
on_clip = lambda v, p: v.stage.currentWidget() is v.video and Path(v.player.source().toLocalFile()) == p
v = ui_viewer.Viewer(ctl)
v.resize(1600, 900); v.show()
v.open(list(clips), 0); wait(lambda: v.player.duration() > 0)

# busy: the trim never starts, the viewer goes back to the clip instead of "Saving…" for good
ctl._busy.acquire()
v.enter_trim(); v.timeline.start, v.timeline.end = 1000, 3000
v.save_trim(False)
assert wait(lambda: on_clip(v, clips[0]), 5), v.msg.text()
ctl._busy.release()
print("trim turned away: back to the clip PASS")

# a trim finishing after you moved on doesn't take you back
real_trim = ctl.trim
ctl.trim = lambda *a: None                     # the job "runs"; its result comes later
v.enter_trim(); v.timeline.start, v.timeline.end = 1000, 3000
v.save_trim(False)
v.step(1); wait(lambda: v.player.duration() > 0)
ctl.trimmed.emit(str(clips[2])); app.processEvents()
assert v.current == clips[1] and on_clip(v, clips[1]), v.current
ctl.trim = real_trim
print("late trim stays put PASS")

# sound preview: Cancel while it's made brings the clip back; it starts where you are in the clip; and
# an older request that ends last is ignored
calls, gate = [], threading.Event()
def fake_remix(src, voice, game, out, seconds=None, start=0, picture=None):
    calls.append((voice, start, out)); gate.wait(5); Path(out).write_bytes(b"x")
real_remix, media.remix_audio = media.remix_audio, fake_remix
v.enter_sound(); v.player.setPosition(3000); wait(lambda: abs(v.player.position() - 3000) < 200, 3)
v.preview_sound(); wait(lambda: calls, 3)
v.exit_sound()
assert wait(lambda: on_clip(v, clips[1]), 5), "Cancel while preparing: the clip again"
gate.set(); wait(lambda: False, 0.3)
assert on_clip(v, clips[1]), "and the late preview doesn't replace it"
print("cancel during sound preview PASS")

gate.clear(); calls.clear()
v.enter_sound(); v.voice_row.set_value(200)
v.preview_sound(); wait(lambda: len(calls) == 1, 3)
v.voice_row.set_value(100)
v.preview_sound(); wait(lambda: len(calls) == 2, 3)
first, second = calls[0][2], calls[1][2]
assert first != second, "each request writes its own file"
v._on_sound_ready(str(clips[1]), str(second), True)       # the newer one ends first...
v._on_sound_ready(str(clips[1]), str(first), True)        # ...then the older one: ignored
assert Path(v.player.source().toLocalFile()) == Path(second)
gate.set()
print("overlapping sound previews PASS")

# a second preview from inside the first one starts where that is in the clip, not near 0
calls.clear(); gate.set()
v._sound_start = 60.0; v.player.setPosition(3000); wait(lambda: abs(v.player.position() - 3000) < 300 or True, 1)
pos = v.player.position() / 1000
v.preview_sound(); wait(lambda: calls, 3)
assert abs(calls[0][1] - (60.0 + pos)) < 0.01, (calls[0][1], pos)
media.remix_audio = real_remix
v.exit_sound(); app.processEvents()
print("preview offset PASS")

# a picture that can't be read after one that can: not the last picture under the new title
from PySide6 import QtGui
good, bad = root / "Screenshot_2026-10-27_10-00-00.png", root / "Screenshot_2026-10-27_10-00-01.png"
QtGui.QImage(64, 64, QtGui.QImage.Format_RGB32).save(str(good)); bad.write_bytes(b"not a png")
v.open([good, bad], 0); app.processEvents()
assert not v.image.pixmap().isNull()
v.step(1); app.processEvents()
assert v.image.pixmap().isNull() and v.stage.currentWidget() is v.msg, "the old picture is gone"
print("damaged picture PASS")

# the 720p preview copy fails with an exception: a message, not "Preparing preview…" forever
real_make = media.make_preview
media.make_preview = lambda *a, **k: (_ for _ in ()).throw(PermissionError("locked"))
v.open(list(clips), 2); wait(lambda: v.player.duration() > 0)
v._tried_preview.discard(clips[2]); v._on_error()
assert wait(lambda: "Preparing" not in v.msg.text(), 5), v.msg.text()
media.make_preview = real_make
v.close_viewer(); app.processEvents()
print("preview error answered PASS")

# ---- QA05-01: a Recent card opens the capture it shows, even after one before it was deleted outside
from capturemenu import ui_menu
shots = root.parent / "Shots"; shots.mkdir(exist_ok=True)
ctl2 = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(shots)))
ctl2.refresh_status = lambda: None
pics = []
for i in range(3):
    p = shots / f"Screenshot_2026-10-27_10-00-0{i}.png"
    QtGui.QImage(64, 64, QtGui.QImage.Format_RGB32).save(str(p))
    os.utime(p, (time.time() - 10 + i,) * 2); pics.append(p)
opened = []
class V:
    def open(self, items, index, **k): opened.append(items[index])
ctl2.recent = pics[::-1]                # newest first, as the bar shows them
m = ui_menu.Menu(ctl2, V()); m.resize(2400, 400); m.refresh_recent()
assert [t.path for t in m.thumbs[:3]] == pics[::-1], [t.path for t in m.thumbs[:4]]
pics[2].unlink()                        # the newest goes outside the app
m._view(1)
assert opened == [pics[1]], opened
print("recent card opens what it shows PASS")

# ---- QA05-02: OBS went away: the lengths row says so instead of the last known minutes
m._on_status({"online": True, "buffer": True, "buffer_seconds": 600, "buffered_ms": 600000, "recording": False,
              "record_ms": 0, "mic_muted": False})
m._on_status({"online": False})
m.picking = True; m._refresh_picker()
assert language.tr("OBS isn't running") in m.pick_caption.text() and not m.mic_card.isVisible(), (m.pick_caption.text(), m.mic_card.isVisible())
print("offline: no stale minutes PASS")

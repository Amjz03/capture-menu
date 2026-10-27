# Viewer fixes from the QA report: a click on the seek bar jumps there (RUNTIME-SEEK); T / V / E from "only the
# video" bring the page back with the panel (QA13-01); fast clicks on Delete delete once, no false error (QA15-03).
import sys, time, tempfile, subprocess
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

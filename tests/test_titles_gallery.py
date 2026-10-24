import sys, time, tempfile, subprocess, os
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp()); now = time.time()
def mk(game, name, secs=4, ago=0, kbps="500k"):
    d = root / game; d.mkdir(exist_ok=True); p = d / name
    if name.endswith(".png"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1", str(p)], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-f", "lavfi", "-i", "sine",
                        "-t", str(secs), "-c:v", "libx264", "-preset", "ultrafast", "-b:v", kbps, "-c:a", "aac", "-shortest", str(p)], check=True)
    os.utime(p, (now - ago,) * 2); return p
a = mk("Neon Highway", "Clip_2026-10-16_21-00-00_60s.mp4", 6, 10, "300k")
b = mk("Neon Highway", "Clip_2026-10-16_20-00-00_30s.mp4", 6, 100, "3000k")     # bigger
c = mk("Neon Highway", "Screenshot_2026-10-16_19-00-00.png", ago=200)
d = mk("Frostfall", "Clip_2026-10-16_18-00-00_30s.mp4", 6, 300, "6000k")          # biggest
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
toasts = []; ctl.toast.connect(lambda t, k: toasts.append(t))

# 12: titles + notes
ctl.set_meta(a, "  Triple kill on the bridge ", "first try")
assert ctl.title_of(a) == "Triple kill on the bridge" and ctl.meta(a)["note"] == "first try"
ctl._trim(a, 0, 3000, replace=False)
new = ctl.recent_items()[0]; assert ctl.title_of(new) == "Triple kill on the bridge", "trimmed copy keeps the title"
ctl.set_meta(new, "", ""); assert ctl.meta(new) == {}, "clearing removes it"
assert cm.safe_filename('a/b:c?"d') == "a b c  d"
print("titles PASS")

viewer = cm.Viewer(ctl); menu = cm.Menu(ctl, viewer); gallery = cm.Gallery(ctl, viewer); menu.gallery = gallery
def pump(n=5):
    for _ in range(n): app.processEvents()
viewer.open([a, b], 0); pump()
assert "Triple kill" in viewer.title.text() and "Neon Highway" in viewer.sub.text() and viewer.note.text() == "first try"
viewer.start_edit(); assert viewer.editing and viewer.title_edit.text() == "Triple kill on the bridge"
assert viewer.title_edit.isVisible() and not viewer.title.isVisible() and not hasattr(viewer, "edit_panel"), "in place, no window"
assert cm.pad_key(cm.A, menu, viewer, gallery) is None and cm.pad_key(cm.B, menu, viewer, gallery) == Qt.Key_Escape
viewer.title_edit.setText("Clutch 1v4"); viewer.note_edit.setText(""); viewer.save_edit()
assert ctl.title_of(a) == "Clutch 1v4" and "note" not in ctl.meta(a) and not viewer.note.isVisible()
viewer.start_edit(); viewer.title_edit.setText("discard me"); cm.send_key(viewer, Qt.Key_Escape); pump()
assert not viewer.editing and ctl.title_of(a) == "Clutch 1v4"
viewer.close_viewer()
print("rename UI PASS")

# 6: open straight into trim (from the notification / T in the bar)
viewer.open([a], 0, trim=True)
end = time.time() + 6
while time.time() < end and not viewer.trimming: app.processEvents(); time.sleep(0.05)
assert viewer.trimming, "opened into trim"
viewer.close_viewer()
menu.show_menu("Neon Highway"); cm.send_key(menu, Qt.Key_T)
end = time.time() + 6
while time.time() < end and not viewer.trimming: app.processEvents(); time.sleep(0.05)
assert viewer.isVisible() and viewer.trimming and not menu.isVisible()
viewer.close_viewer()
t = cm.Toast(); t.thumbs_dir = ctl.thumbs_dir; opened = []; t.open_capture.connect(lambda p, tr: opened.append((Path(p).name, tr)))
t.show_capture("Last 60 sec", str(a)); pump(); assert t.trim_btn.isVisible()
t.trim_btn.click(); assert opened[-1] == (a.name, True) and not t.isVisible()
t.show_capture("", str(c)); pump(); assert not t.trim_btn.isVisible()
QtWidgets.QApplication.sendEvent(t, QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(5, 5), QtCore.QPointF(5, 5),
                                                      Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
assert opened[-1] == (c.name, False)
t.show_message("Saving…", "info"); assert t.path is None and not t.trim_btn.isVisible()
menu.view_capture(str(c)); pump(); assert viewer.isVisible() and not menu.isVisible()
viewer.go_back(); pump(); assert not viewer.isVisible() and menu.isVisible(), "Back from a notice goes to the bar"
menu.hide_menu()
print("trim from notification PASS")

# 3: sizes + sort by size
gallery.open("Neon Highway"); pump()
assert "MB" in gallery.games.item(2).text() or "GB" in gallery.games.item(2).text()
assert "·" in gallery.grid.item(0).text() and "Clutch 1v4" in "".join(gallery.grid.item(i).text() for i in range(gallery.grid.count()))
gallery.toggle_sort(); pump()
assert gallery.sort_btn.text() == "Sort: Largest"
sizes = [cm.file_size(p) for p in gallery.items]; assert sizes == sorted(sizes, reverse=True), sizes
assert gallery.cats[2][0] == "Frostfall", [n for n, _ in gallery.cats]   # biggest game first
print("sizes + sort PASS")

# 2: mark several and delete them together (Recycle Bin), via the controller
gallery.games.setCurrentRow(0); pump()
def pad(btn): cm.send_key(gallery, cm.pad_key(btn, menu, viewer, gallery)); pump()
pad(cm.X); pad(cm.RIGHT); pad(cm.X)
assert len(gallery.marked) == 2 and gallery.del_btn.isVisible() and "2 selected" in gallery.info.text()
victims = set(gallery.marked)
pad(cm.B); assert not gallery.marked and gallery.isVisible(), "Circle clears the selection first"
pad(cm.X); pad(cm.LEFT); pad(cm.X); assert gallery.marked == victims
pad(6); assert gallery.del_btn.property("danger") and all(p.exists() for p in victims), "first press only arms"
pad(6); pump()
assert not any(p.exists() for p in victims) and not gallery.marked and any("Deleted 2 captures" in x for x in toasts), toasts
QtWidgets.QApplication.sendEvent(gallery.grid, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier)); pump()
assert gallery.marked == set(gallery.items)
cm.send_key(gallery, Qt.Key_Escape); assert not gallery.marked
print("multi delete PASS:", [x for x in toasts if "Deleted" in x][0])

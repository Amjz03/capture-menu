# The gallery's Select button: a click then picks captures instead of opening them, the top bar turns
# into Select all / Delete / Cancel, and Esc or Cancel leaves it. No OBS. Usage: test_gallery_select.py REPO
import sys, os, time, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
app = QtWidgets.QApplication([])
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp()); now = time.time()
shots = []
for i in range(4):
    p = root / "Elden Ring" / f"Screenshot_2026-10-16_21-00-0{i}.png"
    p.parent.mkdir(exist_ok=True)
    img = QtGui.QImage(320, 180, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(40 * i, 80, 120))
    img.save(str(p)); os.utime(p, (now - i * 10,) * 2); shots.append(p)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
toasts = []; ctl.toast.connect(lambda t, k: toasts.append(t))
viewer = cm.Viewer(ctl); gallery = cm.Gallery(ctl, viewer); menu = cm.Menu(ctl, viewer); menu.gallery = gallery
gallery.open("Elden Ring"); gallery.resize(1600, 900)


def pump(n=8):
    for _ in range(n): app.processEvents()


def click_tile(row, double=False):
    rect = gallery.grid.visualItemRect(gallery.grid.item(row))
    (QTest.mouseDClick if double else QTest.mouseClick)(gallery.grid.viewport(), Qt.LeftButton, Qt.NoModifier,
                                                         rect.center())
    pump()


def pad(btn):
    cm.send_key(gallery, cm.pad_key(btn, menu, viewer, gallery)); pump()


pump()
assert gallery.select_btn.isVisible() and not gallery.all_btn.isVisible() and not gallery.selecting
gallery.select_btn.click(); pump()
assert gallery.selecting and not gallery.select_btn.isVisible() and not gallery.sort_btn.isVisible()
assert gallery.all_btn.isVisible() and gallery.del_btn.isVisible() and gallery.clear_btn.isVisible()
assert not gallery.del_btn.isEnabled(), "nothing picked yet: Delete is off"
click_tile(0); click_tile(2)
assert gallery.marked == {gallery.items[0], gallery.items[2]}, gallery.marked
assert "2 selected" in gallery.info.text() and gallery.del_btn.isEnabled()
click_tile(2); assert gallery.marked == {gallery.items[0]}, "a second click lets it go"
click_tile(1, double=True); pump()
assert not viewer.isVisible(), "while selecting a double click doesn't open the viewer"
gallery.grid.setCurrentRow(3); cm.send_key(gallery.grid, Qt.Key_Return); pump()
assert gallery.items[3] in gallery.marked, "Enter picks while selecting"
print("select with the mouse and Enter PASS")

gallery.all_btn.click(); pump()
assert gallery.marked == set(gallery.items) and gallery.all_btn.text() == "Select none"
gallery.all_btn.click(); pump()
assert not gallery.marked and gallery.selecting, "Select none keeps you selecting"
click_tile(1); victim = gallery.items[1]
gallery.del_btn.click(); pump(); assert victim.exists() and gallery.del_btn.property("danger"), "first press arms"
gallery.del_btn.click(); pump()
end = time.time() + 5
while time.time() < end and victim.exists(): pump(); time.sleep(0.05)
assert not victim.exists() and any("Deleted 1 capture" in t for t in toasts), toasts
print("select all and delete PASS")

gallery.select_btn.click(); click_tile(0); pump()
gallery.clear_btn.click(); pump()
assert not gallery.selecting and not gallery.marked and gallery.select_btn.isVisible()
gallery.select_btn.click(); pump(); cm.send_key(gallery.grid, Qt.Key_Escape); pump()
assert not gallery.selecting and gallery.isVisible(), "Esc leaves selecting first, not the gallery"
cm.send_key(gallery.grid, Qt.Key_Return); pump()
assert viewer.isVisible(), "not selecting: Enter opens again"
viewer.close_viewer(); pump()
print("cancel and Esc PASS")

gallery.grid.setCurrentRow(0); pad(cm.X)          # ▢ picks straight away and shows the selecting bar
assert gallery.selecting and gallery.marked == {gallery.items[0]} and gallery.del_btn.isVisible()
pad(cm.RIGHT); pad(cm.A); assert len(gallery.marked) == 2, "✕ picks while selecting"
pad(cm.B); assert not gallery.selecting and gallery.isVisible()
print("select with the controller PASS")

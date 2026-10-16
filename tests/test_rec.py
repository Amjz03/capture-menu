import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtGui, QtCore
app = QtWidgets.QApplication([])
g = cm.game_screen().geometry()
r = cm.RecIndicator("top-left")
assert not r.isVisible()
r.set_recording(True); app.processEvents()
assert r.isVisible() and r.text() == "REC  00:00" and r.x() == g.left() + 16 and r.y() == g.top() + 16
assert r.windowFlags() & QtCore.Qt.WindowTransparentForInput and r.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus
r.sync({"online": True, "recording": True, "record_ms": 754_000}); assert r.text() == "REC  12:34", r.text()
r.sync({"online": False}); assert r.isVisible(), "OBS hiccup doesn't hide it"
r.set_recording(False); assert not r.isVisible() and r.started is None
right = cm.RecIndicator("top-right"); right.set_recording(True); app.processEvents()
assert right.x() + right.width() == g.right() + 1 - 16, (right.x(), right.width(), g.right())
off = cm.RecIndicator("off"); off.set_recording(True); off.sync({"online": True, "recording": True, "record_ms": 5000})
assert not off.isVisible()
# a recording already running when the app starts is picked up from the status poll
late = cm.RecIndicator(); late.sync({"online": True, "recording": True, "record_ms": 3_725_000}); assert late.text() == "REC  1:02:05", late.text()
ctl = cm.Controller(dict(cm.DEFAULTS)); s = cm.Settings(ctl); s.encoder = "nvenc_av1"; s.open((2560, 1440))
row = next(x for x in s.rows if x.key == "record_indicator"); assert row.value == "top-left" and row.text() == "Top left"
print("rec indicator PASS")

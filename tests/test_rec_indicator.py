import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, preferences, ui_notices, ui_settings, windows
from PySide6 import QtWidgets, QtGui, QtCore
app = QtWidgets.QApplication([])
g = windows.game_screen().geometry()
r = ui_notices.RecIndicator("top-left")
assert not r.isVisible()
r.set_recording(True); app.processEvents()
assert r.isVisible() and r.text() == "REC  00:00" and r.x() == g.left() + 16 and r.y() == g.top() + 16
assert r.windowFlags() & QtCore.Qt.WindowTransparentForInput and r.windowFlags() & QtCore.Qt.WindowDoesNotAcceptFocus
r.sync({"online": True, "recording": True, "record_ms": 754_000}); assert r.text() == "REC  12:34", r.text()
r.sync({"online": False}); assert r.isVisible(), "OBS hiccup doesn't hide it"
r.set_recording(False); assert not r.isVisible() and r.started is None
right = ui_notices.RecIndicator("top-right"); right.set_recording(True); app.processEvents()
assert right.x() + right.width() == g.right() + 1 - 16, (right.x(), right.width(), g.right())
off = ui_notices.RecIndicator("off"); off.set_recording(True); off.sync({"online": True, "recording": True, "record_ms": 5000})
assert not off.isVisible()
# a recording already running when the app starts is picked up from the status poll
late = ui_notices.RecIndicator(); late.sync({"online": True, "recording": True, "record_ms": 3_725_000}); assert late.text() == "REC  1:02:05", late.text()
ctl = capture_controller.Controller(dict(preferences.DEFAULTS)); s = ui_settings.Settings(ctl); s.encoder = "nvenc_av1"; s.open((2560, 1440))
row = next(x for x in s.rows if x.key == "record_indicator"); assert row.value == "top-left" and row.text() == "Top left"
print("rec indicator PASS")

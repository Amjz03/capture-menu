import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, preferences, ui_settings, ui_widgets
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
preferences.CONFIG_PATH = tmp / "config.json"
cfg = preferences.load_config(); cfg["clips_dir"] = str(tmp / "clips")
ctl = capture_controller.Controller(cfg); ctl.refresh_status = lambda: None
s = ui_settings.Settings(ctl); s.encoder = "nvenc_av1"
s.open((2560, 1440)); s.activateWindow(); app.processEvents()
rows = s.rows
def send(w, kind):
    if kind == "enter":
        ev = QtGui.QEnterEvent(QtCore.QPointF(5, 5), QtCore.QPointF(5, 5), QtCore.QPointF(5, 5))
    elif kind == "press":
        ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(5, 5), QtCore.QPointF(5, 5),
                               Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    else:
        ev = QtCore.QEvent(QtCore.QEvent.Leave)
    QtWidgets.QApplication.sendEvent(w, ev); app.processEvents()
focus = lambda: QtWidgets.QApplication.focusWidget()

# hover lends the highlight, leaving gives it back
rows[1].setFocus(); app.processEvents()
assert focus() is rows[1]
send(rows[4], "enter"); assert focus() is rows[4]
send(rows[4], "leave"); assert focus() is rows[1], focus()
# sliding from row to row, then out: back to where the keyboard left it
send(rows[5], "enter"); send(rows[5], "leave"); send(rows[6], "enter"); assert focus() is rows[6]
send(rows[6], "leave"); assert focus() is rows[1]
print("hover gives back PASS")

# hovering never scrolls the page
bar = s.scroll.verticalScrollBar(); bar.setValue(0); app.processEvents()
far = rows[-1]; send(far, "enter"); assert bar.value() == 0, bar.value()
send(far, "leave")
print("hover doesn't scroll PASS")

# a click keeps it
send(rows[3], "enter"); send(rows[3], "press"); send(rows[3], "leave")
assert focus() is rows[3]
# a key keeps it too
rows[1].setFocus(); app.processEvents()
send(rows[2], "enter")
QtWidgets.QApplication.sendEvent(focus(), QtGui.QKeyEvent(QtCore.QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)); app.processEvents()
send(rows[2], "leave"); assert focus() is rows[2]
print("click and key keep it PASS")

# the bar's tiles and chips do the same
a, b = ui_widgets.Chip("15 sec"), ui_widgets.Chip("30 sec")
holder = QtWidgets.QWidget(); lay = QtWidgets.QHBoxLayout(holder); lay.addWidget(a); lay.addWidget(b)
holder.show(); holder.activateWindow(); a.setFocus(); app.processEvents()
send(b, "enter"); assert focus() is b
send(b, "leave"); assert focus() is a
print("chips PASS")

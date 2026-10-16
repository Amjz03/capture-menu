import sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
import capture_menu as cm
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
W, H = 1920, 1080
bg = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7))
cm.CONFIG_PATH = Path(tempfile.mkdtemp()) / "config.json"
cfg = dict(cm.DEFAULTS, clips_dir="D:\\Videos\\Clips")
ctl = cm.Controller(cfg); ctl.refresh_status = lambda: None
s = cm.Settings(ctl); s.encoder = "nvenc_av1"
def pump(n=8):
    for _ in range(n): app.processEvents()
def shot(name):
    s.resize(W, H); pump(); c = QtGui.QPixmap(bg); p = QtGui.QPainter(c); p.drawPixmap(0, 0, s.grab()); p.end(); c.save(str(out / name))
cm.INPUT.set("playstation")
s.open((2560, 1440)); s.setGeometry(0, 0, W, H); s.rows[4].setFocus(); pump()
shot("s1_settings.png")
key = lambda k: (QtWidgets.QApplication.sendEvent(s.focusWidget(), QtGui.QKeyEvent(QtCore.QEvent.KeyPress, k, Qt.NoModifier)), pump())
s.rows[1].setFocus(); key(Qt.Key_Right); s.rows[2].setFocus(); key(Qt.Key_Right)
hk = next(r for r in s.rows if r.key == "hotkey"); hk.setFocus(); pump(); s.scroll.ensureWidgetVisible(hk, 0, 300); key(Qt.Key_Return)
cm.INPUT.set("keyboard"); s.update_hints(); hk.setFocus(); hk.listening = True; pump()
shot("s2_settings_controls.png")
print("ok")

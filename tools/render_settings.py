import sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
from capturemenu import capture_controller, input_devices, preferences, ui_settings, ui_theme
ui_theme.MOTION_MS = 0     # stills: the focus has already grown into place
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name, frosted
W, H = 1920, 1080
bg = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7))
preferences.CONFIG_PATH = Path(tempfile.mkdtemp()) / "config.json"
cfg = dict(preferences.DEFAULTS, clips_dir="D:\\Videos\\Clips")
ctl = capture_controller.Controller(cfg); ctl.refresh_status = lambda: None
s = ui_settings.Settings(ctl); s.encoder = "nvenc_av1"
def pump(n=8):
    for _ in range(n): app.processEvents()
def shot(name):
    s.resize(W, H); pump(); c = frosted(bg); p = QtGui.QPainter(c); p.drawPixmap(0, 0, s.grab()); p.end(); c.save(str(out / name))
input_devices.input_mode().set("playstation")
s.open((2560, 1440)); s.setGeometry(0, 0, W, H); s.rows[4].setFocus(); pump()
shot("s1_settings.png")
key = lambda k: (QtWidgets.QApplication.sendEvent(s.focusWidget(), QtGui.QKeyEvent(QtCore.QEvent.KeyPress, k, Qt.NoModifier)), pump())
s.rows[1].setFocus(); key(Qt.Key_Right); s.rows[2].setFocus(); key(Qt.Key_Right)
hk = next(r for r in s.rows if r.key == "hotkey"); hk.setFocus(); pump(); s.scroll.ensureWidgetVisible(hk, 0, 300); key(Qt.Key_Return)
input_devices.input_mode().set("keyboard"); s.update_hints(); hk.setFocus(); hk.listening = True; pump()
shot("s2_settings_controls.png")
print("ok")

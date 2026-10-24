import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import (
    capture_controller,
    input_devices,
    obs_client,
    preferences,
    ui_menu,
    ui_settings,
    ui_viewer,
)
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
preferences.CONFIG_PATH = tmp / "config.json"
preferences.CONFIG_PATH.write_text(json.dumps({"obs_password": "keep-me", "hotkey": "alt+c", "buffer_minutes": 45}))
cfg = preferences.load_config(); cfg["clips_dir"] = str(tmp / "clips")
ctl = capture_controller.Controller(cfg); ctl.refresh_status = lambda: None
s = ui_settings.Settings(ctl); s.encoder = "nvenc_av1"
restarts = []; s.restart = lambda: restarts.append(1)
def key(k, mods=Qt.NoModifier):
    QtWidgets.QApplication.sendEvent(s.focusWidget() or s, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, k, mods)); app.processEvents()

# 1) plan: defaults unchanged, settings reach OBS
p = obs_client.obs_plan(dict(preferences.DEFAULTS), 2560, 1440, "nvenc_av1", "31.0")
prof = {(c, n): v for c, n, v in p["profile"]}
assert p["video"]["outputHeight"] == 1440 and p["video"]["fpsNumerator"] == 60 and prof[("SimpleOutput", "VBitrate")] == "8000"
q = obs_client.obs_plan(dict(preferences.DEFAULTS, resolution="1080p", fps=120, quality="high", video_codec="h264", buffer_minutes=10), 2560, 1440, "nvenc_av1", "31.0")
qp = {(c, n): v for c, n, v in q["profile"]}
assert q["video"]["outputWidth"] == 1920 and q["video"]["outputHeight"] == 1080 and q["video"]["fpsNumerator"] == 120
assert qp[("SimpleOutput", "RecEncoder")] == "nvenc" and qp[("SimpleOutput", "RecQuality")] == "HQ" and qp[("SimpleOutput", "RecRBTime")] == "600"
assert q["summary"] != p["summary"], "a change must re-run the OBS setup"
assert obs_client.choose_encoder("nvenc_hevc", "av1") == "nvenc_hevc", "never asks a GPU for a codec it lacks"
assert obs_client.choose_encoder("x264", "av1") == "x264" and obs_client.choose_encoder("amd_av1", "hevc") == "amd_hevc"
print("plan PASS", q["summary"])

# 2) page opens with current values (45 min snaps to the nearest choice)
s.open((2560, 1440)); app.processEvents()
vals = s.values()
assert vals["buffer_minutes"] == 45 and vals["fps"] == 60 and vals["quality"] == "balanced" and vals["hotkey"] == "alt+c"
assert "2560×1440" in s.res_row.text() and "GB of RAM" in s.memory.text()
print("open PASS", s.memory.text())

# 3) keyboard: down to frame rate, right = 120; quality right = high
key(Qt.Key_Down); key(Qt.Key_Right); key(Qt.Key_Down); key(Qt.Key_Right)
assert s.values()["fps"] == 120 and s.values()["quality"] == "high", s.values()
assert "2 unsaved changes" in s.info.text() or "unsaved" in s.info.text()

# 4) new hotkey: Enter, then Ctrl+Shift+F9; a bare letter is refused
hk = next(r for r in s.rows if r.key == "hotkey"); hk.setFocus(); app.processEvents()
key(Qt.Key_Return); assert hk.listening
key(Qt.Key_K); assert hk.listening and hk.value == "alt+c", "bare letter ignored"
key(Qt.Key_F9, Qt.ControlModifier | Qt.ShiftModifier); assert not hk.listening and hk.value == "ctrl+shift+f9", hk.value
print("hotkey PASS")

# 5) Esc cancels without writing
key(Qt.Key_Escape); assert not s.isVisible() and json.loads(preferences.CONFIG_PATH.read_text())["hotkey"] == "alt+c"
# 6) reopen, change, save: only changed keys written, password kept, app restarts
s.open((2560, 1440)); assert s.values()["fps"] == 60, "cancel discarded the edits"
key(Qt.Key_Down); key(Qt.Key_Right)          # fps 120
s.rows[0].setFocus(); key(Qt.Key_Right)      # 1440p is not below native -> next choice 1080p
key(Qt.Key_S)
saved = json.loads(preferences.CONFIG_PATH.read_text())
assert saved["fps"] == 120 and saved["resolution"] == "1080p" and saved["obs_password"] == "keep-me", saved
assert saved["buffer_minutes"] == 45, "untouched keys are left alone"
assert restarts == [1] and not s.isVisible() and ctl.cfg["fps"] == 120
# 7) defaults
s.open((2560, 1440)); key(Qt.Key_R); assert s.values()["fps"] == 60 and s.values()["resolution"] == "native"
# 8) save with nothing changed: no restart
s.ctl.cfg.update(s.values()); restarts.clear(); key(Qt.Key_S); assert restarts == [] and not s.isVisible()
# 9) controller mapping
menu = ui_menu.Menu(ctl, ui_viewer.Viewer(ctl)); s.open((2560, 1440))
assert input_devices.pad_key(input_devices.Y, menu, ui_viewer.Viewer(ctl), None, s) == Qt.Key_S and input_devices.pad_key(input_devices.A, menu, ui_viewer.Viewer(ctl), None, s) == Qt.Key_Return
# 10) ↑ from the first row reaches the buttons along the top, ← → walk them, ↓ comes back
s.rows[0].setFocus(); app.processEvents()
key(Qt.Key_Up); assert s.focusWidget() is s.back_btn, s.focusWidget()
key(Qt.Key_Right); assert s.focusWidget() is s.defaults_btn
key(Qt.Key_Right); key(Qt.Key_Right); assert s.focusWidget() is s.save_btn
key(Qt.Key_Down); assert s.focusWidget() is s.rows[0]
print("settings PASS")

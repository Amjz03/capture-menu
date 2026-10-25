# The first start asks four things (how much to keep, quality, microphone, frame rate), each saying
# it can be changed later in Settings, saves them, and lets setup go on with them. Never asked again.
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, obs_client, preferences, ui_settings
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
preferences.CONFIG_PATH, preferences.STATE_PATH = tmp / "config.json", tmp / "state.json"
obs_client.gpu_names = lambda: ["NVIDIA GeForce RTX 4070"]
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips")))
started = []
w = ui_settings.Welcome(ctl, lambda: started.append(dict(ctl.cfg)))
w.open((2560, 1440))
assert w.isVisible() and [r.key for r in w.rows] == ["language", "buffer_minutes", "quality", "mic_on", "fps"]
assert all(r.describe(r.value).endswith("You can change it later in Settings.") for r in w.rows), \
    [r.describe(r.value) for r in w.rows]
# the recommended choices come first: 30 min, Balanced, the mic on, 60 FPS
assert w.values() == {"language": "auto", "buffer_minutes": 30, "quality": "balanced", "mic_on": True, "fps": 60}, w.values()
print(*(f"{r.label}: {r.display_value() if hasattr(r, 'display_value') else r.value} · {r.describe(r.value)}" for r in w.rows), sep="\n")

# pick: 15 min, High, no microphone, 120 FPS, with the keys
rows = {r.key: r for r in w.rows}
rows["buffer_minutes"].step(-1); rows["quality"].step(1); rows["mic_on"].activate(); rows["fps"].step(1)
assert w.values() == {"language": "auto", "buffer_minutes": 15, "quality": "high", "mic_on": False, "fps": 120}, w.values()
w.save()
assert not w.isVisible() and len(started) == 1
assert started[0]["buffer_minutes"] == 15 and started[0]["mic_on"] is False, "setup goes on with the choices"
saved = json.loads(preferences.CONFIG_PATH.read_text())
assert {k: saved[k] for k in ("buffer_minutes", "quality", "mic_on", "fps")} == \
    {"buffer_minutes": 15, "quality": "high", "mic_on": False, "fps": 120}, saved
assert preferences.load_state().get("welcomed") is True, "never asked again"
print("choices saved PASS")

# the first question is the language: a different one restarts the app straight back to these questions
from capturemenu import language
language.set_language("en")
restarted = []
w3 = ui_settings.Welcome(ctl, lambda: started.append("no")); w3.restart = lambda: restarted.append(True); w3.open((1920, 1080))
lang_row = w3.rows[0]
lang_row.set_value("en", emit=True)          # the language it's already in: nothing happens
assert restarted == [] and w3.isVisible()
lang_row.set_value("ar", emit=True)
assert restarted == [True] and not w3.isVisible() and json.loads(preferences.CONFIG_PATH.read_text())["language"] == "ar"
assert preferences.load_state().get("welcomed") is True and "no" not in started   # (welcomed came from the run above)
print("language first PASS")

# Esc (◯ / B) starts with what's picked
started.clear()
w2 = ui_settings.Welcome(ctl, lambda: started.append(True)); w2.open((1920, 1080))
w2.go_back()
assert started == [True] and not w2.isVisible()
print("Esc starts PASS")

# the same choice lives in Settings afterwards
s = ui_settings.Settings(ctl)
assert "mic_on" in [r.key for r in s.rows] and "buffer_minutes" in [r.key for r in s.rows]
print("in Settings PASS")

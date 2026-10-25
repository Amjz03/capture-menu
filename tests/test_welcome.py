# The first start asks what's worth choosing before anything is recorded, each saying it can be
# changed later in Settings, the language first; saves it and lets setup go on. Never asked again.
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, language, obs_client, preferences, ui_settings, windows
from PySide6 import QtWidgets

app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
preferences.CONFIG_PATH, preferences.STATE_PATH = tmp / "config.json", tmp / "state.json"
obs_client.gpu_names = lambda: ["NVIDIA GeForce RTX 4070"]
windows.windows_hdr = lambda *a: False
windows.starts_with_windows = lambda: True
windows.set_start_with_windows = lambda on: startup_set.append(on)
startup_set = []
language.set_language("en")
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips")))
started, restarted = [], []


def welcome():
    w = ui_settings.Welcome(ctl, lambda: started.append(dict(ctl.cfg)))
    w.restart = lambda: restarted.append(True)
    w.open((2560, 1440))
    return w


w = welcome()
keys = [r.key for r in w.rows]
one_screen = ["language", "start_with_windows", "buffer_minutes", "double_press_seconds", "quality", "resolution",
              "fps", "mic_on", "hotkey", "controller_button", "clips_dir"]
assert keys in (one_screen, one_screen[:7] + ["capture_screen"] + one_screen[7:]), keys
assert "hdr" not in keys, "HDR is only asked when Windows HDR is on"
assert all(r.describe(r.value).endswith("You can change it later in Settings.") for r in w.rows), \
    [r.describe(r.value) for r in w.rows]
# the recommended choices come picked
v = w.values()
assert (v["language"], v["buffer_minutes"], v["double_press_seconds"], v["quality"], v["resolution"], v["fps"],
        v["mic_on"], v["hotkey"], v["controller_button"], v["start_with_windows"]) == \
    ("auto", 30, 30, "balanced", "native", 60, True, "alt+c", "create", True), v
assert [c for c, _ in w.res_row.choices] == ["native", "1080p", "720p"], w.res_row.choices
print(*(f"{r.label} · {r.describe(r.value)}" for r in w.rows), sep="\n")

# change what's read during setup only: Start goes straight on, no restart
rows = {r.key: r for r in w.rows}
rows["buffer_minutes"].step(-1); rows["quality"].step(1); rows["mic_on"].activate(); rows["fps"].step(1)
rows["resolution"].step(1); rows["start_with_windows"].activate()
w.save()
assert not w.isVisible() and len(started) == 1 and restarted == []
saved = json.loads(preferences.CONFIG_PATH.read_text())
assert {k: saved[k] for k in ("buffer_minutes", "quality", "mic_on", "fps", "resolution")} == \
    {"buffer_minutes": 15, "quality": "high", "mic_on": False, "fps": 120, "resolution": "1080p"}, saved
assert startup_set == [False] and "start_with_windows" not in saved, "Windows' own startup entry, not config"
assert preferences.load_state().get("welcomed") is True, "never asked again"
print("choices saved PASS")

# keys, the controller button, the double press or the folder are read as the app starts: one restart
started.clear()
w2 = welcome()
{r.key: r for r in w2.rows}["double_press_seconds"].step(1)
w2.save()
assert restarted == [True] and started == [] and json.loads(preferences.CONFIG_PATH.read_text())["double_press_seconds"] == 60
print("startup choices restart PASS")

# the language: a different one restarts straight back to these questions, in it
restarted.clear()
w3 = welcome()
w3.rows[0].set_value("en", emit=True)
assert restarted == [] and w3.isVisible(), "the language it's already in: nothing happens"
w3.rows[0].set_value("ar", emit=True)
assert restarted == [True] and not w3.isVisible() and json.loads(preferences.CONFIG_PATH.read_text())["language"] == "ar"
print("language first PASS")

# Esc (◯ / B) starts with what's picked
started.clear(); restarted.clear()
ctl.cfg["language"] = "en"; preferences.save_config({"language": "en"})
w4 = welcome(); w4.go_back()
assert started and not w4.isVisible()
print("Esc starts PASS")

# HDR is asked when Windows HDR is on
windows.windows_hdr = lambda *a: True
assert "hdr" in [r.key for r in welcome().rows]
print("HDR when it applies PASS")

# the same choices live in Settings afterwards
s = ui_settings.Settings(ctl)
assert {"mic_on", "buffer_minutes", "double_press_seconds", "hotkey", "clips_dir"} <= {r.key for r in s.rows}
print("in Settings PASS")

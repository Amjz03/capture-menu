import sys, json, time, tempfile, threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtGui
app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
cm.CONFIG_PATH = tmp / "config.json"
cm.STATE_PATH = tmp / "state.json"

# 0.0.10 and older: "Follow the game's screen" off meant the main screen
cm.CONFIG_PATH.write_text(json.dumps({"capture_follow_game": False}))
assert cm.load_config()["capture_screen"] == "main"
cm.CONFIG_PATH.write_text(json.dumps({"capture_follow_game": True}))
assert cm.load_config()["capture_screen"] == "follow"
cm.CONFIG_PATH.write_text(json.dumps({"capture_follow_game": False, "capture_screen": "follow"}))
assert cm.load_config()["capture_screen"] == "follow", "a choice made since wins"
cm.CONFIG_PATH.write_text("{}")
print("migration PASS")

# screens: a lasting id, real pixels, and None (follow) for one that isn't connected
main = QtGui.QGuiApplication.primaryScreen()
sid = cm.screen_id(main)
assert cm.chosen_screen("follow") is None and cm.chosen_screen("main") is main and cm.chosen_screen(sid) is main
assert cm.chosen_screen("Some TV#123") is None
l, t, r, b = cm.screen_px_rect(main)
assert (r - l, b - t) == (round(main.geometry().width() * main.devicePixelRatio()),
                          round(main.geometry().height() * main.devicePixelRatio()))
assert f"{r - l}×{b - t}" in cm.screen_label(main)
print("screens PASS", cm.screen_label(main))

# a picked screen is always recorded, whatever window is in front
ctl = cm.Controller(dict(cm.load_config(), clips_dir=str(tmp / "clips"), capture_screen=sid))
seen = []
ctl.obs = type("O", (), {"capture_monitor": lambda self, rect, only_if_missing=False:
                         seen.append((rect, only_if_missing)) or None})()
ctl._following = threading.Lock()
cm.foreground_screen = lambda: {"own": False, "fullscreen": True, "rect": (9000, 0, 9100, 100), "device": "x"}
ctl._follow_tick(); time.sleep(0.2)
assert seen == [(cm.screen_px_rect(main), False)], seen
ctl.cfg["capture_screen"] = "Some TV#123"     # not connected: follow the game meanwhile
ctl._follow_last = None; ctl._follow_tick(); time.sleep(0.2)
assert seen[-1] == ((9000, 0, 9100, 100), False), seen
print("fixed screen PASS")

# microphones in OBS
class FakeObs(cm.Obs):
    def __init__(self, device="default", has_mic=True):
        super().__init__(dict(cm.DEFAULTS)); self.device, self.has_mic, self.sets = device, has_mic, []
    def raw(self, req, data=None):
        if req == "GetInputList":
            return {"inputs": [{"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"}] +
                    ([{"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"}] if self.has_mic else [])}
        if req == "GetInputPropertiesListPropertyItems":
            return {"propertyItems": [{"itemName": "Default", "itemValue": "default", "itemEnabled": True},
                                      {"itemName": "Headset Microphone (2- Arctis Nova)", "itemValue": "{0.0.1}.{a}", "itemEnabled": True},
                                      {"itemName": "Webcam", "itemValue": "{0.0.1}.{b}", "itemEnabled": True}]}
        if req == "GetInputSettings":
            return {"inputSettings": {"device_id": self.device}}
        if req == "SetInputSettings":
            self.sets.append(data); self.device = data["inputSettings"]["device_id"]
        return {}

o = FakeObs()
assert o.mic_devices() == ("default", [("{0.0.1}.{a}", "Arctis Nova"), ("{0.0.1}.{b}", "Webcam")])
assert o.set_mic_device("{0.0.1}.{a}") and o.sets[-1]["inputName"] == "Mic/Aux"
assert not o.set_mic_device("{0.0.1}.{a}"), "already that one"
assert FakeObs(has_mic=False).mic_devices() is None
assert cm.mic_name("Headset Microphone (3- A50 X Mic)") == "A50 X Mic" and cm.mic_name("Studio Mic") == "Studio Mic"
assert cm.mic_name("Microphone (Realtek(R) Audio)") == "Realtek(R) Audio"
print("obs mics PASS")

# applied only once picked here: a microphone chosen in OBS itself is left alone
ctl.obs = FakeObs(device="{0.0.1}.{b}")
ctl.cfg["mic_device"] = "default"; ctl.apply_mic()
assert ctl.obs.device == "{0.0.1}.{b}" and not ctl.obs.sets
ctl.cfg["mic_device"] = "{0.0.1}.{a}"; ctl.apply_mic()
assert ctl.obs.device == "{0.0.1}.{b}", "not picked in Settings yet"
cm.save_state(dict(cm.load_state(), mic_picked=True)); ctl.apply_mic()
assert ctl.obs.device == "{0.0.1}.{a}" and cm.load_state()["mic_device"] == "{0.0.1}.{a}"
ctl.cfg["mic_device"] = "default"; ctl.apply_mic()
assert ctl.obs.device == "default", "back to Windows' microphone"
print("apply mic PASS")

# Settings: the rows list what's connected, and "main" from an old config isn't a change
cm.save_config({"capture_screen": "main"})
ctl = cm.Controller(dict(cm.load_config(), clips_dir=str(tmp / "clips")))
ctl.refresh_status = lambda: None
ctl.obs = FakeObs()
s = cm.Settings(ctl); s.encoder = "nvenc_av1"
s.open((2560, 1440)); app.processEvents()
assert s.screen_row.value == sid and [c[0] for c in s.screen_row.choices][:2] == ["follow", sid]
assert "capture_screen" not in s.changes(), s.changes()
for _ in range(50):
    app.processEvents(); time.sleep(0.02)
    if s.mics != "checking":
        break
assert [c[1] for c in s.mic_row.choices] == ["Same as Windows", "Arctis Nova", "Webcam"], s.mic_row.choices
assert s.mic_row.value == "default" and not s.changes(), s.changes()
s.mic_row.step(1); s.screen_row.step(-1)
assert s.changes() == {"mic_device": "{0.0.1}.{a}", "capture_screen": "follow"}, s.changes()
s.restart = lambda: None; s.save()
assert cm.load_state()["mic_picked"] and json.loads(cm.CONFIG_PATH.read_text())["mic_device"] == "{0.0.1}.{a}"
print("settings rows PASS")

# a microphone picked in OBS itself shows as it is until one is picked here
cm.save_state({}); cm.CONFIG_PATH.write_text("{}")
ctl = cm.Controller(dict(cm.load_config(), clips_dir=str(tmp / "clips"))); ctl.refresh_status = lambda: None
ctl.obs = FakeObs(device="{0.0.1}.{b}")
s = cm.Settings(ctl); s.encoder = "nvenc_av1"; s.open((2560, 1440))
for _ in range(50):
    app.processEvents(); time.sleep(0.02)
    if s.mics != "checking":
        break
assert s.mic_row.value == "{0.0.1}.{b}" and s.mic_row.text() == "Webcam" and not s.changes(), s.changes()
print("mic picked in OBS PASS")

import sys, time, tempfile, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtCore, QtWidgets

# encoder + bitrate choice
assert cm.pick_encoder(["NVIDIA GeForce RTX 4070 Ti SUPER"]) == "nvenc_av1"
assert cm.pick_encoder(["NVIDIA GeForce RTX 3080"]) == "nvenc_hevc"
assert cm.pick_encoder(["Intel(R) UHD Graphics 770", "AMD Radeon RX 7900 XTX"]) == "amd_av1"
assert cm.pick_encoder(["Microsoft Basic Display Adapter"]) == "x264"
assert cm.pick_bitrate("nvenc_av1", 2560, 1440) == 8000
assert cm.pick_bitrate("nvenc_av1", 1920, 1080) == 4500
assert cm.pick_bitrate("nvenc_av1", 3840, 2160) == 18000
plan = cm.obs_plan(dict(cm.DEFAULTS), 2560, 1440, "nvenc_av1", "31.0.2")
prof = {(c, n): v for c, n, v in plan["profile"]}
assert prof[("SimpleOutput", "RecRBTime")] == "1800" and prof[("SimpleOutput", "RecFormat2")] == "hybrid_mp4"
assert {(c, n): v for c, n, v in cm.obs_plan(dict(cm.DEFAULTS), 2560, 1440, "x264", "29.1.3")["profile"]}[("SimpleOutput", "RecFormat2")] == "mp4"
print(plan["summary"]); print("plan PASS")

class FakeObs(cm.Obs):
    def __init__(self):
        super().__init__(dict(cm.DEFAULTS))
        self.video = {"baseWidth": 1920, "baseHeight": 1080, "outputWidth": 1280, "outputHeight": 720,
                      "fpsNumerator": 30, "fpsDenominator": 1}
        self.params, self.inputs, self.buffer, self.log = {}, [], True, []
    def raw(self, req, d=None):
        self.log.append(req)
        if req == "GetVersion": return {"obsVersion": "31.0.2"}
        if req == "GetVideoSettings": return dict(self.video)
        if req == "SetVideoSettings": self.video.update(d); return {}
        if req == "GetProfileParameter": return {"parameterValue": self.params.get((d["parameterCategory"], d["parameterName"]))}
        if req == "SetProfileParameter": self.params[(d["parameterCategory"], d["parameterName"])] = d["parameterValue"]; return {}
        if req == "GetInputList": return {"inputs": [{"inputName": n} for n in self.inputs]}
        if req == "CreateInput": self.inputs.append(d["inputName"]); return {}
        if req == "GetCurrentProgramScene": return {"sceneName": "Scene"}
        if req == "GetSceneItemId": return {"sceneItemId": 1}
        return {}
    def record_status(self): return False, 0
    def buffer_active(self): return self.buffer
    def call(self, name, *a):
        if name == "stop_replay_buffer": self.buffer = False; return
        if name == "start_replay_buffer": self.buffer = True; return
        return super().call(name, *a)

app = QtWidgets.QApplication([])
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
cm.gpu_names = lambda: ["NVIDIA GeForce RTX 4070 Ti SUPER"]
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=tempfile.mkdtemp())); ctl.obs = FakeObs()
ctl.restart_obs = lambda: True   # the real one closes and restarts the OBS on this PC
toasts = []; ctl.toast.connect(lambda t, k: toasts.append(t))
ctl.auto_setup(2560, 1440)
o = ctl.obs
assert o.video["baseWidth"] == 2560 and o.video["fpsNumerator"] == 60
assert o.params[("SimpleOutput", "StreamEncoder")] == "nvenc_av1" and o.params[("SimpleOutput", "RecRB")] == "true"
assert o.inputs == ["Display Capture"] and "SetSceneItemTransform" in o.log
assert json.loads(cm.STATE_PATH.read_text())["obs_setup"].startswith("2560×1440")
print(*toasts, sep="\n")
o.log.clear(); ctl.auto_setup(2560, 1440)
assert "SetVideoSettings" not in o.log and "SetProfileParameter" not in o.log, "second start: nothing to do"
print("auto setup PASS")

# one press opens (after the wait), two quick presses save instantly
opened, saved, state = [], [], {"open": False}
seq = cm.PressSequencer(350, lambda g: opened.append(g), lambda g: saved.append(g), lambda: state["open"])
def wait(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(); time.sleep(0.01)
seq.press("Elden Ring"); wait(150); assert opened == []          # still waiting for a 2nd press
wait(300); assert opened == ["Elden Ring"] and saved == []
seq.press("Elden Ring"); wait(120); seq.press("Elden Ring"); wait(500)
assert saved == ["Elden Ring"] and opened == ["Elden Ring"], (opened, saved)
state["open"] = True; seq.press("x"); assert opened[-1] == "x", "closing doesn't wait"
off = cm.PressSequencer(0, lambda g: opened.append("now"), lambda g: None, lambda: False)
off.press("y"); assert opened[-1] == "now"
print("double press PASS")

s = cm.Sounds(True); print("sounds loaded:", sorted(s.effects)); s.play("capture"); s.play("missing")
g = cm.Gamepad(dict(cm.DEFAULTS)); g.rumble("capture"); assert g._rumble == g.RUMBLES["capture"]
print("sounds + rumble PASS")
assert ctl.obs.buffer, "buffer back on even when OBS couldn't be restarted"
print("buffer kept PASS")

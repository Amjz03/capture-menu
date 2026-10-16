import sys, time, tempfile
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtCore

MON = {"itemName": "LG ULTRAGEAR: 2560x1440 @ 0,0 (Primary Monitor)", "itemValue": "\\\\?\\DISPLAY#GSM5BBF#1", "itemEnabled": True}
TV  = {"itemName": "SAMSUNG: 3840x2160 @ 2560,0", "itemValue": "\\\\?\\DISPLAY#SAM7056#2", "itemEnabled": True}
assert cm.pick_monitor_item([MON, TV], (2560, 0, 6400, 2160)) is TV
assert cm.pick_monitor_item([MON, TV], (0, 0, 2560, 1440)) is MON
# "TV only" mode: Windows moves the TV to 0,0 -> no position match, matched by size
assert cm.pick_monitor_item([TV | {"itemName": "SAMSUNG: 3840x2160 @ 0,0"}], (0, 0, 3840, 2160))["itemValue"] == TV["itemValue"]
assert cm.pick_monitor_item([MON], (5000, 0, 6000, 1000)) is None

class FakeObs(cm.Obs):
    def __init__(self, items, current):
        super().__init__(dict(cm.DEFAULTS)); self.items, self.settings, self.calls = items, {"monitor_id": current}, []
    def raw(self, req, data=None):
        self.calls.append(req)
        return {"GetInputList": {"inputs": [{"inputName": "Display Capture"}]},
                "GetInputPropertiesListPropertyItems": {"propertyItems": self.items},
                "GetInputSettings": {"inputSettings": dict(self.settings)},
                "GetVideoSettings": {"baseWidth": 2560, "baseHeight": 1440},
                "GetCurrentProgramScene": {"sceneName": "Scene"},
                "GetSceneItemId": {"sceneItemId": 3}}.get(req, {}) if req != "SetInputSettings" else self._set(data)
    def _set(self, data):
        self.settings.update(data["inputSettings"]); return {}

o = FakeObs([MON, TV], MON["itemValue"])
assert o.capture_monitor((2560, 0, 6400, 2160)) == "SAMSUNG"            # game went fullscreen on the TV
assert o.settings["monitor_id"] == TV["itemValue"] and "SetSceneItemTransform" in o.calls
o.calls.clear()
assert o.capture_monitor((2560, 0, 6400, 2160)) is None and "SetInputSettings" not in o.calls  # already there
assert o.capture_monitor((0, 0, 2560, 1440), only_if_missing=True) is None    # Discord on the monitor: stay on TV
# captured monitor disappeared ("TV only"): fix it even without a fullscreen game
o2 = FakeObs([TV | {"itemName": "SAMSUNG: 3840x2160 @ 0,0"}], MON["itemValue"])
assert o2.capture_monitor((0, 0, 3840, 2160), only_if_missing=True) == "SAMSUNG"
print("capture follow PASS")

# the controller only moves the capture for fullscreen windows that aren't ours
app = QtCore.QCoreApplication([])
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=tempfile.mkdtemp()))
seen = []
ctl.obs = type("O", (), {"capture_monitor": lambda self, rect, only_if_missing=False: seen.append((rect, only_if_missing)) or None})()
ctl._following = __import__("threading").Lock()
for info in [None, {"own": True, "fullscreen": True, "rect": (0, 0, 1, 1), "device": "x"},
             {"own": False, "fullscreen": True, "rect": (2560, 0, 6400, 2160), "device": "\\\\.\\DISPLAY2"},
             {"own": False, "fullscreen": False, "rect": (0, 0, 2560, 1440), "device": "\\\\.\\DISPLAY1"}]:
    cm.foreground_screen = lambda info=info: info
    ctl._follow_tick(); time.sleep(0.2)
assert seen == [((2560, 0, 6400, 2160), False), ((0, 0, 2560, 1440), True)], seen
print("follow tick PASS")

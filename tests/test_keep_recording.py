# OBS records the whole time Capture Menu runs, whatever happens: OBS closed or crashed, the graphics
# driver updated or reset under it, a recording that stopped growing, a drive filling up, Capture
# Menu itself closing without Quit. Never restarts OBS while it streams; says a failure once.
import sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, obs_client, preferences, runtime, windows
from PySide6 import QtWidgets

app = QtWidgets.QApplication([])
tmp = Path(tempfile.mkdtemp())
preferences.STATE_PATH = tmp / "state.json"
obs_client.BUFFER_DIR = tmp / "CaptureMenu" / "Buffer"
runtime.ALIVE = tmp / "CaptureMenu" / "alive"

# ---- Capture Menu comes back after closing without Quit, and only then
now = 1_000_000.0; boot = now - 3600
assert not runtime.came_back_needed(now, boot), "Quit deletes ALIVE: stays closed"
runtime.touch_alive()
import os
os.utime(runtime.ALIVE, (now - 30, now - 30)); assert not runtime.came_back_needed(now, boot), "running"
os.utime(runtime.ALIVE, (now - 400, now - 400)); assert runtime.came_back_needed(now, boot), "went silent: crashed"
os.utime(runtime.ALIVE, (boot - 60, boot - 60)); assert not runtime.came_back_needed(now, boot), "Windows restarted since"
sys.argv = ["capture_menu.py", "--watch"]
with patch.object(runtime, "came_back_needed", lambda: False):
    try:
        runtime.leave_if_not_needed(); raise AssertionError("should have left")
    except SystemExit:
        pass
with patch.object(runtime, "came_back_needed", lambda: True):
    runtime.leave_if_not_needed()
assert sys.argv == ["capture_menu.py"], sys.argv
seen = {}
def schtasks(cmd, **kw):
    seen["cmd"], seen["xml"] = cmd, Path(cmd[cmd.index("/XML") + 1]).read_text(encoding="utf-16")
    return type("R", (), {"returncode": 0, "stderr": b""})()
with patch.object(runtime, "FROZEN", True), patch.object(runtime, "IS_WINDOWS", True), \
        patch.object(windows.subprocess, "run", schtasks):
    windows.set_watch_task()
assert "<Interval>PT3M</Interval>" in seen["xml"] and "<Arguments>--watch</Arguments>" in seen["xml"], seen["xml"]
assert seen["cmd"][3].startswith("Capture Menu watch ("), seen["cmd"]
print("comes back after a crash, not after Quit or a Windows restart PASS")


# ---- the minute check
class FakeObs(obs_client.Obs):
    def __init__(self):
        super().__init__(dict(preferences.DEFAULTS))
        self.active, self.stream, self.written, self.starts = True, False, 100, 0
        self.encoder_ok = True
    def buffer_active(self): return self.active
    def streaming(self): return self.stream
    def recorded_bytes(self): return self.written if self.active else None
    def start_buffer(self, wait=0):
        self.starts += 1
        return self.active
    def profile_value(self, c, n): return {"RecEncoder": "nvenc_av1", "Mode": "Simple"}.get(n)
    def raw(self, req, d=None): return {}


class Now:        # run the background check right away
    def __init__(self, target, daemon=None): self.target = target
    def start(self): self.target()
capture_controller.threading.Thread = Now


def controller():
    preferences.save_state({})
    ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips")))
    ctl.obs = FakeObs()
    ctl.restarts = 0
    def restart():
        ctl.restarts += 1
        ctl.obs.active = ctl.obs.encoder_ok
        ctl.obs.written += 1
        return ctl.obs.active
    ctl.restart_obs = restart
    ctl.toasts = []; ctl.toast.connect(lambda t, k: ctl.toasts.append((k, t)))
    return ctl


running = {"obs": True}
obs_client.obs_running = lambda: running["obs"]
started = []
obs_client.start_obs = lambda: started.append(1) or running.update(obs=True) or True
capture_controller.Controller._wait_for_obs = lambda self: True
gpu = {"lost": False}
capture_controller.Controller._obs_lost_gpu = classmethod(lambda cls: gpu["lost"])
runtime.IS_WINDOWS = True

# fine: nothing done, Capture Menu says it's alive
ctl = controller(); runtime.ALIVE.unlink()
ctl._watch_buffer(); ctl.obs.written += 5; ctl._watch_buffer()
assert ctl.restarts == 0 and not started and runtime.ALIVE.exists() and ctl.toasts == [], ctl.toasts
print("fine: left alone PASS")

# OBS closed (by hand, a crash, a driver update that ended it): started again and recording
running["obs"] = False; ctl.obs.active = False
ctl._watch_buffer()
assert started and ctl.obs.starts >= 1, "OBS started, then the recording"
print("OBS closed: started again PASS")

# the graphics driver reset under OBS: restarted once, not again within HEAL_PAUSE
ctl = controller(); gpu["lost"] = True
ctl._watch_buffer(); ctl._watch_buffer()
assert ctl.restarts == 1 and ctl.toasts[-1][1].startswith("OBS stopped recording after a graphics driver reset"), ctl.toasts
gpu["lost"] = False
print("driver reset: restarted PASS")

# the recording stopped growing (a hung encoder): restarted
ctl = controller()
ctl._watch_buffer(); ctl._watch_buffer()
assert ctl.restarts == 1 and ctl.toasts[-1][1] == "OBS stopped recording, so I restarted it", ctl.toasts
print("frozen recording: restarted PASS")

# OBS streams: never restarted under the stream, whatever is wrong
ctl = controller(); ctl.obs.stream = True; gpu["lost"] = True
ctl._watch_buffer(); ctl._watch_buffer()
ctl.obs.active = False; ctl._watch_buffer()
assert ctl.restarts == 0, "a restart would end the stream"
gpu["lost"] = False
print("streaming: never restarted PASS")

# a driver update: the encoder runs again after a plain restart, so it's not marked as failed
ctl = controller(); ctl.obs.active = False
assert ctl.heal_buffer() and ctl.restarts == 1
assert "failed_encoders" not in preferences.load_state(), "AV1 stays: it was the driver, not the card"
print("driver update: plain restart, encoder kept PASS")

# nothing works: said once, not every two minutes
ctl = controller(); ctl.obs.active = False; ctl.obs.encoder_ok = False
assert not ctl.heal_buffer()
ctl._heal_failed_at -= ctl.HEAL_PAUSE + 1
assert not ctl.heal_buffer()
assert [t for k, t in ctl.toasts if k == "error"] == ["OBS can't start recording · open OBS to see why"], ctl.toasts
print("failure said once PASS")

# the drive with the last minutes fills up: said once, again only after it had room
ctl = controller(); free = {"gb": 3}
capture_controller.shutil.disk_usage = lambda p: type("U", (), {"free": free["gb"] * 1024 ** 3})()
ctl._watch_buffer(); ctl._watch_buffer()
assert len([t for k, t in ctl.toasts if "GB free on" in t]) == 1, ctl.toasts
free["gb"] = 50; ctl._watch_buffer(); free["gb"] = 2; ctl._watch_buffer()
assert len([t for k, t in ctl.toasts if "GB free on" in t]) == 2, ctl.toasts
print("drive filling up: said once PASS")

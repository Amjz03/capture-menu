# The replay buffer repairs itself on a new PC: switched off in OBS's settings, an OBS that wasn't
# restarted after setup, an encoder the card can't run. Nothing is done by hand.
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, obs_client, preferences
from obsws_python.error import OBSSDKRequestError
from PySide6 import QtWidgets

# encoders: a card's name isn't proof it can encode, so each has a way down to the CPU
assert obs_client.fallback_encoders("nvenc_hevc") == ["nvenc", "x264"]
assert obs_client.fallback_encoders("amd_av1") == ["amd", "x264"]
assert obs_client.fallback_encoders("qsv") == ["x264"]
assert obs_client.fallback_encoders("x264") == []
assert obs_client.pick_encoder(["NVIDIA GeForce MX450"], ["nvenc_hevc"]) == "nvenc"
assert obs_client.pick_encoder(["NVIDIA GeForce MX450"], ["nvenc_hevc", "nvenc"]) == "x264"
assert obs_client.pick_encoder(["Intel(R) UHD Graphics"], ["qsv"]) == "x264"
print("fallbacks PASS")


class FakeObs(obs_client.Obs):
    """OBS as it behaves: profile changes load on the next start; an encoder that can't run on
    this PC takes the start request and then never starts the output."""
    def __init__(self, broken=(), rb_on=True, recording=False):
        super().__init__(dict(preferences.DEFAULTS))
        self.saved = {("SimpleOutput", "RecRB"): "true" if rb_on else "false",
                      ("SimpleOutput", "RecEncoder"): "nvenc_hevc", ("SimpleOutput", "StreamEncoder"): "nvenc_hevc"}
        self.loaded = dict(self.saved)        # what the running OBS uses
        self.broken, self.active, self.recording, self.restarts = set(broken), False, recording, 0
    def raw(self, req, d=None):
        if req == "GetProfileParameter": return {"parameterValue": self.saved.get((d["parameterCategory"], d["parameterName"]))}
        if req == "SetProfileParameter": self.saved[(d["parameterCategory"], d["parameterName"])] = d["parameterValue"]; return {}
        if req == "GetVideoSettings": return {"outputWidth": 1920, "outputHeight": 1080, "fpsNumerator": 60}
        return {}
    def buffer_active(self): return self.active
    def record_status(self): return self.recording, 0
    def call(self, name, *a):
        if name == "start_replay_buffer":
            if self.loaded.get(("SimpleOutput", "RecRB")) != "true":
                raise OBSSDKRequestError("StartReplayBuffer", 604, "replay buffer not enabled")
            self.active = self.loaded[("SimpleOutput", "RecEncoder")] not in self.broken
            return
        if name == "get_version": return
        raise AssertionError(name)
    def restart(self):
        self.restarts += 1; self.loaded = dict(self.saved); self.active = False


app = QtWidgets.QApplication([])
obs_client.Obs.start_buffer.__defaults__ = (0.0,)      # no real waiting in the test


def controller(obs):
    preferences.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=tempfile.mkdtemp()))
    ctl.obs = obs
    def restart():          # the real one closes and starts the OBS on this PC
        obs.restart()
        try:
            return obs.start_buffer()
        except obs_client.BufferDisabled:
            return False
    ctl.restart_obs = restart
    toasts = []; ctl.toast.connect(lambda t, k: toasts.append((k, t)))
    return ctl, toasts


# 1. switched off in OBS (a fresh OBS, or setup's change waiting for a restart): on, restart, running
ctl, toasts = controller(FakeObs(rb_on=False))
assert ctl.heal_buffer() and ctl.obs.active and ctl.obs.restarts == 1
assert ctl.obs.saved[("SimpleOutput", "RecRB")] == "true"
assert toasts == [("ok", "Turned on the OBS replay buffer")], toasts
print("buffer off in OBS PASS")

# 2. a card that says NVIDIA but can't encode (laptop GeForce MX): down to the CPU, and remembered
ctl, toasts = controller(FakeObs(broken={"nvenc_hevc", "nvenc"}))
assert ctl.heal_buffer() and ctl.obs.active and ctl.obs.restarts == 2
assert ctl.obs.saved[("SimpleOutput", "RecEncoder")] == "x264" and ctl.best_encoder == "x264"
assert json.loads(preferences.STATE_PATH.read_text())["failed_encoders"] == ["nvenc_hevc", "nvenc"]
assert toasts[-1] == ("ok", "Your graphics card couldn't record, so OBS now uses X264"), toasts
print("encoder fallback PASS")

# 3. both at once: switched off and an encoder that can't run
ctl, toasts = controller(FakeObs(rb_on=False, broken={"nvenc_hevc"}))
assert ctl.heal_buffer() and ctl.obs.saved[("SimpleOutput", "RecEncoder")] == "nvenc"
print("off + broken encoder PASS")

# 4. a manual recording is running: never restart OBS under it
ctl, toasts = controller(FakeObs(broken={"nvenc_hevc"}, recording=True))
assert not ctl.heal_buffer() and ctl.obs.restarts == 0
print("recording untouched PASS")

# 5. nothing works: one clear message, and the background check waits before trying again
ctl, toasts = controller(FakeObs(broken={"nvenc_hevc", "nvenc", "x264"}))
assert not ctl.heal_buffer()
assert toasts[-1] == ("error", "OBS can't start recording · open OBS to see why"), toasts
before = ctl.obs.restarts; ctl._watch_buffer(); assert ctl.obs.restarts == before, "waits HEAL_PAUSE"
print("gives up cleanly PASS")

# 6. already running: nothing touched
ctl, toasts = controller(FakeObs()); ctl.obs.active = True
assert ctl.heal_buffer() and ctl.obs.restarts == 0 and toasts == []
print("running PASS")

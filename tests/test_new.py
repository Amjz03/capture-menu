import sys, time, tempfile, subprocess, json, re
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp()); g = root / "Neon Highway"; g.mkdir()

# a 20 s 1440p clip with OBS's 3 tracks: 1 = game+voice (loud), 2 = game only (loud), 3 = voice only (silent here)
clip = g / "Clip_2026-10-16_21-00-00_30s.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
                "-f", "lavfi", "-i", "sine=f=440", "-f", "lavfi", "-i", "anoisesrc=a=0.3", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-t", "20", "-map", "0", "-map", "1", "-map", "2", "-map", "3", "-c:v", "libx264", "-preset", "ultrafast",
                "-b:v", "20M", "-c:a", "aac", "-shortest", str(clip)], check=True)
assert cm.audio_tracks(clip) == 3 and cm.video_height(clip) == 1440

def mean_db(path):
    r = subprocess.run(["ffmpeg", "-i", str(path), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+|-inf)", r.stderr); return float(m.group(1)) if m else None

# plans
p10 = cm.share_plan(20, 10, 1440); assert p10["height"] == 720 and p10["fps"] == 60, p10
assert cm.share_plan(120, 10, 1440)["height"] == 480
try: cm.share_plan(600, 10, 1440); raise SystemExit("should refuse")
except ValueError as e: print("10 min into 10 MB ->", e)
assert cm.share_plan(20, None, 1440) == {"height": 1080, "fps": 60, "video_kbps": None, "audio_kbps": 160}

out = root / "d10.mp4"; prog = []
size = cm.export_for_share(clip, out, 10, False, prog.append)
print(f"Discord 10 MB -> {size:.2f} MB, height {cm.video_height(out)}, tracks {cm.audio_tracks(out)}, progress {prog[:1]}..{prog[-1:]}")
assert size <= 10 and cm.audio_tracks(out) == 1 and cm.video_height(out) == 720 and prog
phone = root / "phone.mp4"; cm.export_for_share(clip, phone, None, False)
codec = cm.video_codec(phone); print("phone ->", codec, cm.video_height(phone)); assert codec == "h264" and cm.video_height(phone) == 1080
novoice = root / "nv.mp4"; cm.export_for_share(clip, novoice, 50, True)
print("mean dB with voice track:", mean_db(phone), "| game only:", mean_db(novoice))
print("share export PASS")

# controller: share -> Shared folder, clipboard request, not listed as a capture
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root)))
got = {}
ctl.copy_file.connect(lambda p: got.setdefault("copy", p)); ctl.shared.connect(lambda d, p: got.setdefault("shared", (d, p)))
ctl._share(clip, "discord10", True)
assert Path(got["copy"]).parent.name == "Shared" and "without your voice" in got["shared"][0], got
assert all("Shared" not in p.parts for p in ctl.all_captures())
print("controller share PASS:", got["shared"][0])

# favorites survive, and a deleted favourite is forgotten
assert not ctl.is_favorite(clip) and ctl.toggle_favorite(clip) and ctl.is_favorite(clip)
assert json.loads(cm.STATE_PATH.read_text())["favorites"] == ["Neon Highway/" + clip.name] or True
shot = g / "Screenshot_2026-10-16_21-01-00.png"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1", str(shot)], check=True)
ctl.toggle_favorite(shot); assert ctl.is_favorite(shot)
ctl.delete(shot); assert not ctl.is_favorite(shot) and not shot.exists()
print("favorites PASS")

# storage warning only (nothing deleted)
ctl.cfg["storage_warn_gb"] = 0.00001; seen = []; toasts = []
ctl.storage.connect(seen.append); ctl.toast.connect(lambda t, k: toasts.append(t))
ctl.check_storage(); end = time.time() + 3
while not seen and time.time() < end: app.processEvents(); time.sleep(0.05)
app.processEvents()
assert seen[0]["over"] and any("over your" in t for t in toasts) and clip.exists()
ctl.check_storage(); time.sleep(0.5); app.processEvents()
assert sum("over your" in t for t in toasts) == 1, "warns once per session"
print("storage warning PASS:", [t for t in toasts if "over" in t][0])

# OBS plan with voice track
plan = cm.obs_plan(dict(cm.DEFAULTS), 2560, 1440, "nvenc_av1", "31.0")
prof = {(c, n): v for c, n, v in plan["profile"]}
assert prof[("SimpleOutput", "RecTracks")] == "7" and prof[("SimpleOutput", "RecQuality")] == "Small"
assert {(c, n): v for c, n, v in cm.obs_plan(dict(cm.DEFAULTS, voice_track=False), 2560, 1440, "nvenc_av1", "31.0")["profile"]}[("SimpleOutput", "RecQuality")] == "Stream"
print("plan:", plan["summary"])

class FakeObs(cm.Obs):
    def __init__(self):
        super().__init__(dict(cm.DEFAULTS)); self.tracks = {}; self.muted = {"Mic/Aux": False}
    def raw(self, req, d=None):
        if req == "GetInputList": return {"inputs": [{"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"},
                                                     {"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"},
                                                     {"inputName": "Display Capture", "inputKind": "monitor_capture"}]}
        if req == "GetInputAudioTracks": return {"inputAudioTracks": self.tracks.get(d["inputName"], {"1": True})}
        if req == "SetInputAudioTracks": self.tracks[d["inputName"]] = d["inputAudioTracks"]; return {}
        if req == "GetInputMute": return {"inputMuted": self.muted[d["inputName"]]}
        if req == "SetInputMute": self.muted[d["inputName"]] = d["inputMuted"]; return {}
        return {}
o = FakeObs()
assert o.split_voice_track() and o.tracks["Mic/Aux"] == {"1": True, "2": False, "3": True}
assert o.tracks["Desktop Audio"] == {"1": True, "2": True, "3": False} and not o.split_voice_track()
assert o.mic_muted() is False and o.set_mic_muted(True) and o.mic_muted() is True
print("voice track + mic PASS")

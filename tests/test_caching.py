import sys, tempfile, subprocess, time, os
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtCore
app = QtCore.QCoreApplication([])
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp()); g = root / "G"; g.mkdir()
clip = g / "Clip_2026-10-16_21-00-00_30s.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30", "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", str(clip)], check=True)
calls = []
real = cm.media_duration
cm.media_duration = lambda p: calls.append(p) or real(p)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.lengths[clip] = cm.media_duration(clip); ctl.save_lengths()
again = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root)))
assert again.length_of(clip) == ctl.length_of(clip) and len(calls) == 1, "remembered, not measured again"
os.utime(clip, (time.time() + 5,) * 2)          # file changed -> stale entry dropped
assert cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))).length_of(clip) is None
print("lengths cache PASS")
# state cache: changes from another writer are picked up
ctl.toggle_favorite(clip); assert ctl.is_favorite(clip)
s = cm.load_state(); s["favorites"] = []; time.sleep(0.01); cm.STATE_PATH.write_text(__import__("json").dumps(s))
assert not ctl.is_favorite(clip), "file changed on disk -> re-read"
s2 = cm.load_state(); s2["x"] = 1; assert "x" not in cm.load_state(), "callers get a copy"
print("state cache PASS")
# follow tick asks OBS only when something changed (or every 10 s)
asked = []
ctl.obs = type("O", (), {"capture_monitor": lambda self, rect, only_if_missing=False: asked.append(rect)})()
ctl._following = __import__("threading").Lock()
cm.foreground_screen = lambda: {"own": False, "fullscreen": True, "rect": (0, 0, 2560, 1440), "device": "x"}
for _ in range(5): ctl._follow_tick(); time.sleep(0.05)
cm.foreground_screen = lambda: {"own": False, "fullscreen": True, "rect": (2560, 0, 6400, 2160), "device": "y"}
ctl._follow_tick(); time.sleep(0.1)
assert asked == [(0, 0, 2560, 1440), (2560, 0, 6400, 2160)], asked
print("follow throttle PASS")

# Memory and time for what main() builds at startup, then after a video was viewed and closed.
import sys, time, tempfile, subprocess, shutil, gc
from pathlib import Path
def rss():
    for l in open("/proc/self/status"):
        if l.startswith("VmRSS"): return int(l.split()[1]) // 1024
t0 = time.perf_counter()
sys.path.insert(0, sys.argv[1])
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
import capture_menu as cm
root = Path(tempfile.mkdtemp()); (root / "Game").mkdir()
clip = root / "Game" / "Clip_2026-10-16_20-00-00_30s.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "3",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
viewer = cm.Viewer(ctl); menu = cm.Menu(ctl, viewer); gallery = cm.Gallery(ctl, viewer)
settings = cm.Settings(ctl) if hasattr(cm, "Settings") else None
toast = cm.Toast(); sounds = cm.Sounds(True)
app.processEvents()
print(f"idle after startup: {rss()} MB in {round((time.perf_counter()-t0)*1000)} ms")
viewer.open([clip], 0)
end = time.time() + 2
while time.time() < end: app.processEvents()
print(f"while playing a video: {rss()} MB")
viewer.close_viewer()
if hasattr(viewer, "_drop_player"): viewer._drop_player()
for _ in range(20): app.processEvents(); QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
gc.collect()
print(f"a minute after closing it: {rss()} MB")
print("player dropped:", getattr(viewer, "player", "n/a") is None)
import ctypes
try:
    ctypes.CDLL("libc.so.6").malloc_trim(0); print(f"after giving freed heap back to the OS: {rss()} MB")
except OSError: pass

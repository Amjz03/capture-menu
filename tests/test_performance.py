import sys, tempfile, subprocess, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
import capture_menu as cm
root = Path(tempfile.mkdtemp()); (root / "Game").mkdir()
clip = root / "Game" / "Clip_2026-10-16_20-00-00_30s.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "2",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
viewer = cm.Viewer(ctl); menu = cm.Menu(ctl, viewer); gallery = cm.Gallery(ctl, viewer); snd = cm.Sounds(True)
assert cm.QtMultimedia is None and "PySide6.QtMultimedia" not in sys.modules, "no media stack at startup"
viewer.open([clip], 0)
end = time.time() + 1.5
while time.time() < end: app.processEvents()
assert viewer.player is not None and cm.QtMultimedia is not None, "made on the first video"
viewer.close_viewer(); assert viewer._drop_timer.isActive()
viewer.open([clip], 0); assert not viewer._drop_timer.isActive(), "reopening keeps it"
p = viewer.player; viewer.close_viewer(); viewer._drop_player(); assert viewer.player is None and viewer.video is None
viewer.open([clip], 0); app.processEvents(); assert viewer.player is not None and viewer.stage.currentWidget() is viewer.video, "comes back"
viewer.close_viewer()
gallery.open(); app.processEvents(); assert gallery.grid.count() == 1
gallery.close_gallery(); assert gallery.grid.count() == 0 and not gallery.tiles.cache
gallery.open(); assert gallery.grid.count() == 1, "reopens fine"
cm.trim_memory()
assert (cm.QUIET != 0) == cm.IS_WINDOWS
plan = cm.obs_plan(dict(cm.DEFAULTS), 2560, 1440, "nvenc_av1", "31.0")
cap = int({n: v for c, n, v in plan["profile"]}["RecRBSize"])
assert cap >= 8000 * 1800 / 8 / 1000 * 2.5, cap
print("perf2 PASS")

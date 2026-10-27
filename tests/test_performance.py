import sys, tempfile, subprocess, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
from capturemenu import (
    capture_controller,
    input_devices,
    media,
    obs_client,
    preferences,
    runtime,
    ui_gallery,
    ui_menu,
    ui_theme,
    ui_viewer,
)
root = Path(tempfile.mkdtemp()); (root / "Game").mkdir()
clip = root / "Game" / "Clip_2026-10-16_20-00-00_30s.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "2",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
viewer = ui_viewer.Viewer(ctl); menu = ui_menu.Menu(ctl, viewer); gallery = ui_gallery.Gallery(ctl, viewer); snd = input_devices.Sounds(True)
assert runtime.QtMultimedia is None and "PySide6.QtMultimedia" not in sys.modules, "no media stack at startup"
viewer.open([clip], 0)
end = time.time() + 1.5
while time.time() < end: app.processEvents()
assert viewer.player is not None and runtime.QtMultimedia is not None, "made on the first video"
viewer.close_viewer(); assert viewer._drop_timer.isActive()
viewer.open([clip], 0); assert not viewer._drop_timer.isActive(), "reopening keeps it"
p = viewer.player; viewer.close_viewer(); viewer._drop_player(); assert viewer.player is None and viewer.video is None
viewer.open([clip], 0); app.processEvents(); assert viewer.player is not None and viewer.stage.currentWidget() is viewer.video, "comes back"
viewer.close_viewer()
gallery.open(); app.processEvents(); assert gallery.grid.count() == 1
gallery.close_gallery(); assert gallery.grid.count() == 0 and not gallery.tiles.cache
gallery.open(); assert gallery.grid.count() == 1, "reopens fine"
assert len(gallery.tiles.cache) <= gallery.tiles.limit() and gallery.tiles.limit() >= 2
gallery.close_gallery()
# hidden pages let their native window (and its screen-sized picture) go, and make a new one on opening
created = lambda w: w.testAttribute(QtCore.Qt.WA_WState_Created)
for w in (menu, gallery): ui_theme.release_window(w); assert not created(w) and not w.dressed
viewer._drop_player(); assert not created(viewer) and not viewer.dressed
menu.show_menu(); app.processEvents(); assert menu.isVisible() and created(menu) and menu.dressed
ui_theme.release_window(menu); assert created(menu), "never while it's open"
menu.hide_menu(); gallery.open(); app.processEvents(); assert gallery.isVisible() and gallery.grid.count() == 1
gallery.close_gallery()
viewer.open([clip], 0); end = time.time() + 1
while time.time() < end: app.processEvents()
assert viewer.isVisible() and viewer.dressed and viewer.stage.currentWidget() is viewer.video, "plays again"
viewer.close_viewer(); viewer._drop_player()
ui_theme.trim_memory()
assert (media.QUIET != 0) == runtime.IS_WINDOWS
plan = obs_client.obs_plan(dict(preferences.DEFAULTS), 2560, 1440, "nvenc_av1", "31.0")
profile = {n: v for c, n, v in plan["profile"]}
assert profile["RecRB"] == "false", "the last minutes are files on the drive, not a RAM buffer (0.0.34)"
print("perf2 PASS")

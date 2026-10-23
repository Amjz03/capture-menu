import sys, os, time, tempfile, subprocess, shutil
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
import capture_menu as cm
cm.MOTION_MS = 0     # stills: the focus has already grown into place
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name, frosted, is_page
W, H = 1920, 1080
GAME = game_name("Neon Highway")
root = Path(tempfile.mkdtemp()); work = Path(tempfile.mkdtemp())
game_bg = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7))
shots = [(GAME, "Clip_2026-10-16_21-04-33_60s.mp4", "dusk", 7, 60, 30),
         (GAME, "Screenshot_2026-10-16_21-00-10.png", "neon", 3, 0, 140),
         (GAME, "Clip_2026-10-16_20-50-00_300s.mp4", "ember", 5, 300, 900),
         (game_name("Ridge Racer X"), "Recording_2026-10-16_20-00-00.mp4", "desert", 11, 754, 7200),
         (game_name("Frostfall"), "Clip_2026-10-16_19-10-00_30s.mp4", "snow", 2, 30, 9000),
         (game_name("Wildwood"), "Clip_2026-10-16_18-00-00_180s.mp4", "forest", 9, 180, 20000)]
now = time.time()
for game, name, pal, seed, secs, ago in shots:
    d = root / game; d.mkdir(exist_ok=True); dst = d / name
    png = work / f"{pal}{seed}.png"; draw_scene(1280, 720, pal, seed).save(str(png))
    if name.endswith(".png"):
        shutil.copy(png, dst)
    else:  # a short slow push-in so the filmstrip has motion
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(png), "-vf",
                        "zoompan=z='1+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30",
                        "-t", "6", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(dst)], check=True)
    os.utime(dst, (now - ago,) * 2)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
for p in ctl.recent:
    cm.make_thumb(p, ctl.thumbs_dir)
# show the lengths the clips would really have
lengths = {s[1]: s[4] for s in shots}
for p in ctl.recent:
    if p.suffix != ".png": ctl.lengths[p] = lengths[p.name]
viewer = cm.Viewer(ctl); m = cm.Menu(ctl, viewer)
m.show_menu(GAME); BH = m.BAR_H + m.HEADROOM
m.setGeometry(0, 0, W, BH); m._place(); m.refresh_recent()
status = {"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1_160_000, "recording": False, "record_ms": 0, "mic_muted": False}
m._on_status(status)
def pump(n=6):
    for _ in range(n): app.processEvents()
def compose(name, *layers):
    canvas = frosted(game_bg) if any(is_page(pm, W, H) for pm, _, _ in layers) else QtGui.QPixmap(game_bg)
    p = QtGui.QPainter(canvas)
    for pm, x, y in layers: p.drawPixmap(x, y, pm)
    p.end(); canvas.save(str(out / name))
cm.INPUT.set("playstation")
m.save_card.setFocus(); pump(); compose("1_bar.png", (m.grab(), 0, H - BH))
m.open_picker(); m._on_status(status); pump(); compose("2_save_recent.png", (m.grab(), 0, H - BH))
m.close_picker()
t = cm.Toast(); t.pad_button = "create"; t.show_capture("Last 1m", str(ctl.recent[0])); pump()
compose("3_notification.png", (t.grab(), W - t.width() - 28, 28))
t.hide(); m.activateWindow(); m.thumbs[0].setFocus(); m._on_focus(m.thumbs[0]); m.save_card.clearFocus(); m.thumbs[0].active = True; pump(); compose("4_recent.png", (m.grab(), 0, H - BH))
# viewer on the screenshot
viewer.open(ctl.recent_items(), 1); VW, VH = W, H; viewer.resize(VW, VH); viewer.show_item(); pump(10)
compose("5_viewer.png", (viewer.grab(), (W - VW) // 2, (H - VH) // 2))
# trim on the first clip; the video surface can't be captured offscreen, so show its frame instead
viewer.index = 0; viewer.show_item()
end = time.time() + 3
while time.time() < end: app.processEvents()
viewer.enter_trim()
end = time.time() + 6
while time.time() < end and len(viewer.timeline.frames) < 12: app.processEvents(); time.sleep(0.05)
viewer.timeline.set_start(1400); viewer.timeline.set_end(4600); viewer.timeline.pos = 2600
viewer.player.pause()
frame = QtGui.QPixmap(str(work / "dusk7.png"))
viewer.image.setPixmap(frame.scaled(viewer.stage.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
viewer.stage.setCurrentWidget(viewer.image); viewer.controls.show()
TH = H; viewer.resize(VW, TH); pump(10)
viewer.image.setPixmap(frame.scaled(viewer.stage.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)); pump(4)
g = viewer.grab(); print("trim grab", g.size())
compose("6_trim.png", (g, (W - VW) // 2, (H - g.height()) // 2))
# monitor -> TV notification
t.show_message("Recording this screen · SAMSUNG", "info"); pump()
compose("7_tv.png", (t.grab(), W - t.width() - 28, 28))
print("ok")

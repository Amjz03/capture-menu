import sys, os, time, tempfile, subprocess, shutil
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
import capture_menu as cm
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
W, H = 1920, 1080
root = Path(tempfile.mkdtemp()); work = Path(tempfile.mkdtemp())
game_bg = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7))
specs = [(game_name("Neon Highway"), "Clip_2026-10-16_21-04-33_60s.mp4", "dusk", 7, 60, 30, True),
         (game_name("Neon Highway"), "Screenshot_2026-10-16_21-00-10.png", "neon", 3, 0, 140, False),
         (game_name("Neon Highway"), "Clip_2026-10-16_20-50-00_300s.mp4", "ember", 5, 300, 900, False),
         (game_name("Neon Highway"), "Clip_2026-10-16_20-10-00_30s.mp4", "neon", 8, 30, 3000, True),
         (game_name("Ridge Racer X"), "Recording_2026-10-16_20-00-00.mp4", "desert", 11, 754, 7200, False),
         (game_name("Ridge Racer X"), "Clip_2026-10-15_22-00-00_180s.mp4", "desert", 4, 180, 90000, False),
         (game_name("Frostfall"), "Clip_2026-10-16_19-10-00_30s.mp4", "snow", 2, 30, 9000, True),
         (game_name("Frostfall"), "Screenshot_2026-10-14_19-10-00.png", "snow", 6, 0, 200000, False),
         (game_name("Wildwood"), "Clip_2026-10-16_18-00-00_180s.mp4", "forest", 9, 180, 20000, False),
         (game_name("Wildwood"), "Clip_2026-10-13_18-00-00_60s.mp4", "forest", 12, 60, 300000, False)]
now = time.time()
for game, name, pal, seed, secs, ago, fav in specs:
    d = root / game; d.mkdir(exist_ok=True); dst = d / name
    png = work / f"{pal}{seed}.png"; draw_scene(1280, 720, pal, seed).save(str(png))
    if name.endswith(".png"): shutil.copy(png, dst)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(png), "-f", "lavfi", "-i", "sine", "-f", "lavfi", "-i", "sine=f=600",
                        "-f", "lavfi", "-i", "sine=f=800", "-map", "0", "-map", "1", "-map", "2", "-map", "3", "-t", "3",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)], check=True)
    os.utime(dst, (now - ago,) * 2)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
for game, name, *_r, fav in specs:
    p = root / game / name; cm.make_thumb(p, ctl.thumbs_dir)
    if p.suffix != ".png": ctl.lengths[p] = [s[4] for s in specs if s[1] == name][0]
    if fav: ctl.toggle_favorite(p)
viewer = cm.Viewer(ctl); m = cm.Menu(ctl, viewer); gallery = cm.Gallery(ctl, viewer); m.gallery = gallery
ctl.last_storage = {"used_gb": 214.3, "free_gb": 812, "limit_gb": 200, "over": True, "low": False}
def pump(n=6):
    for _ in range(n): app.processEvents()
def compose(name, *layers):
    canvas = QtGui.QPixmap(game_bg); p = QtGui.QPainter(canvas)
    for pm, x, y in layers: p.drawPixmap(x, y, pm)
    p.end(); canvas.save(str(out / name))
cm.INPUT.set("playstation")
m.show_menu(game_name("Neon Highway")); BH = m.BAR_H + m.HEADROOM
m.setGeometry(0, 0, W, BH); m._place(); m.refresh_recent()
m._on_status({"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1_160_000, "recording": False, "record_ms": 0, "mic_muted": False})
m.show_storage(ctl.last_storage)
m.mic_card.setFocus(); pump(); compose("n1_bar_mic.png", (m.grab(), 0, H - BH))
m.hide_menu()
# viewer: share panel on a clip (video surface can't be grabbed offscreen, so show its frame)
items = ctl.all_captures(); viewer.open(items, 0); VW = W; viewer.resize(W, H); pump(10)
viewer.enter_share(); viewer._toggle_voice(); viewer.share_chips[2].setFocus()
frame = QtGui.QPixmap(str(work / "dusk7.png"))
viewer.image.setPixmap(frame.scaled(viewer.stage.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
viewer.stage.setCurrentWidget(viewer.image); pump(10)
g = viewer.grab(); compose("n2_share.png", (g, (W - VW) // 2, (H - g.height()) // 2))
viewer.close_viewer()
# toast after sharing
t = cm.Toast(); t.thumbs_dir = ctl.thumbs_dir
t.show_shared("Discord · 10 MB · 9.1 MB · without your voice", str(items[0])); pump()
compose("n3_shared.png", (t.grab(), W - t.width() - 28, 28))
# gallery
gallery.open(game_name("Neon Highway")); GW, GH = W, H; gallery.resize(GW, GH); gallery._load(game_name("Neon Highway")); pump(10)
gallery.grid.setCurrentRow(0); pump(5)
compose("n4_gallery.png", (gallery.grab(), (W - GW) // 2, (H - GH) // 2))
gallery.games.setCurrentRow(1); pump(10)
compose("n5_favorites.png", (gallery.grab(), (W - GW) // 2, (H - GH) // 2))
print("ok")

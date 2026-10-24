import sys, time, tempfile, subprocess, os, shutil, resource, hashlib, statistics
from pathlib import Path
T0 = time.perf_counter()
sys.path.insert(0, sys.argv[1]); N = int(sys.argv[2])
from capturemenu import capture_controller, catalog, preferences, ui_gallery, ui_menu, ui_notices, ui_viewer
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
t_import = time.perf_counter() - T0
app = QtWidgets.QApplication([])
preferences.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp())
# N captures across 12 games: one real clip/png copied around; thumbnails pre-made (as after first use)
seed_clip = root / "seed.mp4"; seed_png = root / "seed.png"; seed_jpg = root / "seed.jpg"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "1", "-c:v", "libx264", "-preset", "ultrafast", str(seed_clip)], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1", str(seed_png)], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(seed_png), "-vf", "scale=480:-2", str(seed_jpg)], check=True)
(root / ".thumbs").mkdir()
now = time.time()
for i in range(N):
    g = root / f"Game {i % 12}"; g.mkdir(exist_ok=True)
    p = g / (f"Screenshot_2026-10-{i:04d}.png" if i % 5 == 0 else f"Clip_2026-10-16_{i:06d}_30s.mp4")
    shutil.copy(seed_png if p.suffix == ".png" else seed_clip, p); os.utime(p, (now - i * 60,) * 2)
    shutil.copy(seed_jpg, root / ".thumbs" / (hashlib.md5(str(p).encode()).hexdigest() + ".jpg"))
seed_clip.unlink(); seed_png.unlink(); seed_jpg.unlink()
def ms(fn, reps=1):
    out = []
    for _ in range(reps):
        t = time.perf_counter(); fn(); app.processEvents(); out.append((time.perf_counter() - t) * 1000)
    return statistics.median(out)
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
r = {}
t = time.perf_counter()
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
viewer = ui_viewer.Viewer(ctl); menu = ui_menu.Menu(ctl, viewer); gallery = ui_gallery.Gallery(ctl, viewer); menu.gallery = gallery
toast = ui_notices.Toast(); toast.thumbs_dir = ctl.thumbs_dir
r["startup (windows built)"] = (time.perf_counter() - t) * 1000
r["  of which: scan all captures"] = ms(ctl._scan_recent)
r["open bar"] = ms(lambda: (menu.show_menu("Game 0"), menu.setGeometry(0, 0, 1920, 296), menu._place()), 5)
r["  bar repaint"] = ms(lambda: menu.grab(), 10)
r["close bar"] = ms(menu.hide_menu, 5)
cap = ctl.all_captures()[1]
r["notification"] = ms(lambda: toast.show_capture("Last 30 sec", str(cap)), 5)
mem_before = rss()
for p in ctl.all_captures():
    if p.suffix != ".png": ctl.lengths[p] = 1.0   # lengths already known
r["open gallery (All)"] = ms(lambda: gallery.open(), 1)
r["  memory added by gallery (MB)"] = rss() - mem_before
r["switch game in gallery"] = ms(lambda: gallery.step_game(1), 5)
r["sort by size"] = ms(gallery.toggle_sort, 1)
r["select all"] = ms(gallery.mark_all, 1)
gallery.clear_marks(); gallery.close_gallery()
r["open viewer"] = ms(lambda: viewer.open(ctl.all_captures(), 0), 1)
viewer.close_viewer()
r["storage check (walk folder)"] = ms(lambda: catalog.folder_size_gb(root), 3)
r["peak memory (MB)"] = rss()
for k, v in r.items(): print(f"{k:34s} {v:8.0f}")
print(f"{'python + Qt import':34s} {t_import * 1000:8.0f}")

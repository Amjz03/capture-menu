"""Renders the README poster: three games side by side with the real Create bar and notice over them.

    set QT_QPA_PLATFORM=offscreen
    set CAPTURE_MENU_SHOTS=<folder of game screenshots>   (optional, see scene.py)
    py -3 tools/render_poster.py <repo folder> <out folder>
"""
import sys, os, time, tempfile, shutil
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
import capture_menu as cm
cm.MOTION_MS = 0     # stills: the focus has already grown into place
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QRectF, QPointF
app = QtWidgets.QApplication([])
for f in ("SegUIVar.ttf", "segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):   # offscreen Qt doesn't see system fonts
    QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / f))
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
W, H = 1920, 960                    # 2:1, so it also works as GitHub's social preview
GAME = game_name("Neon Highway")
# (mockup game, palette, seed, where the picture's subject is (0..1 across, down), zoom)
PANELS = [("Neon Highway", "dusk", 7, 0.50, 0.5, 1.0), ("Ridge Racer X", "desert", 4, 0.40, 0.62, 1.45),
          ("Frostfall", "snow", 2, 0.60, 0.5, 1.0)]
root = Path(tempfile.mkdtemp()); work = Path(tempfile.mkdtemp()); now = time.time()
for i, (game, pal, seed, *_) in enumerate(PANELS * 2):
    d = root / game_name(game); d.mkdir(exist_ok=True)
    png = work / f"{pal}{seed}.png"; draw_scene(1280, 720, pal, seed).save(str(png))
    dst = d / f"Screenshot_2026-10-16_2{i}-00-00.png"; shutil.copy(png, dst); os.utime(dst, (now - 30 - 600 * i,) * 2)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
for p in ctl.recent:
    cm.make_thumb(p, ctl.thumbs_dir)


def pump(n=6):
    for _ in range(n): app.processEvents()


cm.INPUT.set("playstation")
m = cm.Menu(ctl, cm.Viewer(ctl)); m.show_menu(GAME); BH = m.BAR_H + m.HEADROOM
m.setGeometry(0, 0, W, BH); m._place(); m.refresh_recent()
m._on_status({"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1_160_000, "recording": False,
              "record_ms": 0, "mic_muted": False})
m.save_card.setFocus(); pump(); bar = m.grab()
t = cm.Toast(); t.thumbs_dir = ctl.thumbs_dir; t.pad_button = "create"
t.show_capture("", str(ctl.recent[0])); pump(); toast = t.grab()

img = QtGui.QImage(W, H, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor(*cm.NIGHT))
p = QtGui.QPainter(img)
for hint in (QtGui.QPainter.Antialiasing, QtGui.QPainter.SmoothPixmapTransform, QtGui.QPainter.TextAntialiasing):
    p.setRenderHint(hint)
SKEW, GAP = 150, 14
edges = [-SKEW, W / 3, 2 * W / 3, W + SKEW]          # where the slices meet, at mid height
for i, (game, pal, seed, fx, fy, zoom) in enumerate(PANELS):
    a, b = edges[i] + (GAP / 2 if i else 0), edges[i + 1] - (GAP / 2 if i < 2 else 0)
    slice_ = QtGui.QPolygonF([QPointF(a + SKEW / 2, 0), QPointF(b + SKEW / 2, 0), QPointF(b - SKEW / 2, H), QPointF(a - SKEW / 2, H)])
    shot = draw_scene(int(H * zoom * 16 / 9), int(H * zoom), pal, seed, hud=False)
    box = slice_.boundingRect()
    x = min(max(shot.width() * fx - box.width() / 2, 0), shot.width() - box.width())
    y = min(max(shot.height() * fy - H / 2, 0), shot.height() - H)
    path = QtGui.QPainterPath(); path.addPolygon(slice_)
    p.save(); p.setClipPath(path); p.drawImage(box, shot, QRectF(x, y, box.width(), H)); p.restore()
    # the game's name, like a PS5 tile
    p.setFont(cm.font(26, QtGui.QFont.DemiBold, display=True))
    name = game_name(game); tw = p.fontMetrics().horizontalAdvance(name)
    cx = (a + b) / 2 - SKEW * 0.12; pill = QRectF(cx - tw / 2 - 22, H - BH - 74, tw + 44, 50)
    p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(7, 10, 20, 170)); p.drawRoundedRect(pill, 25, 25)
    p.setPen(QtGui.QColor(cm.INK)); p.drawText(pill, Qt.AlignCenter, name)
shade = QtGui.QLinearGradient(0, 0, 0, H)
for at, alpha in ((0, 240), (0.14, 200), (0.3, 60), (0.42, 0), (0.6, 60), (1, 235)):
    shade.setColorAt(at, QtGui.QColor(*cm.NIGHT, alpha))
p.fillRect(img.rect(), shade)
p.drawImage(QRectF(72, 56, 92, 92), QtGui.QImage(str(Path(sys.argv[1]) / "docs" / "icon.png")))
p.setPen(QtGui.QColor(cm.INK)); p.setFont(cm.font(72, QtGui.QFont.Bold, display=True))
p.drawText(QRectF(188, 44, 1000, 90), Qt.AlignLeft | Qt.AlignVCenter, "Capture Menu")
p.setPen(QtGui.QColor(255, 255, 255, 200)); p.setFont(cm.font(30, QtGui.QFont.Normal, display=True))
p.drawText(QRectF(190, 128, 1200, 44), Qt.AlignLeft | Qt.AlignVCenter, "The PS5 Create button, on your PC")
p.drawPixmap(W - toast.width() - 48, 52, toast)
p.drawPixmap(0, H - BH, bar)
p.end()
img.save(str(out / "poster.png"))
print("ok", img.size(), "bar", BH)

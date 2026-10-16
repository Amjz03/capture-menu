import sys, tempfile, subprocess
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2])
import capture_menu as cm
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene
root = Path(tempfile.mkdtemp()); work = Path(tempfile.mkdtemp())
thumbs = root / ".thumbs"; thumbs.mkdir()
def capture(game, name, pal, seed):
    d = root / game; d.mkdir(exist_ok=True); p = d / name
    png = work / f"{pal}{seed}.png"; draw_scene(1280, 720, pal, seed).save(str(png))
    if name.endswith(".png"):
        png.rename(p)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(png), "-t", "1", "-c:v", "libx264",
                        "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p)], check=True)
    return str(p)
clip = capture("Neon Highway", "Clip_2026-10-16_21-04-33_30s.mp4", "dusk", 7)
shot = capture("Neon Highway", "Screenshot_2026-10-16_21-00-10.png", "neon", 3)
rec = capture("Neon Highway", "Recording_2026-10-16_20-00-00.mp4", "ember", 5)
trim = capture("Neon Highway", "Clip_2026-10-16_21-10-00_trim.mp4", "desert", 11)
share = capture("Neon Highway", "Clip_2026-10-16_21-04-33_30s_discord10.mp4", "dusk", 7)

def toast(setup):
    t = cm.Toast(); t.thumbs_dir = thumbs; t.hotkey = "ALT+C"; t.pad_button = "create"
    setup(t)
    for _ in range(4): app.processEvents()
    return t.grab()

rows = [
    ("حفظ مقطع (يد بلايستيشن)", "playstation", lambda t: t.show_capture("Last 30 sec", clip)),
    ("حفظ مقطع (يد إكسبوكس)", "xbox", lambda t: t.show_capture("Last 30 sec", clip)),
    ("حفظ مقطع (كيبورد)", "keyboard", lambda t: t.show_capture("Last 30 sec", clip)),
    ("حفظ كل المسجّل", "playstation", lambda t: t.show_capture("Everything · 30:00", clip)),
    ("صورة", "playstation", lambda t: t.show_capture("", shot)),
    ("تسجيل يدوي انتهى", "playstation", lambda t: t.show_capture("Length 12:34", rec)),
    ("مقطع مقصوص", "playstation", lambda t: t.show_capture("Length 00:07", trim)),
    ("جاهز للمشاركة", "playstation", lambda t: t.show_shared("Discord · 10 MB · 9.1 MB · without your voice", share)),
    ("أثناء الحفظ", "keyboard", lambda t: t.show_message("Saving…", "info")),
    ("أثناء تجهيز المشاركة", "keyboard", lambda t: t.show_message("Preparing for Discord · 10 MB · 40%", "info")),
    ("بدأ التسجيل", "keyboard", lambda t: t.show_message("Recording started · open the menu and choose Stop to finish", "rec")),
    ("إطفاء الميكروفون", "keyboard", lambda t: t.show_message("Mic off · your voice won't be recorded", "info")),
    ("انتقل التسجيل للتلفزيون", "keyboard", lambda t: t.show_message("Recording this screen · SAMSUNG", "info")),
    ("البرنامج جاهز", "keyboard", lambda t: t.show_message("Capture Menu is ready · press ALT+C", "ok")),
    ("تنبيه المساحة", "keyboard", lambda t: t.show_message("Captures use 214 GB, over your 200 GB limit · delete some in the gallery", "error")),
    ("نص طويل بدون فواصل (يلتف لسطرين)", "keyboard", lambda t: t.show_message("Couldn't set up OBS automatically, see the README for the manual steps and try again later", "error")),
    ("OBS مقفل", "keyboard", lambda t: t.show_message("Can't reach OBS · make sure it's running, then try again", "error")),
]
shots = []
for label, mode, fn in rows:
    cm.INPUT.set(mode); shots.append((label, toast(fn)))

W, colw, pad, gap = 1920, 940, 28, 18
col_items = [shots[:8], shots[8:]]
heights = [sum(pm.height() + 30 + gap for _, pm in col) for col in col_items]
H = max(heights) + pad * 2 + 70
bg = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7, hud=False))
p = QtGui.QPainter(bg); p.setRenderHint(QtGui.QPainter.Antialiasing)
p.fillRect(0, 0, W, H, QtGui.QColor(0, 0, 0, 90))
f = QtGui.QFont("Noto Sans Arabic UI"); f.setPixelSize(30); f.setBold(True); p.setFont(f); p.setPen(QtGui.QColor("white"))
p.drawText(QtCore.QRect(0, pad, W, 44), Qt.AlignCenter, "كل إشعارات البرنامج")
f.setPixelSize(17); f.setBold(False); p.setFont(f)
for ci, col in enumerate(col_items):
    x0 = W - pad - colw - ci * (colw + 2 * pad) + 2 * pad if ci == 0 else pad
    x0 = W // 2 + pad // 2 if ci == 0 else W // 2 - colw - pad // 2
    y = pad + 70
    for label, pm in col:
        p.setPen(QtGui.QColor(255, 255, 255, 200))
        p.drawText(QtCore.QRect(x0, y, colw, 26), Qt.AlignRight | Qt.AlignVCenter, label)
        y += 30
        p.drawPixmap(x0 + colw - pm.width(), y, pm)
        y += pm.height() + gap
p.end(); bg.save(str(out / "toasts_all.png")); print("ok", W, H)

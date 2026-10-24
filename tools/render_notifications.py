import sys, tempfile, subprocess
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2])
from capturemenu import input_devices, ui_notices, ui_theme
ui_theme.MOTION_MS = 0     # stills: the focus has already grown into place
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
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
clip = capture(game_name("Neon Highway"), "Clip_2026-10-16_21-04-33_30s.mp4", "dusk", 7)
shot = capture(game_name("Neon Highway"), "Screenshot_2026-10-16_21-00-10.png", "neon", 3)
rec = capture(game_name("Neon Highway"), "Recording_2026-10-16_20-00-00.mp4", "ember", 5)
trim = capture(game_name("Neon Highway"), "Clip_2026-10-16_21-10-00_trim.mp4", "desert", 11)
share = capture(game_name("Neon Highway"), "Clip_2026-10-16_21-04-33_30s_discord10.mp4", "dusk", 7)

def toast(setup):
    t = ui_notices.Toast(); t.thumbs_dir = thumbs; t.hotkey = "ALT+C"; t.pad_button = "create"
    setup(t)
    for _ in range(4): app.processEvents()
    return t.grab()

rows = [
    ("Clip saved (PlayStation controller)", "playstation", lambda t: t.show_capture("Last 30 sec", clip)),
    ("Clip saved (Xbox controller)", "xbox", lambda t: t.show_capture("Last 30 sec", clip)),
    ("Clip saved (keyboard)", "keyboard", lambda t: t.show_capture("Last 30 sec", clip)),
    ("Everything saved", "playstation", lambda t: t.show_capture("Everything · 30:00", clip)),
    ("Screenshot", "playstation", lambda t: t.show_capture("", shot)),
    ("Recording finished", "playstation", lambda t: t.show_capture("Length 12:34", rec)),
    ("Trimmed clip", "playstation", lambda t: t.show_capture("Length 00:07", trim)),
    ("Ready to share", "playstation", lambda t: t.show_shared("Discord · 10 MB · 9.1 MB · without your voice", share)),
    ("Saving", "keyboard", lambda t: t.show_message("Saving…", "info")),
    ("Preparing a share copy", "keyboard", lambda t: t.show_message("Preparing for Discord · 10 MB · 40%", "info")),
    ("Recording started", "keyboard", lambda t: t.show_message("Recording started · open the menu and choose Stop to finish", "rec")),
    ("Mic off", "keyboard", lambda t: t.show_message("Mic off · your voice won't be recorded", "info")),
    ("Capture moved to the TV", "keyboard", lambda t: t.show_message("Recording this screen · SAMSUNG", "info")),
    ("Ready", "keyboard", lambda t: t.show_message("Capture Menu is ready · press ALT+C", "ok")),
    ("Storage warning", "keyboard", lambda t: t.show_message("Captures use 214 GB, over your 200 GB limit · delete some in the gallery", "error")),
    ("Long message (wraps to two lines)", "keyboard", lambda t: t.show_message("Couldn't set up OBS automatically, see the README for the manual steps and try again later", "error")),
    ("OBS is closed", "keyboard", lambda t: t.show_message("Can't reach OBS · make sure it's running, then try again", "error")),
]
shots = []
for label, mode, fn in rows:
    input_devices.input_mode().set(mode); shots.append((label, toast(fn)))

size = lambda pm: pm.deviceIndependentSize().toSize()   # grabs come at the screen's scale
W, colw, pad, gap = 1920, 940, 28, 18
col_items = [shots[:8], shots[8:]]
heights = [sum(size(pm).height() + 30 + gap for _, pm in col) for col in col_items]
H = max(heights) + pad * 2 + 70
bg = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7, hud=False))
p = QtGui.QPainter(bg); p.setRenderHint(QtGui.QPainter.Antialiasing)
p.fillRect(0, 0, W, H, QtGui.QColor(0, 0, 0, 90))
f = QtGui.QFont("Segoe UI"); f.setPixelSize(30); f.setBold(True); p.setFont(f); p.setPen(QtGui.QColor("white"))
p.drawText(QtCore.QRect(0, pad, W, 44), Qt.AlignCenter, "Every notification")
f.setPixelSize(17); f.setBold(False); p.setFont(f)
for ci, col in enumerate(col_items):
    x0 = W - pad - colw - ci * (colw + 2 * pad) + 2 * pad if ci == 0 else pad
    x0 = W // 2 + pad // 2 if ci == 0 else W // 2 - colw - pad // 2
    y = pad + 70
    for label, pm in col:
        p.setPen(QtGui.QColor(255, 255, 255, 200))
        p.drawText(QtCore.QRect(x0, y, colw, 26), Qt.AlignRight | Qt.AlignVCenter, label)
        y += 30
        p.drawPixmap(x0 + colw - size(pm).width(), y, pm)
        y += size(pm).height() + gap
p.end(); bg.save(str(out / "toasts_all.png")); print("ok", W, H)

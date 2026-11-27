"""The ride: the README animation and the website's feature video. The app's real screens (the bar,
Save recent, the notices) over the misty Red Dead Redemption 2 ride in site/assets/hero-bg.mp4,
with the steps written over it, the keys pressed and a mouse pointer.

    set QT_QPA_PLATFORM=offscreen
    py -3 tools/render_ride.py <repo folder> <out folder> [en|ar]

Writes ride-<lang>.mp4 (1920 x 1080, 30 FPS). Needs ffmpeg on PATH.
"""
import os, sys, subprocess, tempfile, time, math
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(exist_ok=True)
LANG = sys.argv[3] if len(sys.argv) > 3 else "en"
sys.path.insert(0, str(repo))
from capturemenu import language
language.set_language(LANG)
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt, QRectF, QPointF
app = QtWidgets.QApplication([])
for f in ("SegUIVar.ttf", "segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):     # offscreen Qt doesn't see system fonts
    QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / f))
if LANG == "ar":
    app.setLayoutDirection(Qt.RightToLeft)
from capturemenu import capture_controller, input_devices, media, preferences, ui_menu, ui_notices, ui_theme, ui_viewer
ui_theme.MOTION_MS = 0
preferences.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
W, H, FPS = 1920, 1080, 30
GAME = "Red Dead Redemption 2"
AR = LANG == "ar"
T = {   # the words over the video
    "en": dict(s1="STEP 1 OF 3  ·  RED DEAD REDEMPTION 2  ·  MOUSE & KEYBOARD", h1=("Press ", "Alt", " + C"),
               s2="STEP 2 OF 3", h2=("Pick ", "how much", " to keep."),
               s3="STEP 3 OF 3", h3=("Saved. ", "View, trim", " or share it."),
               s4="KEYBOARD  ·  THE QUICK WAY", h4=("Press Alt + C ", "twice", ""),
               h5=("Last ", "30", " seconds: saved."), sub5="The menu never opened."),
    "ar": dict(s1="الخطوة 1 من 3  ·  RED DEAD REDEMPTION 2  ·  الماوس والكيبورد", h1=("اضغط ", "Alt", " + C"),
               s2="الخطوة 2 من 3", h2=("اختر ", "كم", " تحفظ."),
               s3="الخطوة 3 من 3", h3=("انحفظ. ", "اعرضه أو قصّه", " أو شاركه."),
               s4="الكيبورد  ·  الطريقة السريعة", h4=("اضغط Alt + C ", "مرتين", ""),
               h5=("آخر ", "30", " ثانية: انحفظت."), sub5="القائمة ما انفتحت."),
}[LANG]

# ---- the ride, frame by frame
ffmpeg = "ffmpeg"
frames_dir = Path(tempfile.mkdtemp())
subprocess.run([ffmpeg, "-v", "error", "-i", str(repo / "site" / "assets" / "hero-bg.mp4"), "-vf", f"fps={FPS},scale={W}:{H}",
                str(frames_dir / "f%04d.jpg")], check=True)
ride = sorted(frames_dir.glob("f*.jpg"))
N = len(ride)

# ---- captures from the ride, so the bar's recent captures and the strip are the same game
root = Path(tempfile.mkdtemp()); work = Path(tempfile.mkdtemp())
d = root / GAME; d.mkdir()
now = time.time()
specs = [("Clip_2026-11-27_21-04-33_60s.mp4", 60, 30, 40), ("Screenshot_2026-11-27_21-00-10.png", 0, 140, 160),
         ("Clip_2026-11-27_20-50-00_300s.mp4", 300, 900, 250), ("Recording_2026-11-27_20-00-00.mp4", 754, 7200, 330)]
for name, secs, ago, fi in specs:
    src = ride[min(fi, N - 1)]
    dst = d / name
    if name.endswith(".png"):
        QtGui.QImage(str(src)).save(str(dst))
    else:
        subprocess.run([ffmpeg, "-v", "error", "-y", "-loop", "1", "-i", str(src), "-t", "2", "-vf", "scale=1280:720",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(dst)], check=True)
    os.utime(dst, (now - ago,) * 2)
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
ctl.buffer_picture_at = lambda *a: None
for p in ctl.recent:
    media.make_thumb(p, ctl.thumbs_dir)
    if p.suffix != ".png":
        ctl.lengths[p] = next(s[1] for s in specs if s[0] == p.name)
viewer = ui_viewer.Viewer(ctl); m = ui_menu.Menu(ctl, viewer)
input_devices.input_mode().set("keyboard")
status = {"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1_800_000, "recording": False,
          "record_ms": 0, "mic_muted": False}


def pump(n=8):
    for _ in range(n):
        app.processEvents()


# ---- the screens, grabbed once
m.show_menu(GAME); BH = m.BAR_H + m.HEADROOM
m.setGeometry(0, 0, W, BH); m._place(); m.refresh_recent(); m._on_status(status)
m.save_card.setFocus(); pump()
bar = m.grab()
pump(); m.bar.layout().activate(); pump()
save_center = m.save_card.mapTo(m, m.save_card.tile().center().toPoint())
print("save", save_center, m.save_card.geometry(), m.bar.geometry(), flush=True)
save_pt = QPointF(save_center.x(), save_center.y() + H - BH)
strip_pics = [str(ride[min(int(i * N / 30), N - 1)]) for i in range(30)]


def fake_frames():
    held = 1800
    m._on_frames([(m._pick_now - held + i * 60, m._pick_now - held + (i + 1) * 60, strip_pics[i]) for i in range(30)])


ctl.load_buffer_frames = fake_frames
m.open_picker(); m._on_status(status); pump()
m.setGeometry(0, 0, W, H); m._place(); pump()
i60 = m.options.index(60)
chip = m.chips[i60]
m.preview.set_picture(str(ride[min(N - 1, int(N * 0.92))])); pump()
picker_rest = m.grab()
chip_center = chip.mapTo(m, chip.rect().center())
chip_pt = QPointF(chip_center.x(), chip_center.y())
m._chip_clicked(60); chip.setFocus(); m.preview.set_picture(str(ride[min(N - 1, int(N * 0.92))])); pump()
picker_armed = m.grab()
m.hide_menu()

toast = ui_notices.Toast(); toast.thumbs_dir = ctl.thumbs_dir
clip = str(ctl.recent[0])
toast.show_capture(language.tr("Last {length}", length=language.duration_label(60, short=True)), clip); pump()
toast_1m = toast.grab()
toast.hide(); toast._burst = 0
toast.show_capture(language.tr("Last {length}", length=language.duration_label(30, short=True)), clip); pump()
toast_30 = toast.grab()


# ---- drawing helpers
def ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def fade(t, a, b, d=0.25):
    """1 inside [a, b], fading in and out over d seconds."""
    if t < a - d or t > b + d:
        return 0.0
    return min(1.0, ease((t - (a - d)) / d) if t < a else 1.0, ease(((b + d) - t) / d) if t > b else 1.0)


def font(px, bold=False):
    f = QtGui.QFont(["Segoe UI Variable Display", "Segoe UI"]); f.setPixelSize(px); f.setWeight(QtGui.QFont.Bold if bold else QtGui.QFont.Normal)
    return f


def caption(p, small, parts, alpha, sub="", maxw=1300):
    """The step: a small line with a red dot, then the heading (its middle part red), wrapped to maxw."""
    if alpha <= 0:
        return
    p.save(); p.setOpacity(alpha)
    x0, y = 64, 64
    p.setFont(font(22, True)); p.setPen(QtGui.QColor(236, 240, 250, 200))
    sw = p.fontMetrics().horizontalAdvance(small)
    p.drawText(QRectF(W - x0 - 22 - sw if AR else x0 + 22, y - 26, sw + 4, 30), Qt.AlignVCenter | Qt.AlignLeft, small)
    p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(ui_theme.RED))
    p.drawEllipse(QPointF(W - x0 - 6 if AR else x0 + 6, y - 11), 6, 6)
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;")
    html = (f'<div style="font-family:\'Segoe UI\'; font-size:64px; font-weight:700; color:{ui_theme.INK}">{esc(parts[0])}'
            f'<span style="color:{ui_theme.RED}">{esc(parts[1])}</span>{esc(parts[2])}</div>')
    if sub:
        html += f'<div style="font-family:\'Segoe UI\'; font-size:26px; color:rgba(236,240,250,0.8)">{esc(sub)}</div>'
    doc = QtGui.QTextDocument(); doc.setDocumentMargin(0)
    opt = doc.defaultTextOption(); opt.setTextDirection(Qt.RightToLeft if AR else Qt.LeftToRight)
    opt.setAlignment(Qt.AlignRight if AR else Qt.AlignLeft); doc.setDefaultTextOption(opt)
    doc.setHtml(html); doc.setTextWidth(maxw)
    p.translate(W - x0 - maxw if AR else x0, y + 4); doc.drawContents(p)
    p.restore()

def keycap(p, x, y, label, pressed, scale=1.0):
    w = (len(label) * 26 + 46) * scale; h = 74 * scale
    r = QRectF(x, y + (6 * scale if pressed else 0), w, h - 6 * scale)
    p.setPen(Qt.NoPen)
    if not pressed:
        p.setBrush(QtGui.QColor(150, 156, 170)); p.drawRoundedRect(QRectF(x, y + 6 * scale, w, h - 6 * scale), 14 * scale, 14 * scale)
    p.setBrush(QtGui.QColor("#f4f6fb" if not pressed else "#d9dde6")); p.drawRoundedRect(r, 14 * scale, 14 * scale)
    p.setPen(QtGui.QColor(ui_theme.DARK)); p.setFont(font(int(30 * scale), True))
    p.drawText(r, Qt.AlignCenter, label)
    return w


def keys(p, cx, cy, pressed, count="", alpha=1.0, scale=1.0):
    if alpha <= 0:
        return
    p.save(); p.setOpacity(alpha)
    wa, wc = (3 * 26 + 46) * scale, (26 + 46) * scale
    plus, tail = 44 * scale, (100 * scale if count else 0)
    total = wa + plus + wc + tail + 48 * scale
    box = QRectF(cx - total / 2, cy - 64 * scale, total, 128 * scale)
    p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(*ui_theme.NIGHT, 200)); p.drawRoundedRect(box, 24 * scale, 24 * scale)
    x = box.left() + 24 * scale; y = cy - 37 * scale
    x += keycap(p, x, y, "Alt", pressed, scale)
    p.setPen(QtGui.QColor(236, 240, 250, 200)); p.setFont(font(int(34 * scale), True))
    p.drawText(QRectF(x, y, plus, 74 * scale), Qt.AlignCenter, "+"); x += plus
    x += keycap(p, x, y, "C", pressed, scale)
    if count:
        p.setPen(QtGui.QColor(ui_theme.RED if count == "×2" else "#a7aec0")); p.setFont(font(int(46 * scale), True))
        p.drawText(QRectF(x + 8 * scale, y, tail, 74 * scale), Qt.AlignCenter, count)
    p.restore()


ARROW = QtGui.QPolygonF([QPointF(0, 0), QPointF(0, 34), QPointF(9, 26), QPointF(15, 40), QPointF(21, 37), QPointF(15, 24), QPointF(27, 24)])


def cursor(p, pt, down):
    p.save(); p.translate(pt); s = 0.9 if down else 1.0; p.scale(s * 1.25, s * 1.25)
    p.setPen(QtGui.QPen(QtGui.QColor("black"), 2)); p.setBrush(QtGui.QColor("white")); p.drawPolygon(ARROW)
    p.restore()


def lerp(a, b, x):
    x = ease(x)
    return QPointF(a.x() + (b.x() - a.x()) * x, a.y() + (b.y() - a.y()) * x)


# ---- the story (seconds)
DUR = N / FPS
start_pt = QPointF(W * 0.62, H * 0.55)


def frame(i):
    t = i / FPS
    img = QtGui.QImage(str(ride[i])).convertToFormat(QtGui.QImage.Format_RGB32)
    p = QtGui.QPainter(img); p.setRenderHint(QtGui.QPainter.Antialiasing); p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    # 1. Press Alt + C: the bar slides up, the pointer goes to Save recent
    keys(p, 300 if not AR else W - 300, H - 150, 0.5 < t < 0.75, alpha=fade(t, 0.3, 0.95, 0.2), scale=0.8)
    if 0.75 <= t < 2.75:
        k = ease((t - 0.75) / 0.3)
        p.drawPixmap(0, int(H - BH + (1 - k) * BH), bar)
    if 1.2 <= t < 2.75:
        pt = lerp(start_pt, save_pt, (t - 1.2) / 0.9)
        cursor(p, pt, 2.3 < t < 2.45)
    # 2. Save recent fills the screen: one click picks 1 min, a second one saves
    if 2.75 <= t < 5.0:
        a = ease((t - 2.75) / 0.25)
        p.setOpacity(a); p.drawPixmap(0, 0, picker_armed if t >= 3.95 else picker_rest); p.setOpacity(1)
        pt = lerp(save_pt, chip_pt, (t - 2.9) / 0.8)
        cursor(p, pt, 3.85 < t < 4.0 or 4.6 < t < 4.75)
    # 3. Saved: the notice, with View, Trim and Share
    tw = toast_1m.width(); tx = 28 if AR else W - tw - 28
    if 5.0 <= t < 7.3:
        k = ease((t - 5.0) / 0.3); p.setOpacity(fade(t, 5.25, 7.0)); p.drawPixmap(int(tx + (1 - k) * (-48 if AR else 48)), 28, toast_1m); p.setOpacity(1)
    # 4. Alt + C twice: the last 30 seconds, without the menu
    c4 = fade(t, 7.5, 8.9, 0.2)
    count = "×2" if t >= 8.4 else "×1"
    keys(p, W / 2, H / 2, (7.85 < t < 8.05) or (8.3 < t < 8.5), count, fade(t, 7.6, DUR - 0.6, 0.25))
    if t >= 8.7:
        k = ease((t - 8.7) / 0.3); p.setOpacity(min(1.0, (t - 8.7) / 0.25)); p.drawPixmap(int(tx + (1 - k) * (-48 if AR else 48)), 28, toast_30); p.setOpacity(1)
    # the words go over everything (beside the picture while Save recent fills the screen)
    caption(p, T["s1"], T["h1"], fade(t, 0.3, 2.5))
    caption(p, T["s2"], T["h2"], fade(t, 3.0, 4.7), maxw=340)
    caption(p, T["s3"], T["h3"], fade(t, 5.1, 6.8), maxw=1100)
    caption(p, T["s4"], T["h4"], c4)
    caption(p, T["s4"], T["h5"], fade(t, 9.2, DUR), T["sub5"])
    p.end()
    return img


enc = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(out / f"ride-{LANG}.mp4")],
                       stdin=subprocess.PIPE)
for i in range(N):
    img = frame(i)
    enc.stdin.write(bytes(img.constBits())[: W * H * 4])
enc.stdin.close(); enc.wait()
print("ride", LANG, N, "frames", round(N / FPS, 1), "s")

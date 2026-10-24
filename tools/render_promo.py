"""Renders a ~20 second promo video from the real app screens over game shots: a 16:9 one
(for YouTube, Reddit, the README) and a 9:16 one (for TikTok, Shorts, Reels).

    set QT_QPA_PLATFORM=offscreen
    set CAPTURE_MENU_SHOTS=<folder of game screenshots>   (optional, see scene.py)
    py -3 tools/render_promo.py <repo folder> <out folder>
"""
import sys, os, time, tempfile, subprocess, shutil
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
from capturemenu import (
    capture_controller,
    input_devices,
    media,
    preferences,
    ui_menu,
    ui_notices,
    ui_theme,
    ui_viewer,
)
ui_theme.MOTION_MS = 0     # stills: the focus has already grown into place
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt, QRectF
app = QtWidgets.QApplication([])
for f in ("SegUIVar.ttf", "segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):   # offscreen Qt doesn't see system fonts
    QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / f))
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
preferences.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
W, H, FPS = 1920, 1080, 30
VW, VH = 1080, 1920
GAME = game_name("Neon Highway")
root = Path(tempfile.mkdtemp()); work = Path(tempfile.mkdtemp())

# ---- captures for the bar and the viewer (three audio tracks, so the sound panel opens)
specs = [(GAME, "Clip_2026-10-16_21-04-33_60s.mp4", "dusk", 7, 60, 30),
         (GAME, "Screenshot_2026-10-16_21-00-10.png", "neon", 8, 0, 140),
         (GAME, "Clip_2026-10-16_20-50-00_300s.mp4", "ember", 5, 300, 900),
         (game_name("Ridge Racer X"), "Clip_2026-10-16_20-00-00_180s.mp4", "desert", 4, 180, 7200),
         (game_name("Frostfall"), "Clip_2026-10-16_19-10-00_30s.mp4", "snow", 6, 30, 9000),
         (game_name("Wildwood"), "Clip_2026-10-16_18-00-00_60s.mp4", "forest", 12, 60, 20000)]
now = time.time()
for game, name, pal, seed, secs, ago in specs:
    d = root / game; d.mkdir(exist_ok=True); dst = d / name
    png = work / f"{pal}{seed}.png"; draw_scene(1280, 720, pal, seed, hud=False).save(str(png))
    if name.endswith(".png"):
        shutil.copy(png, dst)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(png), "-f", "lavfi", "-i", "sine",
                        "-f", "lavfi", "-i", "sine=f=600", "-f", "lavfi", "-i", "sine=f=800",
                        "-map", "0", "-map", "1", "-map", "2", "-map", "3", "-t", "6",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dst)], check=True)
    os.utime(dst, (now - ago,) * 2)
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
for p in ctl.recent:
    media.make_thumb(p, ctl.thumbs_dir)
lengths = {s[1]: s[4] for s in specs}
for p in ctl.recent:
    if p.suffix != ".png": ctl.lengths[p] = lengths[p.name]


def pump(n=6):
    for _ in range(n): app.processEvents()


def wait(seconds, until=lambda: False):
    end = time.time() + seconds
    while time.time() < end and not until(): app.processEvents(); time.sleep(0.02)


# ---- the screens, grabbed once
input_devices.input_mode().set("playstation")
viewer = ui_viewer.Viewer(ctl); m = ui_menu.Menu(ctl, viewer)
m.show_menu(GAME); BH = m.BAR_H + m.HEADROOM
m.setGeometry(0, 0, W, BH); m._place(); m.refresh_recent()
status = {"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1_160_000, "recording": False,
          "record_ms": 0, "mic_muted": False}
m._on_status(status)
m.save_card.setFocus(); pump(); bar_save = m.grab()
m.open_picker(); m._on_status(status); pump(); bar_picker = m.grab(); m.close_picker()
t = ui_notices.Toast(); t.thumbs_dir = ctl.thumbs_dir; t.pad_button = "create"
t.show_capture("Last 1 minute", str(ctl.recent[0])); pump(); toast = t.grab(); t.hide()
m.activateWindow(); m.thumbs[0].setFocus(); m._on_focus(m.thumbs[0]); m.save_card.clearFocus()
m.thumbs[0].active = True; pump(); bar_recent = m.grab()

clip_frame = QtGui.QPixmap(str(work / "dusk7.png"))


def show_frame():
    """The video surface can't be grabbed offscreen, so the clip's picture stands in for it."""
    viewer.image.setPixmap(clip_frame.scaled(viewer.stage.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    viewer.stage.setCurrentWidget(viewer.image); viewer.controls.show(); pump(10)


viewer.open(ctl.recent_items(), 0); viewer.resize(W, H); viewer.show_item(); wait(3)
viewer.enter_trim(); wait(6, lambda: len(viewer.timeline.frames) >= 12)
viewer.timeline.set_start(1400); viewer.timeline.set_end(4600); viewer.timeline.pos = 2600
viewer.player.pause(); show_frame(); show_frame(); view_trim = viewer.grab()
viewer.exit_trim(); viewer.enter_sound(); viewer.voice_row.set_value(200); viewer.game_row.set_value(75)
viewer.player.pause(); show_frame(); show_frame(); view_sound = viewer.grab()
print("screens", bar_save.size(), toast.size(), view_trim.size(), view_sound.size(), "sound panel:", viewer.sounding)

# ---- drawing
bg = draw_scene(W, H, "dusk", 7, hud=False)
icon = QtGui.QImage(str(Path(sys.argv[1]) / "docs" / "icon.png"))
PROMPT = ui_theme.prompt_family()


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def fade(t, a, b, d=0.25):
    """1 inside [a, b], fading in and out over d seconds."""
    return min(ease((t - a) / d), ease((b - t) / d))


def font(px, weight=QtGui.QFont.DemiBold):
    return ui_theme.font(px, weight, display=True)


def glyph_font(px):
    f = QtGui.QFont(PROMPT); f.setPixelSize(px)
    return f


CREATE = ui_theme.glyph("sony-dualsense-share")
CAPTIONS = [  # (from, to, pieces); a piece in [] is a button glyph
    (0.0, 2.6, ["The PS5 Create button,", "\n", "on your PC"]),
    (2.6, 4.0, ["Press ", f"[{CREATE}]", " or Alt + C"]),
    (4.0, 6.2, ["Save the last minute", "\n", "you just played"]),
    (6.2, 8.4, ["Saved. Keep playing."]),
    (8.4, 10.6, ["Your clips are", "\n", "one button away"]),
    (10.6, 13.0, ["Trim the best part"]),
    (13.0, 15.6, ["Turn your voice up", "\n", "or the game down"]),
]
END = 15.6
TOTAL = 19.5


def draw_caption(p, pieces, cx, top, px, alpha):
    if alpha <= 0:
        return
    lines, line = [], []
    for piece in pieces:
        if piece == "\n":
            lines.append(line); line = []
        else:
            line.append(piece)
    lines.append(line)

    def measure(piece):
        if piece.startswith("["):
            return QtGui.QFontMetrics(glyph_font(int(px * 1.15))).horizontalAdvance(piece[1:-1]), glyph_font(int(px * 1.15)), piece[1:-1]
        return QtGui.QFontMetrics(font(px)).horizontalAdvance(piece), font(px), piece

    lh = px * 1.3
    widths = [sum(measure(pc)[0] for pc in ln) for ln in lines]
    pad_x, pad_y = px * 0.7, px * 0.4
    box = QRectF(cx - max(widths) / 2 - pad_x, top, max(widths) + 2 * pad_x, lh * len(lines) + 2 * pad_y)
    p.save(); p.setOpacity(alpha)
    p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(10, 12, 20, 190))
    p.drawRoundedRect(box, px * 0.45, px * 0.45)
    p.setPen(QtGui.QColor("#ffffff"))
    for i, ln in enumerate(lines):
        x = cx - widths[i] / 2
        y = top + pad_y + i * lh
        for pc in ln:
            w, f, text = measure(pc)
            p.setFont(f)
            p.drawText(QRectF(x, y, w + 2, lh), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += w
    p.restore()


def caption_at(t):
    for a, b, pieces in CAPTIONS:
        if a - 0.01 <= t <= b + 0.01:
            return pieces, fade(t, a, b, 0.2)
    return None, 0


def game_frame(t):
    """The landscape picture without captions: the game, the app on top of it."""
    img = QtGui.QImage(W, H, QtGui.QImage.Format_RGB32)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    z = 1.0 + 0.06 * t / TOTAL
    p.drawImage(QRectF(W * (1 - z) / 2, H * (1 - z) / 2, W * z, H * z), bg)

    def bar(pm, y_up):
        p.drawPixmap(0, int(H - BH * y_up), pm)

    if 3.2 <= t < 6.5:
        up = ease((t - 3.2) / 0.4) if t < 6.2 else 1 - ease((t - 6.2) / 0.3)
        bar(bar_picker if t >= 4.9 else bar_save, up)
    if 6.4 <= t < 8.4:
        slide = ease((t - 6.5) / 0.35) * (1 - ease((t - 8.0) / 0.35))
        p.drawPixmap(int(W - (toast.width() + 28) * slide), 28, toast)
    if 8.4 <= t < 10.9:
        bar(bar_recent, ease((t - 8.4) / 0.4))
    if 10.6 <= t < END + 0.5:
        p.setOpacity(ease((t - 10.6) / 0.3)); p.drawPixmap(0, 0, view_trim)
        if t >= 13.0:
            p.setOpacity(ease((t - 13.0) / 0.3)); p.drawPixmap(0, 0, view_sound)
        p.setOpacity(1)
    p.end()
    return img


def end_card(p, w, h, alpha, vertical):
    p.save(); p.setOpacity(alpha)
    p.fillRect(QRectF(0, 0, w, h), QtGui.QColor(8, 9, 14, 235))
    s = 1.35 if vertical else 1.0
    cy = h / 2 - (40 if vertical else 30)
    size = int(150 * s)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    p.drawImage(QRectF(w / 2 - size / 2, cy - size - 40 * s, size, size), icon)
    p.setPen(QtGui.QColor("#ffffff")); p.setFont(font(int(84 * s), QtGui.QFont.Bold))
    p.drawText(QRectF(0, cy - 20 * s, w, 110 * s), Qt.AlignCenter, "Capture Menu")
    p.setPen(QtGui.QColor("#c9cbd6")); p.setFont(font(int(36 * s), QtGui.QFont.Normal))
    lines = ["Free and open source", "for Windows"] if vertical else ["Free and open source for Windows"]
    y = cy + 95 * s
    for line in lines:
        p.drawText(QRectF(0, y, w, 50 * s), Qt.AlignCenter, line); y += 52 * s
    p.setPen(QtGui.QColor("#ffffff")); p.setFont(font(int(30 * s)))
    p.drawText(QRectF(0, y + 30 * s, w, 50 * s), Qt.AlignCenter, "github.com/Amjz03/capture-menu")
    p.restore()


def landscape(t, frame):
    img = QtGui.QImage(frame)
    p = QtGui.QPainter(img); p.setRenderHint(QtGui.QPainter.Antialiasing); p.setRenderHint(QtGui.QPainter.TextAntialiasing)
    pieces, a = caption_at(t)
    if pieces:
        draw_caption(p, pieces, W / 2, 56, 50, a)
    if t >= END:
        end_card(p, W, H, ease((t - END) / 0.5), False)
    p.end()
    return img


CW = 1296   # width of the part of the picture the tall video shows (full height, 6:5)
CROPS = [(0.0, (W - CW) / 2), (3.0, 0), (6.3, W - CW), (8.3, 0), (10.5, (W - CW) / 2), (12.9, 0)]


def crop_x(t):
    """The tall video follows the action: the bar on the left, the notice on the right."""
    x = CROPS[0][1]
    for start, target in CROPS[1:]:
        if t >= start:
            x = x + (target - x) * ease((t - start) / 0.4)
    return x


def portrait(t, frame):
    img = QtGui.QImage(VW, VH, QtGui.QImage.Format_RGB32)
    p = QtGui.QPainter(img); p.setRenderHint(QtGui.QPainter.Antialiasing); p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    small = frame.scaled(W // 16, H // 16, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)   # cheap blur
    p.drawImage(QRectF(-(VH * W / H - VW) / 2, 0, VH * W / H, VH), small)
    p.fillRect(QRectF(0, 0, VW, VH), QtGui.QColor(8, 9, 14, 150))
    fh = VW * H / CW
    top = (VH - fh) / 2 + 150
    p.drawImage(QRectF(0, top, VW, fh), frame, QRectF(crop_x(t), 0, CW, H))
    pieces, a = caption_at(t)
    if pieces:
        lines = pieces.count("\n") + 1
        draw_caption(p, pieces, VW / 2, top - 60 - lines * 86 - 54, 66, a)
    if t >= END:
        end_card(p, VW, VH, ease((t - END) / 0.5), True)
    p.end()
    return img


def encoder(path, w, h):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)


wide, tall = encoder(out / "promo-16x9.mp4", W, H), encoder(out / "promo-9x16.mp4", VW, VH)
frames = int(TOTAL * FPS)
stills = {int(x * FPS): x for x in (1.0, 3.6, 5.5, 7.0, 9.5, 12.0, 14.5, 18.0)}
for i in range(frames):
    t = i / FPS
    f = game_frame(t)
    for enc, img in ((wide, landscape(t, f)), (tall, portrait(t, f))):
        enc.stdin.write(bytes(img.constBits())[:img.sizeInBytes()])
    if i in stills:
        landscape(t, f).save(str(out / f"still_{t:04.1f}.jpg"), quality=85)
        portrait(t, f).save(str(out / f"still_tall_{t:04.1f}.jpg"), quality=85)
for enc in (wide, tall):
    enc.stdin.close(); enc.wait()
print("ok", frames, "frames")

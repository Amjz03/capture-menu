"""Shared visual styles, drawing helpers and window appearance."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import ctypes
import json
import os

from . import runtime


# ---------------------------------------------------------------- UI

def trim_memory():
    """While the app only waits for the hotkey, give back what it doesn't need: Qt's cache of drawn
    pixmaps (refilled as pages are drawn), source lines kept for tracebacks, free heap. Its idle pages
    go back to Windows too; they stay in RAM's standby list, so the menu still opens instantly."""
    import gc, linecache
    gc.collect()
    linecache.clearcache()        # PySide6 reads every module imported after it into this cache
    QtGui.QPixmapCache.clear()    # up to 10 MB of style and icon pixmaps
    if runtime.IS_WINDOWS:
        k32 = ctypes.windll.kernel32
        k32.GetProcessHeap.restype = ctypes.c_void_p
        k32.HeapCompact.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.HeapCompact(k32.GetProcessHeap(), 0)     # decommits the heap's large free blocks
        k32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
        k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    else:
        try:
            ctypes.CDLL(None).malloc_trim(0)           # glibc keeps freed heap otherwise
        except (OSError, AttributeError):
            pass


def bring_to_front(w: QtWidgets.QWidget, keyboard: bool = False):
    """Windows only lets the app that got the last input steal focus. A controller
    press isn't keyboard input, so briefly join the foreground thread's input queue.
    keyboard: typing is next (Rename), so if Windows still keeps the game in front, a tap of Alt
    makes it let go; otherwise the keys would go to the game."""
    w.raise_()
    w.activateWindow()
    if not runtime.IS_WINDOWS:
        return
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = int(w.winId())
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(ctypes.c_void_p(fg), None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(fg_thread, me, True))
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if attached:
        user32.AttachThreadInput(fg_thread, me, False)
    if keyboard and user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(0x12, 0, 0, 0)            # VK_MENU down
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)            # and up (KEYEVENTF_KEYUP)


def hide_from_capture(w: QtWidgets.QWidget):
    """Keeps the window out of recordings and screenshots (Windows 10 2004+)."""
    if runtime.IS_WINDOWS:
        ctypes.windll.user32.SetWindowDisplayAffinity(int(w.winId()), 0x11)  # WDA_EXCLUDEFROMCAPTURE


def set_on_top(w: QtWidgets.QWidget, on: bool):
    """Always on top or not, without Qt making the window again (which would hide it)."""
    if not runtime.IS_WINDOWS or not w.testAttribute(Qt.WA_WState_Created):
        return
    move = ctypes.windll.user32.SetWindowPos
    move.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
    move(int(w.winId()), ctypes.c_void_p(-1 if on else -2), 0, 0, 0, 0,   # HWND_TOPMOST / HWND_NOTOPMOST
         0x0001 | 0x0002 | 0x0010)                                        # no size, no move, no activate


def make_room_above():
    """Another app opens over Capture Menu (File Explorer on a capture): the open pages stay where they
    are but stop being always on top until they're used again, so that window isn't stuck behind them."""
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.property("captureMenuPage") in ("viewer", "gallery", "settings") and w.isVisible():
            set_on_top(w, False)


class _AccentPolicy(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WindowCompositionData(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


GLASS_TINT = 0x70            # how much of the near-black tint lies over the blur (0-255)


GLASS_SHEET = 96             # and how dark the page paints over that; 250 without glass


def glass(w: QtWidgets.QWidget) -> bool:
    """Frosted glass behind a page, like the PS5: the game shows through, blurred and dimmed.
    Windows' own acrylic blur (Windows 10 1803+), drawn by the system, so it costs the game nothing.
    False where it isn't available; the page then stays solid."""
    if not runtime.IS_WINDOWS or os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen"):
        return False
    try:
        tint = (GLASS_TINT << 24) | (NIGHT[2] << 16) | (NIGHT[1] << 8) | NIGHT[0]   # AABBGGRR
        accent = _AccentPolicy(4, 2, tint, 0)                                 # ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = _WindowCompositionData(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
                                      ctypes.sizeof(accent))                  # WCA_ACCENT_POLICY
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(int(w.winId()), ctypes.byref(data)))
    except Exception:
        runtime.log.exception("glass background not available")
        return False


def sheet_color(w: QtWidgets.QWidget) -> QtGui.QColor:
    """The page's own dark layer: light over glass, nearly solid without it."""
    return QtGui.QColor(*NIGHT, GLASS_SHEET if getattr(w, "glassy", False) else 250)


def dress(w: QtWidgets.QWidget, frosted: bool = True):
    """What lives on a page's native window: kept out of captures, glass behind it. Done when the page
    is made, and again on opening it after release_window() let the window go."""
    if getattr(w, "dressed", False):
        return
    hide_from_capture(w)
    if frosted:
        w.glassy = glass(w)
    w.dressed = True


def release_window(w: QtWidgets.QWidget):
    """A hidden page keeps a picture of itself the size of the screen (about 15 MB at 1440p, 33 MB at 4K)
    for as long as its native window lives. Letting the window go gives that back; opening the page
    makes a new one, dressed again."""
    if w.isVisible():
        return
    w.destroy()
    w.dressed = False


# ---- look: the PS5's night blue; white is the focus colour, red only means recording
INK = "#f4f6fb"


MUTED = "rgba(236,240,250,0.76)"


FAINT = "rgba(236,240,250,0.58)"


NIGHT = (7, 10, 20)         # every surface sits on this blue-black, like the PS5's menus


PANEL = "rgba(24,29,44,0.92)"   # a raised card: notices, dialogs


DARK = "#0d1120"            # ink on a white (focused) surface


RED = "#ff453a"


GREEN = "#32d74b"


BLUE = "#2f7bf5"            # PlayStation blue: a switch that's on


AMBER = "#ffb340"


FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'


DISPLAY = '"Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif'


# Interface icons come from Lucide (ISC licence, assets/LUCIDE-LICENSE.txt).
ICON_FILES = {
    "camera": "camera", "rewind": "history", "record": "circle-dot", "stop": "circle-stop",
    "folder": "folder", "play": "play", "pause": "pause", "scissors": "scissors",
    "trash": "trash-2", "external": "external-link", "left": "chevron-left",
    "right": "chevron-right", "close": "x", "image": "image",
    "share": "share-2", "copy": "copy", "star": "star", "mic": "mic", "mic-off": "mic-off",
    "gallery": "layout-grid", "drive": "hard-drive", "settings": "settings",
    "volume": "volume-2", "volume-off": "volume-x", "maximize": "maximize", "minimize": "minimize",
    "pencil": "pencil", "audio": "audio-lines", "export": "upload", "more": "ellipsis",
    "gamepad": "gamepad-2", "info": "info", "file-video": "file-video", "select": "square-check-big",
}


_icon_cache: dict = {}


def icon_pixmap(name: str, size: int, color: str = INK) -> QtGui.QPixmap:
    key = (name, size, color)
    if key not in _icon_cache:
        from PySide6.QtSvg import QSvgRenderer
        svg = (runtime.ASSETS / "icons" / f"{ICON_FILES[name]}.svg").read_text(encoding="utf-8")
        svg = svg.replace("currentColor", color)
        renderer = QSvgRenderer(QtCore.QByteArray(svg.encode()))
        dpr = 3.0
        pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(dpr)
        _icon_cache[key] = pm
    return _icon_cache[key]


def qicon(name: str, color: str = INK) -> QtGui.QIcon:
    return QtGui.QIcon(icon_pixmap(name, 18, color))


def rounded_pixmap(path: Path | None, w: int, h: int, radius: int = 10, dpr: float = 2.0) -> QtGui.QPixmap:
    """The image cropped to fill w×h with rounded corners (dark placeholder if missing)."""
    out = QtGui.QPixmap(int(w * dpr), int(h * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    p = QtGui.QPainter(out)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    clip = QtGui.QPainterPath()
    clip.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(clip)
    src = QtGui.QPixmap(str(path)) if path else QtGui.QPixmap()
    if src.isNull():
        p.fillRect(0, 0, w, h, QtGui.QColor(255, 255, 255, 18))
    else:
        scaled = src.scaled(int(w * dpr), int(h * dpr), Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        p.drawPixmap(QtCore.QPointF((w - scaled.width() / dpr) / 2, (h - scaled.height() / dpr) / 2),
                     scaled)
    p.end()
    return out


def font(px: float, weight: QtGui.QFont.Weight = QtGui.QFont.Normal, display: bool = False) -> QtGui.QFont:
    f = QtGui.QFont()
    f.setFamilies(["Segoe UI Variable Display" if display else "Segoe UI Variable Text",
                   "Segoe UI", "Inter", "Noto Sans"])
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def short_clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# Button prompts come from PromptFont by Shinmera (Yukari Hafner), SIL OFL 1.1,
# https://shinmera.com/promptfont (assets/PROMPTFONT-LICENSE.txt).
_prompt_family: str | None = None


_glyphs: dict[str, str] | None = None


def prompt_family() -> str:
    global _prompt_family
    if _prompt_family is None:
        fid = QtGui.QFontDatabase.addApplicationFont(str(runtime.ASSETS / "promptfont.ttf"))
        families = QtGui.QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _prompt_family = families[0] if families else ""
    return _prompt_family


def glyph(name: str) -> str:
    global _glyphs
    if _glyphs is None:
        _glyphs = json.loads((runtime.ASSETS / "promptfont-glyphs.json").read_text(encoding="utf-8"))
    return _glyphs.get(name, "")


KEY_NAMES = {"←": "left", "→": "right", "↑": "up", "↓": "down", "Enter": "enter", "Esc": "escape",
             "Space": "space", "Del": "delete", "Alt": "alt", "Ctrl": "control", "Shift": "shift"}


PAD_GLYPHS = {
    "playstation": {0: "sony-a", 1: "sony-b", 2: "sony-x", 3: "sony-y", 4: "sony-dualsense-share",
                    5: "icon-playstation", 6: "sony-dualsense-options", 7: "sony-left-stick",
                    8: "sony-right-stick", 9: "sony-left-shoulder", 10: "sony-right-shoulder",
                    20: "sony-dualsense-touchpad"},
    "xbox": {0: "xbox-a", 1: "xbox-b", 2: "xbox-x", 3: "xbox-y", 4: "xbox-view", 5: "icon-xbox",
             6: "xbox-menu", 9: "xbox-left-shoulder", 10: "xbox-right-shoulder"},
}


def token_glyphs(token: str, mode: str) -> list[str]:
    """Hint token -> PromptFont glyph names (or "t:<text>" for plain text).
    "k:Enter" / "k:← →" / "k:1–8" are keys; A B X Y, L1 R1 L1R1, DPAD_LR / DPAD_UD are pad buttons."""
    if token.startswith("k:"):
        out = []
        for piece in token[2:].split():
            if "–" in piece:
                lo, hi = piece.split("–")
                out += [f"keyboard-{lo.lower()}", "t:–", f"keyboard-{hi.lower()}"]
            else:
                out.append("keyboard-" + KEY_NAMES.get(piece, piece.lower()))
        return out
    kind = "playstation" if mode == "playstation" else "xbox"
    pad = {"A": [0], "B": [1], "X": [2], "Y": [3], "L1": [9], "R1": [10], "L1R1": [9, 10]}
    if token in pad:
        return [PAD_GLYPHS[kind][b] for b in pad[token]]
    if token == "OPT":
        return [PAD_GLYPHS[kind][6]]
    if token == "L3":   # PromptFont has no Xbox stick press
        return ["sony-left-stick"] if kind == "playstation" else ["t:LS"]
    if token == "DPAD_U":
        return ["dpad-up" if kind == "playstation" else "xbox-dpad-up"]
    if token == "DPAD":
        return ["dpad-fill" if kind == "playstation" else "xbox-dpad"]
    if token in ("DPAD_LR", "DPAD_UD"):
        suffix = "left-right" if token == "DPAD_LR" else "up-down"
        return [f"dpad-{suffix}" if kind == "playstation" else f"xbox-dpad-{suffix}"]
    return [f"t:{token}"]


def _glyph_parts(token: str, mode: str) -> list[tuple[QtGui.QFont, str]]:
    parts = []
    for name in token_glyphs(token, mode):
        char = "" if name.startswith("t:") else glyph(name)
        if char:
            f = QtGui.QFont(prompt_family())
            f.setPixelSize(22)
            parts.append((f, char))
        else:
            parts.append((font(12, QtGui.QFont.DemiBold),
                          name[2:] if name.startswith("t:") else name.split("-", 1)[-1].upper()))
    return parts


def glyph_width(token: str, mode: str) -> float:
    """How wide draw_glyph() draws this button prompt."""
    return sum(QtGui.QFontMetrics(f).horizontalAdvance(text) + (2 if i else 0)
               for i, (f, text) in enumerate(_glyph_parts(token, mode)))


def draw_glyph(p: QtGui.QPainter, x: float, cy: float, token: str, mode: str,
               color: str | QtGui.QColor = INK) -> float:
    """Draws one button prompt at x (vertically centred on cy); returns its width."""
    width = 0.0
    p.save()
    p.setPen(QtGui.QColor(color))
    for i, name in enumerate(token_glyphs(token, mode)):
        char = "" if name.startswith("t:") else glyph(name)
        if char:
            f = QtGui.QFont(prompt_family())
            f.setPixelSize(22)
            text = char
        else:
            f = font(12, QtGui.QFont.DemiBold)
            text = name[2:] if name.startswith("t:") else name.split("-", 1)[-1].upper()
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text)
        x0 = x + width + (2 if i else 0)
        p.drawText(QtCore.QRectF(x0, cy - 14, w + 1, 28), Qt.AlignCenter, text)
        width += w + (2 if i else 0)
    p.restore()
    return width


def glyph_html(names: list[str], px: int = 17) -> str:
    """Inline PromptFont glyphs for rich-text labels."""
    family = prompt_family()
    parts = []
    for n in names:
        char = glyph(n)
        parts.append(f'<span style="font-family:\'{family}\'; font-size:{px}px">{char}</span>'
                     if char else n.split("-")[-1].upper())
    return "&nbsp;".join(parts)


MOTION_MS = 180       # how long the focus takes to grow into place; 0 jumps (the render tools use that)


def grown(r: QtCore.QRectF, amount: float) -> QtCore.QRectF:
    """r made larger by amount (0.06 = 6 %) around its centre."""
    dx, dy = r.width() * amount / 2, r.height() * amount / 2
    return r.adjusted(-dx, -dy, dx, dy)


def paint_focus(p: QtGui.QPainter, r: QtCore.QRectF, radius: float, t: float = 1.0, ring: bool = True):
    """The PS5's focus frame around r: a soft white glow and, for pictures, a white ring.
    t fades it in (0-1) as the item grows."""
    if t <= 0.01:
        return
    p.save()
    p.setBrush(Qt.NoBrush)
    for out, width, alpha in ((8, 8, 10), (6, 5, 20), (4.5, 3, 34)):     # the glow, softest outside
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(alpha * t)), width))
        p.drawRoundedRect(r.adjusted(-out, -out, out, out), radius + out, radius + out)
    if ring:
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(255 * t)), 3))
        p.drawRoundedRect(r.adjusted(-3.5, -3.5, 3.5, 3.5), radius + 3.5, radius + 3.5)
    p.restore()


BAR_STYLE = f"""
QLabel {{ color: {INK}; background: transparent; }}
#game {{ font-family: {DISPLAY}; font-size: 30px; font-weight: 600; }}
#status {{ color: {MUTED}; font-size: 15px; }}
#caption {{ color: {INK}; font-size: 17px; font-weight: 600; }}
#focusInfo {{ color: {FAINT}; font-size: 15px; }}
#storage {{ color: {AMBER}; font-size: 15px; }}
QPushButton#back {{
    color: {INK}; font-size: 14px; font-weight: 600; border: none; border-radius: 20px;
    background: rgba(255,255,255,16); padding: 0 18px 0 12px; min-height: 40px;
}}
QPushButton#back:hover {{ background: rgba(255,255,255,40); }}
"""


VIEWER_STYLE = f"""
QWidget {{ font-family: {FONT}; }}
#viewer {{ background: transparent; border: none; }}
QLabel {{ color: {INK}; background: transparent; }}
#vTitle {{ font-family: {DISPLAY}; font-size: 32px; font-weight: 600; }}
#vSub, #vNote {{ color: {MUTED}; font-size: 15px; }}
#hint {{ color: {MUTED}; font-size: 15px; }}
#panelTitle {{ font-family: {DISPLAY}; font-size: 24px; font-weight: 600; }}
#panelSub {{ color: {MUTED}; font-size: 15px; }}
#info {{ color: {MUTED}; font-size: 14px; }}
#vMsg {{ color: {MUTED}; font-size: 16px; }}
#time {{ color: {MUTED}; font-size: 14px; font-family: "Cascadia Mono", Consolas, monospace; }}
#stage {{ background: transparent; }}
#videoCard {{ background: #000000; border: 1px solid rgba(255,255,255,22); border-radius: 20px; }}
#ctlBar {{ background: rgba(24,29,44,200); border-top: 1px solid rgba(255,255,255,14);
           border-bottom-left-radius: 19px; border-bottom-right-radius: 19px; }}
#footer {{ border-top: 1px solid rgba(255,255,255,16); }}
#rule {{ background: rgba(255,255,255,40); }}
QPushButton {{
    color: {INK}; font-size: 15px; font-weight: 600;
    background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,30); border-radius: 23px;
    padding: 0 22px; min-height: 46px;
}}
QPushButton:hover {{ background: rgba(255,255,255,24); }}
QPushButton:disabled {{ color: rgba(236,240,250,0.28); border-color: rgba(255,255,255,14); }}
QPushButton#primary {{ background: {INK}; color: {DARK}; border: 4px solid {INK}; padding: 0 22px; }}
QPushButton#primary:hover {{ background: #ffffff; border-color: #ffffff; }}
QPushButton:focus {{ border: 2px solid {INK}; padding: 0 21px; }}
QPushButton#primary:focus {{ border: 4px solid {INK}; background-clip: padding; padding: 0 22px; }}   /* a ring, the same size */
QPushButton#back {{ background: rgba(255,255,255,12); border: 3px solid transparent; padding: 0 18px 0 12px; }}
QPushButton#back:focus, QPushButton#round:focus, QPushButton#ctl:focus {{ border: 3px solid {INK}; }}
QPushButton#back:hover {{ background: rgba(255,255,255,32); }}
QPushButton#round {{ padding: 0; min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px;
                     border-radius: 23px; border: 3px solid transparent; background: rgba(255,255,255,12); }}
QPushButton#round:hover {{ background: rgba(255,255,255,32); }}
QPushButton#pill {{ min-height: 34px; padding: 0 16px; font-size: 13px; border-radius: 17px; }}
QPushButton#ctl {{ padding: 0; min-width: 40px; max-width: 40px; min-height: 40px; border: 3px solid transparent;
                   background: transparent; border-radius: 20px; }}
QPushButton#ctl:hover {{ background: rgba(255,255,255,24); }}
QLineEdit {{
    color: {INK}; background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,40);
    border-radius: 14px; padding: 0 16px; min-height: 50px; font-size: 16px;
    selection-background-color: {BLUE}; selection-color: white;    /* typing replaces what's selected */
}}
QLineEdit:focus {{ border: 2px solid {INK}; padding: 0 15px; }}
QLineEdit#titleEdit {{ font-family: {DISPLAY}; font-size: 30px; font-weight: 600; min-height: 54px; min-width: 520px; }}
QLineEdit#noteEdit {{ font-size: 15px; min-height: 38px; min-width: 520px; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,46); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {INK}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: white; }}
QSlider#seek {{ border: 3px solid transparent; border-radius: 15px; padding: 0 8px; min-height: 30px; }}
QSlider#seek:focus {{ border-color: {INK}; }}
"""


# ---- the viewer's parts. One calm vocabulary: a faint surface with a hairline, round corners,
# white only for focus and for the one main action on screen.
CARD_RADIUS = 18


def paint_card(p: QtGui.QPainter, r: QtCore.QRectF, focused: bool = False, hovered: bool = False,
               radius: float = CARD_RADIUS):
    inset = 1.5 if focused else 0.5
    p.setPen(QtGui.QPen(QtGui.QColor(INK) if focused else QtGui.QColor(255, 255, 255, 26), 3 if focused else 1))
    p.setBrush(QtGui.QColor(255, 255, 255, 24 if (hovered or focused) else 12))
    p.drawRoundedRect(r.adjusted(inset, inset, -inset, -inset), radius, radius)


ARROWS = (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down)


def toward(current: QtWidgets.QWidget, items: list[QtWidgets.QWidget], key: int,
           here: QtCore.QRectF | None = None) -> QtWidgets.QWidget | None:
    """Where an arrow leads from current, by where things sit on screen, the way the PS5 moves its
    highlight: the nearest item that way, and anything in line with it (same row or column) first.
    here: where on screen the highlight is, when it's only part of current (a tile in a grid)."""
    def box(w):
        return QtCore.QRectF(QtCore.QPointF(w.mapToGlobal(QtCore.QPoint(0, 0))), QtCore.QSizeF(w.size()))

    def gap(a0, a1, b0, b1):     # how far apart two spans are (0 when they overlap)
        return max(0.0, b0 - a1, a0 - b1)
    here = here if here is not None else box(current)
    best, best_score = None, None
    for w in items:
        if w is current:
            continue
        r = box(w)
        d = r.center() - here.center()
        way = {Qt.Key_Right: r.left() - here.right(), Qt.Key_Left: here.left() - r.right(),   # it starts past
               Qt.Key_Down: r.top() - here.bottom(), Qt.Key_Up: here.top() - r.bottom()}[key]  # our edge
        if way < -4:
            continue
        if key in (Qt.Key_Left, Qt.Key_Right):
            along, across = max(0.0, way), gap(here.top(), here.bottom(), r.top(), r.bottom())
        else:
            along, across = max(0.0, way), gap(here.left(), here.right(), r.left(), r.right())
        score = (across > 0, along + 2 * across + 0.05 * abs(d.y() if key in (Qt.Key_Left, Qt.Key_Right) else d.x()))
        if best_score is None or score < best_score:
            best, best_score = w, score
    return best


def mirror(w: QtWidgets.QWidget, r: QtCore.QRectF) -> QtCore.QRectF:
    """r as laid out left to right, flipped when the widget runs right to left (Arabic)."""
    if not w.isRightToLeft():
        return r
    return QtCore.QRectF(w.width() - r.x() - r.width(), r.y(), r.width(), r.height())


GALLERY_STYLE = VIEWER_STYLE + f"""
QListWidget {{ background: transparent; border: none; outline: none; color: {INK}; }}
QListWidget#games {{ font-size: 14px; }}
QListWidget#grid {{ font-size: 12px; }}
QListWidget#grid::item {{ border-radius: 12px; padding: 6px; color: {MUTED}; }}
QListWidget#grid::item:selected {{ background: rgba(255,255,255,24); color: {INK}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,45); border-radius: 4px; min-height: 40px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def tray_icon() -> QtGui.QIcon:
    pm = QtGui.QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor("#1c1c21"))
    p.drawRoundedRect(4, 4, 56, 56, 16, 16)
    p.setPen(QtGui.QPen(QtGui.QColor(INK), 4))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(32, 32), 15, 15)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor(RED))
    p.drawEllipse(QtCore.QPointF(32, 32), 7, 7)
    p.end()
    return QtGui.QIcon(pm)

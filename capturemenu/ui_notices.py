"""Recording indicator and capture/status notifications."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import time

import threading

from . import catalog, input_devices, language, media, phone_link, ui_theme, windows


class RecIndicator(QtWidgets.QWidget):
    """A small red REC dot and timer in a corner while a manual recording runs, like the PS5.
    Clicks go straight through to the game, it never takes focus, and recordings don't show it."""

    def __init__(self, corner: str = "top-left"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.corner = corner
        self.started: float | None = None      # time.monotonic() when the recording began
        self.blink = True
        self.setFont(ui_theme.font(18))      # spec: Label 18/24 (Medium: Segoe UI Regular)
        self._tick = QtCore.QTimer(self, interval=1000, timeout=self._on_tick)

    def text(self) -> str:
        secs = int(time.monotonic() - self.started) if self.started is not None else 0
        return f"REC  {language.clock(secs * 1000)}"

    def set_recording(self, on: bool, elapsed_ms: int = 0):
        if self.corner == "off":
            return
        if not on:
            self.started = None
            self._tick.stop()
            self.hide()
            return
        if self.started is None or elapsed_ms:   # OBS knows the real time; trust it over our clock
            self.started = time.monotonic() - elapsed_ms / 1000
        self._place()
        self.show()
        self._tick.start()

    def set_corner(self, corner: str):
        """Settings changed where it shows (or turned it off): from now on, a recording that's running too."""
        was, self.corner = self.started, corner
        if corner == "off":
            self.started = None
            self._tick.stop()
            self.hide()
        elif was is not None:
            self._place()

    def sync(self, st: dict):
        """From the status poll: catches recordings started in OBS itself, or before a restart."""
        if st.get("online"):
            if st.get("mic_muted") is not None and st["mic_muted"] != self.mic_muted:
                self.mic_muted = st["mic_muted"]
                self.update()
            self.set_recording(bool(st.get("recording")), int(st.get("record_ms") or 0))

    mic_muted: bool | None = None          # a green mic, or a red one crossed out; none while unknown

    def _place(self):
        long = self.started is not None and time.monotonic() - self.started >= 3600
        # spec: 40 high, pad 8, 16, 8, 14; dot 12, gap 10, the time, gap 10, mic 18 (steady width)
        w = 14 + 12 + 10 + self.fontMetrics().horizontalAdvance("REC  0:00:00" if long else "REC  00:00") + 16
        w += 28 if self.mic_muted is not None else 0
        self.resize(w, 40)
        g = windows.game_screen().geometry()      # follows the game to the TV and back
        x = g.left() + 40 if self.corner == "top-left" else g.left() + g.width() - w - 40
        self.move(x, g.top() + 36)

    def _on_tick(self):
        self.blink = not self.blink
        self._place()
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(16, 20, 31, 204))     # surface/glass-strong
        p.drawRoundedRect(r, 20, 20)
        dot = QtGui.QColor(ui_theme.RED)
        dot.setAlpha(255 if self.blink else 110)   # a slow pulse, so it reads as live
        p.setPen(Qt.NoPen)
        if self.blink:     # a soft red halo while the dot is lit
            p.setBrush(QtGui.QColor(255, 69, 58, 60))
            p.drawEllipse(QtCore.QPointF(20, r.center().y()), 10, 10)
        p.setBrush(dot)
        p.drawEllipse(QtCore.QPointF(20, r.center().y()), 6, 6)
        p.setPen(QtGui.QColor(ui_theme.INK))
        # (absolute left: in Arabic Qt would put the time at the right edge, under the mic)
        p.drawText(r.adjusted(36, 0, -12, 0), Qt.AlignLeft | Qt.AlignAbsolute | Qt.AlignVCenter, self.text())
        if self.mic_muted is not None:      # is your voice going in
            icon = ("mic-off", ui_theme.RED) if self.mic_muted else ("mic", ui_theme.GREEN)
            p.drawPixmap(QtCore.QPointF(r.right() - 16 - 18, r.center().y() - 9), ui_theme.icon_pixmap(icon[0], 18, icon[1]))


class Toast(QtWidgets.QWidget):
    """Top-right notice, like the PS5's: never takes focus from the game.
    A capture's notice can be clicked to view it, or its Trim button to trim it."""

    open_capture = QtCore.Signal(str, bool)    # path, straight into trim
    share_capture = QtCore.Signal(str)         # path: the viewer on it, its Share window open
    MAX_W = 520                                # wider notices only wrap

    DOTS = {"ok": ui_theme.GREEN, "error": ui_theme.RED, "info": ui_theme.INK, "rec": ui_theme.RED}
    TITLES = {"Clip": "Clip saved", "Screenshot": "Screenshot saved",
              "Recording": "Recording saved", "Trimmed": "Trimmed clip saved"}
    hotkey = "ALT+C"
    pad_button = "create"
    thumbs_dir: Path | None = None
    BURST_S = 8           # captures this close together share one notice: "3 captures saved"
    # an error that has a fix gets its button: (words in the error, button, what it does in the background)
    fixes: list[tuple[str, str, object]] = []

    def show_shared(self, detail: str, path: str):
        """The share copy is ready (and on the clipboard)."""
        self._plain()
        self.path = self.action = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.setPixmap(ui_theme.rounded_pixmap(media.make_thumb(Path(path), self.thumbs_dir or Path(path).parent),
                                            144, 81, 12))
        self.thumb.show()
        self.title.setText(language.tr("Ready to share"))
        self.sub.setText(detail.replace(" · ", "  ·  "))
        self.sub.show()
        self.hint.setText(language.tr("Copied · paste it with Ctrl+V"))
        self.hint.show()
        self._present(7000)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.path: str | None = None
        self.action = None             # what a click on a notice without a capture does
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QtWidgets.QFrame(objectName="toastBox")
        self._frame()
        outer.addWidget(self.box)
        lay = QtWidgets.QHBoxLayout(self.box)
        lay.setContentsMargins(12, 12, 16, 12)      # compact: a notice sits over the game, it shouldn't cover it
        lay.setSpacing(14)
        self.thumb = QtWidgets.QLabel()
        lay.addWidget(self.thumb)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        self.col = col
        self.title = QtWidgets.QLabel()
        self.title.setFont(ui_theme.font(17, QtGui.QFont.DemiBold))
        self.title.setStyleSheet(f"color: {ui_theme.INK};")
        self.title.setTextFormat(Qt.RichText)
        self.sub = QtWidgets.QLabel()
        self.sub.setFont(ui_theme.font(15))
        self.sub.setStyleSheet("color: rgba(236,240,250,0.84);")
        self.hint = QtWidgets.QLabel()
        self.hint.setTextFormat(Qt.RichText)
        self.hint.setFont(ui_theme.font(14))
        self.hint.setStyleSheet(f"color: {ui_theme.MUTED};")
        col.addStretch()
        for w in (self.title, self.sub, self.hint):
            w.setWordWrap(True)          # long notices wrap instead of being cut off (_present sets the width)
            col.addWidget(w, 0, language.lead())     # the words start where the line starts, not centred
        # a capture's notice: View, Trim and Share under its name
        self.actions = QtWidgets.QWidget()
        acts = QtWidgets.QHBoxLayout(self.actions)
        acts.setContentsMargins(0, 6, 0, 0)
        acts.setSpacing(8)
        style = (f"QPushButton {{ font-family: {ui_theme.FONT}; background: rgba(255,255,255,41); color: {ui_theme.INK}; border: none; border-radius: 15px;"
                 f" padding: 0 12px 0 9px; min-height: 30px; font-size: 14px; font-weight: 400; }}"
                 f"QPushButton:hover {{ background: rgba(255,255,255,44); }}")
        self.view_btn, self.trim_btn, self.share_btn = (
            QtWidgets.QPushButton(" " + language.tr(text)) for text in ("View", "Trim", "Share"))
        for b, icon, fn in ((self.view_btn, "play", lambda: self._open(trim=False)),
                            (self.trim_btn, "scissors", lambda: self._open(trim=True)),
                            (self.share_btn, "share", self._share)):
            b.setIcon(ui_theme.qicon(icon))
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(style)
            b.clicked.connect(fn)
            acts.addWidget(b)
        acts.addStretch()
        col.addWidget(self.actions)
        self.actions.hide()
        col.addStretch()
        lay.addLayout(col, 1)      # the words take the room the 640 px leave; buttons stay at the end
        self.fix_btn = QtWidgets.QPushButton()      # an error's own way out: "Start OBS"
        self.fix_btn.setCursor(Qt.PointingHandCursor)
        self.fix_btn.setStyleSheet(   # spec: h52, surface/tile, a subtle edge, r26, Label 18
            f"QPushButton {{ font-family: {ui_theme.FONT}; background: rgba(255,255,255,26); color: {ui_theme.INK}; border: 1px solid rgba(255,255,255,36);"
            f" border-radius: 19px; padding: 0 16px 0 14px; min-height: 38px; font-size: 15px; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,44); }}")
        self.fix_btn.setIconSize(QtCore.QSize(18, 18))
        self.fix_btn.setIcon(ui_theme.qicon("external"))
        self.fix_btn.clicked.connect(self._run_fix)
        lay.addWidget(self.fix_btn, 0, Qt.AlignVCenter)
        self.fix_btn.hide()
        self._fix = None
        self._spin = 0.0                            # "Saving…": a ring that turns while it works
        self._spinner = QtCore.QTimer(self, interval=40, timeout=self._turn)
        self._burst, self._burst_at = 0, 0.0
        self._hide = QtCore.QTimer(self, singleShot=True, timeout=self._fade_out)
        self._slide = QtCore.QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade.finished.connect(lambda: self.hide() if self.windowOpacity() < 0.05 else None)

    def _frame(self, border: str = "rgba(255,255,255,36)", width: float = 1):
        """The notice's card; an error has an amber edge."""
        self.box.setStyleSheet(
            f"#toastBox {{ background: rgba(16,20,31,204); border-radius: 22px; border: {width}px solid {border}; }}"
            f"QLabel {{ background: transparent; border: none; }}")

    def _badge(self, icon: str | None, color: str, spin: bool = False) -> QtGui.QPixmap:
        """The round mark on the left of a notice without a picture: a warning in a 52 px circle,
        or the 44 px saving ring (spec)."""
        dpr, size = 2.0, 40
        pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if spin:      # track surface/tile-strong, the arc surface/focus
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 41), 3))
            p.drawEllipse(QtCore.QRectF(5, 5, 30, 30))
            p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.INK), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QtCore.QRectF(5, 5, 30, 30), int(-self._spin * 16), 100 * 16)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 26))
            p.drawEllipse(QtCore.QRectF(0, 0, 40, 40))
            if icon:
                p.drawPixmap(QtCore.QRectF(10, 10, 20, 20).toRect(), ui_theme.icon_pixmap(icon, 20, color))
        p.end()
        return pm

    def _turn(self):
        self._spin = (self._spin + 12) % 360
        if self.isVisible():
            self.thumb.setPixmap(self._badge(None, ui_theme.INK, spin=True))
        else:
            self._spinner.stop()

    def _run_fix(self):
        fix, self._fix = self._fix, None
        self.hide()
        if fix:
            threading.Thread(target=fix, daemon=True).start()

    def _plain(self):
        """Back to an ordinary notice before showing a new one."""
        self._spinner.stop()
        self.actions.hide()
        self.fix_btn.hide()
        self._fix = None
        self._frame()

    def _open(self, trim: bool = False):
        if self.path:
            self.hide()
            self.open_capture.emit(self.path, trim)

    def _share(self):
        if self.path:
            self.hide()
            self.share_capture.emit(self.path)

    def mousePressEvent(self, e):
        action, self.action = self.action, None
        self._error_until = 0          # read and put away: the next notice needn't wait
        if self.path:
            self._open(trim=False)    # click the notice: open it in the viewer
        else:
            self.hide()
            if action:
                action()

    def show_capture(self, detail: str, path: str):
        capture = Path(path)
        now = time.monotonic()
        # captures right after each other share this notice (it would only be replaced): it counts them
        self._burst = self._burst + 1 if self.isVisible() and self.path and now - self._burst_at < self.BURST_S else 1
        self._burst_at = now
        self._plain()
        self.path, self.action = path, None
        self.setCursor(Qt.PointingHandCursor)
        self.actions.show()
        self.trim_btn.setVisible(capture.suffix.lower() != ".png")
        kind = capture.stem.split("_")[0]
        if kind == "Clip" and catalog.capture_kind(capture) == "Trimmed clip":
            kind = "Trimmed"
        thumb = media.make_thumb(capture, self.thumbs_dir or capture.parents[1] / ".thumbs")
        self.thumb.setPixmap(ui_theme.rounded_pixmap(thumb, 144, 81, 12))
        self.thumb.show()
        self.title.setText(language.tr(self.TITLES.get(kind, "Saved")) if self._burst == 1
                           else language.tr("{n} captures saved", n=self._burst))
        self.sub.setText("  ·  ".join(x for x in (detail, capture.parent.name) if x))
        self.sub.show()
        self.hint.hide()          # View, Trim and Share under it say what it does
        self._present(6000)

    def show_phone_ready(self, path: str, on_click):
        """The phone's copy is made while its panel was put away: a click shows the QR code to scan."""
        capture = Path(path)
        self._plain()
        self.path, self.action = None, on_click
        self.trim_btn.hide()
        self.setCursor(Qt.PointingHandCursor)
        thumb = media.make_thumb(capture, self.thumbs_dir or capture.parents[1] / ".thumbs")
        self.thumb.setPixmap(ui_theme.rounded_pixmap(thumb, 144, 81, 12))
        self.thumb.show()
        self.title.setText(language.tr("The QR code is ready"))
        self.sub.setText(capture.parent.name)
        self.sub.setVisible(bool(capture.parent.name))
        self.hint.setText(language.tr("Works for {minutes} minutes · click to show it, then scan it with your phone",
                                      minutes=phone_link.LIFETIME_S // 60))   # so it's scanned in time
        self.hint.show()
        self._present(10000)

    def show_running(self, title: str, detail: str):
        """The start-up notice: app icon, "running", and how to open it."""
        self._plain()
        self.path = self.action = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.setPixmap(ui_theme.tray_icon().pixmap(44, 44))
        self.thumb.show()
        self.title.setText(title)
        self.sub.setText(detail)
        self.sub.show()
        self.hint.hide()
        self._present(5000)

    def show_update(self, version: str, on_click):
        """A new version is out: app icon, the version, and a click opens Settings to install it."""
        self.show_running(language.tr("Update available"), language.tr("Version {version} is available", version=version))
        self.action = on_click
        self.setCursor(Qt.PointingHandCursor)
        self.hint.setText(language.tr("Click to install it from Settings"))
        self.hint.show()
        self._present(9000)

    ERROR_MS = 6000       # an error stays this long; a smaller notice waits for it

    def show_message(self, text: str, kind: str = "info"):
        left = getattr(self, "_error_until", 0) - time.monotonic()
        if kind in ("info", "ok") and left > 0 and self.isVisible():
            # an error is on screen: "Controller connected" comes after it, not over it
            QtCore.QTimer.singleShot(int(left * 1000) + 300, lambda: self.show_message(text, kind))
            return
        self._error_until = time.monotonic() + self.ERROR_MS / 1000 if kind == "error" else 0
        self._plain()
        self.path = self.action = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.hide()
        title, _, sub = text.partition(" · ")
        if kind == "rec":            # red means recording, and only that
            self.title.setText(f'<span style="color:{ui_theme.RED}">●</span>&nbsp;&nbsp;{title}')
        else:
            self.title.setText(title)
        if kind == "error":          # a warning sign and an amber edge; and its fix, when there is one
            self.thumb.setPixmap(self._badge("warning", ui_theme.AMBER))
            self.thumb.show()
            self._frame(ui_theme.AMBER, 1.5)
            fix = next(((label, fn) for words, label, fn in self.fixes if words.casefold() in text.casefold()), None)
            if fix:
                self.fix_btn.setText(language.tr(fix[0]))
                self._fix = fix[1]
                self.fix_btn.show()
        elif title.endswith("…"):    # "Saving…": it's working; the saved notice takes its place
            self.thumb.setPixmap(self._badge(None, ui_theme.INK, spin=True))
            self.thumb.show()
            if ui_theme.MOTION_MS:
                self._spinner.start()
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        self.hint.hide()
        self._present(self.ERROR_MS if kind == "error" else 3500)

    def _present(self, ms: int):
        # each line gets its natural width and wraps only past the room a notice up to 520 wide leaves it
        pic = self.thumb.pixmap().deviceIndependentSize().width() if not self.thumb.isHidden() else 0
        room = int(self.MAX_W - 12 - 16 - 4 - (pic + 14 if pic else 0)     # (4: the card's edge, both sides)
                   - (self.fix_btn.sizeHint().width() + 14 if not self.fix_btn.isHidden() else 0))
        for w in (self.title, self.sub, self.hint):
            w.setWordWrap(False)
            natural = w.sizeHint().width()
            w.setWordWrap(True)
            w.setFixedWidth(min(natural, room))
        # shrink back after a bigger notice (one with a thumbnail) was shown before
        for lay in (self.box.layout(), self.layout()):
            lay.invalidate()
            lay.activate()
        self.resize(self.sizeHint())
        page_open = any(w.isVisible() for w in QtWidgets.QApplication.topLevelWidgets()
                        if w.property("captureMenuPage"))
        g = (windows.ui_screen() if page_open else windows.game_screen()).geometry()   # beside the page in use
        x, y = g.right() - self.width() - 28, g.top() + 28
        side = next((w.geometry() for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible()
                     and w.property("captureMenuPage") in ("settings", "welcome")), None)
        if side is not None and side.intersects(QtCore.QRect(x, y, self.width(), self.height())):
            x = side.left() - self.width() - 28      # beside the Settings panel, not over its buttons
        self._fade.stop()
        if self.isVisible() or not ui_theme.MOTION_MS:
            self._slide.stop()
            self.move(x, y)
            self.setWindowOpacity(1.0)
        else:   # slides in from the edge and fades in, like the PS5's
            self.move(x + 48, y)
            self._slide.setStartValue(QtCore.QPoint(x + 48, y))
            self._slide.setEndValue(QtCore.QPoint(x, y))
            self._slide.start()
            self.setWindowOpacity(0.0)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.show()
        self.raise_()
        self._hide.start(ms)

    def _fade_out(self):
        """Time's up: the notice fades away instead of vanishing."""
        if not ui_theme.MOTION_MS or not self.isVisible():
            self.hide()
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

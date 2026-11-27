"""Recording indicator and capture/status notifications."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import time

import threading

from . import catalog, input_devices, language, media, ui_theme, windows


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
        self.setFont(ui_theme.font(14, QtGui.QFont.DemiBold))
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
            self.set_recording(bool(st.get("recording")), int(st.get("record_ms") or 0))

    def _place(self):
        long = self.started is not None and time.monotonic() - self.started >= 3600
        w = self.fontMetrics().horizontalAdvance("REC  0:00:00" if long else "REC  00:00") + 52  # steady width
        self.resize(w, 34)
        g = windows.game_screen().geometry()      # follows the game to the TV and back
        x = g.left() + 16 if self.corner == "top-left" else g.left() + g.width() - w - 16
        self.move(x, g.top() + 16)

    def _on_tick(self):
        self.blink = not self.blink
        self._place()
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 26), 1))
        p.setBrush(QtGui.QColor(24, 29, 44, 215))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        dot = QtGui.QColor(ui_theme.RED)
        dot.setAlpha(255 if self.blink else 110)   # a slow pulse, so it reads as live
        p.setPen(Qt.NoPen)
        if self.blink:     # a soft red halo while the dot is lit
            p.setBrush(QtGui.QColor(255, 69, 58, 60))
            p.drawEllipse(QtCore.QPointF(18, r.center().y()), 9, 9)
        p.setBrush(dot)
        p.drawEllipse(QtCore.QPointF(18, r.center().y()), 5.5, 5.5)
        p.setPen(QtGui.QColor(ui_theme.INK))
        p.drawText(r.adjusted(32, 0, -12, 0), Qt.AlignLeft | Qt.AlignVCenter, self.text())


class Toast(QtWidgets.QWidget):
    """Top-right notice, like the PS5's: never takes focus from the game.
    A capture's notice can be clicked to view it, or its Trim button to trim it."""

    open_capture = QtCore.Signal(str, bool)    # path, straight into trim

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
                                            128, 72, 11))
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
        lay.setContentsMargins(12, 12, 20, 12)
        lay.setSpacing(16)
        self.thumb = QtWidgets.QLabel()
        lay.addWidget(self.thumb)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        self.title = QtWidgets.QLabel()
        self.title.setFont(ui_theme.font(16, QtGui.QFont.DemiBold))
        self.title.setStyleSheet(f"color: {ui_theme.INK};")
        self.title.setTextFormat(Qt.RichText)
        self.sub = QtWidgets.QLabel()
        self.sub.setFont(ui_theme.font(14))
        self.sub.setStyleSheet(f"color: {ui_theme.MUTED};")
        self.hint = QtWidgets.QLabel()
        self.hint.setTextFormat(Qt.RichText)
        self.hint.setFont(ui_theme.font(13))
        self.hint.setStyleSheet(f"color: {ui_theme.MUTED};")
        col.addStretch()
        for w in (self.title, self.sub, self.hint):
            w.setMaximumWidth(380)
            w.setWordWrap(True)          # long notices wrap instead of being cut off
            col.addWidget(w)
        col.addStretch()
        lay.addLayout(col)
        self.trim_btn = QtWidgets.QPushButton(" " + language.tr("Trim"))
        self.trim_btn.setIcon(ui_theme.qicon("scissors"))
        self.trim_btn.setCursor(Qt.PointingHandCursor)
        self.trim_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,22); color: {ui_theme.INK}; border: none; border-radius: 15px;"
            f" padding: 8px 16px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,44); }}")
        self.trim_btn.clicked.connect(lambda: self._open(trim=True))
        lay.addWidget(self.trim_btn, 0, Qt.AlignVCenter)
        self.trim_btn.hide()
        self.fix_btn = QtWidgets.QPushButton()      # an error's own way out: "Start OBS"
        self.fix_btn.setCursor(Qt.PointingHandCursor)
        self.fix_btn.setStyleSheet(self.trim_btn.styleSheet())
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

    def _frame(self, border: str = "rgba(255,255,255,22)"):
        """The notice's card; an error has an amber edge."""
        self.box.setStyleSheet(
            f"#toastBox {{ background: {ui_theme.PANEL}; border-radius: 18px; border: 1px solid {border}; }}"
            f"QLabel {{ background: transparent; border: none; }}")

    def _badge(self, icon: str | None, color: str, spin: bool = False) -> QtGui.QPixmap:
        """The round mark on the left of a notice without a picture: a warning, or the saving ring."""
        dpr = 2.0
        pm = QtGui.QPixmap(int(44 * dpr), int(44 * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 22))
        p.drawEllipse(QtCore.QRectF(0, 0, 44, 44))
        if spin:
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 50), 3))
            p.drawEllipse(QtCore.QRectF(11, 11, 22, 22))
            p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.INK), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QtCore.QRectF(11, 11, 22, 22), int(-self._spin * 16), 100 * 16)
        elif icon:
            p.drawPixmap(QtCore.QRectF(11, 11, 22, 22).toRect(), ui_theme.icon_pixmap(icon, 22, color))
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
        self.fix_btn.hide()
        self._fix = None
        self._frame()

    def _open(self, trim: bool = False):
        if self.path:
            self.hide()
            self.open_capture.emit(self.path, trim)

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
        self.trim_btn.setVisible(capture.suffix.lower() != ".png")
        kind = capture.stem.split("_")[0]
        if kind == "Clip" and catalog.capture_kind(capture) == "Trimmed clip":
            kind = "Trimmed"
        thumb = media.make_thumb(capture, self.thumbs_dir or capture.parents[1] / ".thumbs")
        self.thumb.setPixmap(ui_theme.rounded_pixmap(thumb, 128, 72, 11))
        self.thumb.show()
        self.title.setText(language.tr(self.TITLES.get(kind, "Saved")) if self._burst == 1
                           else language.tr("{n} captures saved", n=self._burst))
        self.sub.setText("  ·  ".join(x for x in (detail, capture.parent.name) if x))
        self.sub.show()
        if input_devices.input_mode().mode == "keyboard":
            keys = [f"keyboard-{ui_theme.KEY_NAMES.get(k.capitalize(), k.lower())}"
                    for k in self.hotkey.replace(" ", "").split("+")]
            open_html, view_html = ui_theme.glyph_html(keys, 22), ui_theme.glyph_html(["keyboard-v"], 22)
        else:
            try:
                combo = sorted(input_devices.parse_pad_combo(self.pad_button))
            except ValueError:
                combo = []
            names = ui_theme.PAD_GLYPHS[input_devices.input_mode().mode]
            open_html = ui_theme.glyph_html([names.get(b, input_devices.PAD_NAMES[input_devices.input_mode().mode].get(b, "?"))
                                             for b in combo], 22)
            view_html = ui_theme.glyph_html([names[3]], 22)
        self.hint.setText(language.tr("{open}&nbsp; then &nbsp;{view}&nbsp; to view", open=open_html, view=view_html))
        self.hint.show()
        self._present(6000)

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
            self._frame("rgba(255,179,64,150)")
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
        # each line gets its natural width and wraps only past 380 px (Qt would wrap far earlier)
        for w in (self.title, self.sub, self.hint):
            w.setWordWrap(False)
            natural = w.sizeHint().width()
            w.setWordWrap(True)
            w.setFixedWidth(min(natural, 380))
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

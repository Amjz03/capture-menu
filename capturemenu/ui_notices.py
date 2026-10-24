"""Recording indicator and capture/status notifications."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import time

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
        ui_theme.hide_from_capture(self)
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

    def show_shared(self, detail: str, path: str):
        """The share copy is ready (and on the clipboard)."""
        self.path = None
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
        ui_theme.hide_from_capture(self)
        self.path: str | None = None
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QtWidgets.QFrame(objectName="toastBox")
        self.box.setStyleSheet(
            f"#toastBox {{ background: {ui_theme.PANEL}; border-radius: 18px;"
            f" border: 1px solid rgba(255,255,255,22); }}"
            f"QLabel {{ background: transparent; border: none; }}")
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
            f"QPushButton {{ background: rgba(255,255,255,22); color: {ui_theme.INK}; border: none; border-radius: 17px;"
            f" padding: 8px 16px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,44); }}")
        self.trim_btn.clicked.connect(lambda: self._open(trim=True))
        lay.addWidget(self.trim_btn, 0, Qt.AlignVCenter)
        self.trim_btn.hide()
        self._hide = QtCore.QTimer(self, singleShot=True, timeout=self._fade_out)
        self._slide = QtCore.QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade.finished.connect(lambda: self.hide() if self.windowOpacity() < 0.05 else None)

    def _open(self, trim: bool = False):
        if self.path:
            self.hide()
            self.open_capture.emit(self.path, trim)

    def mousePressEvent(self, e):
        if self.path:
            self._open(trim=False)    # click the notice: open it in the viewer
        else:
            self.hide()

    def show_capture(self, detail: str, path: str):
        capture = Path(path)
        self.path = path
        self.setCursor(Qt.PointingHandCursor)
        self.trim_btn.setVisible(capture.suffix.lower() != ".png")
        kind = capture.stem.split("_")[0]
        if kind == "Clip" and catalog.capture_kind(capture) == "Trimmed clip":
            kind = "Trimmed"
        thumb = media.make_thumb(capture, self.thumbs_dir or capture.parents[1] / ".thumbs")
        self.thumb.setPixmap(ui_theme.rounded_pixmap(thumb, 128, 72, 11))
        self.thumb.show()
        self.title.setText(language.tr(self.TITLES.get(kind, "Saved")))
        self.sub.setText("  ·  ".join(x for x in (detail, capture.parent.name) if x))
        self.sub.show()
        if input_devices.input_mode().mode == "keyboard":
            keys = [f"keyboard-{ui_theme.KEY_NAMES.get(k.capitalize(), k.lower())}"
                    for k in self.hotkey.replace(" ", "").split("+")]
            open_html, view_html = ui_theme.glyph_html(keys), ui_theme.glyph_html(["keyboard-v"])
        else:
            try:
                combo = sorted(input_devices.parse_pad_combo(self.pad_button))
            except ValueError:
                combo = []
            names = ui_theme.PAD_GLYPHS[input_devices.input_mode().mode]
            open_html = ui_theme.glyph_html([names.get(b, input_devices.PAD_NAMES[input_devices.input_mode().mode].get(b, "?")) for b in combo])
            view_html = ui_theme.glyph_html([names[3]])
        self.hint.setText(language.tr("{open}&nbsp; then &nbsp;{view}&nbsp; to view", open=open_html, view=view_html))
        self.hint.show()
        self._present(6000)

    def show_running(self, title: str, detail: str):
        """The start-up notice: app icon, "running", and how to open it."""
        self.path = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.setPixmap(ui_theme.tray_icon().pixmap(44, 44))
        self.thumb.show()
        self.title.setText(title)
        self.sub.setText(detail)
        self.sub.show()
        self.hint.hide()
        self._present(5000)

    def show_message(self, text: str, kind: str = "info"):
        self.path = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.hide()
        title, _, sub = text.partition(" · ")
        dot = self.DOTS.get(kind)
        self.title.setText(f'<span style="color:{dot}">●</span>&nbsp;&nbsp;{title}'
                           if kind in ("error", "rec") else title)
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        self.hint.hide()
        self._present(6000 if kind == "error" else 3500)

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

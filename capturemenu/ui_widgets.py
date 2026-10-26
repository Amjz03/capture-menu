"""Reusable buttons, cards, controls and the trim timeline."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path

from . import input_devices, language, media, ui_theme


class HintBar(QtWidgets.QWidget):
    """A row of button prompts with labels, drawn for the current input device."""

    GAP, ITEM_GAP = 7, 20

    def __init__(self):
        super().__init__()
        self.items: list[tuple[str, str]] = []
        self.mode = "keyboard"
        self.setFixedHeight(28)

    def set_items(self, items: list[tuple[str, str]], mode: str):
        self.items, self.mode = [(glyph, language.tr(label)) for glyph, label in items], mode
        self.setFixedWidth(int(self._layout(None)) + 2)
        self.update()

    def _layout(self, p: QtGui.QPainter | None) -> float:
        x, cy = 0.0, self.height() / 2
        scratch = None
        if p is None:   # measure on a throwaway painter
            scratch = QtGui.QPixmap(1, 1)
            p = QtGui.QPainter(scratch)
        rtl = language.is_rtl()   # right to left: the first prompt sits on the right, each label left of its button
        for i, (glyph, label) in enumerate(reversed(self.items) if rtl else self.items):
            if i:
                x += self.ITEM_GAP
            if glyph and not rtl:
                x += ui_theme.draw_glyph(p, x, cy, glyph, self.mode) + self.GAP
            p.setFont(ui_theme.font(14))
            p.setPen(QtGui.QColor(236, 240, 250, 205))
            w = p.fontMetrics().horizontalAdvance(label)
            p.drawText(QtCore.QRectF(x, 0, w + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, label)
            x += w
            if glyph and rtl:
                x += self.GAP + ui_theme.draw_glyph(p, x + self.GAP, cy, glyph, self.mode)
        if scratch is not None:
            p.end()
        return x

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        self._layout(p)


class HoverFocus:
    """Hover only lends the white highlight: the item under the mouse lights up, and when the mouse
    leaves, the highlight goes back to where it was. A click (or a key) keeps it where it is."""

    def hover_in(self):
        before = QtWidgets.QApplication.focusWidget()
        if before is not self:
            self._lent = True
            self._lent_from = before
        self.setFocus(Qt.MouseFocusReason)

    def hover_out(self):
        lent, before = getattr(self, "_lent", False), getattr(self, "_lent_from", None)
        self.keep_focus()
        if not lent or not self.hasFocus():
            return                          # clicked, or a key moved on meanwhile: that stays
        if before is not None and before.isVisible() and before.window() is self.window():
            before.setFocus(Qt.MouseFocusReason)
        else:
            self.clearFocus()

    def keep_focus(self):
        self._lent, self._lent_from = False, None


class Grow:
    """The PS5's focus: the focused item grows a little and lights up, smoothly, and settles back
    when the focus moves on. self.grow runs from 0 (at rest) to 1 (focused)."""

    grow = 0.0

    def grow_to(self, on: bool):
        end = 1.0 if on else 0.0
        anim = getattr(self, "_grow_anim", None)
        if anim is None:
            anim = self._grow_anim = QtCore.QVariantAnimation(self)
            anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
            anim.valueChanged.connect(self._on_grow)
        anim.stop()
        if not ui_theme.MOTION_MS or not self.isVisible() or self.grow == end:
            self._on_grow(end)
            return
        anim.setDuration(ui_theme.MOTION_MS)
        anim.setStartValue(self.grow)
        anim.setEndValue(end)
        anim.start()

    def _on_grow(self, value):
        self.grow = float(value)
        self.update()


class Card(Grow, HoverFocus, QtWidgets.QAbstractButton):
    """Base for the bar's focusable tiles: hover, and the focus that grows the tile and rings it."""

    RADIUS = 16
    PAD = 12                                  # room around the tile to grow into, with its ring and glow
    SCALE = 0.08                              # how much bigger the focused tile is
    BELOW = 0                                 # room under the tile for its label

    def __init__(self, w: int, h: int):
        super().__init__()
        self.setFixedSize(w + 2 * self.PAD, h + 2 * self.PAD + self.BELOW)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.focused_cb = None
        self.active = False                 # keeps the ring while its popover is open
        self.hover_focus = lambda: True

    def tile(self) -> QtCore.QRectF:
        """Where the tile sits at rest."""
        return QtCore.QRectF(self.PAD, self.PAD, self.width() - 2 * self.PAD,
                             self.height() - 2 * self.PAD - self.BELOW)

    def lit(self) -> float:
        """How focused it looks, 0-1: it grows into focus, and stays lit while its popover is open."""
        return 1.0 if self.active else self.grow

    def shown(self) -> QtCore.QRectF:
        """Where the tile is drawn: grown as far as its focus has come."""
        return ui_theme.grown(self.tile(), self.SCALE * self.lit())

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.grow_to(True)
        if self.focused_cb:
            self.focused_cb(self)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.grow_to(False)

    def enterEvent(self, e):
        super().enterEvent(e)
        if self.hover_focus():
            self.hover_in()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if self.hover_focus():
            self.hover_out()

    def mousePressEvent(self, e):
        self.keep_focus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        self.keep_focus()
        super().keyPressEvent(e)

    def radius(self) -> float:
        """The corner radius as drawn, growing with the tile."""
        return self.RADIUS * self.shown().width() / self.tile().width()

    def paint_ring(self, p: QtGui.QPainter):
        ui_theme.paint_focus(p, self.shown(), self.radius(), self.lit())


class ActionCard(Card):
    """An icon tile with its name underneath. The focused one grows and turns white, like the PS5's
    Create menu."""

    SIZE = 100
    BELOW = 44

    def __init__(self, icon: str, label: str, hint: str = ""):
        super().__init__(self.SIZE + 12, self.SIZE)
        self.icon_name, self.label, self.hint = icon, label, hint
        self.icon_color = ui_theme.INK
        self.tint: QtGui.QColor | None = None
        self.badge = False      # a blue dot on the tile and a blue second line: something new waits there

    def tile(self) -> QtCore.QRectF:
        return QtCore.QRectF((self.width() - self.SIZE) / 2, self.PAD, self.SIZE, self.SIZE)

    def set_state(self, icon: str, label: str, icon_color: str = ui_theme.INK, tint: QtGui.QColor | None = None):
        self.icon_name, self.label, self.icon_color, self.tint = icon, label, icon_color, tint
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r, t, radius = self.shown(), self.lit(), self.radius()
        focused = self.hasFocus() or self.active
        ui_theme.paint_focus(p, r, radius, t, ring=False)
        p.setPen(Qt.NoPen)
        p.setBrush(self.tint if self.tint is not None else QtGui.QColor(255, 255, 255, 34 if self.underMouse() else 20))
        p.drawRoundedRect(r, radius, radius)
        if t > 0.01:      # the white comes in as the tile grows
            white = QtGui.QColor(ui_theme.INK)
            white.setAlphaF(t)
            p.setBrush(white)
            p.drawRoundedRect(r, radius, radius)
        color = (ui_theme.DARK if self.icon_color == ui_theme.INK else self.icon_color) if focused else self.icon_color
        size = 32 * r.width() / self.SIZE
        p.drawPixmap(QtCore.QRectF(r.center().x() - size / 2, r.center().y() - size / 2, size, size).toRect(),
                     ui_theme.icon_pixmap(self.icon_name, 34, color))
        text_r = QtCore.QRectF(0, self.tile().bottom() + 14, self.width(), 18)
        p.setPen(QtGui.QColor(ui_theme.INK) if focused else QtGui.QColor(236, 240, 250, 205))
        p.setFont(ui_theme.font(14, QtGui.QFont.DemiBold if focused else QtGui.QFont.Normal))
        p.drawText(text_r, Qt.AlignHCenter | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(language.tr(self.label), Qt.ElideRight, self.width()))
        if self.hint:
            p.setPen(QtGui.QColor(ui_theme.BLUE) if self.badge else QtGui.QColor(236, 240, 250, 150))
            p.setFont(ui_theme.font(13, QtGui.QFont.DemiBold if self.badge else QtGui.QFont.Normal))
            p.drawText(text_r.translated(0, 17), Qt.AlignHCenter | Qt.AlignVCenter, language.tr(self.hint))
        if self.badge:
            p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.DARK), 2))
            p.setBrush(QtGui.QColor(ui_theme.BLUE))
            p.drawEllipse(QtCore.QPointF(r.right() - 12, r.top() + 12), 7, 7)


def draw_capture_tile(p: QtGui.QPainter, r: QtCore.QRectF, pixmap: QtGui.QPixmap, path: Path | None,
                      length: float | None, favorite: bool, dim: int = 0, radius: int = 10,
                      marked: bool = False, selecting: bool = False):
    """A capture thumbnail with its badges: length (or screenshot) and a favourite star.
    selecting: every tile shows the circle that a pick fills in."""
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    p.drawPixmap(r, pixmap, QtCore.QRectF(pixmap.rect()))     # r may be grown past the picture's own size
    if dim:
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, dim))
        p.drawRoundedRect(r, radius, radius)
    p.setFont(ui_theme.font(11, QtGui.QFont.DemiBold))
    is_shot = path is not None and path.suffix.lower() == ".png"
    label = "" if is_shot or length is None else ui_theme.short_clock(length)
    if is_shot or label:
        text_w = p.fontMetrics().horizontalAdvance(label) if label else 0
        bw = text_w + 14 + (18 if is_shot and label else 0) if label else 22
        badge = QtCore.QRectF(r.right() - bw - 6, r.bottom() - 26, bw, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 150))
        p.drawRoundedRect(badge, 5, 5)
        x = badge.left() + 4
        if is_shot:
            p.drawPixmap(QtCore.QPointF(x, badge.top() + 3), ui_theme.icon_pixmap("image", 14))
            x += 18
        if label:
            p.setPen(QtGui.QColor(ui_theme.INK))
            p.drawText(QtCore.QRectF(x, badge.top(), badge.right() - x - 3, 20), Qt.AlignCenter, label)
    if marked:   # picked for "delete selected": white frame + check in the corner
        p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.INK), 3))
        p.setBrush(QtGui.QColor(0, 0, 0, 90))
        p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), radius, radius)
        c = QtCore.QPointF(r.right() - 17, r.top() + 17)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(ui_theme.INK))
        p.drawEllipse(c, 11, 11)
        p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.DARK), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QtGui.QPolygonF([c + QtCore.QPointF(-5, 0), c + QtCore.QPointF(-1.5, 3.5),
                                        c + QtCore.QPointF(5, -4)]))
    elif selecting:
        c = QtCore.QPointF(r.right() - 17, r.top() + 17)
        p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.INK), 2))
        p.setBrush(QtGui.QColor(0, 0, 0, 120))
        p.drawEllipse(c, 10, 10)
    if favorite:
        star = QtCore.QRectF(r.left() + 6, r.top() + 6, 22, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 165))
        p.drawRoundedRect(star, 6, 6)
        p.drawPixmap(QtCore.QPointF(star.left() + 4, star.top() + 4), ui_theme.icon_pixmap("star", 14, "#ffd34d"))


class ThumbCard(Card):
    RADIUS = 14
    W, H = 178, 100
    BELOW = 44

    def __init__(self):
        super().__init__(self.W, self.H)
        self.path: Path | None = None
        self.pixmap = QtGui.QPixmap()
        self.length: float | None = None
        self.favorite = False
        self.caption, self.when = "", ""

    def set_capture(self, path: Path, thumb: Path | None, length: float | None, favorite: bool = False):
        self.path, self.length, self.favorite = path, length, favorite
        self.pixmap = ui_theme.rounded_pixmap(thumb, self.W, self.H, self.RADIUS)
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        focused = self.hasFocus() or self.active
        dim = int((50 if self.underMouse() else 100) * (1 - self.lit()))   # quieter until focused, like the PS5
        draw_capture_tile(p, self.shown(), self.pixmap, self.path, self.length, self.favorite, dim, self.radius())
        self.paint_ring(p)
        if focused and self.path is not None:   # the focused capture says what it is, nothing else does
            text = QtCore.QRectF(self.PAD, self.tile().bottom() + 14, self.width() - 2 * self.PAD, 18)
            p.setPen(QtGui.QColor(ui_theme.INK))
            p.setFont(ui_theme.font(14, QtGui.QFont.DemiBold))
            p.drawText(text, language.lead() | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(self.caption, Qt.ElideRight, int(text.width())))
            p.setPen(QtGui.QColor(236, 240, 250, 165))
            p.setFont(ui_theme.font(13))
            p.drawText(text.translated(0, 19), language.lead() | Qt.AlignVCenter, self.when)


def chip_label(seconds: int | None) -> str:
    """PS5 wording: Full Video, Last 15s, Last 1m, Last 30m."""
    if seconds is None:
        return language.tr("Full video")
    if seconds < 60:
        return language.tr("Last {n}s", n=seconds)
    if seconds < 3600:
        return language.tr("Last {n}m", n=seconds // 60)
    return language.tr("Last {n}h", n=seconds // 3600)


class Chip(Grow, HoverFocus, QtWidgets.QAbstractButton):
    """A pill in the Save recent gameplay row; the focused one grows and turns white, like the PS5."""

    H = 44
    PAD = 9           # room to grow into

    def __init__(self, text: str):
        super().__init__()
        self.setText(text)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.dimmed = False      # longer than what the buffer holds so far
        self.danger = False      # a delete waiting for its second press
        self.setFont(ui_theme.font(15, QtGui.QFont.DemiBold))
        self._fit()

    def _fit(self):
        self.setFixedSize(QtGui.QFontMetrics(self.font()).horizontalAdvance(language.tr(self.text())) + 44 + 2 * self.PAD,
                          self.H + 2 * self.PAD)

    def setText(self, text: str):
        super().setText(text)
        self._fit()
        self.update()

    def enterEvent(self, e):
        super().enterEvent(e)
        self.hover_in()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self.hover_out()

    def mousePressEvent(self, e):
        self.keep_focus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        self.keep_focus()
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.grow_to(True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.grow_to(False)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        g = self.grow
        r = QtCore.QRectF(self.rect()).adjusted(self.PAD - 4 * g, self.PAD - 2 * g, 4 * g - self.PAD, 2 * g - self.PAD)
        radius = r.height() / 2
        focused = self.hasFocus()
        ui_theme.paint_focus(p, r, radius, self.grow, ring=False)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 105, 97, 150) if self.danger else QtGui.QColor(255, 255, 255, 46), 1))
        p.setBrush(QtGui.QColor(255, 255, 255, 34 if self.underMouse() else 14))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        if self.grow > 0.01:
            fill = QtGui.QColor("#ff6961" if self.danger else ui_theme.INK)
            fill.setAlphaF(self.grow)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r, radius, radius)
        text = QtGui.QColor(ui_theme.DARK) if focused else QtGui.QColor("#ff8a82" if self.danger else ui_theme.INK)
        if self.dimmed and not focused:
            text.setAlpha(110)
        p.setPen(text)
        p.drawText(r, Qt.AlignCenter, language.tr(self.text()))


class ActionButton(QtWidgets.QAbstractButton):
    """A big viewer action: its icon, its name, and the button that does it (□ Trim, like the PS5).
    The main one on screen is white. With no name it's a small icon button (its name is the tooltip)."""

    H = 64

    def __init__(self, text: str, icon: str, pad: str | None = None, key: str | None = None,
                 primary: bool = False):
        super().__init__()
        self.icon_name, self.tokens, self.primary, self.danger = icon, (pad, key), primary, False
        self.icon_color: str | None = None     # e.g. a filled-in yellow star
        self.setText(text)
        self.setFont(ui_theme.font(17, QtGui.QFont.DemiBold))
        self.setFixedHeight(self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.NoFocus)
        input_devices.input_mode().changed.connect(lambda _: self._fit())
        self._fit()

    def _token(self) -> str | None:
        pad, key = self.tokens
        return key if input_devices.input_mode().mode == "keyboard" else pad

    def _parts(self) -> tuple[float, float, float]:
        """Widths of the label and the button prompt, and the whole content."""
        text_w = QtGui.QFontMetrics(self.font()).horizontalAdvance(self.text()) if self.text() else 0
        glyph_w = ui_theme.glyph_width(self._token(), input_devices.input_mode().mode) if self._token() else 0.0
        total = 22 + (12 + text_w if text_w else 0) + (14 + glyph_w if glyph_w else 0)
        return text_w, glyph_w, total

    def _fit(self):
        total = int(self._parts()[2])
        self.setMinimumWidth(total + 56 if self.text() else max(self.H, total + 40))
        self.update()

    def setText(self, text: str):
        super().setText(text)
        if hasattr(self, "tokens"):
            self._fit()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        hover = self.underMouse()
        if self.primary:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#ffffff" if hover else ui_theme.INK))
            p.drawRoundedRect(r, 20, 20)
            ink = QtGui.QColor(ui_theme.DARK)
            if self.hasFocus():   # a dark ring inside the white
                p.setPen(QtGui.QPen(ink, 3))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(4.5, 4.5, -4.5, -4.5), 16, 16)
        elif self.danger:
            p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.INK), 2) if self.hasFocus() else
                     QtGui.QPen(QtGui.QColor(255, 105, 97, 150), 1))
            p.setBrush(QtGui.QColor(255, 69, 58, 46))
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 20, 20)
            ink = QtGui.QColor("#ff8a82")
        else:
            ui_theme.paint_card(p, r, self.hasFocus(), hover, 20)
            ink = QtGui.QColor(ui_theme.INK)
        p.setFont(self.font())
        text_w, glyph_w, total = self._parts()
        x, cy = (self.width() - total) / 2, self.height() / 2
        icon = QtCore.QRectF(x, cy - 11, 22, 22)
        label = QtCore.QRectF(x + 34, 0, text_w + 2, self.height())
        prompt = QtCore.QRectF(x + 22 + (12 + text_w if text_w else 0) + 14, 0, glyph_w, self.height())
        p.drawPixmap(ui_theme.mirror(self, icon).toRect(), ui_theme.icon_pixmap(self.icon_name, 22, self.icon_color or ink.name()))
        p.setPen(ink)
        if text_w:
            p.drawText(ui_theme.mirror(self, label), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if glyph_w:
            faint = QtGui.QColor(ink)
            faint.setAlpha(150)
            ui_theme.draw_glyph(p, ui_theme.mirror(self, prompt).x(), cy, self._token(), input_devices.input_mode().mode, faint)


class Switch(QtWidgets.QAbstractButton):
    """On / off, like Windows' own switches; white when on."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.NoPen if on else QtGui.QPen(QtGui.QColor(255, 255, 255, 70), 1))
        p.setBrush(QtGui.QColor(ui_theme.INK) if on else QtGui.QColor(255, 255, 255, 18))
        p.drawRoundedRect(QtCore.QRectF(0.5, 0.5, 45, 25), 12.5, 12.5)
        knob = 30 if on != self.isRightToLeft() else 4
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(ui_theme.DARK) if on else QtGui.QColor(ui_theme.INK))
        p.drawEllipse(QtCore.QRectF(knob, 5, 16, 16) if on else QtCore.QRectF(knob + 1, 6, 14, 14))


def icon_badge(name: str) -> QtWidgets.QLabel:
    """A round badge with an icon, the leading mark of a card."""
    b = QtWidgets.QLabel(alignment=Qt.AlignCenter)
    b.setFixedSize(46, 46)
    b.setPixmap(ui_theme.icon_pixmap(name, 21))
    b.setStyleSheet("background: rgba(255,255,255,16); border-radius: 23px;")
    return b


class LevelRow(QtWidgets.QWidget):
    """One card of Audio mix: what it is, a volume bar, how loud (100% = as recorded), and Mute."""

    changed = QtCore.Signal()

    def __init__(self, label: str, describe: str, maximum: int, icon: str = "mic"):
        super().__init__()
        self.setFixedHeight(96)
        self.setAttribute(Qt.WA_Hover)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(16)
        lay.addWidget(icon_badge(icon))
        names = QtWidgets.QVBoxLayout()
        names.setSpacing(2)
        self.name = QtWidgets.QLabel(language.tr(label))
        self.name.setFont(ui_theme.font(16, QtGui.QFont.DemiBold))
        self.desc = QtWidgets.QLabel(language.tr(describe))
        self.desc.setFont(ui_theme.font(14))
        self.desc.setStyleSheet(f"color: {ui_theme.MUTED};")
        names.addStretch()
        names.addWidget(self.name)
        names.addWidget(self.desc)
        names.addStretch()
        lay.addLayout(names)
        self.slider = LevelSlider(Qt.Horizontal)
        self.slider.setLayoutDirection(Qt.LeftToRight)   # louder to the right in every language, like the video bar
        self.slider.setRange(0, maximum)
        self.slider.setSingleStep(media.LEVEL_STEP)
        self.slider.setPageStep(media.LEVEL_STEP * 2)
        self.slider.setMinimumWidth(150)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_value)
        lay.addWidget(self.slider, 1)
        self.amount = QtWidgets.QLabel(alignment=Qt.AlignCenter)
        self.amount.setFont(ui_theme.font(15, QtGui.QFont.DemiBold))
        self.amount.setFixedSize(80, 44)
        lay.addWidget(self.amount)
        mute_label = QtWidgets.QLabel(language.tr("Mute"))
        mute_label.setFont(ui_theme.font(14))
        mute_label.setStyleSheet(f"color: {ui_theme.MUTED};")
        lay.addWidget(mute_label)
        self.mute = Switch()
        self.mute.clicked.connect(self.toggle_mute)
        lay.addWidget(self.mute)
        self._unmuted = 100

    @property
    def value(self) -> int:
        return self.slider.value()

    def set_value(self, percent: int):
        self.slider.setValue(percent)
        self._on_value(self.slider.value())

    def step(self, delta: int):
        self.slider.setValue(self.slider.value() + delta * media.LEVEL_STEP)

    def toggle_mute(self):
        """Mute, or back to the level it had before."""
        if self.value > 0:
            self._unmuted = self.value
            self.slider.setValue(0)
        else:
            self.slider.setValue(self._unmuted or 100)

    def _on_value(self, v: int):
        snapped = round(v / media.LEVEL_STEP) * media.LEVEL_STEP     # a drag lands on the nearest 25 %
        if snapped != v:
            self.slider.setValue(snapped)
            return
        self.amount.setText(f"‎{v}%")   # LRM keeps "150%" in order in Arabic
        muted = v == 0
        self.amount.setStyleSheet(
            f"color: {'#ff8a82' if muted else ui_theme.INK}; border-radius: 10px;"
            f"border: 1px solid {'rgba(255,105,97,110)' if muted else 'rgba(255,255,255,40)'};")
        self.mute.setChecked(muted)
        self.changed.emit()

    def setFocus(self, *args):
        self.slider.setFocus(*args)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        ui_theme.paint_card(p, QtCore.QRectF(self.rect()), self.slider.hasFocus(), self.underMouse())


class OptionCard(QtWidgets.QAbstractButton):
    """A Share setting as a card: a name, what it does, and its choices side by side.
    Enter / ✕ moves to the next choice; a click picks one."""

    picked = QtCore.Signal(object)

    def __init__(self, icon: str, title: str, choices: list[tuple[object, str]], describe):
        super().__init__()
        self.icon_name, self.title, self.choices, self.describe = icon, title, choices, describe
        self.index = 0
        self.note = ""            # replaces the description when the card can't be used
        self.setFixedHeight(150)
        self.setMinimumWidth(300)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.StrongFocus)

    @property
    def value(self):
        return self.choices[self.index][0]

    def set_value(self, value):
        self.index = next((i for i, (v, _) in enumerate(self.choices) if v == value), 0)
        self.update()
        self.picked.emit(self.value)

    def next(self):
        if self.isEnabled():
            self.set_value(self.choices[(self.index + 1) % len(self.choices)][0])

    def _segments(self) -> list[QtCore.QRectF]:
        bar = QtCore.QRectF(20, self.height() - 58, self.width() - 40, 40)
        w = (bar.width() - 8) / len(self.choices)
        return [ui_theme.mirror(self, QtCore.QRectF(bar.x() + 4 + i * w, bar.y() + 4, w, bar.height() - 8))
                for i in range(len(self.choices))]

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        self.setFocus(Qt.MouseFocusReason)
        for i, seg in enumerate(self._segments()):
            if seg.contains(e.position()):
                self.set_value(self.choices[i][0])
                return

    def keyPressEvent(self, e):
        e.ignore()        # the viewer moves between cards and picks with Enter

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        ui_theme.paint_card(p, QtCore.QRectF(self.rect()), self.hasFocus(), self.underMouse() and self.isEnabled())
        badge = ui_theme.mirror(self, QtCore.QRectF(20, 20, 40, 40))
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 16))
        p.drawEllipse(badge)
        p.drawPixmap(badge.adjusted(10, 10, -10, -10).toRect(), ui_theme.icon_pixmap(self.icon_name, 20))
        p.setPen(QtGui.QColor(ui_theme.INK))
        p.setFont(ui_theme.font(16, QtGui.QFont.DemiBold))
        flags = Qt.AlignLeft | Qt.AlignVCenter    # Qt turns this to the right in Arabic by itself
        p.drawText(ui_theme.mirror(self, QtCore.QRectF(74, 18, self.width() - 94, 24)), flags, self.title)
        p.setPen(QtGui.QColor(236, 240, 250, 200))
        p.setFont(ui_theme.font(14))
        sub = self.note or (self.describe(self.value) if callable(self.describe) else self.describe)
        p.drawText(ui_theme.mirror(self, QtCore.QRectF(74, 42, self.width() - 94, 22)), flags,
                   p.fontMetrics().elidedText(sub, Qt.ElideRight, self.width() - 94))
        bar = QtCore.QRectF(20, self.height() - 58, self.width() - 40, 40)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 90))
        p.drawRoundedRect(bar, 10, 10)
        p.setFont(ui_theme.font(14, QtGui.QFont.DemiBold))
        for i, seg in enumerate(self._segments()):
            chosen = i == self.index
            if chosen:
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor(ui_theme.INK) if self.hasFocus() else QtGui.QColor(255, 255, 255, 44))
                p.drawRoundedRect(seg, 7, 7)
            p.setPen(QtGui.QColor(ui_theme.DARK) if chosen and self.hasFocus()
                     else QtGui.QColor(ui_theme.INK) if chosen else QtGui.QColor(236, 240, 250, 185))
            p.drawText(seg, Qt.AlignCenter, p.fontMetrics().elidedText(self.choices[i][1], Qt.ElideRight,
                                                                         int(seg.width()) - 12))


class Timeline(QtWidgets.QWidget):
    """PS5-style trim bar: a filmstrip with start/end handles and a playhead."""

    seek = QtCore.Signal(int)       # ms
    changed = QtCore.Signal()       # start or end moved

    MIN_MS = 500
    PAD = 10

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(76)
        self.setCursor(Qt.PointingHandCursor)
        self.duration, self.start, self.end, self.pos = 1, 0, 1, 0
        self.frames: dict[int, QtGui.QPixmap] = {}
        self.slots = 12
        self._drag: str | None = None

    def reset(self, duration_ms: int):
        self.duration = max(1, duration_ms)
        self.start, self.end, self.pos = 0, self.duration, 0
        self.frames.clear()
        self.update()

    def set_frame(self, i: int, path: str):
        self.frames[i] = QtGui.QPixmap(path)
        self.update()

    def _x(self, ms: int) -> float:
        return self.PAD + (self.width() - 2 * self.PAD) * ms / self.duration

    def _ms(self, x: float) -> int:
        w = self.width() - 2 * self.PAD
        return int(max(0, min(self.duration, (x - self.PAD) / w * self.duration)))

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        h = self.height()
        strip = QtCore.QRectF(self.PAD, 8, self.width() - 2 * self.PAD, h - 16)
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(strip, 8, 8)
        p.save()
        p.setClipPath(clip)
        p.fillRect(strip, QtGui.QColor(255, 255, 255, 18))
        slot_w = strip.width() / self.slots
        for i, pm in self.frames.items():
            if pm.isNull():
                continue
            target = QtCore.QRectF(strip.x() + i * slot_w, strip.y(), slot_w + 1, strip.height())
            scaled = pm.scaled(int(target.width()) + 1, int(target.height()) + 1,
                               Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(target, scaled, QtCore.QRectF(
                (scaled.width() - target.width()) / 2, (scaled.height() - target.height()) / 2,
                target.width(), target.height()))
        x1, x2 = self._x(self.start), self._x(self.end)
        dim = QtGui.QColor(0, 0, 0, 185)
        p.fillRect(QtCore.QRectF(strip.left(), strip.top(), x1 - strip.left(), strip.height()), dim)
        p.fillRect(QtCore.QRectF(x2, strip.top(), strip.right() - x2, strip.height()), dim)
        p.restore()
        # selection frame and handles
        ink = QtGui.QColor(ui_theme.INK)
        p.setPen(QtGui.QPen(ink, 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(x1, strip.top() - 1, x2 - x1, strip.height() + 2), 6, 6)
        p.setPen(Qt.NoPen)
        for x in (x1, x2):
            p.setBrush(ink)
            p.drawRoundedRect(QtCore.QRectF(x - 6, 2, 12, h - 4), 5, 5)
            p.setBrush(QtGui.QColor(ui_theme.DARK))
            p.drawRoundedRect(QtCore.QRectF(x - 1.25, h / 2 - 9, 2.5, 18), 1.25, 1.25)
        # playhead
        xp = self._x(self.pos)
        p.setBrush(QtGui.QColor(ui_theme.RED))
        p.drawRoundedRect(QtCore.QRectF(xp - 1.25, 0, 2.5, h), 1.25, 1.25)

    def mousePressEvent(self, e):
        x = e.position().x()
        if abs(x - self._x(self.start)) < 12:
            self._drag = "start"
        elif abs(x - self._x(self.end)) < 12:
            self._drag = "end"
        else:
            self._drag = "pos"
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        ms = self._ms(e.position().x())
        if self._drag == "start":
            self.start = max(0, min(ms, self.end - self.MIN_MS))
            ms = self.start
            self.changed.emit()
        elif self._drag == "end":
            self.end = min(self.duration, max(ms, self.start + self.MIN_MS))
            ms = self.end
            self.changed.emit()
        self.pos = ms
        self.seek.emit(ms)  # show the frame under the handle
        self.update()

    def mouseReleaseEvent(self, _):
        self._drag = None

    def set_start(self, ms: int):
        self.start = max(0, min(ms, self.end - self.MIN_MS))
        self.changed.emit()
        self.update()

    def set_end(self, ms: int):
        self.end = min(self.duration, max(ms, self.start + self.MIN_MS))
        self.changed.emit()
        self.update()


class SettingRow(HoverFocus, QtWidgets.QWidget):
    """One line in Settings: name and explanation on the left, its value on the right.
    Choices change with ← → (or a click), switches flip, actions (folder, shortcut) open with Enter."""

    changed = QtCore.Signal()
    H = 72

    def __init__(self, key: str, label: str, kind: str, choices: list | None = None, describe=None,
                 custom=None, display=None):
        super().__init__()
        self.key, self.label, self.kind = key, language.tr(label), kind
        self.custom = custom                  # names a value typed into config.json that isn't a choice
        self.choices = [(v, language.tr(t)) for v, t in choices or []]     # [(value, text)]
        self.describe = (lambda v: language.tr(describe(v))) if describe else (lambda v: "")
        self.display = display                # how an action's value reads, e.g. a folder that's not set
        self.value = None
        self.listening = False                # waiting for a new keyboard shortcut
        self.on_activate = None
        self.setFixedHeight(self.H)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)

    def set_value(self, value, emit: bool = False):
        values = [c[0] for c in self.choices]
        if self.kind == "choice" and values and value not in values:   # e.g. 45 min typed into config.json
            numeric = isinstance(value, (int, float)) and all(isinstance(c, (int, float)) for c in values)
            if numeric and self.custom:     # keep it, in order, so saving doesn't quietly change it
                self.choices = sorted(self.choices + [(value, self.custom(value))], key=lambda c: c[0])
            else:
                value = min(values, key=lambda c: abs(c - value)) if numeric else values[0]
        self.value = value
        self.update()
        if emit:
            self.changed.emit()

    def text(self) -> str:
        if self.kind == "bool":
            return language.tr("On") if self.value else language.tr("Off")
        if self.kind == "choice":
            return dict(self.choices).get(self.value, str(self.value))
        if self.listening:
            return language.tr("Press the new keys…")
        if self.display:
            return self.display(self.value)
        if self.key == "hotkey":
            return " + ".join(p.upper() if len(p) <= 3 and p[0] == "f" or len(p) == 1 else p.capitalize()
                              for p in str(self.value).split("+"))
        return str(self.value)

    def step(self, delta: int):
        if self.kind == "bool":
            self.set_value(not self.value, emit=True)
        elif self.kind == "choice":
            values = [c[0] for c in self.choices]
            i = values.index(self.value) if self.value in values else 0
            self.set_value(values[max(0, min(len(values) - 1, i + delta))], emit=True)

    def activate(self):
        if self.kind == "action":
            if self.on_activate:
                self.on_activate(self)
        elif self.kind == "bool":
            self.step(1)
        else:   # Enter on a choice moves to the next one and wraps, like a console menu
            values = [c[0] for c in self.choices]
            i = values.index(self.value) if self.value in values else 0
            self.set_value(values[(i + 1) % len(values)], emit=True)

    def keyPressEvent(self, e):
        self.keep_focus()
        self.window().keyPressEvent(e)   # the page decides; the scroll area would eat the arrows

    def enterEvent(self, e):
        super().enterEvent(e)
        self.hover_in()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if not self.listening:           # waiting for a new shortcut: stay put
            self.hover_out()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        parent = self.parent()
        while parent is not None and not isinstance(parent, QtWidgets.QScrollArea):
            parent = parent.parent()
        if parent is not None and e.reason() != Qt.MouseFocusReason:   # the mouse never scrolls the page
            parent.ensureWidgetVisible(self, 0, 40)
        self.update()
        self.parent().update()     # the card hides the lines next to the focused row

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.listening = False
        self.update()
        self.parent().update()

    def mousePressEvent(self, e):
        self.keep_focus()
        if self.kind == "choice" and e.position().x() < self._value_rect().left() + 28:
            self.step(-1)
        elif self.kind == "choice":
            self.step(1)
        else:
            self.activate()

    def _value_rect(self) -> QtCore.QRectF:
        if language.is_rtl():    # mirrored: the value on the left, the name on the right
            return QtCore.QRectF(16, 0, 284, self.height())
        return QtCore.QRectF(self.width() - 300, 0, 284, self.height())

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        focused = self.hasFocus()
        r = QtCore.QRectF(self.rect()).adjusted(0, 2, 0, -2)
        if focused:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(ui_theme.INK))
            p.drawRoundedRect(r, 16, 16)
        elif self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 14))
            p.drawRoundedRect(r, 16, 16)
        ink = QtGui.QColor(ui_theme.DARK) if focused else QtGui.QColor(ui_theme.INK)
        soft = QtGui.QColor(13, 17, 32, 165) if focused else QtGui.QColor(236, 240, 250, 185)
        desc = self.describe(self.value)
        left = QtCore.QRectF(322 if language.is_rtl() else 18, 0, self.width() - 340, self.height())
        p.setPen(ink)
        p.setFont(ui_theme.font(16, QtGui.QFont.DemiBold if focused else QtGui.QFont.Normal))
        if desc:
            p.drawText(left.adjusted(0, 13, 0, 0), language.lead() | Qt.AlignTop, self.label)
            p.setPen(soft)
            p.setFont(ui_theme.font(14))
            p.drawText(left.adjusted(0, 39, 0, 0), language.lead() | Qt.AlignTop,
                       p.fontMetrics().elidedText(desc, Qt.ElideRight, int(left.width())))
        else:
            p.drawText(left, language.lead() | Qt.AlignVCenter, self.label)
        v = self._value_rect()
        if self.kind == "bool":     # a switch
            track = QtCore.QRectF(v.left() if language.is_rtl() else v.right() - 46, v.center().y() - 13, 46, 26)
            on = bool(self.value) != language.is_rtl()   # the knob sits toward the line's end when on
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(ui_theme.BLUE) if self.value else (QtGui.QColor(13, 17, 32, 60) if focused
                                                        else QtGui.QColor(255, 255, 255, 50)))
            p.drawRoundedRect(track, 13, 13)
            p.setBrush(QtGui.QColor("white"))
            p.drawEllipse(QtCore.QPointF(track.right() - 13 if on else track.left() + 13, track.center().y()), 10, 10)
            return
        p.setFont(ui_theme.font(15, QtGui.QFont.DemiBold if focused else QtGui.QFont.Normal))
        p.setPen(ink if focused or self.listening else QtGui.QColor(236, 240, 250, 220))
        if self.kind == "choice":   # a pill with ‹ › on every row, so it's clear the value can change
            values = [c[0] for c in self.choices]
            i = values.index(self.value) if self.value in values else 0
            pill = QtCore.QRectF(v.left(), v.center().y() - 19, v.width(), 38)
            p.save()
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(13, 17, 32, 22) if focused else QtGui.QColor(255, 255, 255, 16))
            p.drawRoundedRect(pill, 19, 19)
            p.restore()
            arrow = ui_theme.DARK if focused else ui_theme.INK
            for name, x, can in (("left", pill.left() + 10, i > 0),
                                 ("right", pill.right() - 28, i < len(values) - 1)):
                p.setOpacity((1.0 if focused else 0.6) if can else 0.16)
                p.drawPixmap(QtCore.QPointF(x, pill.center().y() - 9), ui_theme.icon_pixmap(name, 18, arrow))
            p.setOpacity(1.0)
            p.drawText(pill.adjusted(34, 0, -34, 0), Qt.AlignCenter,
                       p.fontMetrics().elidedText(self.text(), Qt.ElideRight, int(pill.width() - 68)))
        else:   # a folder, the shortcut, updates: the value, then › like a button that opens something
            edge = (Qt.AlignLeft | Qt.AlignAbsolute) if language.is_rtl() else Qt.AlignRight
            room = 0 if self.listening else 26     # room for the ›
            text_rect = v.adjusted(room, 0, 0, 0) if language.is_rtl() else v.adjusted(0, 0, -room, 0)
            text = p.fontMetrics().elidedText(self.text(), Qt.ElideMiddle, int(text_rect.width()))
            p.drawText(text_rect, edge | Qt.AlignVCenter, text)
            if not self.listening:
                p.setOpacity(1.0 if focused else 0.6)
                x = v.left() if language.is_rtl() else v.right() - 18
                p.drawPixmap(QtCore.QPointF(x, v.center().y() - 9),
                             ui_theme.icon_pixmap("left" if language.is_rtl() else "right", 18, ui_theme.DARK if focused else ui_theme.INK))
                p.setOpacity(1.0)


def back_button(on_click) -> QtWidgets.QPushButton:
    """"Back": one step back to where you came from (Esc and ◯ / B do the same)."""
    b = QtWidgets.QPushButton(" " + language.tr("Back"), objectName="back")
    b.setIcon(ui_theme.qicon("right" if language.is_rtl() else "left"))   # points to where the line starts
    b.setIconSize(QtCore.QSize(18, 18))
    b.setFocusPolicy(Qt.NoFocus)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(language.tr("Back (Esc)"))
    b.clicked.connect(on_click)
    return b


class LevelSlider(QtWidgets.QSlider):
    """A volume bar. ← → (and the mouse) move it; every other key goes on to the window."""

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            super().keyPressEvent(e)
        else:
            e.ignore()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.parent().update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.parent().update()


class SectionTitle(QtWidgets.QLabel):
    def __init__(self, text: str):
        text = language.tr(text)
        super().__init__(text.capitalize() if text.isupper() else text)   # the keys are capitals
        self.setStyleSheet(f"color: {ui_theme.INK}; font-size: 20px; font-weight: 600; padding: 30px 10px 12px 10px;")


class SettingsCard(QtWidgets.QWidget):
    """A section's rows on their own darker panel, so they read clearly over any game,
    with thin lines between them."""

    def __init__(self):
        super().__init__()
        self.rows = QtWidgets.QVBoxLayout(self)
        self.rows.setContentsMargins(6, 6, 6, 6)
        self.rows.setSpacing(0)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1))
        p.setBrush(QtGui.QColor(24, 29, 44, 175))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 22, 22)
        rows = [self.rows.itemAt(i).widget() for i in range(self.rows.count())]
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 16), 1))
        for above, below in zip(rows, rows[1:]):
            if not (above.hasFocus() or below.hasFocus()):
                y = below.geometry().top() + 0.5
                p.drawLine(QtCore.QPointF(24, y), QtCore.QPointF(self.width() - 24, y))

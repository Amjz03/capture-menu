"""Capture gallery, categories, selection and batch actions."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_viewer import Viewer

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from datetime import date, datetime
from pathlib import Path
import threading

from . import (
    capture_controller,
    catalog,
    input_devices,
    language,
    media,
    runtime,
    ui_theme,
    ui_viewer,
    ui_widgets,
    windows,
)


class TileDelegate(QtWidgets.QStyledItemDelegate):
    """Draws gallery tiles as they scroll into view, so 1000 captures cost no more than 30."""

    def __init__(self, gallery: "Gallery"):
        super().__init__(gallery)
        self.g = gallery
        self.cache: dict[str, QtGui.QPixmap] = {}   # insertion order = least recently used first

    def limit(self) -> int:
        """Two screens of tiles (each 150-600 KB): scrolling back is instant, a long gallery costs no more."""
        view = self.g.grid.viewport().size()
        cell = QtCore.QSize(self.g.TW + 2 * self.g.PAD, self.g.TH + self.g.PAD + self.g.TEXT_H + self.g.ACTIONS_H)
        return 2 * max(1, view.width() // cell.width()) * (max(0, view.height()) // cell.height() + 2)

    def pixmap(self, path: Path) -> QtGui.QPixmap:
        key = str(path)
        pm = self.cache.pop(key, None)
        if pm is None:
            pm = ui_theme.rounded_pixmap(self.g.ctl.thumb(path), self.g.TW, self.g.TH, 20,
                                max(1.0, self.g.devicePixelRatioF()))
        self.cache[key] = pm
        limit = self.limit()
        while len(self.cache) > limit:
            self.cache.pop(next(iter(self.cache)))
        return pm

    def forget(self, path: str | None = None):
        if path is None:
            self.cache.clear()
        else:
            self.cache.pop(path, None)

    def sizeHint(self, option, index):
        hint = index.data(Qt.SizeHintRole)
        return hint if hint else QtCore.QSize(self.g.TW + 2 * self.g.PAD, self.g.TH + self.g.PAD + self.g.TEXT_H + self.g.ACTIONS_H)

    def paint_header(self, p: QtGui.QPainter, r: QtCore.QRectF, index):
        """A day's heading over its captures: Today, Yesterday, 23 Nov; with how many and how big."""
        title, sub = index.data(Qt.DisplayRole), index.data(Qt.UserRole + 1) or ""
        p.save()
        box = r.adjusted(self.g.PAD, 8, -self.g.PAD, -4)      # spec: Heading 24, then Caption 15 (tertiary) 14 after it
        p.setPen(QtGui.QColor(ui_theme.INK))
        p.setFont(ui_theme.font(21, QtGui.QFont.DemiBold, display=True))
        w = p.fontMetrics().horizontalAdvance(title)
        p.drawText(box, language.lead() | Qt.AlignVCenter, title)
        p.setPen(QtGui.QColor(236, 240, 250, 168))
        p.setFont(ui_theme.font(14))
        rest = box.adjusted(0, 4, -(w + 14), 0) if language.is_rtl() else box.adjusted(w + 14, 4, 0, 0)
        p.drawText(rest, language.lead() | Qt.AlignVCenter, sub)
        p.restore()

    def paint(self, p: QtGui.QPainter, option, index):
        if index.data(Qt.UserRole) is None:
            self.paint_header(p, QtCore.QRectF(option.rect), index)
            return
        path = Path(index.data(Qt.UserRole))
        r = QtCore.QRectF(option.rect)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected) and self.g.grid_lit()
        # the current tile grows into focus, like the PS5, while the one before settles back
        t = self.g.grow if selected else (1 - self.g.grow) if index.row() == self.g.last_row else 0.0
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rest = QtCore.QRectF(r.x() + (r.width() - self.g.TW) / 2, r.y() + self.g.PAD, self.g.TW, self.g.TH)
        tile = ui_theme.grown(rest, 0.05 * t)
        radius = 20 * tile.width() / rest.width()
        ctl = self.g.ctl
        ui_widgets.draw_capture_tile(p, tile, self.pixmap(path), path, ctl.length_of(path), ctl.is_favorite(path),
                          dim=int(70 * (1 - t)), radius=radius, marked=path in self.g.marked,
                          selecting=self.g.selecting)
        ui_theme.paint_focus(p, tile, radius, t)
        title, _, sub = index.data(Qt.DisplayRole).partition("\n")
        # spec: gap 10; the current one Body strong 20/28, the others Label 18/24; meta Caption 15 (secondary)
        text = QtCore.QRectF(rest.left(), rest.bottom() + 10, rest.width(), 26)
        p.setPen(QtGui.QColor(ui_theme.INK))
        p.setFont(ui_theme.font(17, QtGui.QFont.DemiBold) if selected else ui_theme.font(16))
        p.drawText(text, language.lead() | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.ElideRight, int(rest.width())))
        p.setPen(QtGui.QColor(236, 240, 250, 214))
        p.setFont(ui_theme.font(14))
        p.drawText(QtCore.QRectF(text.left(), text.bottom() + 2, text.width(), 20), language.lead() | Qt.AlignVCenter, sub)
        if selected and not self.g.selecting:     # what the current capture can do, right under it
            self.g.quick_rects = self.paint_actions(p, rest, path, option.rect)
        p.restore()

    def paint_actions(self, p: QtGui.QPainter, rest: QtCore.QRectF, path: Path, cell: QtCore.QRect) -> list:
        """Play (or Open), Share and, for a clip, Trim: small buttons under the current tile, with the
        key or controller button that does each. Returns their places, for clicks."""
        mode = input_devices.input_mode().mode
        pad = mode != "keyboard"
        video = path.suffix.lower() != ".png"
        acts = [("play" if video else "image", "Play" if video else "Open", "A" if pad else "k:Enter", "open"),
                ("share", "Share", "Y" if pad else "k:E", "share")]
        if video:
            acts.append(("scissors", "Trim", None if pad else "k:R", "trim"))     # no button left for it on a pad
        # spec: chips 42 high, surface/tile-strong, r20, pad 9, 16, 9, 14, gap 8: glyph 24, icon 18, Hint 17
        x, y = rest.left(), rest.bottom() + 10 + 26 + 2 + 20 + 10
        out = []
        p.setFont(ui_theme.font(15))
        order = list(reversed(acts)) if language.is_rtl() else acts
        widths = [12 + 16 + 8 + p.fontMetrics().horizontalAdvance(language.tr(label)) + 14
                  + (ui_theme.glyph_width(token, mode) + 8 if token else 0) for _, label, token, _ in order]
        if language.is_rtl():
            x = rest.right() - sum(widths) - 8 * (len(widths) - 1)
        for (icon, label, token, action), w in zip(order, widths):
            chip = QtCore.QRectF(x, y, w, 36)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 41))
            p.drawRoundedRect(chip, 18, 18)
            # the button prompt, the icon, then the word; from the right in Arabic
            rtl, cy = language.is_rtl(), chip.center().y()
            gw = ui_theme.glyph_width(token, mode) if token else 0
            gx = chip.right() - 12 - gw if rtl else chip.left() + 12
            if token:
                ui_theme.draw_glyph(p, gx, cy, token, mode)
            ix = (gx - (8 if token else 0) - 16) if rtl else (gx + (gw + 8 if token else 0))
            p.drawPixmap(QtCore.QRectF(ix, cy - 8, 16, 16).toRect(), ui_theme.icon_pixmap(icon, 16))
            p.setFont(ui_theme.font(15))
            p.setPen(QtGui.QColor(ui_theme.INK))
            words = (QtCore.QRectF(chip.left(), chip.top(), ix - 8 - chip.left(), chip.height()) if rtl
                     else QtCore.QRectF(ix + 24, chip.top(), chip.right() - ix - 24, chip.height()))
            p.drawText(words, Qt.AlignVCenter | (Qt.AlignRight | Qt.AlignAbsolute if rtl else Qt.AlignLeft), language.tr(label))
            out.append((chip.translated(-cell.left(), -cell.top()), action))
            x += w + 8
        return out


class CategoryDelegate(QtWidgets.QStyledItemDelegate):
    """Gallery sidebar rows: name on the left, count and size on the right; the current one is white."""

    def sizeHint(self, option, index):
        return QtCore.QSize(option.rect.width(), 50)

    def paint(self, p: QtGui.QPainter, option, index):
        name, count, size, *rest = index.data(Qt.UserRole)
        lead = rest[0] if rest else None       # the game's latest capture, or the icon for All / Favorites
        r = QtCore.QRectF(option.rect).adjusted(12, 3, -14, -3)      # spec: pad 0, 14, 0, 12
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if selected:      # spec: surface/selection, r14
            pill = QtCore.QRectF(option.rect).adjusted(0, 3, 0, -3)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 56))
            p.drawRoundedRect(pill, 14, 14)
            if option.widget is not None and ui_theme.focus_shown(option.widget):   # the controller's highlight is here
                p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.INK), 2.5))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(pill.adjusted(1.25, 1.25, -1.25, -1.25), 13, 13)
        right = f"{count}"
        p.setFont(ui_theme.font(15))
        p.setPen(QtGui.QColor(236, 240, 250, 214))
        rw = p.fontMetrics().horizontalAdvance(right)
        rtl = language.is_rtl()    # the count sits at the far end of the line from the name
        p.drawText(r, ((Qt.AlignLeft | Qt.AlignAbsolute) if rtl else Qt.AlignRight) | Qt.AlignVCenter, right)
        if lead:      # a round picture of the game (its newest capture), or the row's icon
            spot = QtCore.QRectF(r.right() - 26 if rtl else r.left(), r.center().y() - 13, 26, 26)
            if isinstance(lead, str):
                p.drawPixmap(spot.adjusted(4, 4, -4, -4).toRect(), ui_theme.icon_pixmap(lead, 18, ui_theme.INK))
            else:                          # a round picture of the game
                pm = ui_theme.rounded_pixmap(lead, 26, 26, 13)
                p.drawPixmap(spot.toRect(), pm)
            r = r.adjusted(0, 0, -38, 0) if rtl else r.adjusted(38, 0, 0, 0)
        p.setFont(ui_theme.font(17, QtGui.QFont.DemiBold) if selected else ui_theme.font(17))
        p.setPen(QtGui.QColor(ui_theme.INK))
        p.drawText(r.adjusted(rw + 12, 0, 0, 0) if rtl else r.adjusted(0, 0, -rw - 12, 0), language.lead() | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.ElideRight, int(r.width() - rw - 12)))
        p.restore()


class Gallery(ui_widgets.Grow, QtWidgets.QWidget):
    """All captures, like the PS5 Media Gallery: games on the left, their captures on the right."""

    thumb_ready = QtCore.Signal(str)
    deleted = QtCore.Signal(int, int)      # how many went to the Recycle Bin, of how many picked
    TW, TH = 256, 144        # set from the grid's width by _fit_tiles()
    PAD = 12                 # room around a tile to grow into when it's the current one (24 between tiles)
    TEXT_H = 68              # gap 10, the title 26, gap 2, its meta 20, gap 10
    ACTIONS_H = 44           # room under each tile for the current one's Play / Share / Trim (36 + 8)
    HEADER_H = 48            # a day's heading (32), 16 above its captures
    FAVORITES = "★  Favorites"
    last_row = -1            # the tile that had the focus before; it settles back as the new one grows
    _row = -1

    def _on_grow(self, value):
        self.grow = float(value)
        self.grid.viewport().update()

    def _regrow(self, row: int):
        """The current tile changed: it grows into focus."""
        self.last_row, self._row = self._row, row
        self.grow = 0.0
        self.grow_to(True)

    def _room(self) -> int:
        """The grid's width for tiles, as if its scroll bar showed: the same whether it does or not, so the
        columns don't change when the bar comes and goes (that left the first look scattered)."""
        return self.grid.width() - 2 * self.grid.frameWidth() - self.grid.verticalScrollBar().sizeHint().width() - 6

    def _fit_tiles(self):
        """As many columns as fit tiles of about 350 px, sharing the width evenly, so the grid
        fills the page edge to edge. The scroll bar's room is kept either way."""
        room = self._room()
        cell = room // max(2, round(room / 381))       # spec: 357 wide cards, 24 apart
        if cell - 2 * self.PAD != self.TW:
            self.TW = cell - 2 * self.PAD
            self.TH = round(self.TW * 9 / 16)
            self.tiles.forget()
        self._size_rows(cell, room)
        self.grid.doItemsLayout()       # new sizes: the list only places its items again when told

    def _size_rows(self, cell: int | None = None, room: int | None = None):
        """Tiles all one size; a day's heading as wide as the grid, so its captures start a new line."""
        room = room if room is not None else self._room()
        cell = cell if cell is not None else self.TW + 2 * self.PAD
        tile, head = QtCore.QSize(cell, self.TH + self.PAD + self.TEXT_H + self.ACTIONS_H), QtCore.QSize(max(cell, room - 2), self.HEADER_H)
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            want = head if item.data(Qt.UserRole) is None else tile
            if item.sizeHint() != want:
                item.setSizeHint(want)

    def __init__(self, ctl: capture_controller.Controller, viewer: "Viewer"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setProperty("captureMenuPage", "gallery")
        self.ctl, self.viewer = ctl, viewer
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(ui_theme.GALLERY_STYLE)
        self.setFont(ui_theme.font(13))
        ui_theme.dress(self)
        self.cats: list[tuple[str, list[Path]]] = []
        self.items: list[Path] = []
        self.marked: set[Path] = set()
        self._making: set[Path] = set()            # thumbnails being made now (one job per file)
        self.by_size = False
        self.select_mode = False      # Select pressed: a click (or ✕ / Enter) picks instead of opening
        self._deleting = False        # the picked captures are on their way to the Recycle Bin

        # spec: a glass rail down the left (the title, All / Favorites / the games, the storage card at its
        # foot), then the search and buttons along the top of the grid
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 24)
        outer.setSpacing(40)
        self.rail = QtWidgets.QFrame(objectName="sidePanel")
        self.rail.setFixedWidth(300)
        rail = QtWidgets.QVBoxLayout(self.rail)
        rail.setContentsMargins(20, 28, 20, 20)
        rail.setSpacing(6)
        titles = QtWidgets.QVBoxLayout()
        titles.setContentsMargins(8, 0, 0, 16)
        titles.setSpacing(2)
        titles.addWidget(QtWidgets.QLabel(language.tr("Captures"), objectName="vTitle"))
        self.info = QtWidgets.QLabel(objectName="vSub")
        self.info.setWordWrap(True)
        titles.addWidget(self.info)
        rail.addLayout(titles)
        outer.addWidget(self.rail)
        lay = QtWidgets.QVBoxLayout()
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(24)
        outer.addLayout(lay, 1)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(12)
        self.back_btn = ui_widgets.back_button(self.go_back)
        head.addWidget(self.back_btn)
        # find a capture by its title, note, file name or game; and show only one kind of capture
        self.search = QtWidgets.QLineEdit(placeholderText=language.tr("Search titles, notes, games"), objectName="search")
        self.search.setFixedWidth(420)
        self.search.setClearButtonEnabled(True)
        self.search.setFocusPolicy(Qt.ClickFocus)
        self.search.addAction(ui_theme.qicon("search"), QtWidgets.QLineEdit.LeadingPosition)
        self.search.textChanged.connect(lambda _: self._fill(self.games.currentRow()))
        head.addWidget(self.search)
        self.kind = "all"
        self.kind_btns: dict[str, QtWidgets.QPushButton] = {}    # one button per kind, the shown one white
        for kind, label in self.KIND_CHIPS:
            b = QtWidgets.QPushButton(language.tr(label), objectName="kind")
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=kind: self.show_kind(k))
            head.addWidget(b)
            self.kind_btns[kind] = b
        self._mark_kind()
        head.addStretch()
        self.sort_btn = QtWidgets.QPushButton(language.tr("Sort: Newest"))
        self.sort_btn.setFocusPolicy(Qt.NoFocus)
        self.sort_btn.setCursor(Qt.PointingHandCursor)
        self.sort_btn.clicked.connect(self.toggle_sort)
        head.addWidget(self.sort_btn)
        self.select_btn = QtWidgets.QPushButton("  " + language.tr("Select"))
        self.select_btn.setIcon(ui_theme.qicon("select"))
        self.select_btn.setIconSize(QtCore.QSize(18, 18))
        self.select_btn.setFocusPolicy(Qt.NoFocus)
        self.select_btn.setCursor(Qt.PointingHandCursor)
        self.select_btn.clicked.connect(self.start_selecting)
        head.addWidget(self.select_btn)
        self.all_btn = QtWidgets.QPushButton(language.tr("Select all"))
        self.del_btn = QtWidgets.QPushButton(language.tr("Delete selected"))
        self.del_btn.setIcon(ui_theme.qicon("trash"))
        self.clear_btn = QtWidgets.QPushButton(language.tr("Cancel"))
        for b, fn in ((self.all_btn, self.mark_all), (self.del_btn, self.delete_marked),
                      (self.clear_btn, self.stop_selecting)):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            b.hide()
            head.addWidget(b)
        self._disarm = QtCore.QTimer(self, singleShot=True, timeout=self._reset_delete)
        def open_folder():      # the folder opens over the gallery, which stays underneath
            ui_theme.make_room_above()
            self.ctl.open_folder()
        for text, icon, fn in (("", "folder", open_folder), ("", "close", self.close_gallery)):
            b = QtWidgets.QPushButton(text, objectName="" if text else "round")
            b.setToolTip(language.tr("Open the clips folder") if icon == "folder" else language.tr("Close (Esc)"))
            b.setIcon(ui_theme.qicon(icon))
            b.setIconSize(QtCore.QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(fn)
            head.addWidget(b)
            setattr(self, f"{icon}_btn", b)       # folder_btn, close_btn
        lay.addLayout(head)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(0)
        self.games = QtWidgets.QListWidget(objectName="games")
        self.games.setItemDelegate(CategoryDelegate(self.games))
        self.games.setFocusPolicy(Qt.NoFocus)        # switch games with [ ] / L1 R1 or the mouse
        self.games.currentRowChanged.connect(self._fill)
        rail.addWidget(self.games, 1)
        self.storage = StorageMeter()
        rail.addWidget(self.storage)
        self.grid = QtWidgets.QListWidget(objectName="grid")
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.tiles = TileDelegate(self)
        self.grid.setItemDelegate(self.tiles)
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(False)     # a day's heading is a row of its own
        self.grid.setWordWrap(True)
        self.grid.setSpacing(0)
        self.rows: list[Path | None] = []        # what each row of the grid is: a capture, or a day's heading
        self.quick_rects: list = []              # where the current tile's Play / Share / Trim are drawn
        self.grid.viewport().installEventFilter(self)
        self.grid.itemDoubleClicked.connect(lambda item: None if self.selecting or item.data(Qt.UserRole) is None
                                            else self.open_selected())
        self.grid.itemClicked.connect(self._clicked)
        self.grid.currentRowChanged.connect(lambda row: (self._update_info(), self._regrow(row)))
        self.grid.installEventFilter(self)
        self.search.installEventFilter(self)
        for w in (*self._head_nav(all=True), self.games):
            w.installEventFilter(self)          # the D-pad moves between them too, like a mouse
        body.addWidget(self.grid, 1)
        lay.addLayout(body, 1)
        self.hints = ui_widgets.HintBar()
        lay.addWidget(self.hints)

        self.thumb_ready.connect(self._on_thumb)
        self.deleted.connect(self._on_deleted)
        viewer.closed.connect(self._after_viewer)
        viewer.away.connect(self.close_gallery)
        ctl.captured.connect(lambda *_: self.refresh() if self.isVisible() else None)
        ctl.library_changed.connect(lambda: self.refresh() if self.isVisible() else None)
        input_devices.input_mode().changed.connect(lambda _: self.update_hints())
        self.update_hints()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)      # the sheet: the game stays faintly visible behind it
        p.fillRect(self.rect(), ui_theme.sheet_color(self))

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.ActivationChange and self.isActiveWindow():
            ui_theme.set_on_top(self, True)            # back in use after the folder opened over it
        super().changeEvent(e)

    # ---- open / close
    def open(self, game: str | None = None, back_to=None, fresh: bool = False):
        """fresh: opened from outside (the tray), not from another page."""
        self.back_to = back_to      # what Back returns to (None: just close)
        ui_theme.dress(self)
        self.setGeometry(windows.ui_screen(fresh).geometry())
        self._load(select=game)
        self.storage.set_storage(self.ctl.last_storage)
        self.show()
        ui_theme.set_on_top(self, True)
        ui_theme.bring_to_front(self)
        self.grid.setFocus()
        QtCore.QTimer.singleShot(0, self._fit_tiles)     # filled before it showed: lay it out at its real width

    @property
    def selecting(self) -> bool:
        return self.select_mode or bool(self.marked)

    def start_selecting(self):
        self.select_mode = True
        self._update_info()
        self.update_hints()
        self.grid.viewport().update()
        self.grid.setFocus()

    def stop_selecting(self):
        self.select_mode = False
        self.clear_marks()
        self.update_hints()

    def go_back(self):
        """A selection is let go first; then back to wherever the gallery was opened from."""
        if self.selecting:
            self.stop_selecting()
            return
        back, self.back_to = getattr(self, "back_to", None), None
        self.close_gallery()
        if back:
            back()

    def close_gallery(self):
        self.select_mode = False
        self.clear_marks()
        self.hide()
        self.search.blockSignals(True)
        self.search.clear()      # the next visit starts with everything
        self.search.blockSignals(False)
        self.grid.clear()        # the tiles' pixmaps go with it; reopening rebuilds them in ~0.1 s
        self.tiles.forget()
        self.items = []

    def refresh(self):
        name = self.cats[self.games.currentRow()][0] if self.cats and self.games.currentRow() >= 0 else None
        current = self.current_path()
        self._load(select=name, row=self.items.index(current) if current in self.items else 0)

    def _after_viewer(self):
        if self.isVisible():
            self.refresh()
            ui_theme.bring_to_front(self)
            self.grid.setFocus()

    # ---- content
    def _load(self, select: str | None = None, row: int = 0):
        everything = self.ctl.all_captures()
        self.marked &= set(everything)
        favs = self.ctl.favorites()
        by_game: dict[str, list[Path]] = {}
        for p in everything:   # already newest first, so games are ordered by latest capture
            by_game.setdefault(p.parent.name, []).append(p)
        games = list(by_game.items())
        if self.by_size:   # biggest games first, and inside each list the biggest captures first
            games.sort(key=lambda kv: sum(self.ctl.size_of(p) for p in kv[1]), reverse=True)
        self.cats = [("All", everything),
                     (self.FAVORITES, [p for p in everything if self.ctl._fav_key(p) in favs]),
                     *games]
        if self.by_size:
            self.cats = [(n, sorted(ps, key=self.ctl.size_of, reverse=True)) for n, ps in self.cats]
        self.games.blockSignals(True)
        self.games.clear()
        for name, items in self.cats:
            size = catalog.human_size(sum(self.ctl.size_of(p) for p in items))
            item = QtWidgets.QListWidgetItem(f"{name}   {len(items)}  ·  {size}")
            lead = ("gallery" if name == "All" else "star" if name == self.FAVORITES
                    else (self.ctl.thumb(items[0]) if items else None))
            item.setData(Qt.UserRole, (self._cat_name(name), len(items), size, lead))
            self.games.addItem(item)
        names = [c[0] for c in self.cats]
        self.games.setCurrentRow(names.index(select) if select in names else 0)
        self.games.blockSignals(False)
        self._fill(self.games.currentRow(), row)

    def _fill(self, cat_row: int, select_row: int = 0):
        if cat_row < 0 or cat_row >= len(self.cats):
            return
        self.items = self._shown(self.cats[cat_row][1])
        self._items_size = sum(self.ctl.size_of(p) for p in self.items)   # once, not at every move of the highlight
        self.grid.clear()
        self.rows = []
        self.quick_rects = []
        missing = []
        all_cat = self.cats[cat_row][0] == "All"
        for day, paths in self._days(self.items):
            if day is not None:     # newest first: each day under its heading
                head = QtWidgets.QListWidgetItem(day)
                head.setFlags(Qt.NoItemFlags)
                head.setData(Qt.UserRole, None)
                count = language.tr("1 capture") if len(paths) == 1 else language.tr("{n} captures", n=len(paths))
                head.setData(Qt.UserRole + 1, f"{count}  ·  {catalog.human_size(sum(self.ctl.size_of(x) for x in paths))}")
                self.grid.addItem(head)
                self.rows.append(None)
            for p in paths:
                title = self.ctl.title_of(p) or catalog.capture_kind(p)
                title = title if len(title) <= 30 else title[:29] + "…"
                game = f"{p.parent.name}  ·  " if all_cat else ""
                item = QtWidgets.QListWidgetItem(f"{title}\n{game}{catalog.time_ago(self.ctl.modified_of(p))}  ·  "
                                                 f"{catalog.human_size(self.ctl.size_of(p))}")
                item.setData(Qt.UserRole, str(p))
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
                self.grid.addItem(item)
                self.rows.append(p)
                if (self.ctl.thumb(p) is None or (p.suffix.lower() != ".png" and self.ctl.length_of(p) is None)) \
                        and p not in self._making:
                    missing.append(p)
        self._size_rows()
        if self.items:
            self.select_item(max(0, min(select_row, len(self.items) - 1)))
        self._update_info()
        if missing:
            self._making |= set(missing)       # a refresh meanwhile doesn't start them again
            def run():   # thumbnails and lengths for captures not seen yet
                for p in missing:
                    try:
                        media.make_thumb(p, self.ctl.thumbs_dir)
                        if p.suffix.lower() != ".png" and p not in self.ctl.lengths:
                            self.ctl.lengths[p] = media.media_duration(p)
                    finally:
                        self._making.discard(p)
                    runtime.safe_emit(self.thumb_ready, str(p))
                self.ctl.save_lengths()
            threading.Thread(target=run, daemon=True).start()

    def _days(self, items: list[Path]) -> list[tuple[str | None, list[Path]]]:
        """Newest first, in three groups: Today, This week (the 6 days before), All earlier captures. Sorted by size there
        are no groups."""
        if self.by_size:
            return [(None, list(items))]
        groups: list[tuple[str | None, list[Path]]] = []
        today = date.today()
        for p in items:
            ago = (today - datetime.fromtimestamp(self.ctl.modified_of(p)).date()).days
            label = (language.tr("Today") if ago <= 0 else language.tr("This week") if ago < 7
                     else language.tr("All earlier captures"))
            if groups and groups[-1][0] == label:
                groups[-1][1].append(p)
            else:
                groups.append((label, [p]))
        return groups

    def current_path(self) -> Path | None:
        """The capture the highlight is on (never a day's heading)."""
        row = self.grid.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def select_item(self, i: int):
        """Puts the highlight on the i-th capture shown (headings don't count)."""
        if 0 <= i < len(self.items):
            self.grid.setCurrentRow(self.rows.index(self.items[i]))

    def _on_thumb(self, path: str):
        self.tiles.forget(path)
        self.grid.viewport().update()

    def _update_info(self):
        name = self.cats[self.games.currentRow()][0] if self.cats else ""
        count = len(self.items)
        size = catalog.human_size(getattr(self, "_items_size", 0))
        storage = self.ctl.last_storage
        used = "  ·  " + language.tr("{used} GB used in total", used=f"{storage['used_gb']:.0f}") if storage else ""
        captures = language.tr("1 capture") if count == 1 else language.tr("{n} captures", n=count)
        text = f"{self._cat_name(name)}  ·  {captures}  ·  {size}{used}"
        if self.marked:
            text = (language.tr("{n} selected", n=len(self.marked)) + "  ·  "
                    f"{catalog.human_size(sum(self.ctl.size_of(p) for p in self.marked))}  ·  {text}")
        self.info.setText(text)
        picking = self.selecting
        self.select_btn.setVisible(not picking)     # search stays while picking; the rest makes room for its buttons
        self.sort_btn.setVisible(not picking)
        for b in self.kind_btns.values():
            b.setVisible(not picking)
        for b in (self.all_btn, self.del_btn, self.clear_btn):
            b.setVisible(picking)
        self.del_btn.setEnabled(bool(self.marked))
        self.all_btn.setText(language.tr("Select none") if self.items and self.marked == set(self.items) else language.tr("Select all"))
        self.update_hints()
        if not self.del_btn.property("danger") and not self._deleting:
            self.del_btn.setText(language.tr("Delete {n}", n=len(self.marked)))

    @classmethod
    def _cat_name(cls, name: str) -> str:
        return language.tr("Favorites") if name == cls.FAVORITES else language.tr("All") if name == "All" else name

    # ---- search, show, sort, select, delete many
    KINDS = (("all", "Show: Everything"), ("clips", "Show: Clips"), ("shots", "Show: Screenshots"),
             ("recordings", "Show: Recordings"))
    KIND_CHIPS = (("all", "All"), ("clips", "Clips"), ("shots", "Screenshots"), ("recordings", "Recordings"))

    @staticmethod
    def kind_of(path: Path) -> str:
        first = path.stem.split("_")[0]
        return "shots" if path.suffix.lower() == ".png" else "recordings" if first == "Recording" else "clips"

    def _shown(self, items: list[Path]) -> list[Path]:
        """The game's captures that pass "Show" and the search (title, note, file name or game)."""
        words = self.search.text().casefold().split()
        if self.kind == "all" and not words:
            return list(items)
        out = []
        for p in items:
            if self.kind != "all" and self.kind_of(p) != self.kind:
                continue
            if words:
                meta = self.ctl.meta(p)
                text = " ".join((meta.get("title", ""), meta.get("note", ""), p.stem, p.parent.name)).casefold()
                if not all(w in text for w in words):
                    continue
            out.append(p)
        return out

    def next_kind(self):
        kinds = [k for k, _ in self.KINDS]
        self.show_kind(kinds[(kinds.index(self.kind) + 1) % len(kinds)])

    def show_kind(self, kind: str):
        self.kind = kind
        self._mark_kind()
        self._fill(self.games.currentRow())

    def _mark_kind(self):
        for k, b in self.kind_btns.items():
            b.setProperty("on", k == self.kind)
            ui_viewer.Viewer._repolish(b)

    def start_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def toggle_sort(self):
        self.by_size = not self.by_size
        self.sort_btn.setText(language.tr("Sort: Largest") if self.by_size else language.tr("Sort: Newest"))
        self.refresh()

    def _clicked(self, item):
        if self.selecting or QtWidgets.QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_mark()       # while selecting a click picks; Ctrl+click always does, like Explorer

    def toggle_mark(self):
        p = self.current_path()
        if p is not None:
            self.marked.symmetric_difference_update({p})
            self.grid.viewport().update()
            self._reset_delete()
            self._update_info()

    def mark_all(self):
        self.marked = set(self.items) if self.marked != set(self.items) else set()
        self.grid.viewport().update()
        self._reset_delete()
        self._update_info()

    def clear_marks(self):
        if self.marked:
            self.marked.clear()
            self.grid.viewport().update()
        self._reset_delete()
        self._update_info()

    def delete_marked(self):
        if self._deleting:
            return
        if not self.marked:        # nothing picked: Del means the capture the highlight is on
            p = self.current_path()
            if p is None or not self.grid_lit():
                return
            self.marked = {p}
            self.grid.viewport().update()
            self._update_info()
        if not self.del_btn.property("danger"):   # first press arms, second press deletes
            favs = sum(self.ctl.is_favorite(p) for p in self.marked)
            note = (" " + (language.tr("(incl. 1 favorite)") if favs == 1 else language.tr("(incl. {n} favorites)", n=favs))
                    if favs else "")
            self.del_btn.setProperty("danger", True)
            self.del_btn.setText(language.tr("Press again to delete {n}", n=len(self.marked)) + note)
            ui_viewer.Viewer._repolish(self.del_btn)
            self._disarm.start(4000)
            return
        paths = sorted(self.marked)
        self._deleting = True
        self._disarm.stop()
        self.del_btn.setText(language.tr("Deleting…"))

        def run():     # the Recycle Bin takes its time with many files: never on the page's own thread
            try:
                count, _ = self.ctl.delete_many(paths)
            except Exception:
                runtime.log.exception("deleting the selected captures failed")
                count = sum(not p.exists() for p in paths)
            runtime.safe_emit(self.deleted, count, len(paths))
        threading.Thread(target=run, daemon=True).start()

    def _on_deleted(self, count: int, total: int):
        self._deleting = False
        self.marked = {p for p in self.marked if p.exists()}
        self._reset_delete()
        if count == total:
            message = (language.tr("Moved 1 capture to the Recycle Bin") if count == 1 else
                       language.tr("Moved {n} captures to the Recycle Bin", n=count))
        elif count:
            message = language.tr("Moved {n} of {total} captures to the Recycle Bin; {failed} could not be moved",
                         n=count, total=total, failed=total - count)
        else:
            message = language.tr("No captures were moved to the Recycle Bin")
        self.ctl.toast.emit(message, "ok" if count == total else "error")
        self.refresh()

    def _reset_delete(self):
        self.del_btn.setProperty("danger", False)
        ui_viewer.Viewer._repolish(self.del_btn)
        self.del_btn.setText(language.tr("Delete {n}", n=len(self.marked)))

    # ---- actions
    def open_selected(self, then: str | None = None):
        """Opens the current capture; then: "share" or "trim" goes straight on to that."""
        p = self.current_path()
        if p is None:
            return
        self.viewer.open(self.items, self.items.index(p), trim=then == "trim" and p.suffix.lower() != ".png")
        if then == "share":
            self.viewer.enter_share()

    def step_game(self, delta: int):
        row = max(0, min(self.games.count() - 1, self.games.currentRow() + delta))
        self.games.setCurrentRow(row)

    def toggle_favorite(self):
        p = self.current_path()
        if p is not None:
            self.ctl.toggle_favorite(p)
            self.grid.viewport().update()
            if self.cats[self.games.currentRow()][0] == self.FAVORITES:
                self.refresh()

    def update_hints(self):
        pad = input_devices.input_mode().mode != "keyboard"
        if self.selecting:
            self.hints.set_items(
                [("DPAD", "Move"), ("A", "Select"), ("OPT", "Delete selected"), ("B", "Done")] if pad
                else [("k:← →", "Move"), ("k:Enter", "Select"), ("k:Ctrl A", "Select all"),
                      ("k:Del", "Delete selected"), ("k:Esc", "Done")], input_devices.input_mode().mode)
            return
        self.hints.set_items(
            [("DPAD", "Move"), ("A", "Open"), ("Y", "Share"), ("X", "Select"), ("OPT", "Delete"),
             ("L1R1", "Game"), ("B", "Back")] if pad
            else [("k:← →", "Move"), ("k:Enter", "Open"), ("k:E", "Share"), ("k:Space", "Select"), ("k:Del", "Delete"),
                  ("k:[ ]", "Game"), ("k:T", "Show"), ("k:/", "Search"), ("k:F", "Favorite"),
                  ("k:Esc", "Back")], input_devices.input_mode().mode)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:        # Esc empties the search first, then leaves it
                if self.search.text():
                    self.search.clear()
                else:
                    self.grid.setFocus()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
                self.grid.setFocus()
                return True
            return False                            # everything else is typed
        if obj is self.grid and event.type() == QtCore.QEvent.KeyPress:
            if input_devices.latin_key(event) == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
                self.mark_all()
                return True
            if input_devices.latin_key(event) == Qt.Key_F and event.modifiers() & Qt.ControlModifier:
                self.start_search()
                return True
            if event.key() in ui_theme.ARROWS:
                before = self.grid.currentRow()
                QtWidgets.QListWidget.keyPressEvent(self.grid, event)
                if self.grid.currentRow() == before:   # at the grid's edge: on to the games or the buttons
                    item = self.grid.currentItem()
                    rect = self.grid.visualItemRect(item) if item is not None else self.grid.viewport().rect()
                    here = QtCore.QRectF(QtCore.QPointF(self.grid.viewport().mapToGlobal(rect.topLeft())),
                                         QtCore.QSizeF(rect.size()))
                    self._move(self.grid, event.key(), here)
                return True
            return self._key(input_devices.latin_key(event))
        if event.type() == QtCore.QEvent.KeyPress and obj is self.games:
            k = input_devices.latin_key(event)
            if k in (Qt.Key_Up, Qt.Key_Down):
                before = self.games.currentRow()
                QtWidgets.QListWidget.keyPressEvent(self.games, event)
                if self.games.currentRow() == before and k == Qt.Key_Up:   # the top of the list: the buttons
                    self._move(self.games, k, self._row_box(self.games))
            elif k in ui_theme.ARROWS:
                self._move(self.games, k, self._row_box(self.games))
            elif k in (Qt.Key_Return, Qt.Key_Enter):
                self.grid.setFocus()
            else:
                self._key(k)
            return True
        if event.type() == QtCore.QEvent.KeyPress and obj in self._head_nav(all=True):
            k = input_devices.latin_key(event)
            if k in ui_theme.ARROWS:
                self._move(obj, k)
            elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                obj.click()
            else:
                self._key(k)
            return True
        if obj is self.grid and event.type() == QtCore.QEvent.Resize:
            self._fit_tiles()
        if (obj is self.grid.viewport() and event.type() == QtCore.QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton and not self.selecting):    # Play / Share / Trim under the tile
            item = self.grid.itemAt(event.position().toPoint())
            if item is not None and self.grid.row(item) == self.grid.currentRow():
                cell = self.grid.visualItemRect(item)
                spot = event.position() - QtCore.QPointF(cell.topLeft())
                for rect, action in self.quick_rects:
                    if rect.contains(spot):
                        self.open_selected(None if action == "open" else action)
                        return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e):
        if not self._key(input_devices.latin_key(e)):
            super().keyPressEvent(e)

    def _head_nav(self, all: bool = False) -> list[QtWidgets.QWidget]:
        """The buttons along the top; all: hidden ones too."""
        head = [self.back_btn, *self.kind_btns.values(), self.sort_btn, self.select_btn, self.all_btn, self.del_btn,
                self.clear_btn, self.folder_btn, self.close_btn]
        return head if all else [b for b in head if b.isVisible() and b.isEnabled()]

    def grid_lit(self) -> bool:
        """The current tile shows the highlight, unless it's gone up to the buttons or the games."""
        return self.focusWidget() not in (*self._head_nav(all=True), self.games)

    @staticmethod
    def _row_box(view: QtWidgets.QListWidget) -> QtCore.QRectF | None:
        item = view.currentItem()
        if item is None:
            return None
        r = view.visualItemRect(item)
        return QtCore.QRectF(QtCore.QPointF(view.viewport().mapToGlobal(r.topLeft())), QtCore.QSizeF(r.size()))

    def _move(self, current: QtWidgets.QWidget, key: int, here: QtCore.QRectF | None = None):
        """The D-pad, like a mouse: on to whatever is that way on screen (a button, the games, the grid)."""
        nxt = ui_theme.toward(current, [*self._head_nav(), self.games, self.grid], key, here)
        if nxt is not None:
            nxt.setFocus()
            self.grid.viewport().update()

    def _key(self, k: int) -> bool:
        open_or_pick = self.toggle_mark if self.selecting else self.open_selected
        actions = {Qt.Key_Escape: self.go_back,
                   Qt.Key_Return: open_or_pick,
                   Qt.Key_Enter: open_or_pick, Qt.Key_BracketLeft: lambda: self.step_game(-1),
                   Qt.Key_BracketRight: lambda: self.step_game(1), Qt.Key_F: self.toggle_favorite,
                   Qt.Key_Space: self.toggle_mark, Qt.Key_Delete: self.delete_marked,
                   Qt.Key_S: self.toggle_sort, Qt.Key_T: self.next_kind, Qt.Key_Slash: self.start_search,
                   Qt.Key_E: lambda: self.open_selected("share"), Qt.Key_R: lambda: self.open_selected("trim")}
        if k in actions:
            actions[k]()
            return True
        return False


class StorageMeter(QtWidgets.QWidget):
    """Under the games: how much the captures take, as a bar against the limit set in Settings.
    Over the limit it turns amber and says by how much."""

    def __init__(self):
        super().__init__()
        self.info: dict | None = None
        self.setFixedHeight(152)      # spec: 260 x 152, surface/tile, r18, pad 18
        self.hide()

    def set_storage(self, info: dict | None):
        self.info = info if info and info.get("limit_gb") else None
        self.setVisible(self.info is not None)
        self.update()

    def paintEvent(self, _):
        if not self.info:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        used, limit, over = self.info["used_gb"], self.info["limit_gb"], self.info.get("over")
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 26))
        p.drawRoundedRect(r, 18, 18)
        inner = r.adjusted(18, 18, -18, -18)
        head = QtCore.QRectF(inner.left(), inner.top(), inner.width(), 28)
        if over:      # spec: a warning sign, 20, amber
            icon = QtCore.QRectF(head.right() - 20 if language.is_rtl() else head.left(), head.center().y() - 10, 20, 20)
            p.drawPixmap(icon.toRect(), ui_theme.icon_pixmap("warning", 20, ui_theme.AMBER))
            head = head.adjusted(0, 0, -28, 0) if language.is_rtl() else head.adjusted(28, 0, 0, 0)
        p.setPen(QtGui.QColor(ui_theme.INK))
        p.setFont(ui_theme.font(17, QtGui.QFont.DemiBold))
        p.drawText(head, language.lead() | Qt.AlignVCenter,
                   language.tr("{used} of {limit} GB", used=f"{used:.0f}", limit=f"{limit:.0f}"))
        bar = QtCore.QRectF(inner.left(), inner.top() + 38, inner.width(), 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 26))
        p.drawRoundedRect(bar, 4, 4)
        fill = QtCore.QRectF(bar)
        fill.setWidth(bar.width() * min(1.0, used / max(1e-6, limit)))
        if language.is_rtl():
            fill.moveRight(bar.right())
        p.setBrush(QtGui.QColor(ui_theme.AMBER) if over else QtGui.QColor(255, 255, 255, 102))
        p.drawRoundedRect(fill, 4, 4)
        p.setPen(QtGui.QColor(236, 240, 250, 214))
        p.setFont(ui_theme.font(14))
        text = (language.tr("{n} GB over your limit. Delete old clips or raise the limit in Settings.", n=f"{used - limit:.0f}")
                if over else language.tr("{n} GB left before the limit", n=f"{limit - used:.0f}"))
        p.drawText(QtCore.QRectF(inner.left(), bar.bottom() + 10, inner.width(), inner.bottom() - bar.bottom() - 10),
                   language.lead() | Qt.AlignTop | Qt.TextWordWrap, text)

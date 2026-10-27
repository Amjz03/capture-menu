"""Capture gallery, categories, selection and batch actions."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_viewer import Viewer

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
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
        view, cell = self.g.grid.viewport().size(), self.g.grid.gridSize()
        return 2 * max(1, view.width() // cell.width()) * (view.height() // cell.height() + 2)

    def pixmap(self, path: Path) -> QtGui.QPixmap:
        key = str(path)
        pm = self.cache.pop(key, None)
        if pm is None:
            pm = ui_theme.rounded_pixmap(self.g.ctl.thumb(path), self.g.TW, self.g.TH, 14,
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
        return QtCore.QSize(self.g.TW + 2 * self.g.PAD, self.g.TH + self.g.PAD + 62)

    def paint(self, p: QtGui.QPainter, option, index):
        path = Path(index.data(Qt.UserRole))
        r = QtCore.QRectF(option.rect)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected) and self.g.grid_lit()
        # the current tile grows into focus, like the PS5, while the one before settles back
        t = self.g.grow if selected else (1 - self.g.grow) if index.row() == self.g.last_row else 0.0
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rest = QtCore.QRectF(r.x() + (r.width() - self.g.TW) / 2, r.y() + self.g.PAD, self.g.TW, self.g.TH)
        tile = ui_theme.grown(rest, 0.05 * t)
        radius = 14 * tile.width() / rest.width()
        ctl = self.g.ctl
        ui_widgets.draw_capture_tile(p, tile, self.pixmap(path), path, ctl.length_of(path), ctl.is_favorite(path),
                          dim=int(70 * (1 - t)), radius=radius, marked=path in self.g.marked,
                          selecting=self.g.selecting)
        ui_theme.paint_focus(p, tile, radius, t)
        title, _, sub = index.data(Qt.DisplayRole).partition("\n")
        text = QtCore.QRectF(rest.left(), rest.bottom() + 14, rest.width(), 20)
        p.setPen(QtGui.QColor(ui_theme.INK) if selected else QtGui.QColor(236, 240, 250, 225))
        p.setFont(ui_theme.font(15, QtGui.QFont.DemiBold if selected else QtGui.QFont.Normal))
        p.drawText(text, language.lead() | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.ElideRight, int(rest.width())))
        p.setPen(QtGui.QColor(236, 240, 250, 165))
        p.setFont(ui_theme.font(13))
        p.drawText(text.translated(0, 21), language.lead() | Qt.AlignVCenter, sub)
        p.restore()


class CategoryDelegate(QtWidgets.QStyledItemDelegate):
    """Gallery sidebar rows: name on the left, count and size on the right; the current one is white."""

    def sizeHint(self, option, index):
        return QtCore.QSize(option.rect.width(), 44)

    def paint(self, p: QtGui.QPainter, option, index):
        name, count, size = index.data(Qt.UserRole)
        r = QtCore.QRectF(option.rect).adjusted(12, 0, -12, 0)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if selected:
            pill = QtCore.QRectF(option.rect).adjusted(0, 3, 0, -3)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(ui_theme.INK))
            p.drawRoundedRect(pill, 19, 19)
            if option.widget is not None and option.widget.hasFocus():   # the controller's highlight is here
                p.setPen(QtGui.QPen(QtGui.QColor(ui_theme.DARK), 2.5))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(pill.adjusted(3.5, 3.5, -3.5, -3.5), 15.5, 15.5)
        right = f"{count}"
        p.setFont(ui_theme.font(13))
        p.setPen(QtGui.QColor(13, 17, 32, 150) if selected else QtGui.QColor(236, 240, 250, 150))
        rw = p.fontMetrics().horizontalAdvance(right)
        rtl = language.is_rtl()    # the count sits at the far end of the line from the name
        p.drawText(r, ((Qt.AlignLeft | Qt.AlignAbsolute) if rtl else Qt.AlignRight) | Qt.AlignVCenter, right)
        p.setFont(ui_theme.font(15, QtGui.QFont.DemiBold if selected else QtGui.QFont.Normal))
        p.setPen(QtGui.QColor(ui_theme.DARK) if selected else QtGui.QColor(236, 240, 250, 225))
        p.drawText(r.adjusted(rw + 12, 0, 0, 0) if rtl else r.adjusted(0, 0, -rw - 12, 0), language.lead() | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.ElideRight, int(r.width() - rw - 12)))
        p.restore()


class Gallery(ui_widgets.Grow, QtWidgets.QWidget):
    """All captures, like the PS5 Media Gallery: games on the left, their captures on the right."""

    thumb_ready = QtCore.Signal(str)
    TW, TH = 256, 144        # set from the grid's width by _fit_tiles()
    PAD = 15                 # room around a tile to grow into when it's the current one
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

    def _fit_tiles(self):
        """As many columns as fit tiles of about 350 px, sharing the width evenly, so the grid
        fills the page edge to edge. The scroll bar's room is kept either way."""
        room = self.grid.width() - 24     # the scroll bar, and the few px the list keeps at its edges
        cell = room // max(2, round(room / 380))
        if cell - 2 * self.PAD != self.TW:
            self.TW = cell - 2 * self.PAD
            self.TH = round(self.TW * 9 / 16)
            self.tiles.forget()
            self.grid.setGridSize(QtCore.QSize(cell, self.TH + self.PAD + 62))

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

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(64, 40, 64, 32)
        lay.setSpacing(24)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        self.back_btn = ui_widgets.back_button(self.go_back)
        head.addWidget(self.back_btn, 0, Qt.AlignTop)
        head.addSpacing(18)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(QtWidgets.QLabel(language.tr("Captures"), objectName="vTitle"))
        self.info = QtWidgets.QLabel(objectName="vSub")
        titles.addWidget(self.info)
        head.addLayout(titles)
        head.addStretch()
        self.sort_btn = QtWidgets.QPushButton(language.tr("Sort: Newest"))
        self.sort_btn.setFocusPolicy(Qt.NoFocus)
        self.sort_btn.setCursor(Qt.PointingHandCursor)
        self.sort_btn.clicked.connect(self.toggle_sort)
        head.addWidget(self.sort_btn)
        head.addSpacing(4)
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
        body.setSpacing(40)
        self.games = QtWidgets.QListWidget(objectName="games")
        self.games.setItemDelegate(CategoryDelegate(self.games))
        self.games.setFixedWidth(240)
        self.games.setFocusPolicy(Qt.NoFocus)        # switch games with [ ] / L1 R1 or the mouse
        self.games.currentRowChanged.connect(self._fill)
        body.addWidget(self.games)
        self.grid = QtWidgets.QListWidget(objectName="grid")
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.tiles = TileDelegate(self)
        self.grid.setItemDelegate(self.tiles)
        self.grid.setGridSize(QtCore.QSize(self.TW + 2 * self.PAD, self.TH + self.PAD + 62))
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setSpacing(4)
        self.grid.itemDoubleClicked.connect(lambda _: None if self.selecting else self.open_selected())
        self.grid.itemClicked.connect(self._clicked)
        self.grid.currentRowChanged.connect(lambda row: (self._update_info(), self._regrow(row)))
        self.grid.installEventFilter(self)
        for w in (*self._head_nav(all=True), self.games):
            w.installEventFilter(self)          # the D-pad moves between them too, like a mouse
        body.addWidget(self.grid, 1)
        lay.addLayout(body, 1)
        self.hints = ui_widgets.HintBar()
        lay.addWidget(self.hints)

        self.thumb_ready.connect(self._on_thumb)
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
        self.show()
        ui_theme.set_on_top(self, True)
        ui_theme.bring_to_front(self)
        self.grid.setFocus()

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
        self.grid.clear()        # the tiles' pixmaps go with it; reopening rebuilds them in ~0.1 s
        self.tiles.forget()
        self.items = []

    def refresh(self):
        name = self.cats[self.games.currentRow()][0] if self.cats and self.games.currentRow() >= 0 else None
        row = self.grid.currentRow()
        self._load(select=name, row=row)

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
            games.sort(key=lambda kv: sum(catalog.file_size(p) for p in kv[1]), reverse=True)
        self.cats = [("All", everything),
                     (self.FAVORITES, [p for p in everything if self.ctl._fav_key(p) in favs]),
                     *games]
        if self.by_size:
            self.cats = [(n, sorted(ps, key=catalog.file_size, reverse=True)) for n, ps in self.cats]
        self.games.blockSignals(True)
        self.games.clear()
        for name, items in self.cats:
            size = catalog.human_size(sum(catalog.file_size(p) for p in items))
            item = QtWidgets.QListWidgetItem(f"{name}   {len(items)}  ·  {size}")
            item.setData(Qt.UserRole, (self._cat_name(name), len(items), size))
            self.games.addItem(item)
        names = [c[0] for c in self.cats]
        self.games.setCurrentRow(names.index(select) if select in names else 0)
        self.games.blockSignals(False)
        self._fill(self.games.currentRow(), row)

    def _fill(self, cat_row: int, select_row: int = 0):
        if cat_row < 0 or cat_row >= len(self.cats):
            return
        self.items = list(self.cats[cat_row][1])
        self.grid.clear()
        missing = []
        for p in self.items:
            title = self.ctl.title_of(p) or catalog.capture_kind(p)
            title = title if len(title) <= 30 else title[:29] + "…"
            item = QtWidgets.QListWidgetItem(f"{title}\n{catalog.time_ago(p.stat().st_mtime)}  ·  {catalog.human_size(catalog.file_size(p))}")
            item.setData(Qt.UserRole, str(p))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.grid.addItem(item)
            if (self.ctl.thumb(p) is None or (p.suffix.lower() != ".png" and self.ctl.length_of(p) is None)) \
                    and p not in self._making:
                missing.append(p)
        if self.items:
            self.grid.setCurrentRow(max(0, min(select_row, len(self.items) - 1)))
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

    def _on_thumb(self, path: str):
        self.tiles.forget(path)
        self.grid.viewport().update()

    def _update_info(self):
        name = self.cats[self.games.currentRow()][0] if self.cats else ""
        count = len(self.items)
        size = catalog.human_size(sum(catalog.file_size(p) for p in self.items))
        storage = self.ctl.last_storage
        used = "  ·  " + language.tr("{used} GB used in total", used=f"{storage['used_gb']:.0f}") if storage else ""
        captures = language.tr("1 capture") if count == 1 else language.tr("{n} captures", n=count)
        text = f"{self._cat_name(name)}  ·  {captures}  ·  {size}{used}"
        if self.marked:
            text = (language.tr("{n} selected", n=len(self.marked)) + "  ·  "
                    f"{catalog.human_size(sum(catalog.file_size(p) for p in self.marked))}  ·  {text}")
        self.info.setText(text)
        picking = self.selecting
        self.select_btn.setVisible(not picking)
        self.sort_btn.setVisible(not picking)
        for b in (self.all_btn, self.del_btn, self.clear_btn):
            b.setVisible(picking)
        self.del_btn.setEnabled(bool(self.marked))
        self.all_btn.setText(language.tr("Select none") if self.items and self.marked == set(self.items) else language.tr("Select all"))
        self.update_hints()
        if not self.del_btn.property("danger"):
            self.del_btn.setText(language.tr("Delete {n}", n=len(self.marked)))

    @classmethod
    def _cat_name(cls, name: str) -> str:
        return language.tr("Favorites") if name == cls.FAVORITES else language.tr("All") if name == "All" else name

    # ---- sort, select, delete many
    def toggle_sort(self):
        self.by_size = not self.by_size
        self.sort_btn.setText(language.tr("Sort: Largest") if self.by_size else language.tr("Sort: Newest"))
        self.refresh()

    def _clicked(self, item):
        if self.selecting or QtWidgets.QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_mark()       # while selecting a click picks; Ctrl+click always does, like Explorer

    def toggle_mark(self):
        row = self.grid.currentRow()
        if 0 <= row < len(self.items):
            p = self.items[row]
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
        if not self.marked:
            return
        if not self.del_btn.property("danger"):   # first press arms, second press deletes
            favs = sum(self.ctl.is_favorite(p) for p in self.marked)
            note = (" " + (language.tr("(incl. 1 favorite)") if favs == 1 else language.tr("(incl. {n} favorites)", n=favs))
                    if favs else "")
            self.del_btn.setProperty("danger", True)
            self.del_btn.setText(language.tr("Press again to delete {n}", n=len(self.marked)) + note)
            ui_viewer.Viewer._repolish(self.del_btn)
            self._disarm.start(4000)
            return
        total = len(self.marked)
        count, _ = self.ctl.delete_many(sorted(self.marked))
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
    def open_selected(self):
        row = self.grid.currentRow()
        if 0 <= row < len(self.items):
            self.viewer.open(self.items, row)

    def step_game(self, delta: int):
        row = max(0, min(self.games.count() - 1, self.games.currentRow() + delta))
        self.games.setCurrentRow(row)

    def toggle_favorite(self):
        row = self.grid.currentRow()
        if 0 <= row < len(self.items):
            self.ctl.toggle_favorite(self.items[row])
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
            [("DPAD", "Move"), ("A", "Open"), ("X", "Select"), ("OPT", "Delete selected"),
             ("L1R1", "Game"), ("Y", "Favorite"), ("B", "Back")] if pad
            else [("k:← →", "Move"), ("k:Enter", "Open"), ("k:Space", "Select"), ("k:Del", "Delete selected"),
                  ("k:[ ]", "Game"), ("k:S", "Sort"), ("k:F", "Favorite"), ("k:Esc", "Back")], input_devices.input_mode().mode)

    def eventFilter(self, obj, event):
        if obj is self.grid and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
                self.mark_all()
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
            return self._key(event.key())
        if event.type() == QtCore.QEvent.KeyPress and obj is self.games:
            k = event.key()
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
            k = event.key()
            if k in ui_theme.ARROWS:
                self._move(obj, k)
            elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                obj.click()
            else:
                self._key(k)
            return True
        if obj is self.grid and event.type() == QtCore.QEvent.Resize:
            self._fit_tiles()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e):
        if not self._key(e.key()):
            super().keyPressEvent(e)

    def _head_nav(self, all: bool = False) -> list[QtWidgets.QWidget]:
        """The buttons along the top; all: hidden ones too."""
        head = [self.back_btn, self.sort_btn, self.select_btn, self.all_btn, self.del_btn, self.clear_btn,
                self.folder_btn, self.close_btn]
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
                   Qt.Key_S: self.toggle_sort}
        if k in actions:
            actions[k]()
            return True
        return False

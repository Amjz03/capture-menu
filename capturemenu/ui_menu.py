"""Capture menu and recent-capture navigation."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_viewer import Viewer

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path

from . import capture_controller, catalog, input_devices, language, ui_theme, ui_widgets, windows


class Menu(QtWidgets.QWidget):
    """The Create bar: docks along the bottom of the screen so the game stays in view."""

    BAR_H = 316
    PICK_H = 246            # the bar is slimmer while choosing a duration
    HEADROOM = 90           # fade above the bar

    def __init__(self, ctl: capture_controller.Controller, viewer: "Viewer"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setProperty("captureMenuPage", "menu")
        self.ctl = ctl
        self.viewer = viewer
        self.gallery = None          # set by main(); "All captures" opens it
        self.settings = None         # set by main()
        self.game = windows.DESKTOP
        self.picking = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(ui_theme.BAR_STYLE)
        self.setFont(ui_theme.font(13))
        ui_theme.dress(self, frosted=False)
        # chip order follows the PS5: Full video first, then shortest to longest
        self.options: list[int | None] = [None] + sorted(ctl.cfg["durations_seconds"])[:8]
        self.last_choice = self.options.index(60) if 60 in self.options else 1

        self.bar = QtWidgets.QWidget(self)
        lay = QtWidgets.QVBoxLayout(self.bar)
        lay.setContentsMargins(64, 26, 64, 22)
        lay.setSpacing(18)

        # header: which game and what the replay buffer holds
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(18)
        self.game_label = QtWidgets.QLabel(objectName="game")
        self.status = QtWidgets.QLabel(objectName="status")
        self.status.setTextFormat(Qt.RichText)
        head.addWidget(self.game_label, 0, Qt.AlignBaseline)
        head.addWidget(self.status, 0, Qt.AlignBaseline)
        self.storage_label = QtWidgets.QLabel(objectName="storage")
        self.storage_label.hide()
        head.addWidget(self.storage_label, 0, Qt.AlignBaseline)
        head.addStretch()
        lay.addLayout(head)

        # main row: actions, then recent captures
        self.main_row = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.main_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.save_card = ui_widgets.ActionCard("rewind", "Save recent", "last 30 min")
        self.shot_card = ui_widgets.ActionCard("camera", "Screenshot")
        self.rec_card = ui_widgets.ActionCard("record", "Record")
        self.mic_card = ui_widgets.ActionCard("mic", "Mic on")
        self.mic_card.clicked.connect(self.ctl.toggle_mic)
        self.save_card.clicked.connect(self.open_picker)
        self.shot_card.clicked.connect(self._screenshot)
        self.rec_card.clicked.connect(lambda: self._act(self.ctl.toggle_record, self.game))
        for c in (self.save_card, self.shot_card, self.rec_card, self.mic_card):
            row.addWidget(c, 0, Qt.AlignTop)
        row.addSpacing(28)
        self.thumbs = [ui_widgets.ThumbCard() for _ in range(8)]
        for i, t in enumerate(self.thumbs):
            t.clicked.connect(lambda _=False, i=i: self._view(i))
            row.addWidget(t, 0, Qt.AlignTop)
        self.empty_label = QtWidgets.QLabel(language.tr("Your captures will show up here"), objectName="focusInfo")
        self.empty_label.setFixedHeight(ui_widgets.ActionCard.SIZE + 2 * ui_widgets.Card.PAD)
        row.addWidget(self.empty_label, 0, Qt.AlignTop)
        row.addSpacing(4)
        self.all_card = ui_widgets.ActionCard("gallery", "All captures")
        self.all_card.clicked.connect(self.open_gallery)
        row.addWidget(self.all_card, 0, Qt.AlignTop)
        self.settings_card = ui_widgets.ActionCard("settings", "Settings")
        self.settings_card.clicked.connect(self.open_settings)
        row.addWidget(self.settings_card, 0, Qt.AlignTop)
        row.addStretch()
        lay.addWidget(self.main_row)

        # Save recent gameplay: a row of pills, like the PS5
        self.picker = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(self.picker)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(12)
        self.pick_caption = QtWidgets.QLabel(objectName="caption")
        self.pick_caption.setTextFormat(Qt.RichText)
        pl.addWidget(self.pick_caption)
        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(4)
        chips.addWidget(ui_widgets.back_button(self.close_picker), 0, Qt.AlignVCenter)
        chips.addSpacing(12)
        self.chips: list[ui_widgets.Chip] = []
        for sec in self.options:
            c = ui_widgets.Chip(ui_widgets.chip_label(sec))
            c.clicked.connect(lambda _=False, s=sec: self._save(s))
            chips.addWidget(c)
            self.chips.append(c)
        chips.addStretch()
        pl.addLayout(chips)
        self.picker.hide()
        lay.addWidget(self.picker)
        lay.addStretch()

        # footer: button prompts on the left, details of the focused capture on the right
        foot = QtWidgets.QHBoxLayout()
        self.hints = ui_widgets.HintBar()
        foot.addWidget(self.hints)
        foot.addStretch()
        self.focus_info = QtWidgets.QLabel(objectName="focusInfo")
        foot.addWidget(self.focus_info)
        lay.addLayout(foot)

        for c in (self.save_card, self.shot_card, self.rec_card, self.mic_card, self.all_card,
                  self.settings_card, *self.thumbs):
            c.focused_cb = self._on_focus
            c.hover_focus = lambda: not self.picking

        self._buffer = {"active": False, "max_ms": 0, "held_ms": None}
        ctl.status.connect(self._on_status)
        self._timer = QtCore.QTimer(self, interval=1000, timeout=ctl.refresh_status)
        self._rise = QtCore.QPropertyAnimation(self.bar, b"pos", self)    # opening slides the bar up, like the PS5
        self._rise.setDuration(240)
        self._rise.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._rise.valueChanged.connect(lambda _: self.update())
        input_devices.input_mode().changed.connect(lambda _: self.update_hints())
        self.update_hints()

    def update_hints(self):
        pad = input_devices.input_mode().mode != "keyboard"
        if self.picking:
            items = ([("DPAD_LR", "Choose"), ("A", "Save"), ("B", "Back")] if pad else
                     [("k:← →", "Choose"), ("k:Enter", "Save"),
                      (f"k:1–{len(self.options)}", "Pick"), ("k:Esc", "Back")])
        elif pad:
            items = [("DPAD_LR", "Move"), ("A", "Select"), ("X", "Screenshot"),
                     ("Y", "View latest"), ("R1", "Trim latest"), ("B", "Close")]
        else:
            items = [("k:← →", "Move"), ("k:Enter", "Select"),
                     (f"k:1–{len(self.options)}", "Save instantly"), ("k:T", "Trim latest"), ("k:Esc", "Close")]
        self.hints.set_items(items, input_devices.input_mode().mode)

    # ---- show / hide
    def toggle(self, game: str | None = None):
        self.hide_menu() if self.isVisible() else self.show_menu(game)

    def _place(self):
        """Pin the bar to the bottom edge at its current height."""
        h = self.PICK_H if self.picking else self.BAR_H
        self._rise.stop()
        self.bar.setGeometry(0, self.height() - h, self.width(), h)
        self.update()

    def show_menu(self, game: str | None = None, fresh: bool = True):
        """fresh: opened from outside (the game's screen is picked again); False when coming Back."""
        self.game = game or windows.foreground_app(self.ctl.cfg)
        if self.viewer.isVisible():
            self.viewer.close_viewer()
        g = windows.ui_screen(fresh).geometry()   # the screen the game is on, TV or monitor
        h = self.BAR_H + self.HEADROOM
        ui_theme.dress(self, frosted=False)
        self.setGeometry(g.left(), g.bottom() - h + 1, g.width(), h)
        self.game_label.setText(self.game_label.fontMetrics().elidedText(self.game, Qt.ElideRight, 420))
        self.status.setText("")
        self._set_picking(False)
        self.refresh_recent()
        self.ctl.refresh_status()
        self._timer.start()
        if fresh and ui_theme.MOTION_MS:
            self._rise.setStartValue(QtCore.QPoint(0, self.height()))
            self._rise.setEndValue(self.bar.pos())
            self.bar.move(0, self.height())
        self.show()
        ui_theme.bring_to_front(self)
        self.save_card.setFocus()
        if fresh and ui_theme.MOTION_MS:
            self._rise.start()

    def hide_menu(self):
        self._timer.stop()
        self.picking = False
        self.hide()

    def changeEvent(self, e):
        # clicking back into the game closes the bar, like pressing Esc
        if e.type() == QtCore.QEvent.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide_menu()
        super().changeEvent(e)

    def _act(self, fn, *args):
        self.hide_menu()
        fn(*args)

    def _screenshot(self):
        self.hide_menu()
        game = self.game
        QtCore.QTimer.singleShot(250, lambda: self.ctl.screenshot(game))  # bar gone first

    # ---- Save recent gameplay row
    def _set_picking(self, on: bool):
        self.picking = on
        self.main_row.setVisible(not on)
        self.picker.setVisible(on)
        self._place()
        self.update_hints()

    def open_picker(self):
        self._set_picking(True)
        self._refresh_picker()
        self.chips[self.last_choice].setFocus()

    def close_picker(self):
        self._set_picking(False)
        self.save_card.setFocus()

    def _save(self, seconds: int | None):
        self.last_choice = self.options.index(seconds)
        self._act(self.ctl.save_clip, seconds, self.game)

    def _refresh_picker(self):
        b = self._buffer
        if not b["active"]:
            held = language.tr("replay buffer is off")
        elif b["held_ms"] is None:
            held = language.tr("up to {length}", length=language.clock(b["max_ms"]))
        else:
            held = f"{language.clock(min(b['held_ms'], b['max_ms']))} / {language.clock(b['max_ms'])}"
        self.pick_caption.setText(f'{language.tr("Save recent gameplay")}&nbsp;&nbsp;&nbsp;'
                                  f'<span style="color:{ui_theme.MUTED}; font-weight:400">{held}</span>')
        for sec, chip in zip(self.options, self.chips):
            chip.dimmed = (sec is not None and b["held_ms"] is not None
                           and sec * 1000 > b["held_ms"] + 500)
            chip.update()

    # ---- content
    def refresh_recent(self):
        items = self.ctl.recent_items()
        tile = self.save_card.width()
        room = self.width() - 128 - 4 * tile - 40 - 2 * tile if self.width() > 0 else 1200
        count = max(1, min(len(self.thumbs), room // self.thumbs[0].width()))
        for i, card in enumerate(self.thumbs):
            path = items[i] if i < len(items) and i < count else None
            card.setVisible(path is not None)
            if path is not None:
                card.set_capture(path, self.ctl.thumb(path), self.ctl.length_of(path),
                                 self.ctl.is_favorite(path))
                card.caption = self.ctl.title_of(path) or catalog.capture_kind(path)
                card.when = catalog.time_ago(path.stat().st_mtime)
        self.empty_label.setVisible(not items)
        self.focus_info.setText("")

    def _on_focus(self, card: ui_widgets.Card):
        if isinstance(card, ui_widgets.ThumbCard) and card.path is not None:
            path = card.path
            self.focus_info.setText(f"{path.parent.name}    {catalog.human_size(catalog.file_size(path))}")
        else:
            self.focus_info.setText("")

    def show_storage(self, info: dict):
        if info.get("over"):
            self.storage_label.setText(language.tr("Captures {used} GB · over {limit} GB", used=f"{info['used_gb']:.0f}",
                                          limit=f"{info['limit_gb']:.0f}"))
        elif info.get("low"):
            self.storage_label.setText(language.tr("Only {free} GB free", free=f"{info['free_gb']:.0f}"))
        self.storage_label.setVisible(bool(info.get("over") or info.get("low")))

    def open_gallery(self):
        if self.gallery is None:
            self._act(self.ctl.open_folder)
            return
        game = self.game
        self.hide_menu()
        self.gallery.open(game, back_to=lambda: self.show_menu(game, fresh=False))

    def open_settings(self):
        if self.settings is None:
            return
        game = self.game
        self.hide_menu()
        self.settings.open(self.ctl.screen_px, back_to=lambda: self.show_menu(game, fresh=False))

    def _view(self, index: int, trim: bool = False):
        items = self.ctl.recent_items()
        if index < len(items):
            game = self.game
            self.hide_menu()
            self.viewer.open(items, index, trim=trim, back_to=lambda: self.show_menu(game, fresh=False))

    def view_capture(self, path: str, trim: bool = False):
        """A notice was clicked: its capture in the viewer. Back then comes to the bar, the same as
        opening it with Create then △ (it used to close everything)."""
        items = self.ctl.recent_items()
        p = Path(path)
        if p not in items:
            items = [p, *items]
        self.hide_menu()
        if self.gallery is not None:
            self.gallery.close_gallery()
        self.viewer.open(items, items.index(p), trim=trim, fresh=True, back_to=lambda: self.show_menu(fresh=False))

    def _on_status(self, st: dict):
        if not st.get("online"):
            off = language.tr("OBS isn't running")
            text = f'<span style="color:{ui_theme.AMBER}">{off}</span>'
        elif st["recording"]:
            text = (f'<span style="color:{ui_theme.RED}">●</span>&nbsp;&nbsp;<span style="color:{ui_theme.INK}">{language.tr("Recording")}'
                    f'</span>&nbsp;&nbsp;{language.clock(st["record_ms"])}')
        elif st["buffer"]:
            text = language.tr("Keeping the last {length}", length=language.duration_label(st["buffer_seconds"], short=True))
        else:
            text = f'<span style="color:{ui_theme.AMBER}">{language.tr("Replay buffer is off")}</span>'
        self.status.setText(text)
        if st.get("online"):
            self._buffer = {"active": st["buffer"], "max_ms": st["buffer_seconds"] * 1000,
                            "held_ms": st.get("buffered_ms")}
            self.save_card.hint = language.tr("last {length}", length=language.duration_label(st["buffer_seconds"], short=True))
            self.save_card.update()
            if st["recording"]:
                self.rec_card.set_state("stop", language.tr("Stop  {time}", time=language.clock(st["record_ms"])), ui_theme.RED,
                                        QtGui.QColor(255, 69, 58, 40))
            else:
                self.rec_card.set_state("record", "Record")
            muted = st.get("mic_muted")
            self.mic_card.setVisible(muted is not None)
            if muted:
                self.mic_card.set_state("mic-off", "Mic off", ui_theme.RED)
            else:
                self.mic_card.set_state("mic", "Mic on")
        if self.picking:
            self._refresh_picker()

    # ---- painting and input
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        top = max(0, self.bar.y() - self.HEADROOM)
        grad = QtGui.QLinearGradient(0, top, 0, self.height())
        span = max(1, self.height() - top)
        grad.setColorAt(0.0, QtGui.QColor(*ui_theme.NIGHT, 0))
        grad.setColorAt(min(0.9, self.HEADROOM * 0.55 / span), QtGui.QColor(*ui_theme.NIGHT, 120))
        grad.setColorAt(min(0.95, (self.HEADROOM + 24) / span), QtGui.QColor(*ui_theme.NIGHT, 238))
        grad.setColorAt(1.0, QtGui.QColor(*ui_theme.NIGHT, 250))
        p.fillRect(QtCore.QRect(0, top, self.width(), self.height() - top), grad)

    def mousePressEvent(self, e):
        if e.position().y() < self.bar.y():
            self.hide_menu()

    def _nav_cards(self) -> list[QtWidgets.QAbstractButton]:
        if self.picking:
            return list(self.chips)
        cards = [self.save_card, self.shot_card, self.rec_card]
        cards += [self.mic_card] if self.mic_card.isVisible() else []
        cards += [t for t in self.thumbs if t.isVisible()]
        return cards + [self.all_card, self.settings_card]

    def keyPressEvent(self, e):
        k = e.key()
        cards = self._nav_cards()
        focused = self.focusWidget()
        if k in (Qt.Key_Left, Qt.Key_Right) and focused in cards:
            j = cards.index(focused) + language.forward(k)
            cards[max(0, min(len(cards) - 1, j))].setFocus()
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and focused in cards:
            focused.click()
        elif Qt.Key_1 <= k <= Qt.Key_9 and k - Qt.Key_1 < len(self.options):
            self._save(self.options[k - Qt.Key_1])
        elif self.picking:
            if k in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Down):
                self.close_picker()
        elif k == Qt.Key_Escape:
            self.hide_menu()
        elif k == Qt.Key_Up and focused is self.save_card:
            self.open_picker()
        elif k == Qt.Key_S:
            self._screenshot()
        elif k == Qt.Key_R:
            self.rec_card.click()
        elif k == Qt.Key_V:
            self._view(0)
        elif k == Qt.Key_T:
            self._view(0, trim=True)
        elif k in (Qt.Key_O, Qt.Key_G):
            self.all_card.click()
        elif k == Qt.Key_Comma:
            self.open_settings()
        elif k == Qt.Key_M:
            self.ctl.toggle_mic()
        else:
            super().keyPressEvent(e)

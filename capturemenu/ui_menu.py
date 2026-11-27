"""Capture menu and recent-capture navigation."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_viewer import Viewer

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import time

from . import capture_controller, catalog, input_devices, language, obs_client, ui_theme, ui_widgets, windows


class Menu(QtWidgets.QWidget):
    """The Create bar: docks along the bottom of the screen so the game stays in view."""

    BAR_H = 324
    PICK_H = 448            # Save recent: the lengths under a strip of the last minutes
    HEADROOM = 90           # fade above the bar
    SHIFT_STEP = 10         # seconds a clip moves earlier or later per press

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
        # shortest to longest, then everything that's kept
        self.options: list[int | None] = sorted(ctl.cfg["durations_seconds"])[:8] + [None]
        self.last_choice = self.options.index(60) if 60 in self.options else 0
        self.pick_len: int | None = self.options[self.last_choice]
        self.pick_shift = 0          # seconds the clip is moved earlier than now
        self._pick_now = time.time()
        self._asked_at: float | None = None
        self._shown_start: float | None = None
        self._pending_start = 0.0
        self._screen_geo: QtCore.QRect | None = None

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
        head.addWidget(self.status, 0, Qt.AlignVCenter)
        self.storage_label = QtWidgets.QLabel(objectName="storage")
        self.storage_label.hide()
        head.addWidget(self.storage_label, 0, Qt.AlignBaseline)
        # the last thing that went wrong, said again here: its notice is gone in seconds, mid-game
        self.problem_label = QtWidgets.QLabel(objectName="storage")
        self.problem_label.hide()
        head.addWidget(self.problem_label, 0, Qt.AlignBaseline)
        self._problem: tuple[str, float] | None = None
        # a new version: said here, where the player looks, until it's installed (the notice can be missed)
        self.update_btn = QtWidgets.QPushButton(objectName="update")
        self.update_btn.setFocusPolicy(Qt.NoFocus)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(lambda: self.open_settings(update=True))
        self.update_btn.hide()
        head.addWidget(self.update_btn, 0, Qt.AlignBaseline)
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
        self.mic_card = ui_widgets.ActionCard("mic", "Mic", "On")
        self.mic_card.clicked.connect(self.ctl.toggle_mic)
        self.save_card.clicked.connect(self.open_picker)
        self.shot_card.clicked.connect(self._screenshot)
        self.opened_at: float | None = None    # when the bar opened: a Stop ends the recording there
        self.rec_card.clicked.connect(lambda: self._act(self.ctl.toggle_record, self.game, self.opened_at))
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

        # Save recent gameplay: a strip of the last minutes over a row of lengths; a big picture above the
        # bar shows where the clip starts
        self.picker = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(self.picker)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(12)
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(ui_widgets.back_button(self.close_picker), 0, Qt.AlignVCenter)
        self.pick_caption = QtWidgets.QLabel(objectName="caption")
        self.pick_caption.setTextFormat(Qt.RichText)
        top.addWidget(self.pick_caption, 0, Qt.AlignVCenter)
        top.addStretch()
        self.pick_summary = QtWidgets.QLabel(objectName="caption")
        self.pick_summary.setTextFormat(Qt.RichText)
        top.addWidget(self.pick_summary, 0, Qt.AlignVCenter)
        pl.addLayout(top)
        self.strip = ui_widgets.BufferStrip()
        self.strip.moved.connect(self._move_to)
        pl.addWidget(self.strip)
        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(4)
        self.chips: list[ui_widgets.Chip] = []
        for sec in self.options:
            c = ui_widgets.Chip(ui_widgets.chip_label(sec))
            c.clicked.connect(lambda _=False, s=sec: self._save(s))
            c.on_focus = lambda s=sec: self._choose(s)
            chips.addWidget(c)
            self.chips.append(c)
        chips.addStretch()
        self.save_chip = ui_widgets.Chip("Save clip")
        self.save_chip.clicked.connect(lambda: self._save(self.pick_len))
        chips.addWidget(self.save_chip)
        pl.addLayout(chips)
        self.picker.hide()
        lay.addWidget(self.picker)
        lay.addStretch()
        self.preview = ui_widgets.ClipPreview()
        self.preview.setParent(self)
        self.preview.empty_text = language.tr("Pictures show up once a minute is recorded")
        self.preview.hide()
        self._ask_timer = QtCore.QTimer(self, singleShot=True, interval=150, timeout=self._ask_picture)
        ctl.buffer_frames.connect(self._on_frames)
        ctl.buffer_preview.connect(self._on_preview)

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
            items = ([("DPAD_LR", "Length"), ("L1R1", "Earlier / later"), ("A", "Save"), ("B", "Back")] if pad else
                     [("k:← →", "Length"), ("k:[ ]", "Earlier / later"), ("k:Enter", "Save"),
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
        """Pin the bar to the bottom edge at its current height; while choosing a length, the picture
        of where the clip starts sits above it."""
        h = self.PICK_H if self.picking else self.BAR_H
        self._rise.stop()
        self.bar.setGeometry(0, self.height() - h, self.width(), h)
        if self.picking:
            room_h = self.bar.y() - 48 - 28
            pw = int(min(self.width() - 128, room_h * 16 / 9, 1180))
            ph = int(pw * 9 / 16)
            self.preview.setGeometry((self.width() - pw) // 2, max(24, 48 + (room_h - ph) // 2), pw, ph)
        self.preview.setVisible(self.picking and self.preview.height() > 120)
        self.update()

    def _fit_window(self):
        """The bar's window: a band along the bottom, or the whole screen while choosing a length
        (the picture of the clip needs the room)."""
        g = self._screen_geo
        if g is None:
            return
        if self.picking:
            self.setGeometry(g)
        else:
            h = self.BAR_H + self.HEADROOM
            self.setGeometry(g.left(), g.bottom() - h + 1, g.width(), h)

    def show_menu(self, game: str | None = None, fresh: bool = True):
        """fresh: opened from outside (the game's screen is picked again); False when coming Back."""
        self.game = game or windows.foreground_app(self.ctl.cfg)
        if fresh:
            self.opened_at = time.time()
        if self.viewer.isVisible():
            self.viewer.close_viewer()
        g = windows.ui_screen(fresh).geometry()   # the screen the game is on, TV or monitor
        self._screen_geo = g
        h = self.BAR_H + self.HEADROOM
        ui_theme.dress(self, frosted=False)
        self.setGeometry(g.left(), g.bottom() - h + 1, g.width(), h)
        self.game_label.setText(self.game_label.fontMetrics().elidedText(self.game, Qt.ElideRight, 420))
        self.status.setText("")
        self._set_picking(False)
        self._show_problem()
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

    PROBLEM_KEPT = 30 * 60     # seconds an error is still worth repeating in the bar

    def note_problem(self, text: str, kind: str = "error"):
        """An error notice was shown: the bar says it again the next time it opens (once)."""
        if kind == "error":
            self._problem = (text, time.monotonic())

    def _show_problem(self):
        fresh = self._problem is not None and time.monotonic() - self._problem[1] < self.PROBLEM_KEPT
        if fresh:
            text = "⚠  " + self._problem[0].replace(" · ", "  ·  ")
            self.problem_label.setText(self.problem_label.fontMetrics().elidedText(text, Qt.ElideRight, 760))
            self.problem_label.setToolTip(self._problem[0])
        self.problem_label.setVisible(fresh)

    def hide_menu(self):
        self._timer.stop()
        self.picking = False
        if self.isVisible() and self.problem_label.isVisible():
            self._problem = None       # seen
        self.hide()

    def changeEvent(self, e):
        # clicking back into the game closes the bar, like pressing Esc
        if e.type() == QtCore.QEvent.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide_menu()
        super().changeEvent(e)

    def _act(self, fn, *args):
        self.hide_menu()
        fn(*args)

    def shoot(self, game: str):
        """The screenshot shortcut: the same shot as the bar's, without the bar."""
        self.game = game
        self._screenshot()

    def _screenshot(self):
        self.hide_menu()
        game = self.game
        ui_theme.out_of_capture(True)      # the app shows in clips and shares, never in its own screenshots
        QtCore.QTimer.singleShot(250, lambda: self.ctl.screenshot(game))  # bar gone first
        # ponytail: fixed wait, OBS saves the shot well within it; restore on the saved signal if it ever doesn't
        # one timer for all: a second screenshot within 1.5 s pushes the end back instead of ending it early
        if not hasattr(self, "_shown_again"):
            self._shown_again = QtCore.QTimer(self, singleShot=True, interval=1500,
                                              timeout=lambda: ui_theme.out_of_capture(False))
        self._shown_again.start()

    # ---- Save recent gameplay row
    def _set_picking(self, on: bool):
        changed = on != self.picking
        self.picking = on
        self.main_row.setVisible(not on)
        self.picker.setVisible(on)
        if changed:
            self._fit_window()
        self._place()
        self.update_hints()

    def open_picker(self):
        by_mouse = self.save_card.underMouse()
        self._pick_now = time.time()
        self.pick_shift = 0
        self.pick_len = self.options[self.last_choice]
        self.preview.set_picture(None)
        self._shown_start = None
        self._set_picking(True)
        self._refresh_picker()
        self.ctl.load_buffer_frames()
        self.chips[self.last_choice].setFocus()
        if by_mouse:      # the lengths appear under a mouse that hasn't moved: no enter event comes,
            QtCore.QTimer.singleShot(0, self._light_under_mouse)   # so light the one it's on ourselves

    def _light_under_mouse(self):
        chip = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        if chip in self.chips and self.picking:
            chip.hover_in()

    def close_picker(self):
        self._set_picking(False)
        self.save_card.setFocus()

    def _save(self, seconds: int | None):
        """Saves that length; moved earlier in the strip, it ends there instead of now."""
        self.last_choice = self.options.index(seconds)
        if self.picking and self.pick_shift and seconds:
            self._act(self.ctl.save_clip, seconds, self.game, self._pick_now - self.pick_shift)
        else:
            self._act(self.ctl.save_clip, seconds, self.game)

    # what's chosen: a length, moved some seconds earlier
    def _held_s(self) -> float:
        b = self._buffer
        if b.get("held_ms") is None:
            return b.get("max_ms", 0) / 1000
        return min(b["held_ms"], b["max_ms"]) / 1000

    def _choose(self, seconds: int | None):
        self.pick_len = seconds
        self._clamp_shift()
        self._update_selection()

    def _clamp_shift(self):
        held = self._held_s()
        longest = max(0.0, held - (self.pick_len or held))
        self.pick_shift = int(max(0, min(self.pick_shift, longest))) if self.pick_len else 0

    def _shift(self, seconds: int):
        if self.pick_len is None:
            return
        self.pick_shift += seconds
        self._clamp_shift()
        self._update_selection()

    def _move_to(self, until: float):
        """A click on the strip: the clip ends there."""
        if self.pick_len is None:
            return
        self.pick_shift = int(round(self._pick_now - until))
        self._clamp_shift()
        self._update_selection()

    def _selection(self) -> tuple[float, float]:
        end = self._pick_now - self.pick_shift
        held_from = self._pick_now - self._held_s()
        return (held_from if self.pick_len is None else max(held_from, end - self.pick_len)), end

    def _mb_per_minute(self) -> float | None:
        px = self.ctl.screen_px
        if not px:
            return None
        cfg = self.ctl.cfg
        enc = obs_client.choose_encoder(self.ctl.best_encoder or "nvenc_av1", cfg.get("video_codec", "auto"))
        return obs_client.buffer_memory_mb(cfg, *px, enc) / max(1, int(cfg["buffer_minutes"]))

    def _update_selection(self):
        if not self.picking:
            return
        start, end = self._selection()
        b = self._buffer
        span = (self._pick_now - b.get("max_ms", 0) / 1000, self._pick_now)
        length = end - start
        label = ui_widgets.chip_label(self.pick_len) if self.pick_len else language.clock(int(length * 1000))
        self.strip.set_state(span, self._pick_now - self._held_s(), (start, end), label)
        parts = [f"<b>{language.tr('Last {length}', length=ui_widgets.chip_label(self.pick_len)) if self.pick_len else ui_widgets.chip_label(None)}</b>"]
        if self.pick_shift:
            parts.append(language.tr("ends {time} ago", time=language.clock(self.pick_shift * 1000)))
        mb = self._mb_per_minute()
        if mb:
            parts.append(language.tr("about {size}", size=catalog.human_size(mb * length / 60 * 1024 * 1024)))
        self.pick_summary.setText(f'<span style="color:{ui_theme.MUTED}; font-weight:400">'
                                  + "&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts) + "</span>")
        self.preview.tag = language.tr("Clip starts {time} ago", time=language.clock(int((self._pick_now - start) * 1000)))
        if self._shown_start is None or abs(start - self._shown_start) > 2:    # a new start: a new picture
            self._shown_start = self._pending_start = start
            frame = next((f for f in self.strip.frames if f[0] <= start < f[1] and f[2]), None)
            if frame is not None:          # the strip's picture of that minute, until the exact one comes
                self.preview.set_picture(frame[2])
            self._asked_at = None
            self._ask_timer.start()
        self.preview.update()

    def _ask_picture(self):
        self._asked_at = self._pending_start
        self.ctl.buffer_picture_at(self._pending_start)

    def _on_frames(self, items: list):
        self.strip.set_frames(items)
        if self.picking and self.preview.pixmap.isNull():
            start = self._selection()[0]
            frame = next((f for f in items if f[0] <= start < f[1] and f[2]), None) or \
                next((f for f in reversed(items) if f[2]), None)
            if frame is not None:
                self.preview.set_picture(frame[2])

    def _on_preview(self, when: float, path: str):
        if self.picking and self._asked_at is not None and abs(when - self._asked_at) < 0.01:
            self.preview.set_picture(path)

    def _refresh_picker(self):
        b = self._buffer
        if b.get("offline"):
            held = language.tr("OBS isn't running")
        elif not b["active"]:
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
            if sec is None:        # Everything says how much that is
                chip.setText(language.tr("Everything · {length}", length=language.clock(int(self._held_s() * 1000)))
                             if b.get("held_ms") is not None else ui_widgets.chip_label(None))
            chip.update()
        self._clamp_shift()
        self._update_selection()

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
        self.focus_info.setText(self._folder_info())

    def _folder_info(self) -> str:
        """What this game's folder holds, said in the corner while no capture is focused."""
        count = size = 0
        for root in {self.ctl.clips_dir, getattr(self.ctl, "shots_dir", self.ctl.clips_dir)}:
            try:
                for f in (Path(root) / self.game).iterdir():
                    if f.suffix.lower() in catalog.MEDIA_EXTS:
                        count += 1
                        size += catalog.file_size(f)
            except OSError:
                pass
        if not count:
            return ""
        return language.tr("This game: {n} captures · {size}", n=count, size=catalog.human_size(size))

    def _on_focus(self, card: ui_widgets.Card):
        if isinstance(card, ui_widgets.ThumbCard) and card.path is not None:
            path = card.path
            self.focus_info.setText(f"{path.parent.name}  ·  {catalog.human_size(catalog.file_size(path))}")
        else:
            self.focus_info.setText(self._folder_info())

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

    def open_settings(self, update: bool = False):
        if self.settings is None:
            return
        game = self.game
        self.hide_menu()
        self.settings.open(self.ctl.screen_px, back_to=lambda: self.show_menu(game, fresh=False))
        if update or self.settings_card.badge:      # straight to the Updates line: Enter installs
            self.settings.update_row.setFocus()

    def set_update(self, version: str | None):
        """A newer version is out (None: nothing new): a line in the header and a dot on Settings."""
        self.update_btn.setText(language.tr("Update available · {version}", version=version or ""))
        self.update_btn.setVisible(bool(version))
        self.settings_card.badge = bool(version)
        self.settings_card.hint = "New update" if version else ""
        self.settings_card.update()

    def _view(self, index: int, trim: bool = False):
        items = self.ctl.recent_items()
        shown = self.thumbs[index].path if index < len(self.thumbs) else None
        if shown is not None and shown != (items[index] if index < len(items) else None):
            if shown not in items:              # gone since the bar was drawn (deleted outside): show what's there
                self.refresh_recent()
                return
            index = items.index(shown)          # the card opens the capture it shows, not whatever is n-th now
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
        elif st["buffer"]:     # a green dot: the last minutes are being kept
            text = (f'<span style="color:{ui_theme.GREEN}">●</span>&nbsp;&nbsp;'
                    + language.tr("Keeping the last {length}", length=language.duration_label(st["buffer_seconds"], short=True)))
        else:
            text = f'<span style="color:{ui_theme.AMBER}">{language.tr("Replay buffer is off")}</span>'
        self.status.setText(text)
        if not st.get("online"):                 # nothing known now: no last-known minutes or mic state
            self._buffer = dict(self._buffer, offline=True)
            self.mic_card.setVisible(False)
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
            if muted:     # the state is the second line: green On, red Off
                self.mic_card.set_state("mic-off", "Mic", ui_theme.RED)
                self.mic_card.hint, self.mic_card.hint_color = "Off", ui_theme.RED
            else:
                self.mic_card.set_state("mic", "Mic")
                self.mic_card.hint, self.mic_card.hint_color = "On", ui_theme.GREEN
        if self.picking:
            self._refresh_picker()

    # ---- painting and input
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        if self.picking:     # the game dims behind the picture of the clip
            p.fillRect(QtCore.QRect(0, 0, self.width(), self.bar.y()), QtGui.QColor(*ui_theme.NIGHT, 150))
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
            if not self.picking:
                self.hide_menu()
            elif not self.preview.geometry().contains(e.position().toPoint()):
                self.close_picker()

    def _nav_cards(self) -> list[QtWidgets.QAbstractButton]:
        if self.picking:
            return list(self.chips) + [self.save_chip]
        cards = [self.save_card, self.shot_card, self.rec_card]
        cards += [self.mic_card] if self.mic_card.isVisible() else []
        cards += [t for t in self.thumbs if t.isVisible()]
        return cards + [self.all_card, self.settings_card]

    def keyPressEvent(self, e):
        k = input_devices.latin_key(e)
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
            elif k in (Qt.Key_BracketLeft, Qt.Key_BracketRight):    # L1 / R1: the clip earlier / later
                self._shift(self.SHIFT_STEP * (1 if (k == Qt.Key_BracketLeft) != language.is_rtl() else -1))
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

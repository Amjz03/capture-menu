"""Capture playback, trimming, sharing and metadata editing."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import hashlib
import threading

from . import (
    capture_controller,
    catalog,
    input_devices,
    language,
    media,
    phone_link,
    runtime,
    ui_theme,
    ui_widgets,
    windows,
)


class Viewer(QtWidgets.QWidget):
    """Check a capture right after taking it: play, scrub, trim, step through, delete."""

    preview_ready = QtCore.Signal(str, str)   # original, preview path ("" = failed)
    preview_progress = QtCore.Signal(str, int)
    frame_ready = QtCore.Signal(str, int, str)
    sound_ready = QtCore.Signal(str, str)    # clip, short remixed piece to listen to ("" = failed)
    closed = QtCore.Signal()
    away = QtCore.Signal()      # handed the screen to another app (the folder, a video player)

    def __init__(self, ctl: capture_controller.Controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setProperty("captureMenuPage", "viewer")
        self.ctl = ctl
        self.items: list[Path] = []
        self.index = 0
        self.trimming = False
        self.sharing = False
        self.editing = False
        self.sounding = False                    # the Sound panel: voice and game levels of this clip
        self._previewing_sound = False
        self._pending_trim = False
        self._tried_preview: set[Path] = set()
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(ui_theme.VIEWER_STYLE)
        self.setFont(ui_theme.font(13))
        ui_theme.dress(self)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(64, 36, 64, 24)
        lay.setSpacing(16)
        self.full = False                        # only the video, nothing around it

        def button(row, text, fn, icon=None, name=""):
            label = language.tr(text).replace("&", "&&")   # "&" isn't a shortcut here
            b = QtWidgets.QPushButton(("  " + label) if icon and label else label, objectName=name)
            if icon:
                b.setIcon(ui_theme.qicon(icon, ui_theme.DARK if name == "primary" else ui_theme.INK))
                b.setIconSize(QtCore.QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            row.addWidget(b)
            return b

        # ---- header: Back, the title with Rename next to it, newer / older, close
        self.head = QtWidgets.QWidget()
        head = QtWidgets.QHBoxLayout(self.head)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(0)
        self.back_btn = ui_widgets.back_button(self.go_back)
        head.addWidget(self.back_btn, 0, Qt.AlignTop)
        head.addSpacing(22)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(3)
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(14)
        self.title = QtWidgets.QLabel(objectName="vTitle")
        title_row.addWidget(self.title)
        # Rename: the title itself turns into the field, no window over the video
        self.title_edit = QtWidgets.QLineEdit(objectName="titleEdit",
                                              placeholderText=language.tr("Title, e.g. Boss down on the first try"))
        self.title_edit.addAction(ui_theme.qicon("pencil"), QtWidgets.QLineEdit.LeadingPosition)
        self.title_edit.setMaxLength(80)
        title_row.addWidget(self.title_edit)
        self.rename_btn = button(title_row, "Rename", self.start_edit, "pencil", "pill")
        title_row.addStretch()
        titles.addLayout(title_row)
        self.sub = QtWidgets.QLabel(objectName="vSub")
        titles.addWidget(self.sub)
        self.note = QtWidgets.QLabel(objectName="vNote")
        self.note.hide()
        titles.addWidget(self.note)
        self.note_edit = QtWidgets.QLineEdit(objectName="noteEdit", placeholderText=language.tr("Note (optional)"))
        self.note_edit.setMaxLength(200)
        titles.addWidget(self.note_edit, 0, language.lead())
        self.edit_hint = QtWidgets.QLabel(objectName="vNote")   # what to do now, or to click when Windows keeps the keys
        titles.addWidget(self.edit_hint)
        for w in (self.title_edit, self.note_edit):
            w.returnPressed.connect(self.save_edit)
            w.hide()
        self.edit_hint.hide()
        head.addLayout(titles, 1)
        self.counter = QtWidgets.QLabel(objectName="hint")
        head.addWidget(self.counter, 0, Qt.AlignTop)
        head.addSpacing(16)
        rtl = language.is_rtl()     # newer is to the left, or to the right in Arabic
        self.prev_btn = button(head, "", lambda: self.step(-1), "right" if rtl else "left", "round")
        head.addSpacing(10)
        self.next_btn = button(head, "", lambda: self.step(1), "left" if rtl else "right", "round")
        self.prev_btn.setToolTip(language.tr("Newer ({key})", key="D" if rtl else "A"))
        self.next_btn.setToolTip(language.tr("Older ({key})", key="A" if rtl else "D"))
        head.addSpacing(18)
        rule = QtWidgets.QFrame(objectName="rule")
        rule.setFixedSize(1, 30)
        head.addWidget(rule, 0, Qt.AlignVCenter)
        head.addSpacing(18)
        self.close_btn = button(head, "", self.close_viewer, "close", "round")
        for b in (self.prev_btn, self.next_btn, self.close_btn):
            head.setAlignment(b, Qt.AlignTop)
        self.close_btn.setToolTip(language.tr("Close (Esc)"))
        lay.addWidget(self.head)

        # ---- the video card: the picture, and its controls built into the bottom edge
        self.card = QtWidgets.QFrame(objectName="videoCard")
        card = QtWidgets.QVBoxLayout(self.card)
        card.setContentsMargins(1, 1, 1, 0)
        card.setSpacing(0)
        self.stage = QtWidgets.QStackedWidget(objectName="stage")
        self.image = QtWidgets.QLabel(alignment=Qt.AlignCenter)
        self.image.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)  # the picture follows the stage, never the other way
        self.msg = QtWidgets.QLabel(objectName="vMsg", alignment=Qt.AlignCenter, wordWrap=True)
        self.stage.addWidget(self.image)
        self.stage.addWidget(self.msg)
        self.player = self.video = None     # made on the first video, dropped a minute after closing
        self._frames = 0
        self._watchdog = QtCore.QTimer(self, singleShot=True, interval=2500, timeout=self._check_frames)
        self._drop_timer = QtCore.QTimer(self, singleShot=True, interval=60_000, timeout=self._drop_player)
        card.addWidget(self.stage, 1)
        self.controls = QtWidgets.QFrame(objectName="ctlBar")
        self.controls.setFixedHeight(60)
        self.controls.setLayoutDirection(Qt.LeftToRight)   # time runs left to right, like the trim filmstrip
        cl = QtWidgets.QHBoxLayout(self.controls)
        cl.setContentsMargins(16, 0, 16, 0)
        cl.setSpacing(16)
        self.back5_btn = button(cl, "5", lambda: self.seek(-5000), "back5", "ctl")
        self.back5_btn.setToolTip(language.tr("Back 5 seconds"))
        self.play_btn = button(cl, "", self.toggle_play, "pause", "ctl")
        self.fwd5_btn = button(cl, "5", lambda: self.seek(5000), "fwd5", "ctl")
        self.fwd5_btn.setToolTip(language.tr("Forward 5 seconds"))
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player and self.player.setPosition(v))
        self.time = QtWidgets.QLabel("0:00 / 0:00", objectName="time")
        cl.addWidget(self.slider, 1)
        cl.addWidget(self.time)
        self.vol_btn = button(cl, "", self.toggle_mute, "volume", "ctl")
        self.vol_btn.setToolTip(language.tr("Sound on / off"))
        self.full_btn = button(cl, "", self.toggle_full, "maximize", "ctl")
        self.full_btn.setToolTip(language.tr("Only the video"))
        card.addWidget(self.controls)
        lay.addWidget(self.card, 1)

        def panel_head(box, title: str, sub: str = "") -> QtWidgets.QLabel:
            t = QtWidgets.QLabel(language.tr(title), objectName="panelTitle")
            box.addWidget(t)
            s = QtWidgets.QLabel(language.tr(sub) if sub else "", objectName="panelSub")
            box.addWidget(s)
            box.addSpacing(6)
            return s

        # ---- Trim: the filmstrip with its start and end handles
        self.trim_panel = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(self.trim_panel)
        tl.setContentsMargins(0, 4, 0, 0)
        tl.setSpacing(2)
        trim_top = QtWidgets.QHBoxLayout()
        trim_titles = QtWidgets.QVBoxLayout()
        trim_titles.setSpacing(2)
        panel_head(trim_titles, "Trim", "Drag the handles, or mark the start and the end while it plays")
        trim_top.addLayout(trim_titles)
        trim_top.addStretch()
        self.trim_info = QtWidgets.QLabel(objectName="time")
        trim_top.addWidget(self.trim_info, 0, Qt.AlignBottom)
        tl.addLayout(trim_top)
        self.timeline = ui_widgets.Timeline()
        self.timeline.seek.connect(self._timeline_seek)
        self.timeline.changed.connect(self._trim_labels)
        tl.addWidget(self.timeline)
        lay.addWidget(self.trim_panel)

        # ---- Audio mix: how loud your voice and the game are in this clip
        self.sound_panel = QtWidgets.QWidget()
        sdl = QtWidgets.QVBoxLayout(self.sound_panel)
        sdl.setContentsMargins(0, 4, 0, 0)
        sdl.setSpacing(2)
        self.sound_caption = panel_head(sdl, "Audio mix",
                                        "Change your voice and the game separately. 100% is as recorded")
        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(16)
        self.voice_row = ui_widgets.LevelRow("Your voice", "Your microphone in this clip", media.VOICE_MAX, "mic")
        self.game_row = ui_widgets.LevelRow("Game", "The game's sound in this clip", media.GAME_MAX, "gamepad")
        for r in (self.voice_row, self.game_row):
            cards.addWidget(r, 1)
        sdl.addLayout(cards)
        sdl.addSpacing(8)
        kept = QtWidgets.QHBoxLayout()
        kept.setSpacing(8)
        info = QtWidgets.QLabel()
        info.setPixmap(ui_theme.icon_pixmap("info", 16, "#a9a9ae"))
        kept.addWidget(info)
        kept.addWidget(QtWidgets.QLabel(language.tr("Both are kept on their own tracks, so you can change this again"),
                                        objectName="info"))
        kept.addStretch()
        sdl.addLayout(kept)
        lay.addWidget(self.sound_panel)

        # ---- Share / Export: where this capture is going
        self.share_panel = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self.share_panel)
        sl.setContentsMargins(0, 4, 0, 0)
        sl.setSpacing(2)
        self.share_caption = panel_head(sl, "Share / Export")
        share_cards = QtWidgets.QHBoxLayout()
        share_cards.setSpacing(16)
        self.format_card = ui_widgets.OptionCard("file-video", language.tr("Format"),
                                      [("mp4", language.tr("MP4 for phones & apps")), ("copy", language.tr("Original file"))],
                                      lambda v: language.tr("Plays everywhere: WhatsApp, Discord, phones")
                                      if v == "mp4" else language.tr("The clip exactly as it was saved"))
        self.voice_card = ui_widgets.OptionCard("mic", language.tr("Your voice"), [(True, language.tr("Include")), (False, language.tr("Leave out"))],
                                     lambda v: language.tr("Your microphone is in the video") if v
                                     else language.tr("Only the game's sound"))
        self.size_card = ui_widgets.OptionCard("export", language.tr("Size limit"),
                                    [(None, language.tr("No limit"))] + [(mb, f"{mb} {language.tr('MB')}") for mb in (10, 50, 500)],
                                    lambda v: language.tr("Full quality") if v is None
                                    else language.tr("Discord without Nitro allows 10 MB") if v == 10
                                    else language.tr("Made to fit, quality drops as needed"))
        for c in (self.format_card, self.voice_card, self.size_card):
            share_cards.addWidget(c, 1)
        self.format_card.picked.connect(lambda _: self._share_cards_state())
        sl.addLayout(share_cards)
        lay.addWidget(self.share_panel)

        # ---- the main actions, then the rest as small icon buttons (△ / M walks them)
        self.actions_row = QtWidgets.QWidget()
        act = QtWidgets.QHBoxLayout(self.actions_row)
        act.setContentsMargins(0, 4, 0, 0)
        act.setSpacing(14)
        act.addStretch()
        self.trim_btn = ui_widgets.ActionButton(language.tr("Trim"), "scissors", "X", "k:T")
        self.sound_btn = ui_widgets.ActionButton(language.tr("Adjust audio"), "audio", "L3", "k:V")
        self.share_btn = ui_widgets.ActionButton(language.tr("Share / Export"), "export", "OPT", "k:E", primary=True)
        for b, fn in ((self.trim_btn, self.enter_trim), (self.sound_btn, self.enter_sound),
                      (self.share_btn, self.enter_share)):
            b.clicked.connect(fn)
            act.addWidget(b)
        act.addSpacing(18)
        self.tools_hint = ui_widgets.HintBar()             # △ / M: the button that walks the small ones
        act.addWidget(self.tools_hint, 0, Qt.AlignVCenter)
        self.fav_btn = ui_widgets.ActionButton("", "star", None, "k:F")
        self.folder_chip = ui_widgets.ActionButton("", "folder")
        self.external_chip = ui_widgets.ActionButton("", "external")
        self.del_btn = ui_widgets.ActionButton("", "trash", None, "k:Del")
        for b, fn, tip in ((self.fav_btn, self.toggle_favorite, language.tr("Favorite")),
                           (self.folder_chip, self._show_in_folder, language.tr("Show in folder")),
                           (self.external_chip, lambda: self._step_out(self.ctl.open_external),
                            language.tr("Open in your video player")),
                           (self.del_btn, self.delete_current, language.tr("Delete"))):
            b.clicked.connect(fn)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.TabFocus)       # walked with ← →, chosen with ✕; a click leaves the keys alone
            act.addWidget(b)
        act.addStretch()
        lay.addWidget(self.actions_row)

        # ---- footer: what the buttons do on the left, the open panel's buttons on the right
        self.footer = QtWidgets.QFrame(objectName="footer")
        foot = QtWidgets.QHBoxLayout(self.footer)
        foot.setContentsMargins(0, 14, 0, 0)
        foot.setSpacing(10)
        self.keys_hint = self.trim_hints = self.share_hints = self.sound_hints = ui_widgets.HintBar()
        foot.addWidget(self.keys_hint)
        foot.addStretch()
        self.trim_buttons = QtWidgets.QWidget()
        trow = QtWidgets.QHBoxLayout(self.trim_buttons)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(10)
        button(trow, "Preview", self.preview_selection, "play")
        button(trow, "Cancel", self.exit_trim)
        button(trow, "Replace original", lambda: self.save_trim(replace=True))
        button(trow, "Save as new clip", lambda: self.save_trim(replace=False), "scissors", "primary")
        self.sound_buttons = QtWidgets.QWidget()
        srow = QtWidgets.QHBoxLayout(self.sound_buttons)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(10)
        button(srow, "Preview mix", self.preview_sound, "play")
        button(srow, "Cancel", self.exit_sound)
        button(srow, "Save mix", self.save_sound, None, "primary")
        self.share_buttons = QtWidgets.QWidget()
        shrow = QtWidgets.QHBoxLayout(self.share_buttons)
        shrow.setContentsMargins(0, 0, 0, 0)
        shrow.setSpacing(10)
        self.share_cancel = button(shrow, "Cancel", lambda: self._set_sharing(False))
        self.phone_go = button(shrow, "To your phone", self.send_to_phone, "phone")   # the original file, by QR
        self.share_go = button(shrow, "Export & copy", self._do_share, "copy", "primary")
        for w in (self.trim_buttons, self.sound_buttons, self.share_buttons):
            foot.addWidget(w)
        lay.addWidget(self.footer)


        self._disarm = QtCore.QTimer(self, singleShot=True, timeout=self._reset_delete)
        self.phone_panel = PhonePanel(self)
        for b in self.findChildren(QtWidgets.QPushButton):
            b.setFocusPolicy(Qt.NoFocus)  # keys go to the viewer, not to a button
        for b in (self.share_cancel, self.phone_go, self.share_go):
            b.setFocusPolicy(Qt.StrongFocus)   # Share is walked with ← → like its cards
        input_devices.input_mode().changed.connect(lambda _: (self.update_hints(), self._pick_focus()) if self.items else None)
        QtWidgets.QApplication.instance().focusChanged.connect(self._keep_focus_off_video)
        self.slider.setObjectName("seek")
        self.slider.setFocusPolicy(Qt.NoFocus)   # a click doesn't take the keys; the controller still lands on it
        for w in self._all_nav():
            w.installEventFilter(self)           # their keys come to the viewer, which moves the highlight
        self.preview_ready.connect(self._on_preview_ready)
        self.preview_progress.connect(self._on_preview_progress)
        self.frame_ready.connect(self._on_frame)
        self.sound_ready.connect(self._on_sound_ready)
        ctl.trimmed.connect(self._on_trimmed)
        ctl.remixed.connect(self._on_remixed)
        self._sync()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)      # the sheet: the game stays faintly visible behind it
        p.fillRect(self.rect(), ui_theme.sheet_color(self))

    @property
    def current(self) -> Path:
        return self.items[self.index]

    def is_video(self) -> bool:
        return bool(self.items) and self.current.suffix.lower() != ".png"

    # ---- open / close
    def open(self, items: list[Path], index: int = 0, trim: bool = False, back_to=None, fresh: bool = False):
        """fresh: opened from outside (a notice), not from another page."""
        self.back_to = back_to      # what Back returns to once no panel is open (None: just close)
        self._drop_timer.stop()
        self.items, self.index = list(items), index
        self._pending_trim = trim and items[index].suffix.lower() != ".png"
        ui_theme.dress(self)
        self.setGeometry(windows.ui_screen(fresh).geometry())   # covers the game's screen, like the PS5 viewer
        self.show()
        ui_theme.set_on_top(self, True)
        ui_theme.bring_to_front(self)
        self.show_item()

    def go_back(self):
        """One step back: an open panel first, then wherever the viewer was opened from."""
        if self.editing:
            self.cancel_edit()
        elif self.full:
            self.toggle_full()
        elif self.sounding:
            self.exit_sound()
        elif self.sharing:
            self._set_sharing(False)
        elif self.trimming:
            self.exit_trim()
        elif self.del_btn.danger:
            self._reset_delete()
        else:
            back, self.back_to = getattr(self, "back_to", None), None
            self.close_viewer()
            if back:
                back()

    def close_viewer(self):
        self.phone_panel.close_panel()
        self._release()
        self.image.clear()       # a screenshot fitted to the screen: up to 15 MB
        self.hide()
        self._drop_timer.start()
        self.closed.emit()

    def _release(self):
        self._watchdog.stop()
        if self.player:
            self.player.stop()
            self.player.setSource(QtCore.QUrl())  # let go of the file

    def _ensure_player(self) -> bool:
        self._drop_timer.stop()
        if self.player is not None:
            return True
        if not runtime.load_multimedia():
            return False
        self.video = runtime.QtMultimediaWidgets.QVideoWidget()
        self.video.setFocusPolicy(Qt.NoFocus)
        self.video.installEventFilter(self)      # if it takes the keys anyway, they still reach the viewer
        self.stage.addWidget(self.video)
        self.player = runtime.QtMultimedia.QMediaPlayer(self)
        self.audio = runtime.QtMultimedia.QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setMuted(getattr(self, "_muted", False))
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)
        # Some decoders (e.g. AV1 without GPU support) play the sound but never
        # deliver a picture and report no error, so watch for real frames.
        self.video.videoSink().videoFrameChanged.connect(self._on_frame_shown)
        return True

    def _drop_player(self):
        """Gives the decoder's memory back once the viewer has been closed for a while,
        and the window's picture of itself with it."""
        if self.isVisible():
            return
        if self.player is not None:
            self._release()
            self.stage.removeWidget(self.video)
            for obj in (self.player, self.audio, self.video):
                obj.deleteLater()
            self.player = self.audio = self.video = None
        ui_theme.release_window(self)

    # ---- showing a capture
    def show_item(self):
        self._release()
        self._reset_delete()
        self._set_trimming(False)
        self._set_sharing(False)
        self._set_editing(False)
        self._set_sound(False)
        path = self.current
        runtime.log.info("viewer: %s (%s) on %s", path.name, path.parent.name, self.screen().name() if self.screen() else "?")
        self._show_title()
        self.sub.setToolTip(str(path))
        self.counter.setText(language.tr("{n} of {total}", n=self.index + 1, total=len(self.items)))
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.items) - 1)
        self.trim_btn.setVisible(self.is_video())
        self.sound_btn.setVisible(self.is_video())
        self.controls.setVisible(self.is_video())
        self.update_hints()
        self._pick_focus(fresh=True)
        if not self.is_video():
            self.controls.hide()
            self.stage.setCurrentWidget(self.image)
            self._fit_image()
        elif not self._ensure_player():
            self._show_msg("Preview isn't available here. Use “Open in player”.")
        else:
            preview = self.ctl.preview_path(path)
            self._play(preview if preview.exists() else path)

    def _play(self, source: Path):
        self.controls.show()
        self.stage.setCurrentWidget(self.video)
        self._frames = 0
        self.player.setSource(QtCore.QUrl.fromLocalFile(str(source)))
        self.player.play()
        self._watchdog.start()

    def _on_duration(self, ms: int):
        self.slider.setRange(0, ms)
        if self._pending_trim and ms > 0:     # opened with "Trim" from the notification
            self._pending_trim = False
            QtCore.QTimer.singleShot(150, self.enter_trim)

    def _on_frame_shown(self, frame):
        if frame.isValid():
            self._frames += 1

    def _check_frames(self):
        on_video = self.player is not None and self.isVisible() and self.stage.currentWidget() is self.video
        if on_video and self._frames == 0 and self.player.position() > 0:
            runtime.log.warning("no video frames decoded; switching to a preview copy")
            self._release()
            self._on_error()

    def _fit_image(self):
        pm = QtGui.QPixmap(str(self.current))
        if not pm.isNull():
            self.image.setPixmap(pm.scaled(self.stage.size(), Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))

    def _show_msg(self, text: str):
        self.controls.hide()
        self.msg.setText(language.tr(text))
        self.stage.setCurrentWidget(self.msg)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        side = 24 if self.full else max(64, (self.width() - 1680) // 2)    # keep lines short on a wide TV
        self.layout().setContentsMargins(side, 24 if self.full else 36, side, 24)
        if self.items and self.stage.currentWidget() is self.image:
            QtCore.QTimer.singleShot(0, self._fit_image)    # once the layout has settled

    def _on_error(self, *_):
        path = self.current if self.items else None
        runtime.log.warning("playback failed for %s: %s", path.name if path else "?",
                    self.player.errorString() if self.player else "no player")
        if path is None or path in self._tried_preview or self.ctl.preview_path(path).exists():
            self._show_msg("This clip can't be previewed here.\nIt's saved fine. Use “Open in player” to watch it.")
            return
        self._tried_preview.add(path)
        self._show_msg("Preparing preview…")

        def run():
            ok = media.make_preview(path, self.ctl.preview_path(path),
                              lambda pct: runtime.safe_emit(self.preview_progress, str(path), pct))
            runtime.safe_emit(self.preview_ready, str(path), str(self.ctl.preview_path(path)) if ok else "")
        threading.Thread(target=run, daemon=True).start()

    def _on_preview_progress(self, path: str, pct: int):
        if self.isVisible() and self.items and str(self.current) == path:
            self.msg.setText(language.tr("Preparing preview…  {pct}%", pct=pct))

    def _on_preview_ready(self, path: str, preview: str):
        if not (self.isVisible() and self.items and str(self.current) == path):
            return
        if preview:
            self._play(Path(preview))
        else:
            self._show_msg("This clip can't be previewed here.\nIt's saved fine. Use “Open in player” to watch it.")

    # ---- playback
    def toggle_play(self):
        if self.player is None or self.stage.currentWidget() is not self.video:
            return
        if self.player.playbackState() == runtime.QtMultimedia.QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if self.trimming and self.player.position() >= self.timeline.end - 50:
                self.player.setPosition(self.timeline.start)
            self.player.play()

    def seek(self, ms: int):
        if self.player is not None and self.stage.currentWidget() is self.video:
            self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + ms)))

    def _on_position(self, pos: int):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.time.setText(f"{ui_theme.short_clock(pos / 1000)} / {ui_theme.short_clock(self.player.duration() / 1000)}")
        if self.trimming:
            self.timeline.pos = pos
            self.timeline.update()
            playing = self.player.playbackState() == runtime.QtMultimedia.QMediaPlayer.PlayingState
            if playing and pos >= self.timeline.end:   # stop at the end of the selection
                self.player.pause()
                self.player.setPosition(self.timeline.end)

    def _on_state(self, state):
        playing = state == runtime.QtMultimedia.QMediaPlayer.PlayingState
        self.play_btn.setIcon(ui_theme.qicon("pause" if playing else "play"))

    # ---- trimming
    def enter_trim(self):
        if not self.is_video() or self.player is None or self.stage.currentWidget() is not self.video:
            return
        duration = self.player.duration() or int((media.media_duration(self.current) or 0) * 1000)
        if duration < 1000:
            return
        self.player.pause()
        self.timeline.reset(duration)
        self.timeline.pos = self.player.position()
        self._set_trimming(True)
        self._trim_labels()
        src, slots = self.current, self.timeline.slots
        tag = hashlib.md5(str(src).encode()).hexdigest()

        def run():  # filmstrip frames, filled in as they arrive
            for i in range(slots):
                out = self.ctl.thumbs_dir / f"strip_{tag}_{i}.jpg"
                if media.filmstrip_frame(src, int(duration * (i + 0.5) / slots), out):
                    runtime.safe_emit(self.frame_ready, str(src), i, str(out))
        threading.Thread(target=run, daemon=True).start()

    def _on_frame(self, src: str, i: int, path: str):
        if self.trimming and str(self.current) == src:
            self.timeline.set_frame(i, path)

    def exit_trim(self):
        self._set_trimming(False)

    def _set_trimming(self, on: bool):
        self.trimming = on
        self._sync()
        if not on:
            self._pick_focus()

    def _show_title(self):
        path = self.current
        fav = self.ctl.is_favorite(path)
        self.title.setTextFormat(Qt.RichText)
        star = '<span style="color:#ffd34d">★</span>&nbsp;' if fav else ""
        meta = self.ctl.meta(path)
        name = meta.get("title") or path.stem      # the file's name, as the folder shows it
        self.title.setText(star + name.replace("&", "&amp;").replace("<", "&lt;"))
        self.sub.setText(f"{path.parent.name}  ·  {catalog.capture_kind(path)}  ·  {catalog.time_ago(path.stat().st_mtime)}")
        self.note.setText(meta.get("note", ""))
        self.note.setVisible(bool(meta.get("note")))
        self.fav_btn.setToolTip(language.tr("Favorited") if fav else language.tr("Favorite"))
        self.fav_btn.icon_color = "#ffd34d" if fav else None
        self.fav_btn.update()

    def toggle_favorite(self):
        if self.items:
            self.ctl.toggle_favorite(self.current)
            self._show_title()

    # ---- rename
    def start_edit(self):
        if not self.items:
            return
        meta = self.ctl.meta(self.current)
        self.title_edit.setText(meta.get("title", ""))
        self.note_edit.setText(meta.get("note", ""))
        if self.full:
            self.toggle_full()             # the title is in the header
        if self.player is not None:
            self.player.pause()
        self._set_trimming(False)
        self._set_sharing(False)
        self._reset_delete()
        self._set_editing(True)
        ui_theme.bring_to_front(self, keyboard=True)     # after a controller press the keyboard may still be on the game
        self.title_edit.setFocus()
        self.title_edit.selectAll()
        self._edit_hint()

    def _edit_hint(self):
        """Says what to do now; if Windows kept the keyboard on another window, says to click the name
        (a click always brings it here)."""
        self.edit_hint.setText(language.tr("Type a new name, then press Enter") if self.isActiveWindow()
                               else language.tr("Click the name, then type"))

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.ActivationChange:
            if self.isActiveWindow():
                ui_theme.set_on_top(self, True)        # back in use after the folder opened over it
            if self.editing:
                self._edit_hint()
        super().changeEvent(e)

    def save_edit(self):
        if self.editing:
            self.ctl.set_meta(self.current, self.title_edit.text(), self.note_edit.text())
            self._set_editing(False)
            self._show_title()

    def cancel_edit(self):
        self._set_editing(False)

    def _set_editing(self, on: bool):
        self.editing = on
        self._sync()
        if not on:
            self._pick_focus()

    def enter_sound(self):
        if not self.is_video():
            return
        if media.audio_tracks(self.current) < 3:
            self.ctl.toast.emit(language.tr("This clip has no separate voice track · "
                                   "it was recorded with “Voice on its own track” off"), "info")
            return
        voice, game = self.ctl.mix_of(self.current)
        self.voice_row.set_value(voice)
        self.game_row.set_value(game)
        self._set_trimming(False)
        self._set_sharing(False)
        self._set_sound(True)
        self.voice_row.setFocus()

    def exit_sound(self):
        previewed = self._previewing_sound
        self._set_sound(False)
        if previewed:
            self.show_item()     # back to the clip as it is

    def _set_sound(self, on: bool):
        self.sounding = on
        self._previewing_sound = self._previewing_sound and on
        self._sync()
        if not on:
            self._pick_focus()

    def preview_sound(self):
        """Plays 12 seconds from here with the levels picked, before anything is saved."""
        if not self.sounding or self.player is None:
            return
        src, start = self.current, self.player.position() / 1000
        voice, game = self.voice_row.value, self.game_row.value
        showing = Path(self.player.source().toLocalFile() or src)
        picture = showing if showing != src and showing.exists() and showing.parent == self.ctl.previews_dir \
            else None   # the 720p copy, when the clip itself doesn't play here
        out = self.ctl.thumbs_dir / "sound_preview.mp4"
        self._release()          # the last preview may still be open
        self._show_msg("Preparing preview…")

        def run():
            try:
                media.remix_audio(src, voice, game, out, seconds=12, start=start, picture=picture)
                runtime.safe_emit(self.sound_ready, str(src), str(out))
            except Exception:
                runtime.log.exception("sound preview failed")
                runtime.safe_emit(self.sound_ready, str(src), "")
        threading.Thread(target=run, daemon=True).start()

    def _on_sound_ready(self, src: str, piece: str):
        if not (self.isVisible() and self.sounding and self.items and str(self.current) == src):
            return
        if not piece:
            self._show_msg("Couldn't make a preview of this clip.")
            return
        self._previewing_sound = True
        self._play(Path(piece))
        self.player.play()

    def save_sound(self):
        if not self.sounding:
            return
        src, voice, game = self.current, self.voice_row.value, self.game_row.value
        previewed = self._previewing_sound
        self._set_sound(False)
        if (voice, game) == self.ctl.mix_of(src):   # nothing to save
            if previewed:
                self.show_item()   # back to the clip from the preview piece
            return
        self._release()          # the file is rewritten, so let go of it
        self._show_msg("Changing the sound…")
        self.ctl.set_mix(src, voice, game)

    def _on_remixed(self, path: str):
        if self.isVisible() and self.items and str(self.current) == path:
            self.show_item()

    # ---- share
    def enter_share(self):
        if not self.items:
            return
        self._set_trimming(False)
        self._reset_delete()
        self._set_sharing(True)

    def _set_sharing(self, on: bool):
        self.sharing = on
        if on:
            video = self.is_video()
            # leaving your voice out needs the separate game-only track (voice_track in OBS)
            split = video and media.audio_tracks(self.current) >= 3
            for card in (self.format_card, self.voice_card, self.size_card):
                card.setVisible(video)
            self.format_card.set_value("mp4")
            self.voice_card.set_value(True)
            self.size_card.set_value(None)
            self._split = split
            self.share_caption.setText(language.tr("Makes a file that plays everywhere and copies it, ready to paste")
                                       if video else language.tr("Copies the screenshot so you can paste it anywhere"))
            self._share_cards_state()
            self.share_go.setFocus()
        self._sync()
        if not on:
            self._pick_focus()

    def _share_cards_state(self):
        """The original file is copied as it is: your voice and the size don't apply to it."""
        original = not self.is_video() or self.format_card.value == "copy"
        split = getattr(self, "_split", False)
        self.voice_card.setEnabled(split and not original)
        self.voice_card.note = ("" if split and not original else
                                language.tr("Not needed for the original file") if original else
                                language.tr("This clip has your voice and the game together"))
        self.size_card.setEnabled(not original)
        self.size_card.note = language.tr("Not needed for the original file") if original else ""
        for card in (self.voice_card, self.size_card):
            card.update()
        self.share_go.setText("  " + (language.tr("Copy") if not self.is_video() else
                                      language.tr("Copy file") if original else language.tr("Export & copy")).replace("&", "&&"))

    def _toggle_voice(self):
        self.voice_card.next()

    @property
    def without_voice(self) -> bool:
        return self.voice_card.isEnabled() and self.voice_card.value is False

    def _do_share(self, *_):
        path = self.current
        copy_only = not self.is_video() or self.format_card.value == "copy"
        size, without_voice = self.size_card.value, self.without_voice
        self._set_sharing(False)
        if copy_only:
            self.ctl.copy(path)
        else:
            self.ctl.share(path, "phone" if size is None else f"discord{size}", without_voice)

    def send_to_phone(self):
        """A link to this capture, as it is, for a phone on the same Wi-Fi: shown as a QR code."""
        if not self.items:
            return
        if self.player is not None:
            self.player.pause()               # the phone plays it now
        self.phone_panel.show_link(phone_link.PhoneLink(self.items[self.index]))

    def _share_nav(self) -> list[QtWidgets.QWidget]:
        cards = [c for c in (self.format_card, self.voice_card, self.size_card) if c.isVisible() and c.isEnabled()]
        return cards + [self.share_cancel, self.phone_go, self.share_go]

    def _all_nav(self) -> list[QtWidgets.QWidget]:
        return [self.back_btn, self.rename_btn, self.prev_btn, self.next_btn, self.close_btn,
                self.back5_btn, self.play_btn, self.fwd5_btn, self.slider, self.vol_btn, self.full_btn,
                self.trim_btn, self.sound_btn, self.share_btn,
                self.fav_btn, self.folder_chip, self.external_chip, self.del_btn]

    def _nav_items(self) -> list[QtWidgets.QWidget]:
        """Everything on screen the controller's highlight can go to, like a mouse."""
        return [w for w in self._all_nav() if w.isVisible() and w.isEnabled()]

    def _pick_focus(self, fresh: bool = False):
        """With a controller the highlight sits on something on screen (Play, or Share for a picture);
        with the keyboard the viewer keeps the keys for its shortcuts. fresh: a new capture is shown."""
        if not self.isVisible() or self.trimming or self.sounding or self.sharing or self.editing:
            return
        if input_devices.input_mode().mode == "keyboard":
            self.setFocus()
        elif fresh or self.focusWidget() not in self._nav_items():
            (self.play_btn if self.is_video() else self.share_btn).setFocus()

    def _keep_focus_off_video(self, _old, new):
        """The video picture takes the focus when it appears; the highlight goes back to the buttons."""
        if new is not None and self.video is not None and (new is self.video or self.video.isAncestorOf(new)):
            QtCore.QTimer.singleShot(0, self._pick_focus)

    # ---- the small buttons, only the video, sound on / off
    def toggle_more(self):
        """△ / M: the highlight jumps to the small buttons at the end of the row."""
        self.fav_btn.setFocus()

    def eventFilter(self, obj, event):
        if (obj is self.video and event.type() == QtCore.QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton and not self.trimming):
            self.toggle_play()               # a click on the video plays / pauses it, like a phone's player
            return True
        if event.type() == QtCore.QEvent.KeyPress and (obj in self._all_nav() or obj is self.video):
            self.keyPressEvent(event)        # a focused button would eat the arrows and ✕ itself
            return True
        return super().eventFilter(obj, event)

    def toggle_full(self):
        self.full = not self.full
        self._sync()
        self.resizeEvent(QtGui.QResizeEvent(self.size(), self.size()))

    def toggle_mute(self):
        self._muted = not getattr(self, "_muted", False)
        if self.player is not None:
            self.audio.setMuted(self._muted)
        self.vol_btn.setIcon(ui_theme.qicon("volume-off" if self._muted else "volume"))

    def _sync(self):
        """Shows what goes with the state: one panel at a time, its buttons in the footer."""
        panel = self.trimming or self.sounding or self.sharing
        full = self.full
        self.head.setVisible(not full)
        self.trim_panel.setVisible(self.trimming and not full)
        self.sound_panel.setVisible(self.sounding and not full)
        self.share_panel.setVisible(self.sharing and not full)
        self.actions_row.setVisible(not panel and not full)
        self.footer.setVisible(not full)
        self.trim_buttons.setVisible(self.trimming)
        self.sound_buttons.setVisible(self.sounding)
        self.share_buttons.setVisible(self.sharing)
        self.full_btn.setIcon(ui_theme.qicon("minimize" if full else "maximize"))
        editing = self.editing
        for w in (self.title_edit, self.note_edit, self.edit_hint):
            w.setVisible(editing)
        self.title.setVisible(not editing)
        self.rename_btn.setVisible(not editing)
        self.note.setVisible(not editing and bool(self.note.text()))
        self.update_hints()

    def update_hints(self):
        pad, mode = input_devices.input_mode().mode != "keyboard", input_devices.input_mode().mode
        if self.editing:
            items = [("k:Enter", "Save"), ("B", "Cancel")] if pad else [("k:Enter", "Save"), ("k:Esc", "Cancel")]
        elif self.sounding:
            items = ([("DPAD_UD", "Switch"), ("DPAD_LR", "Change"), ("Y", "Mute"), ("X", "Preview"), ("A", "Save"),
                      ("B", "Cancel")] if pad else
                     [("k:↑ ↓", "Switch"), ("k:← →", "Change"), ("k:M", "Mute"), ("k:P", "Preview"),
                      ("k:Enter", "Save"), ("k:Esc", "Cancel")])
        elif self.sharing:
            items = ([("DPAD_LR", "Move"), ("A", "Select"), ("B", "Back")] if pad
                     else [("k:← →", "Move"), ("k:Enter", "Select"), ("k:Esc", "Back")])
        elif self.trimming:
            items = ([("X", "Start"), ("Y", "End"), ("L1", "Preview"), ("A", "Save"), ("B", "Cancel")] if pad
                     else [("k:I", "Start"), ("k:O", "End"), ("k:P", "Preview"), ("k:Enter", "Save"),
                           ("k:Esc", "Cancel")])
        elif pad:
            items = [("DPAD", "Move"), ("A", "Select"), ("L1R1", "Newer/older"), ("B", "Back")]
        elif self.is_video():
            items = [("k:Space", "Play/pause"), ("k:A D", "Newer/older"), ("k:F", "Favorite"),
                     ("k:N", "Rename"), ("k:Esc", "Back")]
        else:
            items = [("k:A D", "Newer/older"), ("k:F", "Favorite"), ("k:N", "Rename"), ("k:Esc", "Back")]
        self.keys_hint.set_items(items, mode)
        self.tools_hint.set_items([("Y" if pad else "k:M", "")], mode)

    def _timeline_seek(self, ms: int):
        if self.player:
            self.player.pause()
            self.player.setPosition(ms)

    def _trim_labels(self):
        t = self.timeline
        self.trim_info.setText(f"{language.clock_precise(t.start)}  →  {language.clock_precise(t.end)}     "
                               + language.tr("{length} selected", length=language.clock_precise(t.end - t.start)))

    def preview_selection(self):
        if self.player:
            self.player.setPosition(self.timeline.start)
            self.player.play()

    def save_trim(self, replace: bool):
        t = self.timeline
        if t.start <= 0 and t.end >= t.duration and not replace:
            self.exit_trim()
            return
        src = self.current
        self._release()
        self._set_trimming(False)
        self._show_msg("Saving trimmed clip…")
        self.ctl.trim(src, t.start, t.end, replace)

    def _on_trimmed(self, path: str):
        if not self.isVisible():
            return
        self.items = self.ctl.recent_items()
        new = Path(path)
        self.index = self.items.index(new) if new in self.items else 0
        self.show_item()

    # ---- navigation and actions
    def step(self, delta: int):
        i = self.index + delta
        if 0 <= i < len(self.items):
            self.index = i
            self.show_item()

    def _show_in_folder(self):
        """File Explorer opens on top with the capture selected; Capture Menu stays where it is underneath."""
        if self.player is not None:
            self.player.pause()
        ui_theme.make_room_above()
        self.ctl.reveal(self.current)

    def _step_out(self, open_it):
        """Shows the capture in another app (its folder, a video player): Capture Menu gets out of the
        way first, the gallery behind too, so that app isn't covered."""
        path = self.current
        self._release()
        self.back_to = None
        self.hide()
        self._drop_timer.start()
        self.away.emit()
        open_it(path)

    def delete_current(self):
        if not self.del_btn.danger:       # the highlight goes to Delete, ready to confirm
            self.del_btn.danger = True
            self.del_btn.setText(language.tr("Press again to delete"))
            self.del_btn.setFocus()
            self._disarm.start(3000)
            return
        self._release()
        path = self.current
        QtCore.QTimer.singleShot(200, lambda: self._finish_delete(path))  # file handle released

    def _finish_delete(self, path: Path):
        if not self.ctl.delete(path):
            self._show_msg("Couldn't delete this file. Is it open somewhere else?")
            return
        self.items.remove(path)
        if not self.items:
            self.close_viewer()
            return
        self.index = min(self.index, len(self.items) - 1)
        self.show_item()

    def _reset_delete(self):
        self.del_btn.danger = False
        self.del_btn.setText("")

    @staticmethod
    def _repolish(w):
        w.style().unpolish(w)
        w.style().polish(w)

    def keyPressEvent(self, e):
        k = e.key()
        if self.phone_panel.isVisible():   # the QR on screen: Esc, ◯ / B or Enter puts it away
            if k in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Return, Qt.Key_Enter):
                self.phone_panel.close_panel()
            return
        pos = self.player.position() if self.player else 0
        if self.editing:
            if k == Qt.Key_Escape:
                self.cancel_edit()
            return
        if self.sounding:
            rows = [self.voice_row, self.game_row]
            row = next((r for r in rows if r.slider.hasFocus()), self.voice_row)
            if k in (Qt.Key_Up, Qt.Key_Down):
                rows[1 if row is self.voice_row else 0].setFocus()
            elif k in (Qt.Key_Left, Qt.Key_Right):   # only when a bar doesn't have the keys itself
                row.step(1 if k == Qt.Key_Right else -1)   # the bars run left to right everywhere
            elif k == Qt.Key_M:
                row.toggle_mute()
            elif k == Qt.Key_P:
                self.preview_sound()
            elif k in (Qt.Key_Return, Qt.Key_Enter):
                self.save_sound()
            elif k in (Qt.Key_Escape, Qt.Key_Backspace):
                self.exit_sound()
            elif k == Qt.Key_Space:
                self.toggle_play()
            return
        if self.sharing:
            nav = self._share_nav()
            focused = self.focusWidget()
            i = nav.index(focused) if focused in nav else len(nav) - 1
            if k in (Qt.Key_Left, Qt.Key_Right) and nav:
                nav[max(0, min(len(nav) - 1, i + language.forward(k)))].setFocus()
            elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and nav:
                item = nav[i]
                item.next() if isinstance(item, ui_widgets.OptionCard) else item.click()
            elif k in (Qt.Key_Escape, Qt.Key_Backspace):
                self.go_back()
            return
        items = [] if self.trimming else self._nav_items()
        focused = self.focusWidget()
        if items and (focused in items or input_devices.input_mode().mode != "keyboard"):   # the highlight, moved like a mouse
            if focused not in items:
                self._pick_focus(fresh=True)
                focused = self.focusWidget()
            if focused is self.slider and k in (Qt.Key_Left, Qt.Key_Right):
                self.seek(5000 if k == Qt.Key_Right else -5000)   # on the seek bar ← → move through the video
                return
            if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                nxt = ui_theme.toward(focused, items, k)
                if nxt is not None:
                    nxt.setFocus()
                return
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.toggle_play() if focused is self.slider else focused.click()
                return
        if self.trimming:
            handlers = {
                Qt.Key_Escape: self.exit_trim,
                Qt.Key_I: lambda: self.timeline.set_start(pos),
                Qt.Key_O: lambda: self.timeline.set_end(pos),
                Qt.Key_P: self.preview_selection,
                Qt.Key_Return: lambda: self.save_trim(replace=False),
                Qt.Key_Enter: lambda: self.save_trim(replace=False),
            }
        else:
            handlers = {
                Qt.Key_Escape: self.go_back,
                Qt.Key_A: lambda: self.step(1 if language.is_rtl() else -1),   # A / D (L1 / R1) go the way the arrows point
                Qt.Key_D: lambda: self.step(-1 if language.is_rtl() else 1),
                Qt.Key_T: self.enter_trim,
                Qt.Key_V: self.enter_sound,
                Qt.Key_Delete: self.delete_current,
                Qt.Key_E: self.enter_share,
                Qt.Key_F: self.toggle_favorite,
                Qt.Key_N: self.start_edit,
                Qt.Key_M: self.toggle_more,
                Qt.Key_F11: self.toggle_full,
                Qt.Key_C: lambda: self.ctl.copy(self.current),
            }
        handlers.update({
            Qt.Key_Space: self.toggle_play,
            Qt.Key_Left: lambda: self.seek(-5000),
            Qt.Key_Right: lambda: self.seek(5000),
        })
        if k in handlers:
            handlers[k]()
        else:
            super().keyPressEvent(e)


class PhonePanel(QtWidgets.QWidget):
    """Over the viewer: the QR code for the phone, what it needs (the same Wi-Fi) and what it gets (the original
    file). Closing it ends the link. Its own window on top of the viewer's: the video draws in a native window
    that would cover anything placed inside the viewer."""

    def __init__(self, viewer: QtWidgets.QWidget):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.viewer = viewer
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(viewer.styleSheet())
        self.setFont(viewer.font())
        self.link: phone_link.PhoneLink | None = None
        self.hide()
        outer = QtWidgets.QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        self.card = QtWidgets.QFrame(objectName="phoneCard")
        self.card.setStyleSheet(f"#phoneCard {{ background: {ui_theme.PANEL}; border-radius: 24px; border: 1px solid rgba(255,255,255,22); }}"
                                "QLabel { background: transparent; }")
        outer.addWidget(self.card)
        lay = QtWidgets.QVBoxLayout(self.card)
        lay.setContentsMargins(40, 32, 40, 30)
        lay.setSpacing(14)
        self.title = QtWidgets.QLabel(language.tr("Send to your phone"), objectName="vTitle")
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title)
        self.code = QtWidgets.QLabel()            # the percentage while the phone's copy is made, then the code
        self.code.setAlignment(Qt.AlignCenter)
        self.code.setFixedSize(280, 280)
        self.code.setStyleSheet(f"color: {ui_theme.INK}; font-size: 72px; font-weight: 700;")
        lay.addWidget(self.code, 0, Qt.AlignCenter)
        self.notes = []
        for icon, text in (("phone", "Scan the code with your phone's camera: the video opens, with a button to download it"),
                           ("info", "Your phone and this PC must be on the same Wi-Fi network"),
                           ("file-video", "The video goes over in its full, original quality")):   # (or at 60 FPS: show_link)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(12)
            pic = QtWidgets.QLabel()
            pic.setPixmap(ui_theme.icon_pixmap(icon, 20, ui_theme.INK))
            row.addWidget(pic, 0, Qt.AlignTop)
            words = QtWidgets.QLabel(language.tr(text))
            words.setWordWrap(True)
            words.setStyleSheet(f"color: {ui_theme.INK}; font-size: 16px;")
            row.addWidget(words, 1)
            lay.addLayout(row)
            self.notes.append(words)
        self.fine = QtWidgets.QLabel(objectName="info")
        self.fine.setWordWrap(True)
        self.fine.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.fine)
        close = QtWidgets.QPushButton(language.tr("Done"), objectName="primary")
        close.setCursor(Qt.PointingHandCursor)
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(self.close_panel)
        lay.addWidget(close, 0, Qt.AlignCenter)
        self.card.setFixedWidth(560)

    def show_link(self, link: phone_link.PhoneLink):
        self.close_panel()
        self.link = link
        self.notes[2].setText(link.what())
        self.code.clear()
        if link.url is None:
            self.fine.setText(language.tr("This PC isn't connected to a network"))
        else:
            self._tick()                       # the code shows once the video is ready (a 60 FPS copy takes a moment)
        self.setGeometry(self.viewer.geometry())
        self.show()
        ui_theme.bring_to_front(self)

    def _tick(self):
        link = self.link
        if link is None or link.url is None:
            return
        if not link.ready.is_set():
            self.code.setText(f"{link.progress}%")
            self.fine.setText(language.tr("Getting the video ready for the phone…"))
            QtCore.QTimer.singleShot(250, self._tick)
            return
        pm = QtGui.QPixmap()
        pm.loadFromData(link.qr_png(scale=9))
        self.code.setPixmap(pm.scaled(280, 280, Qt.KeepAspectRatio, Qt.FastTransformation))
        self.fine.setText(language.tr("If Windows asks about network access, choose Allow. If the phone can't open it, set this Wi-Fi to Private in Windows settings") + "\n" + link.url)

    def close_panel(self):
        if self.link is not None:
            self.link.stop()
            self.link = None
        self.hide()

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self.close_panel()          # a click beside the card puts it away

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Return, Qt.Key_Enter):
            self.close_panel()
            if self.viewer.isVisible():
                ui_theme.bring_to_front(self.viewer)   # the keys go back to the viewer

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(6, 7, 11, 190))

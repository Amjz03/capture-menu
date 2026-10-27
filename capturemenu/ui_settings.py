"""Settings page and its update/install UI state."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import shutil
import tempfile
import threading

from . import (
    capture_controller,
    input_devices,
    language,
    obs_client,
    preferences,
    runtime,
    ui_theme,
    ui_widgets,
    updates,
    version,
    windows,
)


class Settings(QtWidgets.QWidget):
    """Everything in config.json that a player would want to change, on one page.
    Nothing is written until Save; then the app restarts itself (and OBS if recording changed)."""

    encoder_ready = QtCore.Signal(str)
    mics_ready = QtCore.Signal(object)       # Obs.mic_devices(), or None
    update_event = QtCore.Signal(dict)       # what the update check / download is doing
    update_found = QtCore.Signal(dict)       # the background check saw a newer release

    def __init__(self, ctl: capture_controller.Controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setProperty("captureMenuPage", "settings")
        self.ctl = ctl
        self.restart = windows.restart_app          # tests swap this out
        self.encoder: str | None = None
        self.screen_px = (2560, 1440)
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(ui_theme.GALLERY_STYLE + "QScrollArea, #rows { background: transparent; border: none; }")
        self.setFont(ui_theme.font(13))
        ui_theme.dress(self)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(48, 36, 48, 28)
        lay.setSpacing(18)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        self.back_btn = ui_widgets.back_button(self.go_back)
        head.addWidget(self.back_btn, 0, Qt.AlignTop)
        head.addSpacing(18)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        self.title = QtWidgets.QLabel(language.tr("Settings"), objectName="vTitle")
        titles.addWidget(self.title)
        self.info = QtWidgets.QLabel(objectName="vSub")
        titles.addWidget(self.info)
        head.addLayout(titles)
        head.addStretch()
        self.defaults_btn = QtWidgets.QPushButton(language.tr("Restore defaults"))
        self.cancel_btn = QtWidgets.QPushButton(language.tr("Cancel"))
        self.save_btn = QtWidgets.QPushButton(language.tr("Save"), objectName="primary")
        for b, fn in ((self.defaults_btn, self.restore_defaults), (self.cancel_btn, self.close_settings),
                      (self.save_btn, self.save)):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            head.addWidget(b, 0, Qt.AlignTop)
        lay.addLayout(head)
        for b in self._head():
            b.installEventFilter(self)          # the D-pad reaches them from the first row

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        holder = QtWidgets.QWidget(objectName="rows")
        outer = QtWidgets.QHBoxLayout(holder)
        outer.setContentsMargins(0, 0, 0, 0)
        column = QtWidgets.QWidget(objectName="rows")
        column.setMaximumWidth(920)
        self.rows_layout = QtWidgets.QVBoxLayout(column)
        self.rows_layout.setContentsMargins(0, 0, 12, 0)
        self.rows_layout.setSpacing(0)
        column.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        outer.addWidget(column, 1)
        outer.addStretch(0)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll, 1)

        foot = QtWidgets.QHBoxLayout()
        self.hints = ui_widgets.HintBar()
        foot.addWidget(self.hints)
        foot.addStretch()
        self.memory = QtWidgets.QLabel(objectName="vSub")
        self.memory.setWordWrap(True)        # the panel is narrow: two lines rather than a wider page
        self.memory.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        foot.addWidget(self.memory)
        lay.addLayout(foot)

        self.rows: list[ui_widgets.SettingRow] = []
        self.update: dict = {"state": "idle"}
        self.mics: tuple | None | str = "checking"   # Obs.mic_devices() once OBS has answered
        self.install = updates.run_update_installer     # tests swap this out
        self._build_rows()
        self.update_event.connect(self._on_update_event)
        self.update_found.connect(self._on_update_found)
        self.encoder_ready.connect(self._on_encoder)
        self.mics_ready.connect(self._on_mics)
        input_devices.input_mode().changed.connect(lambda _: self.update_hints())
        self.update_hints()

    # ---- the rows
    def _row(self, *args, **kw) -> ui_widgets.SettingRow:
        row = ui_widgets.SettingRow(*args, **kw)
        row.changed.connect(self._refresh)
        self.card.rows.addWidget(row)
        self.rows.append(row)
        return row

    def _section(self, title: str):
        """A title, then a card that the next rows go into."""
        self.rows_layout.addWidget(ui_widgets.SectionTitle(title))
        self.card = ui_widgets.SettingsCard()
        self.rows_layout.addWidget(self.card)

    def _build_rows(self):
        # first, so it's easy to find again: the website, to send to anyone ("_" keeps it out of config.json)
        self._section("Capture Menu")
        share = self._row("_share", "Share Capture Menu", "action",
                          describe=lambda v: "Opens the website, to send its link to anyone",
                          display=lambda v: language.tr("Open the website"))
        share.on_activate = lambda row: QtGui.QDesktopServices.openUrl(QtCore.QUrl(version.SITE))
        self._section("RECORDING")
        self.res_row = self._row("resolution", "Resolution", "choice", [("native", "Native")],
                                 lambda v: "Lower uses less space; Native looks sharpest")
        self._row("fps", "Frame rate", "choice", [(30, "30 FPS"), (60, "60 FPS"), (120, "120 FPS")],
                  lambda v: "60 is smooth for every game; 120 for fast shooters on a high-refresh screen",
                  custom=lambda v: language.tr("{n} FPS", n=v))
        self._row("quality", "Quality", "choice",
                  [("light", "Light"), ("balanced", "Balanced"), ("high", "High"), ("max", "Max")],
                  self._quality_text)
        self.codec_row = self._row("video_codec", "Video format", "choice",
                                   [("auto", "Auto"), ("av1", "AV1"), ("hevc", "HEVC"), ("h264", "H.264")],
                                   self._codec_text)
        self._row("buffer_minutes", "Replay buffer", "choice",
                  [(m, language.tr("{n} min", n=m)) for m in (5, 10, 15, 30, 60)], self._buffer_text,
                  custom=lambda v: language.tr("{n} min", n=v))
        self._row("voice_track", "Voice on its own track", "bool",
                  describe=lambda v: "So you can share a clip with or without your voice")
        self._row("hdr", "HDR", "choice", [("auto", "Auto"), ("off", "Off")],
                  lambda v: "HDR clips while Windows HDR is on. Shared copies get normal colours"
                  if v == "auto" else "Always normal colours (SDR)")
        self._row("colours", "Colours", "choice",
                  [("natural", "Natural"), ("soft", "Soft"), ("vivid", "Vivid"), ("max", "Max")],
                  lambda v: "Colours exactly as Windows shows them" if v == "natural"
                  else "More colour and contrast when an HDR screen is recorded in normal colours")
        self._row("record_indicator", "Recording indicator", "choice",
                  [("top-left", "Top left"), ("top-right", "Top right"), ("off", "Off")],
                  lambda v: "A small REC timer while you record by hand"
                  if v != "off" else "Nothing on screen while recording")
        self._section("DEVICES")
        # the screens and microphones are filled in by open(): they change while the app runs
        self.screen_row = self._row("capture_screen", "Recording screen", "choice",
                                    [("follow", "Follow the game")], self._screen_text)
        self.mic_row = self._row("mic_device", "Microphone", "choice",
                                 [("default", "Same as Windows")], self._mic_text)
        self._row("mic_on", "Record your microphone", "bool",
                  describe=lambda v: "Your voice goes into your clips. The menu's Mic button turns it off for now"
                  if v else "Clips have the game's sound only")
        self._section("CONTROLS")
        hk = self._row("hotkey", "Keyboard shortcut", "action",
                       describe=lambda v: "Opens the menu. Press Enter, then the new keys")
        hk.on_activate = self._listen_hotkey
        self._row("controller_button", "Controller button", "choice",
                  [("create", "Create / View"), ("ps", "PS / Xbox button"), ("touchpad", "Touchpad"),
                   ("mute", "Mute / Share"), ("l3+r3", "L3 + R3")],
                  lambda v: "The button that opens the menu, like Create on the PS5")
        self._row("controller_hold_ms", "Open the menu with", "choice", [(0, "A press"), (400, "A hold")],
                  lambda v: "Hold keeps a quick tap for the game, if it uses the same button",
                  custom=lambda v: language.tr("A hold ({n} ms)", n=v))
        self._row("double_press_seconds", "Double-press to save", "choice",
                  [(0, "Off"), (15, "15 sec"), (30, "30 sec"), (60, "1 min"), (120, "2 min")],
                  lambda v: "Press twice quickly to save without opening the menu" if v else
                  "Double-pressing does nothing extra", custom=lambda v: language.tr("{n} sec", n=v))
        self._row("rumble", "Rumble", "bool", describe=lambda v: "A short buzz on the controller when something is saved")
        self._row("sounds", "Sounds", "bool", describe=lambda v: "A short sound when something is saved")
        self._section("LIBRARY")
        # a folder Windows refused shows where captures really go (the setting itself is kept)
        in_use = lambda v: str(self.ctl.clips_dir) if self.ctl.blocked and v == str(self.ctl.blocked) else v
        folder = self._row("clips_dir", "Clips folder", "action",
                           describe=lambda v: "Windows Security protects the folder you picked, so captures "
                                              "are saved here"
                           if in_use(v) != v else "Clips and recordings, a folder per game",
                           display=in_use)
        folder.on_activate = self._pick_folder
        shots = self._row("screenshots_dir", "Screenshots folder", "action",
                          describe=lambda v: "A folder per game here too",
                          display=lambda v: v or language.tr("Same as the clips folder"))
        shots.on_activate = self._pick_folder
        self._row("storage_warn_gb", "Warn me when captures pass", "choice",
                  [(0, "Never"), (50, "50 GB"), (100, "100 GB"), (200, "200 GB"), (500, "500 GB"),
                   (1000, "1 TB")], lambda v: "Only a notice. Nothing is ever deleted for you",
                  custom=lambda v: language.tr("{n} GB", n=v))
        self._section("GENERAL")
        self._row("start_with_windows", "Start with Windows", "bool",
                  describe=lambda v: "Capture Menu and OBS start when you sign in")
        self._row("language", "Language", "choice",
                  [("auto", "Same as Windows"), *language.LANGUAGES.items()],
                  lambda v: "Capture Menu restarts in the new language when you save")
        # not a setting: "_" keeps it out of config.json
        self.update_row = self._row("_update", "Updates", "action", describe=lambda v: self._update_describe(),
                                    display=lambda v: self._update_value())
        self.update_row.on_activate = lambda row: self.check_or_install()
        self.rows_layout.addStretch()

    def _plan_cfg(self) -> dict:
        return dict(self.ctl.cfg, **self.values())

    def _quality_text(self, v) -> str:
        cfg = self._plan_cfg()
        w, h = obs_client.output_size(*self.screen_px, cfg["resolution"])
        enc = obs_client.choose_encoder(self.encoder or "nvenc_av1", cfg["video_codec"])
        kbps = obs_client.pick_bitrate(enc, w, h, int(cfg["fps"]), v or "balanced")
        return language.tr("About {kbps} Kbps. Higher is sharper in fast motion and makes bigger files", kbps=f"{kbps:,}")

    def _codec_text(self, v) -> str:
        if self.encoder is None:
            return "Checking your graphics card…"
        best = obs_client.codec_of(self.encoder).upper().replace("H264", "H.264")
        used = obs_client.codec_of(obs_client.choose_encoder(self.encoder, v)).upper().replace("H264", "H.264")
        if v == "auto":
            return language.tr("{codec}, the best your graphics card can record. Shared copies are always H.264", codec=best)
        if used != (v or "").upper().replace("H264", "H.264"):
            return language.tr("Your graphics card can't record this, so {codec} is used", codec=used)
        return "H.264 plays everywhere; AV1 and HEVC make smaller files" if v == "h264" else \
            "Smaller files than H.264 at the same quality. Shared copies are always H.264"

    def _screen_text(self, v) -> str:
        if v == "follow":
            return "Records the monitor or TV the game is on"
        if windows.chosen_screen(v) is None:
            return "Not connected now, so the game's screen is recorded"
        return "Always records this screen, wherever the game is"

    def _mic_text(self, v) -> str:
        if self.mics == "checking":
            return "Asking OBS which microphones it can use…"
        if self.mics == "offline":
            return "OBS isn't running, so its microphones can't be listed"
        if self.mics is None:
            return "OBS has no microphone yet · add one in OBS under Settings → Audio"
        if v == "default":
            return "The microphone Windows uses. Your voice goes on its own track"
        if v not in dict(self.mics[1]):
            return "Not connected now"
        return "Your voice is recorded from this microphone"

    def _fill_screens(self, current: str):
        """Follow the game, then every screen connected now (and the saved one, if it isn't)."""
        choices = [("follow", language.tr("Follow the game"))]
        choices += [(windows.screen_id(s), windows.screen_label(s)) for s in QtGui.QGuiApplication.screens()]
        if current not in dict(choices):
            choices.append((current, language.tr("A screen that isn't connected")))
        self.screen_row.choices = choices

    def _fill_mics(self, current: str):
        choices = [("default", language.tr("Same as Windows"))]
        if isinstance(self.mics, tuple):
            choices += list(self.mics[1])
        if current not in dict(choices):
            choices.append((current, language.tr("Checking…") if self.mics == "checking" else
                            language.tr("Picked before") if self.mics == "offline" else
                            language.tr("A microphone that isn't connected")))
        self.mic_row.choices = choices

    def _on_mics(self, found):
        dirty = "mic_device" in self.changes()
        self.mics = found
        value = self.mic_row.value if dirty else self._saved()["mic_device"]
        self._fill_mics(value)
        self.mic_row.set_value(value)
        self._refresh()

    def _saved(self) -> dict:
        """The settings as they are now, in the rows' terms."""
        cfg = dict(self.ctl.cfg)
        if runtime.IS_WINDOWS:
            cfg["start_with_windows"] = windows.starts_with_windows()
        if cfg.get("capture_screen") == "main":
            cfg["capture_screen"] = windows.screen_id(QtGui.QGuiApplication.primaryScreen())
        if isinstance(self.mics, tuple) and not preferences.load_state().get("mic_picked"):
            cfg["mic_device"] = self.mics[0]    # never picked here: show the one OBS records now
        return cfg

    def _buffer_text(self, v) -> str:
        mb = obs_client.buffer_memory_mb(dict(self._plan_cfg(), buffer_minutes=v or 30), *self.screen_px,
                              obs_client.choose_encoder(self.encoder or "nvenc_av1", self._plan_cfg()["video_codec"]))
        return language.tr("The longest clip you can save. Takes up to {gb} GB on the drive, not RAM", gb=f"{mb / 1024:.1f}")

    def values(self) -> dict:
        return {r.key: r.value for r in self.rows if not r.key.startswith("_")}

    # ---- updates: looked for at start and every hour, installed only when the player says so
    def check_quietly(self):
        """The background look for a new version: it only says so, never installs."""
        def run():
            try:
                rel = updates.latest_release()
            except Exception:
                runtime.log.info("background update check failed (offline?)")
                return
            if updates.version_tuple(rel["version"]) > updates.version_tuple(version.APP_VERSION):
                runtime.safe_emit(self.update_found, rel)
        threading.Thread(target=run, daemon=True).start()

    def _on_update_found(self, rel: dict):
        if self.update["state"] in ("idle", "latest", "error"):   # Settings shows it too, ready for Enter
            self.update = dict(rel, state="available")
            if self.isVisible():       # the rows have no values before Settings is first opened
                self._refresh()

    def show_update(self):
        """Opened from the update notice: Settings on the Updates line, Enter installs."""
        self.open(self.ctl.screen_px, fresh=True)
        self.update_row.setFocus()

    def _update_value(self) -> str:
        u, state = self.update, self.update["state"]
        if state == "checking":
            return language.tr("Checking…")
        if state == "available":
            return language.tr("Version {version} is available", version=u["version"])
        if state in ("downloading", "ready"):
            return language.tr("Downloading… {pct}%", pct=u.get("pct", 99))
        if state == "latest":
            return language.tr("Up to date")
        return language.tr("Version {version}", version=version.APP_VERSION)

    def _update_describe(self) -> str:
        state = self.update["state"]
        if state == "available":
            return (language.tr("Press Enter to download and install it. Your settings and captures stay") if runtime.FROZEN
                    else language.tr("Press Enter to open the download page"))
        if state == "latest":
            return language.tr("You have the newest version, {version}", version=version.APP_VERSION)
        if state == "error":
            return language.tr("Update failed · nothing was installed. Press Enter to try again")
        if state in ("downloading", "ready"):
            return language.tr("Capture Menu closes and installs it when the download finishes")
        if state == "checking":
            return ""
        return language.tr("Press Enter to look for a new version. Nothing is installed unless you say so")

    def check_or_install(self):
        state = self.update["state"]
        if state in ("checking", "downloading", "ready"):
            return
        if state == "available":
            self._install_update()
            return
        self.update = {"state": "checking"}
        self._refresh()

        def run():
            try:
                rel = updates.latest_release()
                newer = updates.version_tuple(rel["version"]) > updates.version_tuple(version.APP_VERSION)
                runtime.safe_emit(self.update_event, dict(rel, state="available" if newer else "latest"))
            except Exception:
                runtime.log.exception("update check failed")
                runtime.safe_emit(self.update_event, {"state": "error"})
        threading.Thread(target=run, daemon=True).start()

    def _install_update(self):
        rel = dict(self.update)
        if not runtime.FROZEN or not rel.get("url"):   # the Python version updates from the zip on GitHub
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(rel.get("page") or f"https://github.com/{version.REPO}/releases/latest"))
            return
        self.update = dict(rel, state="downloading", pct=0)
        self._refresh()
        def run():
            update_dir = None
            try:
                updates.update_sha256(rel["size"], rel.get("digest"))
                update_dir = Path(tempfile.mkdtemp(prefix="CaptureMenu-update-"))
                out = update_dir / "CaptureMenu-Setup.exe"
                updates.download_update(rel["url"], rel["size"], out,
                                lambda pct: runtime.safe_emit(self.update_event, dict(rel, state="downloading", pct=pct)),
                                digest=rel["digest"])
                runtime.safe_emit(self.update_event, dict(rel, state="ready", file=str(out)))
            except Exception:
                runtime.log.exception("update download failed")
                if update_dir is not None:
                    shutil.rmtree(update_dir, ignore_errors=True)
                runtime.safe_emit(self.update_event, {"state": "error"})
        threading.Thread(target=run, daemon=True).start()

    def _on_update_event(self, info: dict):
        self.update = info
        self._refresh()
        if info["state"] == "ready":
            runtime.log.info("installing version %s from %s", info.get("version"), info["file"])
            try:
                self.install(Path(info["file"]), size=info["size"], digest=info["digest"])
            except Exception:
                runtime.log.exception("update verification or installer launch failed")
                failed = Path(info["file"])
                try:
                    failed.unlink(missing_ok=True)
                    failed.parent.rmdir()
                except OSError:
                    runtime.log.exception("could not remove failed update")
                self.update = {"state": "error"}
                self._refresh()

    def _refresh(self):
        for r in self.rows:
            r.update()
        cfg = self._plan_cfg()
        enc = obs_client.choose_encoder(self.encoder or "nvenc_av1", cfg["video_codec"])
        w, h = obs_client.output_size(*self.screen_px, cfg["resolution"])
        mb = obs_client.buffer_memory_mb(cfg, *self.screen_px, enc)
        self.memory.setText(language.tr("Recording {w}×{h} at {fps} FPS  ·  the last minutes take up to {gb} GB on the drive",
                               w=w, h=h, fps=cfg["fps"], gb=f"{mb / 1024:.1f}"))
        dirty = self.changes()
        self.info.setText((language.tr("1 unsaved change") if len(dirty) == 1 else
                           language.tr("{n} unsaved changes", n=len(dirty))) if dirty else language.tr("Changes apply when you save"))

    def changes(self) -> dict:
        current = self._saved()
        return {k: v for k, v in self.values().items() if current.get(k) != v}

    # ---- open / close
    def open(self, screen_px: tuple[int, int] | None = None, back_to=None, fresh: bool = False):
        """fresh: opened from outside (the tray), not from another page."""
        self.back_to = back_to      # what Back returns to (None: just close)
        if screen_px:
            self.screen_px = screen_px
        w, h = self.screen_px
        self.res_row.choices = [("native", language.tr("Native  {w}×{h}", w=w, h=h))] + [
            (k, k) for k, v in obs_client.RESOLUTIONS.items() if v < h]
        cfg = self._saved()
        self._fill_screens(cfg["capture_screen"])
        self.mics = "checking"
        self._fill_mics(cfg["mic_device"])
        for r in self.rows:
            r.set_value(cfg.get(r.key, preferences.DEFAULTS.get(r.key)))

        def ask_obs():
            try:
                found = self.ctl.obs.mic_devices()
            except Exception:
                found = "offline"
            runtime.safe_emit(self.mics_ready, found)
        threading.Thread(target=ask_obs, daemon=True).start()
        if self.encoder is None:
            self.encoder = getattr(self.ctl, "best_encoder", None)
        if self.encoder is None:
            threading.Thread(target=lambda: runtime.safe_emit(self.encoder_ready, obs_client.pick_encoder(obs_client.gpu_names(), preferences.load_state().get("failed_encoders", []))),
                             daemon=True).start()
        self._refresh()
        ui_theme.dress(self)
        self.place(windows.ui_screen(fresh))
        self.show()
        ui_theme.bring_to_front(self)
        self.rows[0].setFocus()

    PANEL_W = 1000

    def place(self, screen: QtGui.QScreen):
        """A panel along the side of the screen (the right; the left in Arabic), above the taskbar: the
        rest of the screen stays visible and usable, the game or desktop keeps running beside it."""
        g = screen.availableGeometry()
        w = min(self.PANEL_W, g.width())
        self.setGeometry(g.left() if language.is_rtl() else g.right() - w + 1, g.top(), w, g.height())

    def _on_encoder(self, enc: str):
        self.encoder = enc
        self._refresh()

    def go_back(self):
        """Leaves without saving, back to wherever Settings was opened from."""
        back, self.back_to = getattr(self, "back_to", None), None
        self.close_settings()
        if back:
            back()

    def close_settings(self):
        self.hide()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), ui_theme.sheet_color(self))
        p.setPen(QtGui.QColor(255, 255, 255, 26))      # the panel's edge toward the rest of the screen
        x = self.width() - 1 if language.is_rtl() else 0
        p.drawLine(x, 0, x, self.height())

    # ---- actions
    def restore_defaults(self):
        for r in self.rows:
            if r.key in preferences.DEFAULTS:
                r.set_value(preferences.DEFAULTS[r.key])
        self._refresh()

    def save(self):
        changes = self.changes()
        if not changes:
            self.close_settings()
            return
        preferences.save_config(changes)
        if "start_with_windows" in changes:
            windows.set_start_with_windows(bool(changes["start_with_windows"]))
        if "mic_device" in changes:      # from now on the microphone is picked here (see apply_mic)
            state = preferences.load_state()
            state["mic_picked"] = True
            preferences.save_state(state)
        self.ctl.cfg.update(changes)
        runtime.log.info("settings saved: %s", ", ".join(changes))
        self.hide()
        self.restart()

    def _listen_hotkey(self, row: ui_widgets.SettingRow):
        row.listening = True
        row.update()

    def _pick_folder(self, row: ui_widgets.SettingRow):
        clips = self.values().get("clips_dir")
        path = QtWidgets.QFileDialog.getExistingDirectory(self, row.label, str(row.value or clips or ""))
        if path:
            path = str(Path(path))
            # screenshots in the clips folder are the default, stored as "not set"
            row.set_value("" if row.key == "screenshots_dir" and path == clips else path, emit=True)
        ui_theme.bring_to_front(self)
        row.setFocus()

    def update_hints(self):
        pad = input_devices.input_mode().mode != "keyboard"
        self.hints.set_items(
            [("DPAD_UD", "Move"), ("DPAD_LR", "Change"), ("A", "Select"), ("Y", "Save"),
             ("X", "Defaults"), ("B", "Back")] if pad
            else [("k:↑ ↓", "Move"), ("k:← →", "Change"), ("k:Enter", "Select"), ("k:S", "Save"),
                  ("k:Esc", "Back")], input_devices.input_mode().mode)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress and obj in self._head():
            self.keyPressEvent(event)        # a focused button would eat the arrows itself
            return True
        return super().eventFilter(obj, event)

    def _head(self) -> list[QtWidgets.QWidget]:
        return [self.back_btn, self.defaults_btn, self.cancel_btn, self.save_btn]

    def keyPressEvent(self, e):
        row = self.focusWidget() if isinstance(self.focusWidget(), ui_widgets.SettingRow) else None
        k = e.key()
        if self.focusWidget() in self._head():   # the highlight is on the buttons along the top
            button = self.focusWidget()
            if k in (Qt.Key_Left, Qt.Key_Right):
                nxt = ui_theme.toward(button, [b for b in self._head() if b.isVisible()], k)
                if nxt is not None:
                    nxt.setFocus()
            elif k == Qt.Key_Down:
                back = getattr(self, "_row_before_head", None)
                (back if back in self.rows else self.rows[0]).setFocus()
            elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                button.click()
            elif k == Qt.Key_S:
                self.save()
            elif k == Qt.Key_R:
                self.restore_defaults()
            elif k == Qt.Key_Escape:
                self.go_back()
            return
        if k == Qt.Key_Up and row is not None and self.rows and row is self.rows[0]:   # up to the buttons
            self._row_before_head = row
            self.scroll.ensureWidgetVisible(row, 0, 40)   # so the buttons are above it on screen
            # Back first, as it always was; the narrow panel would otherwise land on the nearest button
            nxt = self.back_btn if self.back_btn.isVisible() else ui_theme.toward(row, [b for b in self._head() if b.isVisible()], k)
            if nxt is not None:
                nxt.setFocus()
            return
        if row is not None and row.listening:
            if k == Qt.Key_Escape:
                row.listening = False
                row.update()
                return
            spec = input_devices.hotkey_from_event(e)
            if spec:
                row.listening = False
                row.set_value(spec, emit=True)
            return
        if k in (Qt.Key_Up, Qt.Key_Down):
            i = self.rows.index(row) if row in self.rows else -1
            j = max(0, min(len(self.rows) - 1, i + (1 if k == Qt.Key_Down else -1)))
            self.rows[j].setFocus()
        elif k in (Qt.Key_Left, Qt.Key_Right) and row is not None:
            row.step(1 if k == Qt.Key_Right else -1)
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and row is not None:
            row.activate()
        elif k == Qt.Key_S:
            self.save()
        elif k == Qt.Key_R:
            self.restore_defaults()
        elif k == Qt.Key_Escape:
            self.go_back()
        else:
            super().keyPressEvent(e)


class Welcome(Settings):
    """The first start: the choices worth making before anything is recorded, each saying it can be
    changed later in Settings. The language comes first, so the rest are read in it. Same page and
    rows as Settings; Start saves them and setup goes on, OBS set up with them. Choices the app only
    reads as it starts (keys, controller button, double press, folder) restart it once on Start.
    Which screen and HDR are only asked when there's a choice (two screens, Windows HDR on)."""

    LATER = "You can change it later in Settings."
    READ_AT_START = ("hotkey", "controller_button", "double_press_seconds", "clips_dir")

    def __init__(self, ctl: capture_controller.Controller, done):
        self.done = done
        super().__init__(ctl)
        self.setProperty("captureMenuPage", "welcome")
        self.title.setText(language.tr("Welcome to Capture Menu"))
        self.save_btn.setText(language.tr("Start"))
        for b in (self.back_btn, self.defaults_btn, self.cancel_btn):
            b.hide()

    def _later(self, text: str) -> str:
        first = language.tr(text).rstrip()
        if not first.endswith((".", "?", "؟", "!")):
            first += "."      # Settings' own descriptions have no full stop
        return f"{first} {language.tr(self.LATER)}"

    def _build_rows(self):
        self._section("GENERAL")
        lang = self._row("language", "Which language?", "choice",
                         [("auto", "Same as Windows"), *language.LANGUAGES.items()],
                         lambda v: self._later("The page switches to it right away."))
        lang.changed.connect(self._switch_language)
        self._row("start_with_windows", "Start with Windows?", "bool",
                  describe=lambda v: self._later("Capture Menu and OBS start when you sign in" if v else
                                                 "Start it yourself from the Start menu"))

        self._section("RECORDING")
        self._row("buffer_minutes", "How much should it keep?", "choice",
                  [(m, language.tr("The last {n} min", n=m)) for m in (5, 10, 15, 30, 60)],
                  lambda v: self._later(language.tr("Takes up to {gb} GB on the drive, not RAM.", gb=f"{self._buffer_gb(v):.1f}")))
        self._row("double_press_seconds", "What should a double press save?", "choice",
                  [(0, "Off"), (15, "15 sec"), (30, "30 sec"), (60, "1 min"), (120, "2 min")],
                  lambda v: self._later("Press twice quickly to save without opening the menu" if v else
                                        "Double-pressing does nothing extra"),
                  custom=lambda v: language.tr("{n} sec", n=v))
        self._row("quality", "What quality?", "choice",
                  [("light", "Light"), ("balanced", "Balanced"), ("high", "High"), ("max", "Max")],
                  lambda v: self._later("Higher is sharper and makes bigger files."))
        self.res_row = self._row("resolution", "What resolution should it record?", "choice", [("native", "Native")],
                                 lambda v: self._later("Lower uses less space."))
        self._row("fps", "How many frames per second?", "choice", [(30, "30 FPS"), (60, "60 FPS"), (120, "120 FPS")],
                  lambda v: self._later("60 suits every game; 120 is for fast shooters."))
        if windows.windows_hdr():
            self._row("hdr", "Record in HDR?", "choice", [("auto", "Auto"), ("off", "Off")],
                      lambda v: self._later("HDR clips while Windows HDR is on." if v == "auto" else
                                            "Always normal colours (SDR)"))
        if len(QtGui.QGuiApplication.screens()) > 1:
            self.screen_row = self._row("capture_screen", "Which screen should it record?", "choice",
                                        [("follow", "Follow the game")], lambda v: self._later(self._screen_text(v)))

        self._section("DEVICES")
        self._row("mic_on", "Record your microphone?", "bool",
                  describe=lambda v: self._later("Your voice goes into your clips." if v else
                                                 "Clips have the game's sound only."))

        self._section("CONTROLS")
        hk = self._row("hotkey", "Which keys open the menu?", "action",
                       describe=lambda v: self._later("Press Enter, then the new keys."))
        hk.on_activate = self._listen_hotkey
        self._row("controller_button", "Which controller button opens it?", "choice",
                  [("create", "Create / View"), ("ps", "PS / Xbox button"), ("touchpad", "Touchpad"),
                   ("mute", "Mute / Share"), ("l3+r3", "L3 + R3")],
                  lambda v: self._later("Like Create on the PS5."))

        self._section("LIBRARY")
        folder = self._row("clips_dir", "Where should your clips go?", "action",
                           describe=lambda v: self._later("A folder per game. 30 minutes can take a few GB."))
        folder.on_activate = self._pick_folder
        self.rows_layout.addStretch()

    def _switch_language(self, *_):
        """The language is the first question, so the rest are read in it: a different language
        restarts the app straight back here (these questions are only done once Start is pressed)."""
        choice = next(r.value for r in self.rows if r.key == "language")
        wanted = language.system_language() if choice not in language.LANGUAGES else choice
        if wanted == language.LANG:
            return
        preferences.save_config({"language": choice})
        runtime.log.info("first start: language %s", choice)
        self.hide()
        self.restart()

    def _buffer_gb(self, minutes) -> float:
        return obs_client.buffer_memory_mb(dict(self._plan_cfg(), buffer_minutes=minutes or 30), *self.screen_px,
                                           obs_client.choose_encoder(self.encoder or "nvenc_av1", "auto")) / 1024

    def _refresh(self):
        super()._refresh()
        self.info.setText(language.tr("A few quick choices before it starts recording"))

    def open(self, screen_px: tuple[int, int] | None = None):
        if screen_px:
            self.screen_px = screen_px
        w, h = self.screen_px
        self.res_row.choices = [("native", language.tr("Native  {w}×{h}", w=w, h=h))] + [
            (k, k) for k, v in obs_client.RESOLUTIONS.items() if v < h]
        cfg = self._saved()
        if hasattr(self, "screen_row"):
            self._fill_screens(cfg["capture_screen"])
        for r in self.rows:
            r.set_value(cfg.get(r.key, preferences.DEFAULTS.get(r.key)))
        if self.encoder is None:     # the quality line's bitrate follows the graphics card, found in the background
            threading.Thread(target=lambda: runtime.safe_emit(self.encoder_ready, obs_client.pick_encoder(
                obs_client.gpu_names(), preferences.load_state().get("failed_encoders", []))), daemon=True).start()
        self._refresh()
        ui_theme.dress(self)
        self.place(windows.ui_screen(True))
        self.show()
        ui_theme.bring_to_front(self)
        self.rows[0].setFocus()

    def save(self):
        chosen = self.values()
        before = self._saved()
        preferences.save_config({k: v for k, v in chosen.items() if k != "start_with_windows"})
        if runtime.IS_WINDOWS and chosen.get("start_with_windows") != before.get("start_with_windows"):
            windows.set_start_with_windows(bool(chosen["start_with_windows"]))
        self.ctl.cfg.update(chosen)
        preferences.save_state(preferences.load_state() | {"welcomed": True})
        runtime.log.info("first start: %s", ", ".join(f"{k}={v}" for k, v in chosen.items()))
        self.hide()
        if any(chosen.get(k) != before.get(k) for k in self.READ_AT_START):
            self.restart()     # comes back already welcomed, with the new keys, button and folder
        else:
            self.done()

    def go_back(self):
        self.save()        # Esc / B: start with what's picked (the recommended choices if nothing changed)

    def update_hints(self):
        pad = input_devices.input_mode().mode != "keyboard"
        self.hints.set_items(
            [("DPAD_UD", "Move"), ("DPAD_LR", "Change"), ("A", "Select"), ("Y", "Start")] if pad
            else [("k:↑ ↓", "Move"), ("k:← →", "Change"), ("k:Enter", "Select"), ("k:S", "Start")],
            input_devices.input_mode().mode)

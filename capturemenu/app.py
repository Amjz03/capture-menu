"""Application startup, signal wiring and lifecycle."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from pathlib import Path
import sys
import threading
import time

from . import (
    capture_controller,
    catalog,
    diagnostics,
    input_devices,
    language,
    obs_client,
    preferences,
    runtime,
    ui_gallery,
    ui_menu,
    ui_notices,
    ui_settings,
    ui_theme,
    ui_viewer,
    windows,
)


def main():
    runtime.configure_logging()
    diagnostics.install_crash_log()
    runtime.log.info("starting: %s %s", sys.executable, " ".join(sys.argv))
    cfg = preferences.load_config()
    language.set_language(cfg.get("language", "auto"))
    app = QtWidgets.QApplication(sys.argv)
    if language.is_rtl():
        app.setLayoutDirection(Qt.RightToLeft)   # Arabic: the whole interface mirrors, like the PS5 does
    app.setQuitOnLastWindowClosed(False)
    app._freeze_watch = diagnostics.watch_for_freezes(app)
    app.setWindowIcon(ui_theme.tray_icon())
    restarted = "--restarted" in sys.argv

    # one copy at a time: starting it again (or Windows starting it twice) quietly does nothing
    lock = QtCore.QLockFile(str(Path(QtCore.QDir.tempPath()) / "capture-menu.lock"))
    lock.setStaleLockTime(0)   # never by age; a lock left by a crashed copy is still taken over
    if not lock.tryLock(8000 if restarted else 0):   # after Save, wait for the old copy to quit
        runtime.log.info("already running, exiting")
        return
    app.aboutToQuit.connect(lock.unlock)
    def tasks():          # schtasks takes a moment
        windows.update_start_with_windows()
        windows.set_watch_task()
    threading.Thread(target=tasks, daemon=True).start()
    problems: list[str] = []

    ctl = capture_controller.Controller(cfg)
    # Where captures went instead, said once and calmly: it all works, there's nothing to do.
    # (Windows Security's settings stay the user's: we don't ask anyone to change them.)
    moved_notice = None
    if ctl.blocked and preferences.load_state().get("fallback_told") != str(ctl.blocked):
        moved_notice = (language.tr("Your captures are saved in {fallback} · Windows Security protects {folder}",
                           fallback=ctl.clips_dir, folder=ctl.blocked.parent)
                        if catalog.controlled_folder_access_on() else
                        language.tr("Your captures are saved in {fallback} · {folder} can't be used",
                           fallback=ctl.clips_dir, folder=ctl.blocked))
    viewer = ui_viewer.Viewer(ctl)
    menu = ui_menu.Menu(ctl, viewer)
    gallery = ui_gallery.Gallery(ctl, viewer)
    menu.gallery = gallery
    settings = ui_settings.Settings(ctl)
    menu.settings = settings
    toast = ui_notices.Toast()
    toast.thumbs_dir = ctl.thumbs_dir
    rec_dot = ui_notices.RecIndicator(cfg.get("record_indicator", "top-left"))
    ctl.recording.connect(rec_dot.set_recording)
    ctl.status.connect(rec_dot.sync)
    toast.hotkey = cfg["hotkey"].upper()
    toast.pad_button = cfg["controller_button"]
    app.installEventFilter(input_devices.input_mode())   # any real key press switches the hints back to the keyboard
    ctl.toast.connect(toast.show_message)
    ctl.captured.connect(toast.show_capture)
    ctl.captured.connect(lambda *_: menu.refresh_recent())
    ctl.shared.connect(toast.show_shared)

    toast.open_capture.connect(menu.view_capture)
    ctl.storage.connect(menu.show_storage)
    ctl.library_changed.connect(menu.refresh_recent)

    def to_clipboard(path: str):
        # a file on the clipboard, like Ctrl+C in Explorer: paste into Discord, WhatsApp, a chat
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(path)])
        QtGui.QGuiApplication.clipboard().setMimeData(mime)
    ctl.copy_file.connect(to_clipboard)

    tray = QtWidgets.QSystemTrayIcon(ui_theme.tray_icon())
    tray.setToolTip(language.tr("Capture Menu is running · {keys} to open", keys=cfg["hotkey"].upper()))
    tm = QtWidgets.QMenu()
    tm.addAction(language.tr("Open menu"), lambda: menu.show_menu())
    tm.addAction(language.tr("Open gallery"), lambda: gallery.open(fresh=True))
    tm.addAction(language.tr("Open clips folder"), ctl.open_folder)
    tm.addAction(language.tr("Settings"), lambda: settings.open(ctl.screen_px, fresh=True))

    def check_updates():
        settings.open(ctl.screen_px, fresh=True)
        settings.update_row.setFocus()
        settings.check_or_install()
    tm.addAction(language.tr("Check for updates"), check_updates)
    tm.addSeparator()
    def quit_app():
        try:
            stopped = ctl.obs.stop_buffer()    # nothing would delete the old minutes OBS goes on recording
        except obs_client.ObsOffline:
            stopped = True                     # OBS is closed: it records nothing
        except Exception:
            runtime.log.exception("couldn't stop OBS's recording")
            stopped = False
        if not stopped and QtWidgets.QMessageBox.warning(
                None, "Capture Menu",
                language.tr("OBS is still recording the last minutes, and nothing deletes the old ones while "
                            "Capture Menu is closed. Quit anyway?"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
            return                             # keep running: it goes on looking after the files
        runtime.ALIVE.unlink(missing_ok=True)     # closed on purpose: the watch task leaves it closed
        app.quit()
    tm.addAction(language.tr("Quit"), quit_app)
    tray.setContextMenu(tm)
    tray.activated.connect(lambda r: menu.show_menu()
                           if r == QtWidgets.QSystemTrayIcon.Trigger else None)
    tray.show()
    for delay in (3000, 30000):   # Windows registers the icon a moment after it first shows
        QtCore.QTimer.singleShot(delay, windows.promote_tray_icon)

    def open_or_close(game: str):
        if settings.isVisible():
            settings.close_settings()
        elif viewer.isVisible():
            viewer.close_viewer()
        elif gallery.isVisible():
            gallery.close_gallery()
        elif menu.isVisible():
            menu.hide_menu()
        else:
            menu.show_menu(game)

    quick = int(cfg.get("double_press_seconds") or 0)
    # with "A hold" each press only counts once held, so the second one comes that much later
    presses = input_devices.PressSequencer(
        350 + int(cfg.get("controller_hold_ms") or 0) if quick else 0, open_or_close,
        lambda game: ctl.save_clip(quick, game),
        lambda: menu.isVisible() or viewer.isVisible() or gallery.isVisible() or settings.isVisible())

    sounds = input_devices.Sounds(bool(cfg.get("sounds", True)))
    ctl.captured.connect(lambda _d, path: sounds.play("shutter" if path.endswith(".png") else "capture"))
    ctl.recording.connect(lambda on: sounds.play("record") if on else None)

    def pad_press(button: int):
        welcome = next((p for p in pages if isinstance(p, ui_settings.Welcome) and p.isVisible()), None)
        page = welcome or settings     # the first-start questions take the pad like Settings does
        key = input_devices.pad_key(button, menu, viewer, gallery, page)
        if key is not None:
            input_devices.send_key(page if page.isVisible() else viewer if viewer.isVisible()
                     else gallery if gallery.isVisible() else menu, key)

    try:
        gamepad = input_devices.Gamepad(cfg)
        gamepad.activated.connect(lambda: presses.press(windows.foreground_app(cfg)))
        if cfg.get("rumble", True):
            # buzz the controller only when it's what the player is using
            ctl.captured.connect(lambda *_: gamepad.rumble("capture") if input_devices.input_mode().mode != "keyboard" else None)
            ctl.recording.connect(lambda on: gamepad.rumble("record") if on and input_devices.input_mode().mode != "keyboard"
                                  else None)
        gamepad.pressed.connect(pad_press)
        gamepad.used.connect(input_devices.input_mode().set)
        gamepad.connected.connect(lambda name, on: toast.show_message(
            language.tr("Controller connected · {name}", name=name) if on else
            language.tr("Controller disconnected · {name}", name=name), "ok" if on else "info"))
        gamepad.start()
    except ValueError as e:
        problems.append(language.tr("{problem} · pick another controller button in Settings", problem=e))

    hotkey = input_devices.Hotkey(cfg["hotkey"], lambda: windows.foreground_app(cfg))
    hotkey.pressed.connect(presses.press)
    registered = hotkey.start()
    for _ in range(20 if restarted and runtime.IS_WINDOWS else 0):   # the old copy may still be letting go
        if registered:
            break
        time.sleep(0.25)
        registered = hotkey.start()
    if runtime.IS_WINDOWS and not registered:
        problems.append(language.tr("{keys} is taken by another app · "
                           "use the controller or the tray icon, and pick other keys in Settings",
                           keys=cfg["hotkey"].upper()))
    keys = " + ".join(k.upper() if len(k) == 1 or k[0] == "f" and k[1:].isdigit() else k.capitalize()
                      for k in cfg["hotkey"].split("+"))   # alt+c -> Alt + C
    pad_name = cfg["controller_button"].replace("+", " + ").title()
    if problems:
        toast.show_message(problems[0], "error")
    else:
        toast.show_running(language.tr("Settings saved") if restarted else language.tr("Capture Menu is running"),
                           language.tr("Press {keys} or {button} to open", keys=keys, button=pad_name))
    if moved_notice:
        def tell_moved():
            toast.show_message(moved_notice, "info")
            preferences.update_state(lambda s: s.update(fallback_told=str(ctl.blocked)))
        QtCore.QTimer.singleShot(7000, tell_moved)   # after the notice above has been read
    told = set()      # each new version is announced once while the app runs; a click opens Settings on it
    def update_found(rel: dict):
        if rel["version"] not in told:
            told.add(rel["version"])
            toast.show_update(rel["version"], settings.show_update)
            menu.set_update(rel["version"])
            tray.setToolTip(language.tr("Update available · {version}", version=rel["version"]))
            tm.insertAction(tm.actions()[0], QtGui.QAction(language.tr("Install update {version}", version=rel["version"]),
                                                           tm, triggered=settings.show_update))
    settings.update_found.connect(update_found)
    # a check from Settings finds it too: the menu says so from then on (the notice isn't needed there)
    settings.update_event.connect(lambda info: menu.set_update(info["version"]) if info["state"] == "available" else None)
    QtCore.QTimer.singleShot(60_000, settings.check_quietly)     # well after the start-up notices
    QtCore.QTimer(app, interval=3600_000, timeout=settings.check_quietly).start()   # hourly: one small request
    # once everything has been closed for a while, give memory back (once per idle stretch): a page
    # that has been open since holds a native window again, so even a quick look counts
    pages = (menu, viewer, gallery, settings)

    def idle_check():
        if any(w.isVisible() for w in pages) or not any(w.testAttribute(Qt.WA_WState_Created) for w in pages):
            return
        for w in (menu, gallery, settings):
            ui_theme.release_window(w)
        if viewer.player is None:    # otherwise the viewer lets its window go with the player
            ui_theme.release_window(viewer)
        ui_theme.trim_memory()
    QtCore.QTimer(app, interval=90_000, timeout=idle_check).start()

    primary = app.primaryScreen()
    native = primary.size() * primary.devicePixelRatio()

    def begin():
        ctl.startup((native.width(), native.height()))
        ctl.start_following()
    state = preferences.load_state()
    if state.get("welcomed") or state.get("obs_setup"):   # set up before: no questions
        begin()
    else:   # the first start: a few choices first, so OBS is set up with them
        welcome = ui_settings.Welcome(ctl, begin)
        pages += (welcome,)
        welcome.open((native.width(), native.height()))
    sys.exit(app.exec())

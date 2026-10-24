# With two screens, every page opened from the bar (Settings, the gallery, the viewer) and Back stay on
# the screen the bar opened on, even when another screen's window comes to the front in between.
# Opening the app again from outside picks the game's screen again. Two fake screens; no OBS.
# Usage: test_one_screen.py REPO
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
work = Path(tempfile.mkdtemp())
(work / "screens.json").write_text(json.dumps({"screens": [
    {"name": "MONITOR", "x": 0, "y": 0, "width": 2560, "height": 1440, "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},
    {"name": "TV", "x": 2560, "y": 0, "width": 1920, "height": 1080, "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}))
os.chdir(work)   # a relative path: the ":" in "C:" would split the platform setting
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=screens.json"
from capturemenu import (
    capture_controller,
    preferences,
    ui_gallery,
    ui_menu,
    ui_notices,
    ui_settings,
    ui_viewer,
    windows,
)
from PySide6 import QtGui, QtWidgets
app = QtWidgets.QApplication([])
screens = {s.name(): s for s in QtGui.QGuiApplication.screens()}
assert set(screens) == {"MONITOR", "TV"}, list(screens)

preferences.STATE_PATH = work / "state.json"
shot = work / "Clips" / "Elden Ring" / "Screenshot_2026-10-16_21-00-00.png"
shot.parent.mkdir(parents=True)
QtGui.QImage(64, 36, QtGui.QImage.Format_RGB32).save(str(shot))
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(work / "Clips"))); ctl.refresh_status = lambda: None
viewer = ui_viewer.Viewer(ctl); menu = ui_menu.Menu(ctl, viewer)
gallery = ui_gallery.Gallery(ctl, viewer); settings = ui_settings.Settings(ctl)
menu.gallery, menu.settings = gallery, settings


def in_front(name):   # the window in front is on this screen (not ours)
    g = screens[name].geometry()
    windows.foreground_screen = lambda: {"device": name, "rect": (g.left(), g.top(), g.right() + 1, g.bottom() + 1),
                                    "fullscreen": True, "own": False}


def on(w):
    return QtGui.QGuiApplication.screenAt(w.geometry().center()).name()


def pump():
    for _ in range(5): app.processEvents()


in_front("TV")
menu.show_menu("Elden Ring"); pump()
assert on(menu) == "TV", on(menu)
in_front("MONITOR")          # once the bar hides, a window on the other screen is in front

menu.open_settings(); pump()
assert settings.isVisible() and on(settings) == "TV", on(settings)
settings.go_back(); pump()
assert menu.isVisible() and on(menu) == "TV", on(menu)
print("settings and back stay on the bar's screen PASS")

menu.open_gallery(); pump()
assert gallery.isVisible() and on(gallery) == "TV", on(gallery)
gallery.go_back(); pump()
assert on(menu) == "TV"
print("gallery and back stay on the bar's screen PASS")

menu._view(0); pump()
assert viewer.isVisible() and on(viewer) == "TV", on(viewer)
toast = ui_notices.Toast(); toast.show_message("Trimmed clip saved", "ok"); pump()
assert on(toast) == "TV", on(toast)        # a notice shows beside the page in use
viewer.go_back(); pump()
assert on(menu) == "TV"
print("viewer, its notices and back stay on the bar's screen PASS")

menu.hide_menu(); toast.hide(); pump()
menu.toggle("Elden Ring"); pump()          # opened again from outside: the game is on the monitor now
assert on(menu) == "MONITOR", on(menu)
menu.hide_menu(); in_front("TV")
settings.open(ctl.screen_px, fresh=True); pump()   # the tray's Settings
assert on(settings) == "TV", on(settings)
settings.close_settings()
print("opening from outside picks the game's screen again PASS")

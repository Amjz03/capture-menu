"""Application paths, explicit logging setup and lazy Qt multimedia loading."""
from __future__ import annotations

from pathlib import Path
import logging
import os
import sys
import time


# Qt Multimedia (video player + its FFmpeg backend, ~25 MB) loads the first time a video
# is opened, not at startup: most of the time the app just waits for the hotkey.
QtMultimedia = QtMultimediaWidgets = None


def load_multimedia() -> bool:
    global QtMultimedia, QtMultimediaWidgets
    if QtMultimedia is None:
        try:
            from PySide6 import QtMultimedia as mm, QtMultimediaWidgets as mmw
        except ImportError:  # viewer falls back to the default video player
            return False
        QtMultimedia, QtMultimediaWidgets = mm, mmw
    return True


FROZEN = getattr(sys, "frozen", False)          # running as a built .exe


APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]


BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))


IS_WINDOWS = sys.platform == "win32"


def configure_logging():
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
    logging.basicConfig(
        filename=APP_DIR / "capture_menu.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


# Library verbosity is set only when the app starts.


log = logging.getLogger("capture_menu")


def safe_emit(signal, *args):
    """Emit from a worker thread; quietly skip if the window is already gone (app quitting)."""
    try:
        signal.emit(*args)
    except (RuntimeError, TypeError):   # PySide raises either when the signal's owner was deleted
        pass


ASSETS = BUNDLE_DIR / "assets"


# While Capture Menu runs, OBS records the last minutes and only Capture Menu deletes the old ones,
# so it must not stay closed after a crash (or being ended in Task Manager). It touches ALIVE every
# minute and deletes it on Quit; a scheduled task starts it with --watch every few minutes, and that
# copy goes on only when ALIVE says Capture Menu was running in this Windows session and went silent.
ALIVE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CaptureMenu" / "alive"
SILENT = 150          # seconds without a touch: closed without Quit


def touch_alive():
    try:
        ALIVE.parent.mkdir(parents=True, exist_ok=True)
        ALIVE.touch()
    except OSError:
        pass


def came_back_needed(now: float | None = None, boot: float | None = None) -> bool:
    """--watch: start Capture Menu again? Not after Quit (no ALIVE), not while it runs (touched
    lately), not after a restart of Windows (touched before it: starting with Windows decides)."""
    try:
        seen = ALIVE.stat().st_mtime
    except OSError:
        return False
    now = time.time() if now is None else now
    if boot is None:
        import ctypes
        tick = ctypes.windll.kernel32.GetTickCount64
        tick.restype = ctypes.c_uint64
        boot = now - tick() / 1000
    return boot < seen < now - SILENT


def leave_if_not_needed():
    """Started with --watch: quits at once unless came_back_needed (most checks end here)."""
    if "--watch" in sys.argv:
        if not came_back_needed():
            sys.exit(0)
        sys.argv.remove("--watch")

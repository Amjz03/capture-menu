"""Application paths, explicit logging setup and lazy Qt multimedia loading."""
from __future__ import annotations

from pathlib import Path
import logging
import sys


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

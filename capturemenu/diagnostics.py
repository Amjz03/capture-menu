"""Explicit crash logging and UI freeze diagnostics."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from datetime import datetime
import sys
import threading
import time

from . import runtime


def install_crash_log():
    import faulthandler
    import traceback

    def log_error(kind, value, tb):
        runtime.log.critical("unhandled error:\n%s", "".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = log_error
    threading.excepthook = lambda a: log_error(a.exc_type, a.exc_value, a.exc_traceback)
    try:
        faulthandler.enable(open(runtime.APP_DIR / "crash.log", "a", encoding="utf-8"))   # hard crashes too
    except OSError:
        pass


def watch_for_freezes(app: QtWidgets.QApplication, seconds: float = 6.0) -> QtCore.QTimer:
    """If the interface stops responding, writes where it is stuck to crash.log (once per freeze),
    so a freeze that can't be reproduced on demand can still be found."""
    import faulthandler
    beat = [time.monotonic()]
    timer = QtCore.QTimer(app, interval=500, timeout=lambda: beat.__setitem__(0, time.monotonic()))
    timer.start()

    def run():
        written = False
        while True:
            time.sleep(1)
            stale = time.monotonic() - beat[0]
            if stale > seconds and not written:
                written = True
                runtime.log.error("the interface hasn't responded for %.0f s; where it's stuck is in crash.log", stale)
                try:
                    with open(runtime.APP_DIR / "crash.log", "a", encoding="utf-8") as f:
                        f.write(f"\n--- not responding for {stale:.0f} s, {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                        faulthandler.dump_traceback(f, all_threads=True)
                except OSError:
                    pass
            elif stale < 2:
                if written:
                    runtime.log.info("the interface responds again")
                written = False
    threading.Thread(target=run, daemon=True, name="freeze-watch").start()
    return timer

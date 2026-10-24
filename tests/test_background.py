import sys, os, subprocess, time
from pathlib import Path
app_dir = Path(sys.argv[1]); py = sys.executable
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
probe = r'''
import sys, runpy
sys.argv = ["capture_menu.py"] + sys.argv[1:]
from PySide6 import QtWidgets, QtCore
orig = QtWidgets.QApplication.exec
def exec_(*a):
    def report():
        shown = [w for w in QtWidgets.QApplication.topLevelWidgets() if w.isVisible()]
        print("VISIBLE", sorted(type(w).__name__ for w in shown), flush=True)
        for w in shown:
            if type(w).__name__ == "Toast":
                print("TOAST", w.title.text(), "|", w.sub.text(), flush=True)
        print("TASKBAR", [type(w).__name__ for w in shown if not (w.windowFlags() & QtCore.Qt.Tool) == QtCore.Qt.Tool], flush=True)
    QtCore.QTimer.singleShot(1500, report)
    return orig()
QtWidgets.QApplication.exec = exec_
runpy.run_path(sys.argv[0] if False else "capture_menu.py", run_name="__main__")
'''
import tempfile
log = open(Path(tempfile.mkdtemp()) / "a.log", "w+")
a = subprocess.Popen([py, "-c", probe], cwd=app_dir, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 4)
t = time.time(); b = subprocess.run([py, "capture_menu.py"], cwd=app_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
print("second copy exited", b.returncode, "in", round(time.time() - t, 1), "s")
a.kill(); a.wait(); log.seek(0); out = log.read(); print("\n".join(l for l in out.splitlines() if l.startswith(("VISIBLE", "TOAST", "TASKBAR"))))
assert b.returncode == 0 and time.time() - t < 15
assert "VISIBLE ['Toast']" in out, out
assert "TASKBAR []" in out
# here OBS isn't installed, so its warning replaces the "running" notice
assert ("Capture Menu is running" in out and "Press Alt + C or Create to open" in out) or "OBS isn't running" in out
print("background PASS")
# the "running" notice itself
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(app_dir))
from PySide6 import QtWidgets
qa = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from capturemenu import ui_notices
t = ui_notices.Toast(); t.show_running("Capture Menu is running", "Press Alt + C or Create to open")
assert t.isVisible() and t.thumb.isVisible() and t.title.text() == "Capture Menu is running" and t.path is None
print("running notice PASS")

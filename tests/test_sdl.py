import sys, time, threading
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtCore
app = QtCore.QCoreApplication([])
g = cm.Gamepad(dict(cm.DEFAULTS)); g.start()
end = time.time() + 2
while time.time() < end: app.processEvents(); time.sleep(0.05)
alive = [t for t in threading.enumerate() if t.daemon and t.is_alive()]
print("reader thread alive:", bool(alive))
print(open(cm.APP_DIR / "capture_menu.log").read()[-400:] or "(no log entries)")

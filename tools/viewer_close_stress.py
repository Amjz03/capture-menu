"""Opens a real clip fullscreen in the viewer on every screen and closes it (Esc, like ◯ / B) at different
moments, with the controller reader running as in the app. If closing hangs for 6 s, it prints where the
main thread is stuck and stops. Needs a real display, a clip and ideally a connected controller:

    py -3 tools/viewer_close_stress.py <repo folder> <clip.mp4> [rounds]

It found the 0.0.2 freeze on close (SDL's Windows.Gaming.Input / RawInput); see Gamepad._run."""
import faulthandler, random, shutil, sys, tempfile, time
from pathlib import Path
repo, src = sys.argv[1:3]
rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 40
sys.path.insert(0, repo)
import capture_menu as cm
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
root = Path(tempfile.mkdtemp())
cm.STATE_PATH = root / "state.json"
clip = root / "Clips" / "Desktop" / Path(src).name
clip.parent.mkdir(parents=True)
shutil.copy(src, clip)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root / "Clips")))
v = cm.Viewer(ctl)
pad = cm.Gamepad(dict(cm.DEFAULTS))          # the controller reader, as in the app
pad.connected.connect(lambda name, on: print("controller", "connected" if on else "gone", name, flush=True))
pad.start()
log = open(root / "stack.txt", "w")
random.seed(7)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


for i in range(rounds):
    screens = app.screens()
    scr = screens[i % len(screens)]
    wait = 17.0 if i % 6 == 5 else random.choice([0.0, 0.2, 1.0, 2.6, 4.0])   # some reach the end
    v.open([clip])
    v.setScreen(scr)
    v.setGeometry(scr.geometry())      # fullscreen, like the app
    pump(wait)
    frames = v._frames
    faulthandler.dump_traceback_later(6, exit=True, file=sys.stdout)   # a hang prints the stack and exits
    t = time.time()
    QtWidgets.QApplication.sendEvent(v, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    took = time.time() - t
    faulthandler.cancel_dump_traceback_later()
    print(f"round {i + 1:2d}: {scr.name()} closed after {wait:.2f}s ({frames} frames) in {took:.2f}s", flush=True)
    pump(0.3)
print("no hang in", rounds, "rounds", flush=True)

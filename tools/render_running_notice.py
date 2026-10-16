import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2])
import capture_menu as cm
from PySide6 import QtWidgets, QtGui
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
W, H = 1920, 1080
canvas = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7))
t = cm.Toast(); t.show_running("Capture Menu is running", "Press Alt + C or Create to open")
for _ in range(5): app.processEvents()
p = QtGui.QPainter(canvas); p.drawPixmap(W - t.width() - 28, 28, t.grab()); p.end()
canvas.copy(W - 640, 0, 640, 200).scaled(1280, 400).save(str(out / "running_toast.png"))
print("ok")

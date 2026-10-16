import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1]); out = Path(sys.argv[2])
import capture_menu as cm
from PySide6 import QtWidgets, QtGui
app = QtWidgets.QApplication([])
sys.path.insert(0, str(Path(__file__).resolve().parent)); from scene import draw_scene, game_name
W, H = 1920, 1080
canvas = QtGui.QPixmap.fromImage(draw_scene(W, H, "dusk", 7))
r = cm.RecIndicator("top-right"); r.sync({"online": True, "recording": True, "record_ms": 754_000})
for _ in range(5): app.processEvents()
p = QtGui.QPainter(canvas); p.drawPixmap(W - r.width() - 16, 16, r.grab())
# zoomed crop so the detail is visible
p.end(); canvas.save(str(out / "rec_indicator.png"))
canvas.copy(W - 520, 0, 520, 160).scaled(1040, 320).save(str(out / "rec_indicator_zoom.png"))
print("ok")

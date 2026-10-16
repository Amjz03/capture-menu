import sys, time, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

# combos
assert cm.parse_pad_combo("create") == {4}
assert cm.parse_pad_combo("L1 + R1") == {9, 10}
try: cm.parse_pad_combo("banana"); raise SystemExit("bad name accepted")
except ValueError: pass

# PadState: edge-triggered open, no repeat while held, button excluded from presses
s = cm.PadState(frozenset({4}), 0)
assert s.step({4}, 0.0) == (True, [])
assert s.step({4}, 0.5) == (False, [])
assert s.step(set(), 0.6) == (False, [])
assert s.step({4}, 0.7)[0] is True
# hold time
h = cm.PadState(frozenset({4}), 400)
assert h.step({4}, 0.0)[0] is False and h.step({4}, 0.3)[0] is False and h.step({4}, 0.41)[0] is True
assert h.step({4}, 0.9)[0] is False                      # fires once per hold
assert h.step(set(), 1.0)[0] is False and h.step({4}, 1.1)[0] is False  # tap shorter than hold: nothing
# combo needs both
c = cm.PadState(frozenset({9, 10}), 0)
assert c.step({9}, 0)[0] is False and c.step({9, 10}, 0.1)[0] is True
# direction repeat: press, wait for delay, then every 0.11 s
d = cm.PadState(frozenset({4}), 0)
assert d.step({cm.RIGHT}, 0.0)[1] == [cm.RIGHT]
assert d.step({cm.RIGHT}, 0.2)[1] == []
assert d.step({cm.RIGHT}, 0.36)[1] == [cm.RIGHT]
assert d.step({cm.RIGHT}, 0.40)[1] == []
assert d.step({cm.RIGHT}, 0.48)[1] == [cm.RIGHT]
assert d.step({cm.A}, 0.5)[1] == [cm.A]                  # face buttons don't repeat
assert d.step({cm.A}, 1.5)[1] == []
print("PadState PASS")

# controller drives the real bar
app = QtWidgets.QApplication([])
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=tempfile.mkdtemp())); ctl.refresh_status = lambda: None
saved = []; ctl.save_clip = lambda sec, game: saved.append((sec, game))
shots = []; ctl.screenshot = lambda game: shots.append(game)
viewer = cm.Viewer(ctl); menu = cm.Menu(ctl, viewer)
press = lambda b: cm.send_key(viewer if viewer.isVisible() else menu, cm.pad_key(b, menu, viewer))
menu.show_menu("Elden Ring"); app.processEvents()
assert menu.focusWidget() is menu.save_card
press(cm.RIGHT); assert menu.focusWidget() is menu.shot_card
press(cm.LEFT);  assert menu.focusWidget() is menu.save_card
press(cm.A);     assert menu.picking and menu.focusWidget() is menu.chips[3], "Cross opens the row on Last 1m"
assert [c.text() for c in menu.chips] == ["Full video", "Last 15s", "Last 30s", "Last 1m", "Last 3m",
                                          "Last 5m", "Last 15m", "Last 30m"]
press(cm.RIGHT); press(cm.RIGHT)                         # 1m -> 3m -> 5m
press(cm.A);     assert saved == [(300, "Elden Ring")] and not menu.isVisible(), saved
menu.show_menu("Elden Ring"); press(cm.A)
assert menu.focusWidget() is menu.chips[5], "remembers the last choice"
press(cm.B)
assert not menu.picking and menu.isVisible() and menu.focusWidget() is menu.save_card, "Circle goes back first"
press(cm.B);     assert not menu.isVisible(), "then Circle closes the bar"
# buffer fill: options longer than what's recorded are dimmed
menu.show_menu("Elden Ring"); menu.open_picker()
menu._on_status({"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 200_000,
                 "recording": False, "record_ms": 0})
assert "03:20" in menu.pick_caption.text() and "30:00" in menu.pick_caption.text()
assert [c.dimmed for c in menu.chips] == [False, False, False, False, False, True, True, True]
menu.hide_menu()
menu.show_menu("Elden Ring"); press(cm.X); app.processEvents()
end = time.time() + 1
while time.time() < end: app.processEvents()
assert shots == ["Elden Ring"], shots
print("bar navigation PASS")

# hints follow the device
app.installEventFilter(cm.INPUT)
menu.show_menu("Elden Ring"); app.processEvents()
cm.INPUT.set("playstation")
assert menu.hints.mode == "playstation" and ("A", "Select") in menu.hints.items
press(cm.RIGHT)                                           # controller-sent key: stays PlayStation
assert cm.INPUT.mode == "playstation"
from PySide6 import QtGui, QtCore
QtWidgets.QApplication.sendEvent(menu.focusWidget(), QtGui.QKeyEvent(QtCore.QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
assert cm.INPUT.mode == "keyboard" and ("k:Enter", "Select") in menu.hints.items, "real key switches back"
cm.INPUT.set("xbox"); menu.open_picker()
assert ("B", "Back") in menu.hints.items
assert cm.pad_combo_name("create", "xbox") == "View" and cm.pad_combo_name("l1+r1", "playstation") == "L1 + R1"
print("input mode hints PASS")

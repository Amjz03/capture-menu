import sys, time, tempfile, subprocess, os
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
cm.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
root = Path(tempfile.mkdtemp()); now = time.time()
def mk(game, name, tracks=1, ago=0):
    d = root / game; d.mkdir(exist_ok=True); p = d / name
    if name.endswith(".png"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1", str(p)], check=True)
    else:
        ins = sum([["-f", "lavfi", "-i", f"sine=f={300 + 100 * i}"] for i in range(tracks)], [])
        maps = sum([["-map", f"{i + 1}"] for i in range(tracks)], [])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", *ins,
                        "-t", "4", "-map", "0", *maps, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(p)], check=True)
    os.utime(p, (now - ago,) * 2); return p
a = mk("Neon Highway", "Clip_2026-10-16_21-00-00_60s.mp4", 3, 10)
b = mk("Neon Highway", "Screenshot_2026-10-16_20-00-00.png", ago=100)
c = mk("Frostfall", "Clip_2026-10-16_19-00-00_30s.mp4", 1, 1000)
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root))); ctl.refresh_status = lambda: None
calls = []
ctl.share = lambda p, k, nv: calls.append(("share", p.name, k, nv))
ctl.copy = lambda p: calls.append(("copy", p.name))
viewer = cm.Viewer(ctl); menu = cm.Menu(ctl, viewer); gallery = cm.Gallery(ctl, viewer); menu.gallery = gallery
def key(w, k): cm.send_key(w, k); app.processEvents()
def pad(btn): 
    k = cm.pad_key(btn, menu, viewer, gallery)
    cm.send_key(viewer if viewer.isVisible() else gallery if gallery.isVisible() else menu, k); app.processEvents()

# viewer: share a 3-track clip at 10 MB without the voice, via the controller
viewer.open(ctl.all_captures(), 0); app.processEvents()
pad(6)                                   # Options -> Share / Export
assert viewer.sharing and viewer.voice_card.isEnabled() and viewer.share_panel.isVisible()
assert viewer.focusWidget() is viewer.share_go, "starts on Export, so ✕ shares right away"
pad(cm.LEFT); pad(cm.LEFT); pad(cm.A)    # Cancel -> Size limit, next choice
assert viewer.size_card.value == 10
pad(cm.LEFT); pad(cm.A)                  # Your voice: leave it out
assert viewer.without_voice
for _ in range(3): pad(cm.RIGHT)         # Size limit, Cancel, Export
pad(cm.A)
assert calls[-1] == ("share", a.name, "discord10", True) and not viewer.sharing, calls
viewer.enter_share(); pad(cm.LEFT); pad(cm.LEFT); pad(cm.LEFT); pad(cm.LEFT); pad(cm.A)   # Format: original
assert viewer.format_card.value == "copy" and not viewer.size_card.isEnabled() and not viewer.voice_card.isEnabled()
pad(cm.RIGHT); pad(cm.RIGHT); pad(cm.A)   # past the cards it turned off, to Copy file
assert calls[-1] == ("copy", a.name) and not viewer.sharing, calls
cm.INPUT.set("playstation"); app.processEvents()
pad(cm.Y); pad(cm.A)                     # △ jumps to the small buttons, ✕ presses Favorite
assert ctl.is_favorite(a) and "★" in viewer.title.text()
viewer.step(1); viewer.enter_share()     # a screenshot: only Copy
assert not any(c.isVisible() for c in (viewer.format_card, viewer.voice_card, viewer.size_card))
key(viewer, Qt.Key_Return); assert calls[-1] == ("copy", b.name)
viewer.step(1); viewer.enter_share(); assert not viewer.voice_card.isEnabled(), "1-track clip: no voice option"
key(viewer, Qt.Key_Escape); assert not viewer.sharing and viewer.isVisible()
print("viewer share/favorite PASS")

# the controller moves a highlight over everything on screen, like a mouse, and ✕ presses it
assert not hasattr(viewer, "more_btn") and viewer.del_btn.isVisible() and not viewer.del_btn.text()
viewer.show_item(); app.processEvents()
assert viewer.focusWidget() is viewer.play_btn, "a clip starts on Play"
pad(cm.RIGHT); assert viewer.focusWidget() is viewer.slider
pad(cm.RIGHT); assert viewer.focusWidget() is viewer.slider, "on the seek bar → moves through the video"
pad(cm.DOWN); assert viewer.focusWidget() in (viewer.trim_btn, viewer.sound_btn, viewer.share_btn)
pad(cm.UP); pad(cm.UP)
assert viewer.focusWidget() in (viewer.back_btn, viewer.rename_btn, viewer.prev_btn, viewer.next_btn, viewer.close_btn)
pad(cm.Y); pad(cm.RIGHT); assert viewer.focusWidget() is viewer.folder_chip
revealed = []; ctl.reveal = lambda p: revealed.append(p.name)
pad(cm.A); assert revealed == [c.name] and viewer.isVisible()
key(viewer, Qt.Key_Delete)               # Delete armed, nothing deleted yet
assert viewer.del_btn.danger and viewer.focusWidget() is viewer.del_btn and c.exists()
pad(cm.B); assert not viewer.del_btn.danger and not viewer.del_btn.text() and c.exists() and viewer.isVisible()
cm.INPUT.set("keyboard"); app.processEvents()
assert viewer.focusWidget() is viewer, "with the keyboard the viewer keeps the keys for its shortcuts"
viewer.close_viewer()
print("viewer highlight PASS")

# gallery: categories, favourites, open, controller
menu.show_menu("Frostfall"); menu.all_card.click(); app.processEvents()
assert gallery.isVisible() and not menu.isVisible()
assert [n for n, _ in gallery.cats] == ["All", gallery.FAVORITES, "Neon Highway", "Frostfall"]
assert gallery.cats[gallery.games.currentRow()][0] == "Frostfall", "opens on the current game"
assert [p.name for p in gallery.cats[1][1]] == [a.name]
pad(cm.L1); pad(cm.L1); assert gallery.cats[gallery.games.currentRow()][0] == gallery.FAVORITES
pad(cm.L1); assert gallery.items == ctl.all_captures()           # All
pad(cm.RIGHT); assert gallery.grid.currentRow() == 1
pad(cm.Y); assert ctl.is_favorite(b)
pad(cm.A); assert viewer.isVisible() and viewer.current == b
pad(cm.B); assert not viewer.isVisible() and gallery.isVisible()
pad(cm.B); assert not gallery.isVisible()
end = time.time() + 5
while time.time() < end and any(ctl.thumb(p) is None for p in ctl.all_captures()):
    app.processEvents(); time.sleep(0.05)
assert all(ctl.thumb(p) for p in ctl.all_captures()), "gallery made the missing thumbnails"
print("gallery PASS")

# bar: mic tile + storage warning
menu.show_menu("Neon Highway")
menu._on_status({"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1000, "recording": False,
                 "record_ms": 0, "mic_muted": True})
assert menu.mic_card.isVisible() and menu.mic_card.label == "Mic off"
assert menu.mic_card in menu._nav_cards()
menu._on_status({"online": True, "buffer": True, "buffer_seconds": 1800, "buffered_ms": 1000, "recording": False,
                 "record_ms": 0, "mic_muted": None})
assert not menu.mic_card.isVisible(), "no mic in OBS: no tile"
menu.show_storage({"used_gb": 214, "free_gb": 500, "limit_gb": 200, "over": True, "low": False})
assert menu.storage_label.isVisible() and "214 GB" in menu.storage_label.text()
print("bar mic/storage PASS")

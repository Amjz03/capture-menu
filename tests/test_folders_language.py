# Screenshots can go to their own folder; the language setting switches every text and the direction.
# Needs no OBS: nothing here talks to it.
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, catalog, language, preferences, ui_settings, ui_widgets
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])

# ---- folders
root = Path(tempfile.mkdtemp())
clips, shots = root / "Clips", root / "Shots"
clip = clips / "Elden Ring" / "Clip_2026-10-16_21-00-00_30s.mp4"
clip.parent.mkdir(parents=True); clip.write_bytes(b"x")
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(clips), screenshots_dir=str(shots)))
assert ctl.shots_dir == shots and ctl.roots == [clips, shots]
shot = ctl.folder_for("Elden Ring", ctl.shots_dir) / "Screenshot_2026-10-16_21-00-05.png"
shot.write_bytes(b"x")
assert shot.parent == shots / "Elden Ring"
assert set(ctl.all_captures()) == {clip, shot}           # the gallery sees both folders
assert ctl.folder_for("Elden Ring") == clips / "Elden Ring"   # clips stay in the clips folder

same = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(clips)))   # not set: screenshots with the clips
assert same.shots_dir == clips and same.roots == [clips]
inside = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(clips), screenshots_dir=str(clips / "Screens")))
assert inside.roots == [clips]                             # a folder inside the clips folder isn't scanned twice
outside = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(clips), screenshots_dir=str(root)))
assert outside.all_captures().count(clip) == 1             # the clips folder inside it isn't counted twice
print("folders PASS")

# ---- settings rows
s = ui_settings.Settings(ctl)
row = next(r for r in s.rows if r.key == "screenshots_dir")
row.set_value("")
assert row.text() == "Same as the clips folder"
assert any(r.key == "language" for r in s.rows)
print("settings rows PASS")

# ---- language
language.set_language("en")
assert language.tr("Save recent") == "Save recent" and not language.is_rtl() and language.forward(Qt.Key_Right) == 1
language.set_language("ar")
assert language.LANG == "ar" and language.is_rtl()
assert language.tr("Save recent") == "حفظ الأخير"
assert language.tr("Keeping the last {length}", length="30 min") == "يحفظ آخر 30 min من اللعب"
assert language.duration_label(None) == "كل اللعب المحفوظ" and ui_widgets.chip_label(30) == "آخر 30 ث"
assert language.forward(Qt.Key_Right) == -1 and language.lead() == Qt.AlignRight | Qt.AlignAbsolute   # mirrored, and Qt mustn't flip it back
assert catalog.time_ago(time.time()) == "الحين"
assert language.tr("Not a known text") == "Not a known text"      # anything new falls back to English
language.set_language("xx")                                        # unknown: follow Windows (en or ar)
assert language.LANG in language.LANGUAGES
language.set_language("en")
print("language PASS")

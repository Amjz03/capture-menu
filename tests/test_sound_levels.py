# Your voice and the game can be made louder or quieter in one clip, from its separate tracks, and put
# back later. Needs ffmpeg; no OBS. Usage: test_sound_levels.py REPO
import re, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
app = QtWidgets.QApplication([])
ffmpeg = cm.find_tool("ffmpeg")
assert ffmpeg, "needs ffmpeg"

root = Path(tempfile.mkdtemp())
cm.STATE_PATH = root / "state.json"
clips = root / "Clips"
clip = clips / "Elden Ring" / "Clip_2026-10-16_21-00-00_30s.mp4"
clip.parent.mkdir(parents=True)
# like OBS with "voice on its own track": 1 = everything, 2 = game only, 3 = mic only
subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
                # the game in the first 2 s, the voice in the last 2 s, so each can be measured on its own
                "-filter_complex", "[1]volume=-20dB,apad=whole_dur=4,asplit[g1][g2];"
                                   "[2]volume=-40dB,adelay=2000:all=1,apad=whole_dur=4,asplit[v1][v2];"
                                   "[g1][v1]amix=inputs=2:normalize=0:duration=longest[all]",
                "-map", "0:v", "-map", "[all]", "-map", "[g2]", "-map", "[v2]",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(clip)], check=True)


def peaks(path):
    out = []
    for i in range(3):
        r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-map", f"0:a:{i}",
                            "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        out.append(float(re.search(r"max_volume: (-?[\d.]+) dB", r.stderr).group(1)))
    return out


def part_peak(path, start, length):   # track 1 in a stretch where only the game or only the voice plays
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-ss", str(start), "-t", str(length), "-i", str(path),
                        "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.search(r"max_volume: (-?[\d.]+) dB", r.stderr).group(1))


voice_peak = lambda path: part_peak(path, 2.3, 1.4)
game_peak = lambda path: part_peak(path, 0.2, 1.4)


before = peaks(clip)
voice_before = voice_peak(clip)
mtime = clip.stat().st_mtime
assert cm.audio_tracks(clip) == 3

ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(clips)))
assert ctl.mix_of(clip) == (100, 100)            # 100 % = as recorded
ctl._set_mix(clip, 400, 100)                     # voice 4x as loud = +20 dB
after = peaks(clip)
assert abs(voice_peak(clip) - (voice_before + 20)) < 1.5, (voice_before, voice_peak(clip))
assert abs(after[1] - before[1]) < 0.2 and abs(after[2] - before[2]) < 0.2, (before, after)   # raw tracks untouched
assert clip.stat().st_mtime == mtime            # stays in its place in Recent and the gallery
assert ctl.mix_of(clip) == (400, 100)
assert not list(clip.parent.glob("*.part")), "no leftover temp file"
assert set(ctl.all_captures()) == {clip}
v = subprocess.run([cm.find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_packets",
                    "-show_entries", "stream=codec_name,nb_read_packets", "-of", "csv=p=0", str(clip)],
                   capture_output=True, text=True).stdout.strip()
assert v.startswith("h264,") and int(v.split(",")[1]) == 120, v   # the video is copied, frame for frame

ctl._set_mix(clip, 100, 100)                     # back to how it was recorded
assert abs(voice_peak(clip) - voice_before) < 1.5 and ctl.mix_of(clip) == (100, 100)
game_before = game_peak(clip)
ctl._set_mix(clip, 100, 25)                      # game a quarter as loud = -20 dB
assert abs(game_peak(clip) - (game_before - 20)) < 1.5, (game_before, game_peak(clip))
ctl._set_mix(clip, 0, 100)                       # voice muted
assert voice_peak(clip) < -80, voice_peak(clip)
assert cm.level_text(100).startswith("100%") and cm.level_text(0) == "Muted"
assert abs(20 * cm.math.log10(cm.level_gain(200)) - 10) < 0.01   # twice as loud = +10 dB
print("remix PASS")

# a short piece to listen to, from a point in the clip
piece = root / "piece.mp4"
cm.remix_audio(clip, 300, 100, piece, seconds=1.5, start=2.0)
assert abs(cm.media_duration(piece) - 1.5) < 0.3 and cm.audio_tracks(piece) == 3
print("preview piece PASS")

# the viewer's Sound panel: V opens it, the volume bars move, Enter saves through the controller
from PySide6 import QtGui
press = lambda w, k: QtWidgets.QApplication.sendEvent(w, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, k, Qt.NoModifier))
viewer = cm.Viewer(ctl)
viewer.open([clip])
for _ in range(20):
    app.processEvents()
press(viewer, Qt.Key_V)
assert viewer.sounding and (viewer.voice_row.value, viewer.game_row.value) == (0, 100)
press(viewer.voice_row.slider, Qt.Key_Right); press(viewer.voice_row.slider, Qt.Key_Right)   # the bar itself
press(viewer.game_row.slider, Qt.Key_Left)
assert (viewer.voice_row.value, viewer.game_row.value) == (50, 75), (viewer.voice_row.value, viewer.game_row.value)
viewer.voice_row.slider.setValue(140)            # a drag lands on the nearest step
assert viewer.voice_row.value == 150 and viewer.voice_row.amount.text().endswith("150%")
saved = []
ctl.remixed.connect(saved.append)
press(viewer.game_row.slider, Qt.Key_Return)     # Enter isn't the bar's: it reaches the viewer
assert not viewer.sounding
end = time.time() + 30
while not saved and time.time() < end:
    app.processEvents()
    time.sleep(0.05)
assert saved == [str(clip)] and ctl.mix_of(clip) == (150, 75)
print("sound panel PASS")

# Back: a panel closes first, then the viewer goes back to where it was opened from
went = []
viewer.open([clip], back_to=lambda: went.append("bar"))
press(viewer, Qt.Key_V)
assert viewer.sounding
press(viewer, Qt.Key_Escape)
assert not viewer.sounding and viewer.isVisible() and not went
press(viewer, Qt.Key_Escape)
assert not viewer.isVisible() and went == ["bar"]
viewer.open([clip])                              # from a notice: Back just closes
viewer.go_back()
assert not viewer.isVisible() and went == ["bar"]
gallery = cm.Gallery(ctl, viewer)
gallery.open(back_to=lambda: went.append("bar2"))
gallery.marked = {clip}
gallery.go_back()                                # a selection goes first
assert gallery.isVisible() and not gallery.marked
gallery.go_back()
assert not gallery.isVisible() and went[-1] == "bar2"
settings = cm.Settings(ctl)
settings.open((1920, 1080), back_to=lambda: went.append("bar3"))
press(settings, Qt.Key_Escape)
assert not settings.isVisible() and went[-1] == "bar3"
viewer.close_viewer()
print("back PASS")

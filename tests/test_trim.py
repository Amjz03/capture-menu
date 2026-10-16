import sys, time, subprocess, tempfile, os
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication([])
root = Path(tempfile.mkdtemp()); g = root / "Elden Ring"; g.mkdir()
def mk(name, vcodec):
    p = g / name
    subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=size=1280x720:rate=30","-f","lavfi","-i","sine",
                    "-t","20","-g","60",*vcodec,"-c:a","aac",str(p)], check=True); return p
h264 = mk("Clip_2026-10-16_20-00-00_30s.mp4", ["-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p"])
av1 = mk("Clip_2026-10-16_21-00-00_60s.mp4", ["-c:v","libsvtav1","-preset","12","-pix_fmt","yuv420p"])
print("codecs:", cm.video_codec(h264), cm.video_codec(av1))

# 1) trim helper (NVENC unavailable here -> falls back to lossless copy)
out = g / "t.mp4"; mode = cm.trim_clip(h264, 4000, 9000, out)
d = cm.media_duration(out); print("trim:", mode, round(d,2)); assert 4.5 <= d <= 7.5

# 2) controller trim: save-as-new keeps original, replace removes it
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(root)))
got = []; ctl.trimmed.connect(got.append)
ctl._trim(h264, 2000, 6000, replace=False); app.processEvents()
assert h264.exists() and got and Path(got[0]).exists() and cm.capture_kind(Path(got[0])) == "Trimmed clip"
time.sleep(1.1)
ctl._trim(Path(got[0]), 0, 2000, replace=True); app.processEvents()
assert not Path(got[0]).exists() and Path(got[1]).exists()
print("controller trim PASS")

# 3) viewer: H.264 shows real frames; AV1 without a decoder switches to a preview copy
v = cm.Viewer(ctl)
def wait(cond, secs):
    end = time.time() + secs
    while time.time() < end and not cond():
        app.processEvents(); time.sleep(0.05)
other = [p for p in g.glob("Clip_*trim*")][0]
v.open([other], 0); wait(lambda: v._frames > 5, 10)
print("h264 frames shown:", v._frames); assert v._frames > 5
wait(lambda: False, 3)   # watchdog must not fire for a working clip
assert "previews" not in v.player.source().toLocalFile()
v.open([av1], 0)
wait(lambda: "previews" in v.player.source().toLocalFile() and v._frames > 5, 90)
src = v.player.source().toLocalFile()
print("AV1 playing from:", "preview copy" if "previews" in src else "original", "| frames", v._frames)
assert "previews" in src and v._frames > 5

# 4) trim mode on the AV1 clip
v.enter_trim()
end = time.time() + 15
while time.time() < end and len(v.timeline.frames) < 12:
    app.processEvents(); time.sleep(0.05)
v.timeline.set_start(5000); v.timeline.set_end(12500); v.timeline.pos = 8000; v.timeline.update()
v.resize(1100, 900); app.processEvents()
v.grab().save(sys.argv[2])
print("frames:", len(v.timeline.frames), "|", v.trim_info.text())
v.save_trim(replace=False)
end = time.time() + 60
while time.time() < end and v.stage.currentWidget() is v.msg:
    app.processEvents(); time.sleep(0.05)
new = v.current; print("after save viewer shows:", new.name, round(cm.media_duration(new),2), "| original kept:", av1.exists())
assert 6.5 <= cm.media_duration(new) <= 9 and av1.exists()
print("PASS")

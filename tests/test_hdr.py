# HDR: OBS gets 10-bit Rec.2100 only when asked and the encoder can do it; an HDR clip is found as
# one; share copies, thumbnails, filmstrip frames and previews come out in normal colours (not grey
# and washed out); a GPU trim keeps the clip HDR. Needs ffmpeg; no OBS. Usage: test_hdr.py REPO
import statistics, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtGui, QtWidgets
app = QtWidgets.QApplication([])
ffmpeg, ffprobe = cm.find_tool("ffmpeg"), cm.find_tool("ffprobe")
assert ffmpeg and ffprobe, "needs ffmpeg"

# ---- OBS settings
cfg = dict(cm.DEFAULTS)
profile = lambda plan: {(c, n): v for c, n, v in plan["profile"]}
on = cm.obs_plan(cfg, 2560, 1440, "nvenc_av1", "31.0.0", hdr=True)
assert on["hdr"] and profile(on)[("Video", "ColorFormat")] == "P010" and profile(on)[("Video", "ColorSpace")] == "2100PQ"
assert on["summary"].endswith("HDR")
off = cm.obs_plan(cfg, 2560, 1440, "nvenc_av1", "31.0.0", hdr=False)
assert not off["hdr"] and profile(off)[("Video", "ColorFormat")] == "NV12" and profile(off)[("Video", "ColorSpace")] == "709"
h264 = cm.obs_plan(dict(cfg, video_codec="h264"), 2560, 1440, "nvenc_av1", "31.0.0", hdr=True)
assert not h264["hdr"] and profile(h264)[("Video", "ColorFormat")] == "NV12", "H.264 can't carry HDR"
assert on["summary"] != off["summary"], "turning HDR on or off sets OBS up again"
bright = cm.obs_plan(cfg, 2560, 1440, "nvenc_av1", "31.0.0", hdr=False, white=240)
assert profile(bright)[("Video", "SdrWhiteLevel")] == "240", "OBS's white level matches Windows' (not grey)"
assert ("Video", "SdrWhiteLevel") not in profile(off) and bright["summary"] != off["summary"]
assert bright["vivid"] and not off["vivid"], "normal colours from an HDR screen get a light colour boost"
natural = cm.obs_plan(dict(cfg, colours="natural"), 2560, 1440, "nvenc_av1", "31.0.0", hdr=False, white=240)
assert not natural["vivid"] and natural["summary"] != bright["summary"], "Colours: Natural turns the boost off"
assert not cm.obs_plan(cfg, 2560, 1440, "nvenc_av1", "31.0.0", hdr=True, white=240)["vivid"], "HDR clips stay as they are"
assert cm.sdr_white() is None or 80 <= cm.sdr_white() <= 1000
screens = cm.hdr_screens()
assert isinstance(screens, dict) and all(isinstance(v, bool) for v in screens.values())
print("OBS colour settings PASS", screens)

# ---- an HDR clip (BT.2020, PQ, 10-bit) and an ordinary one
work = Path(tempfile.mkdtemp())
hdr = work / "Game" / "Clip_2026-10-17_10-00-00_30s.mp4"
sdr = work / "Game" / "Clip_2026-10-17_10-01-00_30s.mp4"
hdr.parent.mkdir()
src = ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-f", "lavfi", "-i", "sine", "-t", "3"]
subprocess.run([ffmpeg, "-v", "error", "-y", *src, "-vf",
                "zscale=tin=bt709:pin=bt709:min=bt709:t=smpte2084:p=bt2020:m=bt2020nc:r=tv:npl=100,format=yuv420p10le",
                "-c:v", "libx265", "-x265-params", "log-level=error:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-tag:v", "hvc1",
                "-c:a", "aac", str(hdr)], check=True)
subprocess.run([ffmpeg, "-v", "error", "-y", *src, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(sdr)],
               check=True)
assert cm.is_hdr(hdr) and not cm.is_hdr(sdr)
assert cm.sdr_filter(sdr, "scale=480:-2") == "scale=480:-2" and cm.sdr_filter(hdr, "scale=480:-2").startswith("zscale")
print("finds HDR clips PASS")


def color(path):
    r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=pix_fmt,color_transfer", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return r.stdout.strip()


def look(img_path):
    """Contrast and colour of a picture: a washed-out HDR frame has little of either."""
    img = QtGui.QImage(str(img_path)).convertToFormat(QtGui.QImage.Format_RGB32)
    lum, sat = [], []
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            c = img.pixelColor(x, y)
            lum.append(0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()); sat.append(c.hsvSaturation())
    return statistics.pstdev(lum), statistics.mean(sat)


def frame_of(video, out):
    subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", "1", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return out


ref = look(frame_of(sdr, work / "ref.png"))                      # the same picture, never HDR
washed = work / "washed.png"
subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", "1", "-i", str(hdr), "-frames:v", "1", str(washed)], check=True)
grey = look(washed)
assert grey[1] < ref[1] * 0.75, ("the raw HDR frame should look washed out", grey, ref)

# ---- share copy: normal colours, tagged BT.709
out = work / "share.mp4"
cm.export_for_share(hdr, out, None, False)
assert color(out).startswith("yuv420p,bt709"), color(out)
shared = look(frame_of(out, work / "shared.png"))
assert shared[1] > grey[1] * 1.3 and shared[0] > grey[0], ("share copy should have its colour back", shared, grey)
print("share copy in normal colours PASS", [round(v) for v in shared], "vs washed", [round(v) for v in grey])

# ---- Copy puts a normal-colour copy of an HDR clip on the clipboard, an SDR clip as it is
ctl = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(work)))
ctl._bg = lambda fn, *a, **kw: fn(*a)
copied = []
ctl.copy_file.connect(copied.append)
ctl.copy(sdr)
assert copied == [str(sdr)], copied
ctl.copy(hdr)
assert len(copied) == 2 and Path(copied[1]).parent.name == "Shared" and not cm.is_hdr(Path(copied[1])), copied
assert look(frame_of(Path(copied[1]), work / "copied.png"))[1] > grey[1] * 1.3
print("copy gives normal colours PASS")

# ---- thumbnail, filmstrip frame and preview copy
thumb = cm.make_thumb(hdr, work)
assert thumb and look(thumb)[1] > grey[1] * 1.3, look(thumb)
strip = work / "strip.jpg"
assert cm.filmstrip_frame(hdr, 1000, strip) and look(strip)[1] > grey[1] * 1.2, look(strip)
preview = work / "preview.mp4"
assert cm.make_preview(hdr, preview) and color(preview).startswith("yuv420p")
assert look(frame_of(preview, work / "prev.png"))[1] > grey[1] * 1.3
print("thumbnails, filmstrip and preview in normal colours PASS")

# ---- a GPU trim keeps HDR
if cm.has_encoder("hevc_nvenc"):
    cut = work / "Game" / "Clip_2026-10-17_10-00-00_trim.mp4"
    how = cm.trim_clip(hdr, 500, 2500, cut)
    assert how == "precise" and color(cut) == "yuv420p10le,smpte2084", (how, color(cut))
    print("trim keeps HDR PASS")
else:
    print("trim keeps HDR SKIPPED (no NVIDIA encoder)")

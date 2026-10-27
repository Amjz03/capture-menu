# To your phone: a link this PC serves for one capture, as it is, shown as a QR code; the phone plays it in
# pieces (byte ranges) and saves the original file. Closing the panel ends the link.
import sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, language, phone_link, preferences, ui_viewer
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt

app = QtWidgets.QApplication([])
language.set_language("en")
tmp = Path(tempfile.mkdtemp())
clip = tmp / "Red Dead Redemption 2" / "Clip_2026-10-27_09-00-00_30s.mp4"
clip.parent.mkdir()
data = bytes(range(256)) * 4096          # 1 MB that a byte-for-byte check can tell apart
clip.write_bytes(data)

link = phone_link.PhoneLink(clip, host="127.0.0.1")
assert link.url.startswith("http://127.0.0.1:") and len(link.token) >= 20, link.url
get = lambda path, **h: urllib.request.urlopen(urllib.request.Request(link.url + path, headers=h), timeout=5)
page = get("").read().decode()
assert "<video" in page and "Download the video" in page and "Clip_2026-10-27_09-00-00_30s" in page and "/file?dl=1" in page
whole = get("/file")
assert whole.read() == data and whole.headers["Content-Type"] == "video/mp4", "the original file, as it is"
assert "Content-Disposition" not in whole.headers, "plays in the page"
part = get("/file", Range="bytes=1000-1999")
assert part.status == 206 and part.read() == data[1000:2000] and part.headers["Content-Range"] == f"bytes 1000-1999/{len(data)}"
assert get("/file", Range="bytes=-10").read() == data[-10:]
dl = get("/file?dl=1")
assert dl.read() == data and dl.headers["Content-Disposition"].startswith('attachment; filename="Clip_2026-10-27_09-00-00_30s.mp4"'), "the button saves it"
try:
    urllib.request.urlopen(link.url.rsplit("/", 1)[0] + "/someone-elses-guess", timeout=5)
    raise AssertionError("only this capture's link is served")
except urllib.error.HTTPError as e:
    assert e.code == 404
# an Arabic file name: HTTP headers are Latin-1, so the name goes as filename* (UTF-8) with a plain fallback
ar = tmp / "Red Dead Redemption 2" / "لقطة.mp4"
ar.write_bytes(b"x" * 18)
arl = phone_link.PhoneLink(ar, host="127.0.0.1")
r = urllib.request.urlopen(arl.url + "/file?dl=1", timeout=5)
assert r.read() == b"x" * 18 and "filename*=UTF-8''%D9%84%D9%82%D8%B7%D8%A9.mp4" in r.headers["Content-Disposition"], r.headers
arl.stop()
print("arabic name PASS")
pm = QtGui.QPixmap(); assert pm.loadFromData(link.qr_png()) and pm.width() > 200, "a QR code"
print("link PASS", link.url)

# a connection the phone opened before the link ended gets nothing after it (QA18-02)
import http.client
conn = http.client.HTTPConnection(link.url.split("/")[2], timeout=5)
conn.request("GET", "/" + link.token); conn.getresponse().read()      # kept open (HTTP/1.1)
link.stop()
try:
    conn.request("GET", "/" + link.token + "/file"); r = conn.getresponse()
    assert r.status == 410 and not r.read(), r.status
except (ConnectionError, OSError, http.client.HTTPException):
    pass                                 # or the connection is simply closed: also nothing
conn.close()
import time; time.sleep(0.5)
try:
    get("", ); raise AssertionError("the link stops when the panel closes")
except (urllib.error.URLError, ConnectionError, OSError):
    pass
print("stops PASS")

# in the viewer: Share / Export -> To your phone shows the code and the notes; Esc puts it away and ends the link
phone_link.local_ip = lambda: "127.0.0.1"
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp)))
v = ui_viewer.Viewer(ctl)
v.items, v.index = [clip], 0
v.resize(1600, 900); v.show(); app.processEvents()
v.send_to_phone(); app.processEvents()
panel = v.phone_panel
panel.link.ready.wait(10)
for _ in range(10): app.processEvents(); time.sleep(0.05)   # the code shows once the file is ready
assert panel.isVisible() and panel.link and panel.link.url and not panel.code.pixmap().isNull()
assert any("same Wi-Fi" in n.text() for n in panel.notes) and panel.notes[2].text() == "The original file, in full quality"
running = panel.link
QtWidgets.QApplication.sendEvent(v, QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
assert not panel.isVisible() and panel.link is None and running.server is None
print("viewer PASS")

# no network: the panel says so instead of a code
phone_link.local_ip = lambda: None
v.send_to_phone(); app.processEvents()
assert panel.isVisible() and panel.code.pixmap().isNull() and "isn't connected" in panel.fine.text()
panel.close_panel()
print("no network PASS")

# HEVC as OBS writes it (hev1) is retagged hvc1 for iPhone, the same frames copied; anything else goes as it is
import subprocess
from capturemenu import media
ff, fp = media.find_tool("ffmpeg"), media.find_tool("ffprobe")
if ff and media.has_encoder("libx265"):
    hevc = tmp / "hevc.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1", "-c:v", "libx265",
                    "-tag:v", "hev1", str(hevc)], check=True)
    tag = lambda p: subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_tag_string",
                                    "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip()
    assert tag(hevc) == "hev1"
    out = phone_link.for_apple(hevc, Path(tempfile.mkdtemp()))
    assert out != hevc and tag(out) == "hvc1", tag(out)
    assert phone_link.for_apple(clip, tmp) == clip, "not HEVC: as it is"
    print("hvc1 PASS")
    # 120 FPS goes over at 60 (the Photos app plays no more), same size; the panel says so and waits for it
    fast = tmp / "Red Dead Redemption 2" / "Clip_2026-10-27_09-10-00_30s.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=120:duration=2", "-c:v", "libx265",
                    "-tag:v", "hev1", str(fast)], check=True)
    link = phone_link.PhoneLink(fast, host="127.0.0.1")
    assert link.at60 and link.ready.wait(60) and link.path != fast, "a 60 FPS copy"
    assert abs(media.frame_rate(link.path) - 60) < 0.5 and tag(link.path) == "hvc1", (media.frame_rate(link.path), tag(link.path))
    assert "At 60 FPS" in link.page()
    link.stop()
    phone_link.local_ip = lambda: "127.0.0.1"
    v.items, v.index = [fast], 0
    v.send_to_phone()
    deadline = time.time() + 60
    while not panel.link.ready.is_set() and time.time() < deadline: app.processEvents()
    for _ in range(10): app.processEvents(); time.sleep(0.05)
    assert "60 FPS" in panel.notes[2].text() and not panel.code.pixmap().isNull(), panel.fine.text()
    assert link.what() and not link.sdr, "an SDR clip only slows down"
    panel.close_panel()
    print("60 FPS PASS")
    # FFmpeg lists NVENC on PCs without an NVIDIA card: when it fails the processor makes the 60 FPS copy
    real_run = media.run_ffmpeg
    media.run_ffmpeg = lambda cmd, *a, **k: 1 if "hevc_nvenc" in cmd else real_run(cmd, *a, **k)
    real_has = media.has_encoder
    media.has_encoder = lambda name: True if name == "hevc_nvenc" else real_has(name)
    link = phone_link.PhoneLink(fast, host="127.0.0.1")
    assert link.ready.wait(120) and abs(media.frame_rate(link.path) - 60) < 0.5 and link.at60, "the CPU made it"
    link.stop()
    # every encoder fails: the original goes over, and the panel and page say so (not 60 FPS)
    media.run_ffmpeg = lambda *a, **k: 1
    link = phone_link.PhoneLink(fast, host="127.0.0.1")
    assert link.ready.wait(30) and not link.at60 and link.what() == "The original file, in full quality"
    assert "60 FPS" not in link.page()
    link.stop()
    media.run_ffmpeg, media.has_encoder = real_run, real_has
    print("encoder fallback PASS")
else:
    print("hvc1 SKIPPED (no ffmpeg with libx265)")
v.close_viewer(); app.processEvents()   # let go of the file, so the test folder can be removed

# To your phone: a link this PC serves for one capture, as it is, shown as a QR code; the phone plays it in
# pieces (byte ranges) and saves the original file. Closing the panel leaves the link up (back to the game).
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

# in the viewer: Share / Export -> To your phone shows the code and the notes; Esc puts it away, the link keeps working
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
assert "127.0.0.1" not in panel.fine.text(), "no address under the code"
assert any("same Wi-Fi" in n.text() for n in panel.notes) and panel.notes[2].text() == "The original file, in full quality"
running = panel.link
QtWidgets.QApplication.sendEvent(v, QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
assert not panel.isVisible() and panel.link is None and running.server is not None, "the phone keeps downloading"
assert urllib.request.urlopen(running.url + "/file", timeout=5).read() == data
v.send_to_phone(); app.processEvents()
assert panel.link is running, "the same clip again: the same QR code"
panel.close_panel(); v.close_viewer(); app.processEvents()
assert running.server is not None, "closing the viewer doesn't end it either"
v.show()
# it ends 30 minutes after the phone last asked
running.last -= phone_link.LIFETIME_S; running._timer.cancel(); running._expire()
assert running.server is None
v.send_to_phone(); app.processEvents()
assert panel.link is not running and panel.link.server is not None, "an ended link is made again"
panel.close_panel()
print("viewer PASS")

# no network: the panel says so instead of a code
for up in phone_link._links.values(): up.stop()   # the links from above end (they'd still serve)
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
    # 120 FPS goes over at 30 (a smaller file), same size; the panel says so and waits for it
    fast = tmp / "Red Dead Redemption 2" / "Clip_2026-10-27_09-10-00_30s.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=120:duration=2", "-c:v", "libx265",
                    "-tag:v", "hev1", str(fast)], check=True)
    link = phone_link.PhoneLink(fast, host="127.0.0.1")
    assert link.slowed and link.ready.wait(60) and link.path != fast, "a 30 FPS copy"
    assert abs(media.frame_rate(link.path) - 30) < 0.5 and tag(link.path) == "hvc1", (media.frame_rate(link.path), tag(link.path))
    assert "At 30 FPS" in link.page()
    link.stop()
    phone_link.local_ip = lambda: "127.0.0.1"
    v.items, v.index = [fast], 0
    v.send_to_phone()
    deadline = time.time() + 60
    while not panel.link.ready.is_set() and time.time() < deadline: app.processEvents()
    for _ in range(10): app.processEvents(); time.sleep(0.05)
    assert "30 FPS" in panel.notes[2].text() and not panel.code.pixmap().isNull(), panel.fine.text()
    assert link.what() and not link.sdr, "an SDR clip only slows down"
    panel.close_panel()
    print("30 FPS PASS")
    # FFmpeg lists NVENC on PCs without an NVIDIA card: when it fails the processor makes the 30 FPS copy
    real_run = media.run_ffmpeg
    media.run_ffmpeg = lambda cmd, *a, **k: 1 if "hevc_nvenc" in cmd else real_run(cmd, *a, **k)
    real_has = media.has_encoder
    media.has_encoder = lambda name: True if name == "hevc_nvenc" else real_has(name)
    link = phone_link.PhoneLink(fast, host="127.0.0.1")
    assert link.ready.wait(120) and abs(media.frame_rate(link.path) - 30) < 0.5 and link.slowed, "the CPU made it"
    link.stop()
    # every encoder fails: the original goes over, and the panel and page say so (not 30 FPS)
    media.run_ffmpeg = lambda *a, **k: 1
    link = phone_link.PhoneLink(fast, host="127.0.0.1")
    assert link.ready.wait(30) and not link.slowed and link.what() == "The original file, in full quality"
    assert "30 FPS" not in link.page()
    link.stop()
    media.run_ffmpeg, media.has_encoder = real_run, real_has
    print("encoder fallback PASS")
    # "Leave out" your voice in Share: the phone gets the game's track alone, and the panel says so
    three = tmp / "Red Dead Redemption 2" / "Clip_2026-10-27_09-20-00_30s.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1",
                    *sum([["-f", "lavfi", "-i", f"sine=f={300 + 100 * i}:d=1"] for i in range(3)], []),
                    "-map", "0", "-map", "1", "-map", "2", "-map", "3", "-c:v", "libx265", "-tag:v", "hev1",
                    "-c:a", "aac", str(three)], check=True)
    link = phone_link.PhoneLink(three, host="127.0.0.1", without_voice=True)
    assert link.ready.wait(60) and media.audio_tracks(link.path) == 1 and tag(link.path) == "hvc1", link.path
    assert "without your voice" in link.what() and media.audio_tracks(three) == 3, "the clip itself is untouched"
    link.stop()
    link = phone_link.PhoneLink(three, host="127.0.0.1")
    assert link.ready.wait(60) and media.audio_tracks(link.path) == 3 and "without" not in link.what()
    link.stop()
    print("phone without your voice PASS")
else:
    print("hvc1 SKIPPED (no ffmpeg with libx265)")
v.close_viewer(); app.processEvents()   # let go of the file, so the test folder can be removed

# while the phone's copy is made: a blurred code with the percentage on it, and the code is coming
class Slow:
    url, progress, ready = "http://x", 0, __import__("threading").Event()
    def what(self): return "x"
    def stop(self): pass
slow = Slow()
v2 = ui_viewer.Viewer(ctl); v2.resize(1600, 900); v2.show()
v2.phone_panel.show_link(slow); app.processEvents()
slow.progress = 38; v2.phone_panel._tick()
pp = v2.phone_panel
assert pp.waiting.isVisible() and pp.waiting.text() == "The QR code will appear in a moment" and not pp.code.pixmap().isNull()
lay = pp.code.parentWidget().layout()
assert lay.indexOf(pp.waiting) == lay.indexOf(pp.code) + 1, "right under the code"
v2.phone_panel.link = None; v2.phone_panel.hide(); v2.close_viewer(); app.processEvents()
print("QR coming PASS")

# the code gets ready after its panel was put away (back in the game): a notice says so, and a click shows it
import threading
from capturemenu import ui_notices
class Making(Slow):
    def __init__(self): self.ready, self.server = threading.Event(), object()
    qr_png = lambda self, scale=10: phone_link.PhoneLink.qr_png(self, scale)
making = Making()
real_link_for, phone_link.link_for = phone_link.link_for, lambda *a, **k: making
got = []
v3 = ui_viewer.Viewer(ctl); v3.phone_ready.connect(lambda p, nv: got.append((p, nv)))
v3.items, v3.index = [clip], 0; v3.resize(1600, 900); v3.show()
v3.send_to_phone(); app.processEvents()
v3.phone_panel.close_panel()
making.ready.set()
for _ in range(20): app.processEvents(); time.sleep(0.05)
assert got == [(str(clip), False)], got
v3.send_to_phone(); app.processEvents()             # ready already: the code shows, no notice
for _ in range(20): app.processEvents(); time.sleep(0.05)
assert len(got) == 1
v3.phone_panel.link = None; v3.phone_panel.hide(); v3.close_viewer(); app.processEvents()
phone_link.link_for = real_link_for
toast = ui_notices.Toast(); clicked = []
toast.show_phone_ready(str(clip), lambda: clicked.append(1)); app.processEvents()
assert toast.isVisible() and toast.title.text() == "The QR code is ready" and toast.sub.text() == "Red Dead Redemption 2"
assert toast.hint.text().startswith("Works for 30 minutes"), toast.hint.text()
toast.mousePressEvent(None)
assert clicked == [1] and not toast.isVisible()
print("ready notice PASS")

# a 30 FPS copy downloads while it's made: the code shows after its first MB, the download keeps pace and ends
# when it's whole; if the copy fails halfway the download is cut (a failed download, not a broken video)
import http.client
real_copy, real_rate = phone_link.phone_copy, media.frame_rate
media.frame_rate = lambda p: 120.0 if Path(p).name.startswith("Clip") else real_rate(p)
step, piece = threading.Event(), bytes(range(256)) * 4096 * 3          # 3 MB a step
def growing(ok):
    def copy(src, out, fps, sdr, on_progress=None, game_only=False):
        with open(out, "wb") as o:
            for i in range(4):
                o.write(piece); o.flush(); on_progress(i * 25)
                step.wait(5); step.clear()
        return ok
    return copy
phone_link.phone_copy = growing(True)
link = phone_link.PhoneLink(clip, host="127.0.0.1")
assert link.ready.wait(5) and not link.made.is_set(), "the code shows while it's made"
page = urllib.request.urlopen(link.url, timeout=5).read().decode()
assert "<video" not in page and "Still being made" in page
r = urllib.request.urlopen(link.url + "/file?dl=1", timeout=10)
assert r.headers["Transfer-Encoding"] == "chunked" and r.headers["Content-Disposition"].startswith("attachment")
got = r.read(len(piece))
for _ in range(4): time.sleep(0.3); step.set()
got += r.read()
assert got == piece * 4 and link.made.is_set(), len(got)
assert "<video" in urllib.request.urlopen(link.url, timeout=5).read().decode(), "whole: it plays in the page"
link.stop()
phone_link.phone_copy = growing(False)
link = phone_link.PhoneLink(clip, host="127.0.0.1")
assert link.ready.wait(5)
r = urllib.request.urlopen(link.url + "/file?dl=1", timeout=10)
for _ in range(4): time.sleep(0.3); step.set()
try:
    r.read(); raise AssertionError("a failed copy must not download as a whole file")
except http.client.IncompleteRead:
    pass
assert link.made.wait(5) and link.path == clip and not link.slowed, "the original goes instead"
assert urllib.request.urlopen(link.url + "/file?dl=1", timeout=5).read() == data
link.stop()
phone_link.phone_copy, media.frame_rate = real_copy, real_rate
print("download while made PASS")

# HDR as OBS records it (10-bit PQ) goes into normal colours on the graphics card, through a LUT made from
# media.TO_SDR: the same colours as the processor's way. Anything else (SDR, HLG, 8-bit) never uses the LUT.
ff = media.find_tool("ffmpeg")
if ff and media.has_encoder("hevc_nvenc"):
    pq = tmp / "Red Dead Redemption 2" / "Clip_2026-10-27_09-30-00_30s.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=60:duration=2",
                    "-vf", "gblur=sigma=6,format=yuv420p10le", "-c:v", "libx265", "-x265-params",   # soft edges, like footage
                    "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:log-level=error", "-color_primaries", "bt2020",
                    "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-color_range", "tv", str(pq)], check=True)
    assert phone_link.pq10(pq) and not phone_link.pq10(clip)
    used, real_run = [], media.run_ffmpeg
    media.run_ffmpeg = lambda cmd, *a, **k: (used.append(cmd), real_run(cmd, *a, **k))[1]
    card, cpu = tmp / "card.mp4", tmp / "cpu.mp4"
    assert phone_link.phone_copy(pq, card, True, True) and not media.is_hdr(card)
    media.run_ffmpeg = real_run
    if any("libplacebo" in " ".join(c) for c in used[-1:]):          # this PC has Vulkan: the card did it
        real_lut, phone_link.sdr_lut = phone_link.sdr_lut, lambda: None
        assert phone_link.phone_copy(pq, cpu, True, True)
        phone_link.sdr_lut = real_lut
        r = subprocess.run([ff, "-i", str(card), "-i", str(cpu), "-lavfi", "[0][1]psnr", "-f", "null", "-"],
                           capture_output=True, text=True)
        db = float([l for l in r.stderr.splitlines() if "average:" in l][-1].split("average:")[1].split()[0])
        assert db > 40, db
        print(f"HDR on the card PASS ({db:.0f} dB against the processor's)")
    else:
        print("HDR on the card SKIPPED (no Vulkan): the processor made it")

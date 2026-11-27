"""Send a capture to a phone on the same Wi-Fi: a link that only this PC serves, for this one file, as a QR code.
The link opens a page that plays the video first, with a clear button under it that saves the file to the phone,
as it is (full, original quality). One exception: a clip faster than 30 frames a second goes over at 30 (same size,
same colours, HDR kept), made on the graphics card: about a third smaller, so it gets there sooner.
Nothing leaves the home network. The link keeps working after the panel (or the viewer) closes, so you can go back
to your game while the phone downloads; it stops 30 minutes after the phone last asked for anything, or on quit."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import atexit
import array
import hashlib
import html
import io
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote

from . import language, media, runtime

LIFETIME_S = 30 * 60
TYPES = {".mp4": "video/mp4", ".mkv": "video/x-matroska", ".mov": "video/quicktime", ".png": "image/png", ".jpg": "image/jpeg"}


def for_apple(path: Path, work: Path, game_only: bool = False) -> Path:
    """OBS tags HEVC as hev1, which an iPhone won't play or save to Photos: the same video retagged hvc1, a copy
    without re-encoding (every frame as recorded). game_only: just the game's sound track (no voice). Anything
    else is sent as it is."""
    hevc = path.suffix.lower() == ".mp4" and media.video_codec(path) == "hevc"
    ffmpeg = media.find_tool("ffmpeg")
    if not ffmpeg or not (hevc or game_only):
        return path
    out = work / path.name
    maps = ["-map", "0:v:0", "-map", "0:a:1"] if game_only else ["-map", "0"]
    r = media.run_quiet([ffmpeg, "-v", "error", "-y", "-i", str(path), *maps, "-c", "copy",
                         *(["-tag:v", "hvc1"] if hevc else []), "-movflags", "+faststart", str(out)])
    return out if r.returncode == 0 and out.exists() else path


PHONE_FPS = 30                                   # fewer frames, not less quality: a smaller file
GROWING_FROM = 1 << 20                           # the copy's first MB is written: the phone can start downloading


LUT_SIZE = 65


def sdr_lut() -> Path | None:
    """media.TO_SDR baked into a 3D LUT, so the graphics card does the HDR -> normal colours conversion (3x faster,
    the same colours: 51 dB PSNR against the processor's). Made once from TO_SDR itself, by running it on every
    lattice colour (each in a 2x2 block, so the 4:2:0 chroma is the colour's own). For libplacebo's "native" LUT
    on the clip tagged as plain BT.709 (so libplacebo converts nothing itself): in = the 10-bit YCbCr codes / 1023,
    out = the 8-bit result's codes as libplacebo writes them (code * 4 / 1023)."""
    n = LUT_SIZE
    cube = Path(tempfile.gettempdir()) / f"CaptureMenu-sdr-{hashlib.md5(media.TO_SDR.encode()).hexdigest()[:10]}.cube"
    if cube.exists():
        return cube
    ffmpeg = media.find_tool("ffmpeg")
    if not ffmpeg:
        return None
    code = [round(i * 1023 / (n - 1)) for i in range(n)]
    # block (row, col) holds lattice point col + n*row: Y = col, Cb = row % n, Cr = row // n. 8x8 blocks, read at
    # their middle: FFmpeg's chroma scaling reaches into the next pixels, so a smaller block takes its neighbour's colour
    b, c = 8, 4                                  # a block's size in Y and in Cb / Cr pixels
    w, h = b * n, b * n * n
    planes = array.array("H", [v for v in code for _ in range(b)] * h)
    for colour in (lambda r: code[r % n], lambda r: code[r // n]):
        for r in range(n * n):
            planes.extend([colour(r)] * (c * n * c))
    r = subprocess.run([ffmpeg, "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p10le", "-s", f"{w}x{h}",
                        "-color_trc", "smpte2084", "-color_primaries", "bt2020", "-colorspace", "bt2020nc",
                        "-color_range", "tv", "-i", "-", "-vf", media.TO_SDR, "-f", "rawvideo", "-pix_fmt", "yuv420p",
                        "-"], input=planes.tobytes(), capture_output=True, creationflags=media.QUIET)
    out = r.stdout if r.returncode == 0 else b""
    ysize, cw = w * h, w // 2                    # the Y plane; Cb and Cr are a quarter of it each
    if len(out) != ysize * 3 // 2:
        runtime.log.warning("the HDR colour table couldn't be made")
        return None
    luma, cb, cr = out[:ysize], out[ysize:ysize * 5 // 4], out[ysize * 5 // 4:]
    lines = [f"# Capture Menu: media.TO_SDR as a LUT\nLUT_3D_SIZE {n}"]
    for row in range(n * n):
        y_at, c_at = (row * b + b // 2) * w, (row * c + c // 2) * cw
        for col in range(n):
            x, cx = col * b + b // 2, col * c + c // 2
            lines.append(f"{luma[y_at + x] * 4 / 1023:.6f} {cb[c_at + cx] * 4 / 1023:.6f} {cr[c_at + cx] * 4 / 1023:.6f}")
    part = cube.with_suffix(".part")
    part.write_text("\n".join(lines) + "\n", encoding="ascii")
    part.replace(cube)
    return cube


def pq10(src: Path) -> bool:
    """HDR as OBS records it: 10-bit 4:2:0, BT.2020, PQ, limited range. The only kind sdr_lut() is made for (an HLG
    or 8-bit clip would come out in the wrong colours), so the others go through the processor."""
    ffprobe = media.find_tool("ffprobe")
    r = media.run_quiet([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=pix_fmt,color_transfer,color_space,color_range", "-of", "csv=p=0",
                         str(src)]) if ffprobe else None
    return bool(r) and r.stdout.strip().split("\n")[0].split(",")[:4] == ["yuv420p10le", "tv", "bt2020nc", "smpte2084"]


def phone_copy(src: Path, out: Path, fps: bool, sdr: bool, on_progress=None, game_only: bool = False) -> bool:
    """The clip as the phone gets it fastest: at most 30 frames a second (about a third smaller), and HDR in
    normal colours with the app's own tone mapping (an iPhone guesses at OBS's HDR and shows it grey). The same
    size, HEVC (hvc1), only the first sound track (everything). On the graphics card when it can.
    Fragmented MP4: it only grows at its end while it's made, so the phone can download it at the same time
    (the iPhone's Photos app takes it like any MP4)."""
    ffmpeg = media.find_tool("ffmpeg")
    if not ffmpeg:
        return False
    # frames dropped first: tone mapping half the frames (the slow part, on the processor) is half the work
    vf = ",".join(([f"fps={PHONE_FPS}"] if fps else []) + ([media.TO_SDR] if sdr else [])) or "null"
    hdr = media.is_hdr(src) and not sdr          # a clip only slowed down keeps its HDR
    bt2020 = ["-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc"]
    decode = ["-hwaccel", "auto"]                # read on the graphics card when it can (AV1 1440p120 is heavy)
    tries = []                                   # the graphics card first; FFmpeg lists NVENC even with no NVIDIA card
    if media.has_encoder("hevc_nvenc"):   # p3: a minute of 1440p120 in 11 s (p5: 18 s), about 8% bigger
        nvenc = ["-c:v", "hevc_nvenc", "-preset", "p3", "-rc", "vbr", "-cq", "17", "-b:v", "0", "-maxrate", "80M",
                 "-g", str(PHONE_FPS * 2)] + (["-profile:v", "main10", *bt2020] if hdr else [])
        if not sdr:   # only slowed down: frames never leave the card (a minute of 1440p120 AV1: 15 s, was 52 s)
            tries.append((["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"], nvenc, "hvc1", vf))
        elif pq10(src) and (lut := sdr_lut()) is not None:   # TO_SDR as a LUT on the card (20 s in 4.9 s, was 13.3)
            at = str(lut).replace("\\", "/").replace(":", "\\:")
            card = ("setparams=color_trc=bt709:color_primaries=bt709:colorspace=bt709:range=tv,"
                    f"libplacebo=lut='{at}':lut_type=native:colorspace=bt709:color_primaries=bt709:color_trc=bt709:"
                    "range=tv:format=yuv420p:dithering=none:peak_detect=0,hwdownload,format=yuv420p")
            tries.append((["-init_hw_device", "vulkan=vk", "-hwaccel", "vulkan", "-hwaccel_output_format", "vulkan",
                           "-filter_hw_device", "vk"], nvenc + ["-pix_fmt", "yuv420p"], "hvc1",
                          (f"fps={PHONE_FPS}," if fps else "") + card))
        tries.append((decode, nvenc + ["-pix_fmt", "p010le" if hdr else "yuv420p"], "hvc1", vf))
    if media.has_encoder("libx265"):
        tries.append((decode, ["-c:v", "libx265", "-preset", "fast", "-crf", "18"] + (
            ["-profile:v", "main10", "-pix_fmt", "yuv420p10le", "-x265-params",
             "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc", *bt2020] if hdr else ["-pix_fmt", "yuv420p"]),
            "hvc1", vf))
    # no HEVC at all: H.264 in normal colours plays everywhere
    tries.append((decode, ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"], "avc1",
                  ("" if vf == "null" else vf + ",") + media.TO_SDR if hdr else vf))
    for pre, video, tag, filters in tries:
        code = media.run_ffmpeg([ffmpeg, "-y", "-v", "error", *pre, "-i", str(src), "-map", "0:v:0",
                                 "-map", "0:a:1" if game_only else "0:a:0?",       # track 2: the game alone
                                 "-vf", filters, *video, "-tag:v", tag, "-c:a", "copy",
                                 "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                                 str(out)], media.media_duration(src) or 0, on_progress)
        if code == 0 and out.exists() and out.stat().st_size > 0 and (
                not fps or media.frame_rate(out) <= PHONE_FPS + 0.5):
            return True
        runtime.log.warning("phone copy with %s failed, trying the next encoder", video[1])
    try:
        out.unlink(missing_ok=True)
    except OSError:                              # a phone still has it open: the temp folder goes with the link
        pass
    return False


def local_ip() -> str | None:
    """This PC's address on the home network (no packet is sent: a UDP socket only picks the route)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") or ip.startswith("0.") else ip


class PhoneLink:
    """Serves one file to the phone. url is None when the PC is on no network."""

    def __init__(self, path: Path, host: str | None = None, without_voice: bool = False):
        self.source = self.path = Path(path)
        # "Leave out" your voice in Share: the phone gets the game's own track (OBS writes it when the voice is apart)
        self.novoice = without_voice and media.audio_tracks(self.source) >= 3
        self.ready = threading.Event()          # the file to send is set (retagged, or at 30 FPS): the code shows
        self.made = threading.Event()           # ...and it's whole (a 30 FPS copy downloads while it's made)
        self.slowed = media.frame_rate(self.source) > PHONE_FPS + 0.5   # goes over at 30 FPS
        self.sdr = media.is_hdr(self.source)    # HDR goes over in normal colours
        self.progress = 0                       # 0-100 while the phone's copy is made
        self.work = Path(tempfile.mkdtemp(prefix="CaptureMenu-phone-"))
        self.token = secrets.token_urlsafe(16)
        ip = host or local_ip()
        self.url: str | None = None
        self.server: ThreadingHTTPServer | None = None
        if ip is None:
            self.ready.set()
            self.made.set()
            return

        def prepare():
            try:
                if self.slowed or self.sdr:
                    out = self.work / self.source.name

                    def progress(pct):
                        self.progress = pct
                        # the first MB is out, so the encoder works: the phone can download it while it's made
                        if not self.ready.is_set() and out.exists() and out.stat().st_size > GROWING_FROM:
                            self.path = out
                            self.last = time.monotonic()
                            self.ready.set()
                    if phone_copy(self.source, out, self.slowed, self.sdr, progress, game_only=self.novoice):
                        self.path = out
                    else:                       # say what really goes over: the original
                        runtime.log.warning("the phone's copy failed, sending the original")
                        self.slowed = self.sdr = False
                        self.path = for_apple(self.source, self.work, self.novoice)
                else:
                    self.path = for_apple(self.source, self.work, self.novoice)
                if self.novoice and self.path == self.source:   # couldn't take the voice out: say so, don't send it
                    self.novoice = False
            finally:
                self.progress = 100
                self.last = time.monotonic()    # the 30 minutes start once the code can be scanned
                self.made.set()
                self.ready.set()
        threading.Thread(target=prepare, daemon=True).start()   # a long recording takes a moment to copy
        link = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):     # quiet: the app's log isn't for every request
                pass

            def do_GET(self):
                link.last = time.monotonic()
                route, _, query = self.path.partition("?")
                if link.server is None:          # the panel closed (or 30 minutes): an open connection gets nothing
                    self.send_error(410)
                    return
                if route == f"/{link.token}":
                    body = link.page().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                elif route == f"/{link.token}/file":
                    link.send_file(self, download="dl=1" in query)
                else:
                    self.send_error(404)

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://{ip}:{self.server.server_address[1]}/{self.token}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.last = time.monotonic()            # when the phone last asked (or the copy got ready)
        self._expire()
        runtime.log.info("phone link up for %s", self.path.name)

    def _expire(self):
        """Ends the link once the phone has asked for nothing for 30 minutes (a long download keeps it going)."""
        idle = time.monotonic() - self.last
        if idle >= LIFETIME_S:
            self.stop()
            return
        self._timer = threading.Timer(LIFETIME_S - idle, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def stop(self):
        if self.server is not None:
            server, self.server = self.server, None
            self._timer.cancel()
            def close():
                server.shutdown(); server.server_close()
                shutil.rmtree(self.work, ignore_errors=True)
            threading.Thread(target=close, daemon=True).start()

    def qr_png(self, scale: int = 10) -> bytes:
        import segno
        out = io.BytesIO()
        segno.make(self.url, error="m").save(out, kind="png", scale=scale, border=3)
        return out.getvalue()

    def what(self) -> str:
        """What the phone gets, in a line."""
        line = self._what()
        return line + language.tr(" · without your voice") if self.novoice else line

    def _what(self) -> str:
        if self.slowed and self.sdr:
            return language.tr("At 30 FPS and in normal colours, so it gets to the phone sooner and looks right, in full resolution")
        if self.slowed:
            return language.tr("At 30 FPS, so it's smaller and gets to the phone sooner, in full resolution")
        if self.sdr:
            return language.tr("In normal colours, so it looks right on the phone, in full resolution")
        return language.tr("The original file, in full quality")

    def page(self) -> str:
        """What the phone opens: the video, playing in the phone's own player, then one big Download button."""
        rtl = language.is_rtl()
        name = html.escape(self.source.stem)
        self.ready.wait(600)
        making = not self.made.is_set()          # still being made: it downloads as it's made, plays once whole
        size = f"{self.path.stat().st_size / 1024 ** 2:.0f} MB" if self.path.exists() and not making else ""
        image = self.source.suffix.lower() in (".png", ".jpg")
        media = (f'<img src="{self.token}/file" alt="">' if image else "" if making else
                 f'<video src="{self.token}/file" controls playsinline autoplay muted preload="auto"></video>')
        early = html.escape(language.tr("Still being made: you can download it now, it finishes as soon as it's ready"))
        save = html.escape(language.tr("Download the video") if not image else language.tr("Download the picture"))
        note = html.escape(self.what()) + (f' · <bdi dir="ltr">{size}</bdi>' if size else "")
        ios = html.escape(language.tr("On iPhone: after it downloads, open it from Downloads and choose Save Video to keep it in Photos"))
        cant = html.escape(language.tr("This phone can't play this video here, but you can still download it"))
        return f"""<!doctype html><html lang="{language.LANG}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="dark">
<title>Capture Menu</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:#0b0d12;color:#f2f4f8;font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;
display:flex;flex-direction:column;align-items:center;gap:16px;padding:max(18px,env(safe-area-inset-top)) 16px max(24px,env(safe-area-inset-bottom))}}
.app{{font-weight:700;opacity:.6;font-size:14px;letter-spacing:.02em}}
video,img{{display:block;width:100%;max-width:960px;max-height:62vh;border-radius:16px;background:#000;object-fit:contain}}
h1{{font-size:17px;margin:0;font-weight:600;text-align:center;word-break:break-word}}
.dl{{display:flex;align-items:center;justify-content:center;gap:12px;width:100%;max-width:520px;padding:18px 22px;border-radius:999px;
background:#fff;color:#0b0d12;font-weight:800;font-size:19px;text-decoration:none;box-shadow:0 10px 30px rgba(0,0,0,.4)}}
.dl svg{{width:24px;height:24px}}p{{margin:0;font-size:14px;opacity:.6;text-align:center;max-width:520px}}</style></head><body>
<div class="app">Capture Menu</div>{media}<h1>{name}</h1>
<a class="dl" href="{self.token}/file?dl=1" download><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>{save}</a>
<p id="cant" hidden>{cant}</p>{f"<p>{early}</p>" if making else ""}<p>{note}</p><p>{ios}</p>
<script>var v=document.querySelector("video");if(v){{v.addEventListener("error",function(){{document.getElementById("cant").hidden=false}});
document.querySelector(".dl").addEventListener("click",function(){{v.pause()}})}}</script></body></html>"""

    def send_file(self, h: BaseHTTPRequestHandler, download: bool = False):
        """The file as it is, with byte ranges (the phone's player reads it in pieces); as a download when asked."""
        self.ready.wait(300)
        if self.server is None:                  # ended while the copy was made
            h.send_error(410)
            return
        if not self.made.is_set():
            if download and not h.headers.get("Range"):
                self._stream(h)                  # the download keeps pace with the copy
                return
            self.made.wait()                     # the player (byte ranges) needs the whole file
        size = self.path.stat().st_size
        start, end = 0, size - 1
        rng = h.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].strip().partition("-")
            if a:
                start, end = int(a), int(b) if b else size - 1
            elif b:                          # the last n bytes
                start = max(0, size - int(b))
            end = min(end, size - 1)
            if start > end:
                h.send_response(416)
                h.send_header("Content-Range", f"bytes */{size}")
                h.end_headers()
                return
            h.send_response(206)
            h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            h.send_response(200)
        h.send_header("Content-Type", TYPES.get(self.path.suffix.lower(), "application/octet-stream"))
        h.send_header("Accept-Ranges", "bytes")
        h.send_header("Content-Length", str(end - start + 1))
        if download:
            name = self.source.name                  # HTTP headers are Latin-1: an Arabic name goes as UTF-8
            plain = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
            h.send_header("Content-Disposition", f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}")
        h.end_headers()
        try:
            with self.path.open("rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    h.wfile.write(chunk)
                    left -= len(chunk)
                    self.last = time.monotonic()    # still downloading: the link stays up
        except (BrokenPipeError, ConnectionResetError):
            pass                             # the phone stopped reading (it seeks with new ranges)

    def _stream(self, h: BaseHTTPRequestHandler):
        """The phone's copy while it's made, as it grows (chunked: its size isn't known yet). If the copy fails or
        starts over, the connection is cut without the last chunk, so the phone shows a failed download, not a
        broken video."""
        path = self.path
        name = self.source.name
        plain = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
        h.protocol_version = "HTTP/1.1"          # chunked needs it; the connection closes after
        h.close_connection = True
        h.send_response(200)
        h.send_header("Content-Type", TYPES.get(path.suffix.lower(), "application/octet-stream"))
        h.send_header("Content-Disposition", f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}")
        h.send_header("Transfer-Encoding", "chunked")
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        sent = 0
        try:
            with path.open("rb") as f:
                while True:
                    whole = self.made.is_set()
                    chunk = f.read(1 << 20)
                    if chunk:
                        h.wfile.write(b"%X\r\n" % len(chunk))
                        h.wfile.write(chunk)
                        h.wfile.write(b"\r\n")
                        sent += len(chunk)
                        self.last = time.monotonic()
                        continue
                    if self.server is None or os.fstat(f.fileno()).st_size < sent:
                        return                   # ended, or the copy started over with another encoder: cut
                    if whole:
                        if self.path != path:
                            return               # the copy failed (the original goes instead): cut
                        break
                    time.sleep(0.2)
            h.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass                                 # the phone stopped


_links: dict[tuple[Path, bool], PhoneLink] = {}


def link_for(path: Path, without_voice: bool = False) -> PhoneLink:
    """The link already up for this capture (the same QR code, still serving after the panel closed), or a new one."""
    key = (Path(path), without_voice)
    link = _links.get(key)
    if link is None or link.server is None:
        link = _links[key] = PhoneLink(path, without_voice=without_voice)
    return link


@atexit.register
def _stop_all():
    """On quit: no link outlives the app, and no phone copy is left in the temp folder."""
    for link in _links.values():
        if link.server is not None:
            server, link.server = link.server, None
            server.shutdown(); server.server_close()
        shutil.rmtree(link.work, ignore_errors=True)

"""Send a capture to a phone on the same Wi-Fi: a link that only this PC serves, for this one file, as a QR code.
The link opens a page that plays the video first, with a clear button under it that saves the file to the phone,
as it is (full, original quality). One exception: the iPhone's Photos app won't play more than 60 frames a second,
so a faster clip goes over at 60 (same size, same colours, HDR kept), made on the graphics card.
Nothing leaves the home network, and the link stops working when the panel closes (or after 30 minutes)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import html
import io
import secrets
import shutil
import socket
import tempfile
import threading
from urllib.parse import quote

from . import language, media, runtime

LIFETIME_S = 30 * 60
TYPES = {".mp4": "video/mp4", ".mkv": "video/x-matroska", ".mov": "video/quicktime", ".png": "image/png", ".jpg": "image/jpeg"}


def for_apple(path: Path, work: Path) -> Path:
    """OBS tags HEVC as hev1, which an iPhone won't play or save to Photos: the same video retagged hvc1, a copy
    without re-encoding (every frame as recorded). Anything else is sent as it is."""
    if path.suffix.lower() != ".mp4" or media.video_codec(path) != "hevc":
        return path
    ffmpeg = media.find_tool("ffmpeg")
    if not ffmpeg:
        return path
    out = work / path.name
    r = media.run_quiet([ffmpeg, "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy",
                         "-tag:v", "hvc1", "-movflags", "+faststart", str(out)])
    return out if r.returncode == 0 and out.exists() else path


PHONE_FPS = 60


def phone_copy(src: Path, out: Path, fps: bool, sdr: bool, on_progress=None) -> bool:
    """The clip as the phone plays it best: at most 60 frames a second (the Photos app plays no more), and HDR in
    normal colours with the app's own tone mapping (an iPhone guesses at OBS's HDR and shows it grey). The same
    size, HEVC (hvc1), only the first sound track (everything). On the graphics card when it can."""
    ffmpeg = media.find_tool("ffmpeg")
    if not ffmpeg:
        return False
    vf = ",".join(([media.TO_SDR] if sdr else []) + ([f"fps={PHONE_FPS}"] if fps else [])) or "null"
    hdr = media.is_hdr(src) and not sdr          # a clip only slowed down keeps its HDR
    bt2020 = ["-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc"]
    tries = []                                   # the graphics card first; FFmpeg lists NVENC even with no NVIDIA card
    if media.has_encoder("hevc_nvenc"):
        tries.append((["-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "17", "-b:v", "0", "-maxrate", "80M",
                       "-g", str(PHONE_FPS * 2)] + (["-profile:v", "main10", "-pix_fmt", "p010le", *bt2020] if hdr
                                                    else ["-pix_fmt", "yuv420p"]), "hvc1", vf))
    if media.has_encoder("libx265"):
        tries.append((["-c:v", "libx265", "-preset", "fast", "-crf", "18"] + (
            ["-profile:v", "main10", "-pix_fmt", "yuv420p10le", "-x265-params",
             "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc", *bt2020] if hdr else ["-pix_fmt", "yuv420p"]),
            "hvc1", vf))
    # no HEVC at all: H.264 in normal colours plays everywhere
    tries.append((["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"], "avc1",
                  media.TO_SDR + ("," + vf if vf != "null" else "") if hdr else vf))
    for video, tag, filters in tries:
        code = media.run_ffmpeg([ffmpeg, "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
                                 "-vf", filters, *video, "-tag:v", tag, "-c:a", "copy", "-movflags", "+faststart",
                                 str(out)], media.media_duration(src) or 0, on_progress)
        if code == 0 and out.exists() and out.stat().st_size > 0 and (
                not fps or media.frame_rate(out) <= PHONE_FPS + 0.5):
            return True
        runtime.log.warning("phone copy with %s failed, trying the next encoder", video[1])
    out.unlink(missing_ok=True)
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

    def __init__(self, path: Path, host: str | None = None):
        self.source = self.path = Path(path)
        self.ready = threading.Event()          # the file to send is set (retagged, or at 60 FPS, for iPhone)
        self.at60 = media.frame_rate(self.source) > PHONE_FPS + 0.5   # faster than the Photos app plays
        self.sdr = media.is_hdr(self.source)    # HDR goes over in normal colours
        self.progress = 0                       # 0-100 while the phone's copy is made
        self.work = Path(tempfile.mkdtemp(prefix="CaptureMenu-phone-"))
        self.token = secrets.token_urlsafe(16)
        ip = host or local_ip()
        self.url: str | None = None
        self.server: ThreadingHTTPServer | None = None
        if ip is None:
            self.ready.set()
            return

        def prepare():
            try:
                if self.at60 or self.sdr:
                    out = self.work / self.source.name
                    if phone_copy(self.source, out, self.at60, self.sdr, lambda pct: setattr(self, "progress", pct)):
                        self.path = out
                    else:                       # say what really goes over: the original
                        runtime.log.warning("the phone's copy failed, sending the original")
                        self.at60 = self.sdr = False
                        self.path = for_apple(self.source, self.work)
                else:
                    self.path = for_apple(self.source, self.work)
            finally:
                self.progress = 100
                self.ready.set()
        threading.Thread(target=prepare, daemon=True).start()   # a long recording takes a moment to copy
        link = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):     # quiet: the app's log isn't for every request
                pass

            def do_GET(self):
                route, _, query = self.path.partition("?")
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
        self._timer = threading.Timer(LIFETIME_S, self.stop)
        self._timer.daemon = True
        self._timer.start()
        runtime.log.info("phone link up for %s", self.path.name)

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
        if self.at60 and self.sdr:
            return language.tr("At 60 FPS and in normal colours, so the phone plays it right, in full resolution")
        if self.at60:
            return language.tr("At 60 FPS, the most the iPhone's Photos app plays, in full resolution")
        if self.sdr:
            return language.tr("In normal colours, so it looks right on the phone, in full resolution")
        return language.tr("The original file, in full quality")

    def page(self) -> str:
        """What the phone opens: the video, playing in the phone's own player, then one big Download button."""
        rtl = language.is_rtl()
        name = html.escape(self.source.stem)
        self.ready.wait(600)
        size = f"{self.path.stat().st_size / 1024 ** 2:.0f} MB" if self.path.exists() else ""
        image = self.source.suffix.lower() in (".png", ".jpg")
        media = (f'<img src="{self.token}/file" alt="">' if image else
                 f'<video src="{self.token}/file" controls playsinline autoplay muted preload="auto"></video>')
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
<p id="cant" hidden>{cant}</p><p>{note}</p><p>{ios}</p>
<script>var v=document.querySelector("video");if(v)v.addEventListener("error",function(){{document.getElementById("cant").hidden=false}});</script></body></html>"""

    def send_file(self, h: BaseHTTPRequestHandler, download: bool = False):
        """The file as it is, with byte ranges (the phone's player reads it in pieces); as a download when asked."""
        self.ready.wait(300)
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
        except (BrokenPipeError, ConnectionResetError):
            pass                             # the phone stopped reading (it seeks with new ranges)

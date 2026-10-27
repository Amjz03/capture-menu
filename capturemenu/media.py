"""FFmpeg trimming, previews, thumbnails, sharing and audio processing."""
from __future__ import annotations

from pathlib import Path
import hashlib
import math
import os
import shutil
import subprocess
import time

from . import language, runtime


def wait_until_written(path: Path, timeout: float = 30) -> bool:
    """Waits until OBS has finished writing the file: its size stops changing and nothing else has it
    open. The size alone isn't enough: OBS writes a recording in fragments seconds apart, and a file
    moved in between is copied half-written. False if OBS still has it after `timeout`."""
    last, deadline = -1, time.monotonic() + timeout
    while time.monotonic() < deadline:
        size = path.stat().st_size if path.exists() else 0
        if size > 0 and size == last and not open_elsewhere(path):
            return True
        last = size
        time.sleep(0.5)
    return False


def open_elsewhere(path: Path) -> bool:
    """Is another program (OBS) still writing this file? Asks Windows for it with no sharing at all."""
    if not runtime.IS_WINDOWS:
        return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    handle = k32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)   # GENERIC_READ, no sharing, OPEN_EXISTING
    if handle == wintypes.HANDLE(-1).value:
        return ctypes.get_last_error() == 32                                    # ERROR_SHARING_VIOLATION
    k32.CloseHandle(handle)
    return False


# ---------------------------------------------------------------- ffmpeg

def find_tool(name: str) -> str | None:
    local = runtime.APP_DIR / f"{name}.exe"
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found or not runtime.IS_WINDOWS:
        return found
    # winget puts ffmpeg in its own folder and only adds it to PATH for new sign-ins
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    for exe in [winget / "Links" / f"{name}.exe",
                *sorted((winget / "Packages").glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"), reverse=True)]:
        if exe.exists():
            return str(exe)
    return None


# Helper processes (ffmpeg, PowerShell) run without a window and below normal priority,
# so exporting or making thumbnails never takes CPU time from the game.
QUIET = 0x08000000 | 0x00004000 if runtime.IS_WINDOWS else 0   # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS


def run_quiet(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, creationflags=QUIET)


def media_duration(path: Path) -> float | None:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return None
    r = run_quiet([ffprobe, "-v", "error", "-show_entries", "format=duration",
                   "-of", "csv=p=0", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def join(parts: list[Path], inpoint: float, out: Path):
    """Joins the files OBS split its recording into, from `inpoint` seconds into the first, into
    out without re-encoding (every track kept)."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is not installed")
    part = out.with_name(out.name + ".part")   # this join's own file (not a capture, so the gallery skips it)
    listing = out.with_name(out.name + ".txt")
    lines = []
    for i, p in enumerate(parts):
        lines.append("file '" + str(p).replace("\\", "/").replace("'", "'\\''") + "'")
        if i == 0 and inpoint > 0:
            lines.append(f"inpoint {inpoint:.3f}")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        r = run_quiet([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                       "-i", str(listing), "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero",
                       "-f", {".mkv": "matroska", ".mov": "mov"}.get(out.suffix.lower(), "mp4"), str(part)])
    finally:
        listing.unlink(missing_ok=True)
    if r.returncode != 0 or not part.exists():
        part.unlink(missing_ok=True)
        raise RuntimeError(r.stderr.strip() or "joining failed")
    os.replace(part, out)


# ---------------------------------------------------------------- trimming and previews

_encoders: str | None = None


NVENC = {"h264": "h264_nvenc", "hevc": "hevc_nvenc", "av1": "av1_nvenc"}


def has_encoder(name: str) -> bool:
    global _encoders
    if _encoders is None:
        ffmpeg = find_tool("ffmpeg")
        _encoders = run_quiet([ffmpeg, "-hide_banner", "-encoders"]).stdout if ffmpeg else ""
    return f" {name} " in _encoders


_color_cache: dict[tuple[str, float], str] = {}


# HDR (PQ / HLG) to normal colours, tuned to look like Qt's own player: tone mapping that keeps
# the contrast, at a brightness that matches it, and the colour that tone mapping takes away
TO_SDR = ("zscale=t=linear:npl=50,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
          "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,eq=saturation=1.4")


def is_hdr(path: Path) -> bool:
    """An HDR video (PQ, as OBS and the NVIDIA app record it, or HLG)."""
    if path.suffix.lower() == ".png":
        return False
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return False
    if key not in _color_cache:
        ffprobe = find_tool("ffprobe")
        r = run_quiet([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "stream=color_transfer", "-of", "csv=p=0", str(path)]) if ffprobe else None
        # one field, though OBS's clips come back as "smpte2084," (with a comma)
        _color_cache[key] = r.stdout.strip().split(",")[0] if r else ""
    return _color_cache[key] in ("smpte2084", "arib-std-b67")


def sdr_filter(path: Path, vf: str) -> str:
    """vf, after turning an HDR clip into normal colours (phones, Discord and thumbnails are SDR)."""
    return f"{TO_SDR},{vf}" if is_hdr(path) else vf


def frame_rate(path: Path) -> float:
    """Frames a second of the first video stream (0 when it can't be read)."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return 0.0
    r = run_quiet([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                   "-of", "csv=p=0", str(path)])
    num, _, den = r.stdout.strip().split(",")[0].partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def video_codec(path: Path) -> str | None:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return None
    r = run_quiet([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=codec_name", "-of", "csv=p=0", str(path)])
    return r.stdout.strip() or None


def trim_clip(src: Path, start_ms: int, end_ms: int, out: Path) -> str:
    """Cuts [start, end] out of src. Re-encodes on the GPU (NVENC) for a frame-exact
    cut in the same codec; falls back to a lossless stream copy, which may start up
    to a keyframe earlier. Returns "precise" or "fast"."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is not installed")
    start, length = f"{start_ms / 1000:.3f}", f"{(end_ms - start_ms) / 1000:.3f}"
    enc = NVENC.get(video_codec(src) or "")
    # an HDR clip stays HDR: 10-bit, with its BT.2020 / PQ colour tags (else: the lossless cut)
    hdr = (["-pix_fmt", "p010le", "-color_primaries", "bt2020", "-color_trc", "smpte2084",
            "-colorspace", "bt2020nc", "-color_range", "tv"] + (["-profile:v", "main10"] if enc == "hevc_nvenc" else [])
           if enc in ("hevc_nvenc", "av1_nvenc") and is_hdr(src) else [])
    if enc and has_encoder(enc) and (hdr or not is_hdr(src)):
        r = run_quiet([ffmpeg, "-y", "-v", "error", "-hwaccel", "auto",
                       "-ss", start, "-i", str(src), "-t", length,
                       "-map", "0:v:0", "-map", "0:a?",
                       "-c:v", enc, "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", *hdr,
                       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return "precise"
        runtime.log.warning("GPU trim failed, using stream copy: %s", r.stderr.strip()[-300:])
        out.unlink(missing_ok=True)
    r = run_quiet([ffmpeg, "-y", "-v", "error", "-ss", start, "-i", str(src), "-t", length,
                   "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(out)])
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(r.stderr.strip() or "trimming failed")
    return "fast"


def make_preview(src: Path, out: Path, on_progress=None) -> bool:
    """A light 720p H.264 copy for clips the built-in player can't decode (e.g. AV1)."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        return False
    total_ms = (media_duration(src) or 0) * 1000
    tmp = out.with_suffix(".part.mp4")
    encoders = [["-c:v", "h264_nvenc", "-preset", "p1", "-cq", "28"]] if has_encoder("h264_nvenc") else []
    encoders.append(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"])
    for venc in encoders:
        cmd = [ffmpeg, "-y", "-v", "error", "-hwaccel", "auto", "-i", str(src),
               "-vf", sdr_filter(src, "scale=-2:720"), "-pix_fmt", "yuv420p", *venc, "-c:a", "aac", "-b:a", "128k",
               "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                creationflags=QUIET)
        for line in proc.stdout:
            if on_progress and total_ms and line.startswith("out_time_ms="):
                try:
                    on_progress(min(99, int(int(line.split("=")[1]) / 1000 / total_ms * 100)))
                except ValueError:
                    pass
        if proc.wait() == 0 and tmp.exists():
            os.replace(tmp, out)
            return True
        tmp.unlink(missing_ok=True)
    return False


def filmstrip_frame(src: Path, at_ms: int, out: Path) -> bool:
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        return False
    run_quiet([ffmpeg, "-y", "-v", "error", "-ss", f"{at_ms / 1000:.3f}", "-i", str(src),
               "-frames:v", "1", "-vf", sdr_filter(src, "scale=-2:90"), "-q:v", "5", str(out)])
    return out.exists()


# ---------------------------------------------------------------- sharing

# Discord's upload limits: free, Nitro Basic, Nitro.
SHARE_PRESETS = {
    "phone": {"label": "Phone & WhatsApp", "size_mb": None},
    "discord10": {"label": "Discord · 10 MB", "size_mb": 10},
    "discord50": {"label": "Discord · 50 MB", "size_mb": 50},
    "discord500": {"label": "Discord · 500 MB", "size_mb": 500},
}


def audio_tracks(path: Path) -> int:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return 0
    r = run_quiet([ffprobe, "-v", "error", "-select_streams", "a", "-show_entries",
                   "stream=index", "-of", "csv=p=0", str(path)])
    return len([line for line in r.stdout.splitlines() if line.strip()])


def video_height(path: Path) -> int:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return 1080
    r = run_quiet([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=height", "-of", "csv=p=0", str(path)])
    try:
        return int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 1080


def run_ffmpeg(cmd: list[str], total_s: float, on_progress=None) -> int:
    """Runs ffmpeg with -progress and reports 0-99 %. Returns the exit code."""
    proc = subprocess.Popen([*cmd[:1], "-progress", "pipe:1", "-nostats", *cmd[1:]],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            creationflags=QUIET)
    for line in proc.stdout:
        if on_progress and total_s and line.startswith("out_time_ms="):
            try:
                on_progress(min(99, int(int(line.split("=")[1]) / 1e6 / total_s * 100)))
            except ValueError:
                pass
    return proc.wait()


def share_plan(seconds: float, size_mb: int | None, src_height: int) -> dict:
    """Video bitrate/height/fps for a target file size (None = phone quality, no size cap)."""
    if size_mb is None:
        return {"height": min(src_height, 1080), "fps": 60, "video_kbps": None, "audio_kbps": 160}
    audio = 96 if size_mb <= 10 else 128
    total = size_mb * 8 * 1024 * 0.92 / max(seconds, 1)   # leave room for the container
    video = int(total - audio)
    if video < 150:
        raise ValueError(f"Too long for {size_mb} MB. Trim it to about "
                         f"{int(size_mb * 8 * 1024 * 0.92 / (150 + audio))} seconds first")
    height = 1080 if video >= 4000 else 720 if video >= 1500 else 540 if video >= 700 else 480
    return {"height": min(src_height, height), "fps": 60 if video >= 1500 else 30,
            "video_kbps": video, "audio_kbps": audio}


def export_for_share(src: Path, out: Path, size_mb: int | None, without_voice: bool,
                     on_progress=None) -> float:
    """Re-encodes to H.264/AAC MP4 (plays everywhere). Returns the file size in MB."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is not installed")
    seconds = media_duration(src) or 1
    plan = share_plan(seconds, size_mb, video_height(src))
    # track 1 = everything; with a separate voice track OBS writes 2 = game only, 3 = mic only
    audio_map = "0:a:1" if without_voice and audio_tracks(src) >= 3 else "0:a:0?"
    encoders = (["h264_nvenc"] if has_encoder("h264_nvenc") else []) + ["libx264"]
    video_kbps = plan["video_kbps"]
    size = 0.0
    for _ in range(3):   # a size target that comes out too big gets a second, smaller try
        for enc in encoders:
            nvenc = enc == "h264_nvenc"
            if video_kbps is None:
                rate = (["-c:v", enc, "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0"] if nvenc else
                        ["-c:v", enc, "-preset", "veryfast", "-crf", "22"]) + ["-maxrate", "14M", "-bufsize", "28M"]
            else:
                rate = ["-c:v", enc, "-preset", "p5" if nvenc else "veryfast",
                        "-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 1.15)}k",
                        "-bufsize", f"{video_kbps * 2}k"]
            cmd = [ffmpeg, "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", audio_map,
                   "-vf", sdr_filter(src, f"scale=-2:{plan['height']},fps={plan['fps']}"), "-pix_fmt", "yuv420p",
                   *rate, "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                   "-c:a", "aac", "-b:a", f"{plan['audio_kbps']}k", "-ac", "2",
                   "-movflags", "+faststart", str(out)]
            if run_ffmpeg(cmd, seconds, on_progress) == 0 and out.exists():
                break
            out.unlink(missing_ok=True)
            if nvenc:   # no usable NVIDIA encoder right now: use the CPU from here on
                runtime.log.warning("NVENC export failed, using libx264")
                encoders = ["libx264"]
        else:
            raise RuntimeError("couldn't convert the clip")
        size = out.stat().st_size / 1024 / 1024
        if size_mb is None or size <= size_mb:
            return size
        video_kbps = int(video_kbps * size_mb / size * 0.93)
    out.unlink(missing_ok=True)       # never "ready" with a file Discord would turn away
    raise RuntimeError(language.tr("it stayed over {mb} MB · trim the clip or pick a bigger size", mb=size_mb))


# ---------------------------------------------------------------- sound levels

# Levels are how loud something sounds, in %: 100 = as recorded, 200 = twice as loud (+10 dB),
# 50 = half as loud, 0 = muted. A volume bar in the viewer sets them, in steps of 25.
VOICE_MAX, GAME_MAX, LEVEL_STEP = 400, 200, 25


def level_gain(percent: int) -> float:
    """The amplitude factor for a loudness in %: loudness doubles every 10 dB."""
    return 0.0 if percent <= 0 else 10 ** (10 * math.log2(percent / 100) / 20)


def level_text(percent: int) -> str:
    if percent == 100:
        return language.tr("100% · as recorded")
    return language.tr("Muted") if percent <= 0 else f"\u200e{percent}%"   # LRM keeps "150%" in order in Arabic


def remix_audio(src: Path, voice: int, game: int, out: Path, seconds: float | None = None,
                start: float = 0.0, picture: Path | None = None):
    """Rebuilds track 1 (what players play) from track 2 (game only) and track 3 (mic only) at new
    levels (in %, 100 = as recorded). The video and those two tracks are copied untouched, so any level
    can be picked again later. `start` / `seconds` make a short piece to listen to; otherwise the whole
    clip. `picture` takes the video from another file (the 720p preview copy, for clips the built-in
    player can't show)."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is not installed")
    seek = ["-ss", f"{start:.3f}"] if start else []
    inputs = [*seek, "-i", str(picture or src)] + ([*seek, "-i", str(src)] if picture else [])
    a = "1" if picture else "0"     # the input that has the sound tracks
    mix = (f"[{a}:a:1]volume={level_gain(game):.4f}[g];[{a}:a:2]volume={level_gain(voice):.4f}[v];"
           f"[g][v]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.95:level=disabled[mix]")
    cmd = [ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", mix,
           "-map", "0:v:0", "-map", "[mix]", "-map", f"{a}:a:1", "-map", f"{a}:a:2",
           "-c:v", "copy", "-c:a:0", "aac", "-b:a:0", "192k", "-c:a:1", "copy", "-c:a:2", "copy",
           "-disposition:a:0", "default", "-disposition:a:1", "0", "-disposition:a:2", "0",
           *(["-t", f"{seconds:.3f}"] if seconds else []), "-movflags", "+faststart", "-f", "mp4", str(out)]
    r = run_quiet(cmd)
    if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(r.stderr.strip()[-300:] or "couldn't change the sound")


def make_thumb(path: Path, thumbs_dir: Path) -> Path | None:
    """A small JPEG of the clip's last moment (or the screenshot itself)."""
    thumb = thumbs_dir / (hashlib.md5(str(path).encode()).hexdigest() + ".jpg")
    if thumb.exists():
        return thumb
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg or not path.exists():
        return None
    seek = [] if path.suffix.lower() == ".png" else ["-sseof", "-1"]
    run_quiet([ffmpeg, "-y", "-v", "error", *seek, "-i", str(path), "-frames:v", "1",
               "-vf", sdr_filter(path, "scale=480:-2"), "-q:v", "4", str(thumb)])
    return thumb if thumb.exists() else None

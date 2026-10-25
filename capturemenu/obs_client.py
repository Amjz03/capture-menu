"""OBS WebSocket operations, recording plans and process discovery."""
from __future__ import annotations

from obsws_python.error import OBSSDKRequestError
from pathlib import Path
import obsws_python as obsws
import os
import re
import threading
import time

from . import media, runtime, windows


# ---------------------------------------------------------------- OBS

class ObsOffline(Exception):
    pass


class BufferDisabled(Exception):
    """OBS isn't in Simple output mode, so its recording can't be split into BUFFER_DIR."""


# The last minutes are kept on disk, not in OBS's RAM replay buffer: OBS records all the time,
# split into a new file every SPLIT_SECONDS, and Capture Menu deletes what's older than it keeps.
# A hidden folder in AppData, away from the clips, so nobody deletes it by accident.
BUFFER_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CaptureMenu" / "Buffer"
SPLIT_SECONDS = 60
FILE_OUTPUT = "simple_file_output"


def mic_name(name: str) -> str:
    """Windows names microphones "Headset Microphone (3- A50 X Mic)": the device is in the brackets
    (after the number Windows adds), and it's what tells two microphones apart."""
    m = re.fullmatch(r"[^(]*\((?:\d+- )?(.+)\)\s*", name)
    return m.group(1).strip() if m else name


class Obs:
    """Thin, thread-safe wrapper around obs-websocket."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._client = None
        self._lock = threading.RLock()

    def call(self, name: str, *args):
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._client is None:
                        self._client = obsws.ReqClient(
                            host=self.cfg["obs_host"],
                            port=self.cfg["obs_port"],
                            password=self.cfg["obs_password"],
                            timeout=3,
                        )
                    return getattr(self._client, name)(*args)
                except OBSSDKRequestError:
                    raise
                except Exception as e:  # connection dropped or OBS closed
                    self._client = None
                    if attempt == 2:
                        raise ObsOffline(str(e)) from e

    def buffer_active(self) -> bool:
        """OBS is recording the last minutes: a recording split into BUFFER_DIR (a recording the
        player started in OBS itself isn't, so it's restarted the way we need it)."""
        if not self.record_status()[0]:
            return False
        try:
            s = self.raw("GetOutputSettings", {"outputName": FILE_OUTPUT}).get("outputSettings", {})
        except OBSSDKRequestError:
            return False      # Advanced output mode: another output records
        return bool(s.get("split_file")) and Path(s.get("directory", "")) == BUFFER_DIR

    def start_buffer(self, wait: float = 8.0) -> bool:
        """Starts recording the last minutes to disk: OBS's own recording, split into a new file
        every SPLIT_SECONDS in BUFFER_DIR (Simple output mode keeps every other setting: encoder,
        quality, tracks), and waits until OBS reports it running. False: OBS took the request but
        never started (most often an encoder this PC can't run). Raises BufferDisabled when OBS
        isn't in Simple output mode."""
        if self.buffer_active():
            return True
        if self.profile_value("Output", "Mode") != "Simple":
            raise BufferDisabled()
        self.stop_buffer()          # a recording without the split (started in OBS itself)
        BUFFER_DIR.mkdir(parents=True, exist_ok=True)
        fmt = self.profile_value("SimpleOutput", "RecFormat2") or "mp4"
        self.raw("SetRecordDirectory", {"recordDirectory": str(BUFFER_DIR)})
        # OBS names the next files from directory/format/extension: without them it crashes at the split
        self.raw("SetOutputSettings", {"outputName": FILE_OUTPUT, "outputSettings": {
            "split_file": True, "max_time_sec": SPLIT_SECONDS, "max_size_mb": 0,
            "directory": str(BUFFER_DIR), "format": "%CCYY-%MM-%DD %hh-%mm-%ss", "allow_spaces": True,
            "extension": "mp4" if "mp4" in fmt else fmt}})
        self.call("start_record")
        end = time.monotonic() + wait
        while not self.buffer_active():
            if time.monotonic() >= end:
                return False
            time.sleep(0.25)
        return True

    def stop_buffer(self, wait: float = 10.0):
        if not self.record_status()[0]:
            return
        self.call("stop_record")
        end = time.monotonic() + wait
        while self.record_status()[0] and time.monotonic() < end:
            time.sleep(0.25)

    def stop_ram_buffer(self):
        """Stops OBS's own replay buffer (until 0.0.34 the last minutes were kept in it, in RAM)."""
        try:
            if self.call("get_replay_buffer_status").output_active:
                self.call("stop_replay_buffer")
                end = time.monotonic() + 10        # or OBS asks whether to stop it before it closes
                while self.call("get_replay_buffer_status").output_active and time.monotonic() < end:
                    time.sleep(0.25)
        except OBSSDKRequestError:
            pass             # switched off in OBS's settings already

    def recorded_bytes(self) -> int | None:
        """How much the recording has written so far (None when it doesn't run)."""
        r = self.raw("GetRecordStatus")
        return int(r.get("outputBytes") or 0) if r.get("outputActive") else None

    def streaming(self) -> bool:
        try:
            return bool(self.raw("GetStreamStatus").get("outputActive"))
        except OBSSDKRequestError:
            return False

    def split(self):
        """Closes the file being written and goes on in a new one (at the next keyframe)."""
        self.raw("SplitRecordFile")

    def set_profile(self, params: list[tuple[str, str, str]]) -> bool:
        """Writes OBS profile settings; True if anything changed (OBS loads them on its next start)."""
        changed = False
        for category, name, value in params:
            current = self.raw("GetProfileParameter", {"parameterCategory": category,
                                                       "parameterName": name}).get("parameterValue")
            if current != value:
                self.raw("SetProfileParameter", {"parameterCategory": category,
                                                 "parameterName": name, "parameterValue": value})
                changed = True
        return changed

    def profile_value(self, category: str, name: str) -> str | None:
        return self.raw("GetProfileParameter", {"parameterCategory": category,
                                                "parameterName": name}).get("parameterValue")

    def raw(self, request: str, data: dict | None = None) -> dict:
        return self.call("send", request, data, True) or {}

    def apply_plan(self, plan: dict) -> bool:
        """Applies the plan; returns True if anything changed (OBS then needs a restart)."""
        changed = False
        video = self.raw("GetVideoSettings")
        if any(video.get(k) != v for k, v in plan["video"].items()):
            self.raw("SetVideoSettings", plan["video"])
            changed = True
        changed |= self.set_profile(plan["profile"])
        if plan.get("voice_track"):
            changed |= self.split_voice_track()
        if not self.display_source():
            scene = self.raw("GetCurrentProgramScene")
            scene = scene.get("sceneName") or scene.get("currentProgramSceneName")
            self.raw("CreateInput", {"sceneName": scene, "inputName": "Display Capture",
                                     "inputKind": "monitor_capture", "inputSettings": {},
                                     "sceneItemEnabled": True})
            self.fit_to_canvas("Display Capture")
        self.set_colours(plan.get("force_sdr", False), plan.get("vivid"))
        return changed

    VIVID = "Capture Menu colour"

    def set_colours(self, force_sdr: bool, boost: dict | None):
        """force_sdr: Windows turns an HDR screen into normal colours, as its own screenshots do
        (OBS's own conversion lifts the blacks and dims the whites: grey and washed out).
        boost: a colour correction on the display capture (see COLOUR_BOOST), None removes it.
        Both apply live."""
        source = self.display_source()
        if not source:
            return
        if self.raw("GetInputSettings", {"inputName": source}).get("inputSettings", {}).get("force_sdr", False) != force_sdr:
            self.raw("SetInputSettings", {"inputName": source, "inputSettings": {"force_sdr": force_sdr}, "overlay": True})
        filters = [f["filterName"] for f in self.raw("GetSourceFilterList", {"sourceName": source}).get("filters", [])]
        if boost and self.VIVID in filters:
            self.raw("SetSourceFilterSettings", {"sourceName": source, "filterName": self.VIVID,
                                                 "filterSettings": boost})
        elif boost:
            self.raw("CreateSourceFilter", {"sourceName": source, "filterName": self.VIVID,
                                            "filterKind": "color_filter_v2", "filterSettings": boost})
        elif self.VIVID in filters:
            self.raw("RemoveSourceFilter", {"sourceName": source, "filterName": self.VIVID})

    def audio_inputs(self) -> tuple[list[str], list[str]]:
        """(game/desktop sound inputs, microphone inputs)."""
        inputs = self.raw("GetInputList").get("inputs", [])
        desktop = [i["inputName"] for i in inputs if i.get("inputKind") == "wasapi_output_capture"]
        mics = [i["inputName"] for i in inputs if i.get("inputKind") == "wasapi_input_capture"]
        return desktop, mics

    def split_voice_track(self) -> bool:
        """Track 1: game + mic, track 2: game only, track 3: mic only."""
        desktop, mics = self.audio_inputs()
        wanted = {**{n: {"1": True, "2": True, "3": False} for n in desktop},
                  **{n: {"1": True, "2": False, "3": True} for n in mics}}
        changed = False
        for name, tracks in wanted.items():
            now = self.raw("GetInputAudioTracks", {"inputName": name}).get("inputAudioTracks", {})
            if any(now.get(k) != v for k, v in tracks.items()):
                self.raw("SetInputAudioTracks", {"inputName": name, "inputAudioTracks": tracks})
                changed = True
        return changed

    def mic_muted(self) -> bool | None:
        _, mics = self.audio_inputs()
        if not mics:
            return None
        return all(self.raw("GetInputMute", {"inputName": m}).get("inputMuted") for m in mics)

    def set_mic_muted(self, muted: bool) -> bool:
        _, mics = self.audio_inputs()
        for m in mics:
            self.raw("SetInputMute", {"inputName": m, "inputMuted": muted})
        return bool(mics)

    def mic_devices(self) -> tuple[str, list[tuple[str, str]]] | None:
        """(the microphone OBS records now, [(device id, name)] of every microphone it can record).
        None when OBS has no microphone input. "default" means Windows' default microphone."""
        _, mics = self.audio_inputs()
        if not mics:
            return None
        items = self.raw("GetInputPropertiesListPropertyItems",
                         {"inputName": mics[0], "propertyName": "device_id"}).get("propertyItems", [])
        current = self.raw("GetInputSettings", {"inputName": mics[0]}).get("inputSettings", {})
        return (current.get("device_id") or "default",
                [(i["itemValue"], mic_name(i["itemName"])) for i in items
                 if i.get("itemValue") not in (None, "", "default") and i.get("itemEnabled", True)])

    def set_mic_device(self, device: str) -> bool:
        """Points OBS's (first) microphone input at device. Returns True if it changed."""
        found = self.mic_devices()
        if found is None or found[0] == device:
            return False
        _, mics = self.audio_inputs()
        self.raw("SetInputSettings", {"inputName": mics[0], "overlay": True,
                                      "inputSettings": {"device_id": device}})
        return True

    def display_source(self) -> str | None:
        name = self.cfg.get("obs_display_source")
        if name:
            return name
        inputs = self.raw("GetInputList", {"inputKind": "monitor_capture"}).get("inputs", [])
        return inputs[0]["inputName"] if inputs else None

    def capture_monitor(self, rect: tuple[int, int, int, int], only_if_missing: bool = False) -> str | None:
        """Points the display capture at the monitor at rect and fits it to the canvas.
        Returns the monitor's name when it switched, None otherwise."""
        source = self.display_source()
        if not source:
            return None
        for prop in ("monitor_id", "monitor"):   # newer and older OBS use different keys
            try:
                items = self.raw("GetInputPropertiesListPropertyItems",
                                 {"inputName": source, "propertyName": prop}).get("propertyItems", [])
            except OBSSDKRequestError:
                continue
            if items:
                break
        else:
            return None
        current = self.raw("GetInputSettings", {"inputName": source}).get("inputSettings", {}).get(prop)
        if only_if_missing and current in [i.get("itemValue") for i in items]:
            return None   # the captured monitor still exists: leave it
        target = windows.pick_monitor_item(items, rect)
        if target is None or target.get("itemValue") == current:
            return None
        self.raw("SetInputSettings", {"inputName": source, "overlay": True,
                                      "inputSettings": {prop: target["itemValue"]}})
        self.fit_to_canvas(source)
        return target["itemName"].split(":")[0].strip()

    def fit_to_canvas(self, source: str):
        """Scale the capture to fill the canvas (a 4K TV into a 1440p recording, etc.)."""
        try:
            video = self.raw("GetVideoSettings")
            scene = self.raw("GetCurrentProgramScene")
            scene = scene.get("sceneName") or scene.get("currentProgramSceneName")
            item = self.raw("GetSceneItemId", {"sceneName": scene, "sourceName": source})["sceneItemId"]
            self.raw("SetSceneItemTransform", {"sceneName": scene, "sceneItemId": item, "sceneItemTransform": {
                "positionX": 0, "positionY": 0, "alignment": 5,
                "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                "boundsWidth": video["baseWidth"], "boundsHeight": video["baseHeight"]}})
        except Exception:
            runtime.log.exception("could not fit the capture to the canvas")

    def record_status(self) -> tuple[bool, int]:
        r = self.call("get_record_status")
        return r.output_active, int(r.output_duration or 0)

    def screenshot(self, path: Path):
        r = self.call("get_current_program_scene")
        scene = getattr(r, "scene_name", None) or r.current_program_scene_name
        with self._lock:
            self._client.send("SaveSourceScreenshot", {
                "sourceName": scene,
                "imageFormat": "png",
                "imageFilePath": str(path),
            })


# ---------------------------------------------------------------- automatic OBS setup

# (name fragment, OBS simple-mode encoder). First match wins, so newer GPUs come first.
GPU_ENCODERS = [
    ("rtx 50", "nvenc_av1"), ("rtx 40", "nvenc_av1"), ("nvidia", "nvenc_hevc"),
    ("rx 9", "amd_av1"), ("rx 7", "amd_av1"), ("radeon", "amd_hevc"), ("amd", "amd_hevc"),
    ("arc", "qsv_av1"), ("intel", "qsv"),
]


# Bitrate (Kbps) for 1440p60 by codec; scaled by pixel count and frame rate for other settings.
BITRATE_1440P = {"av1": 8000, "hevc": 12000, "h264": 16000}


QUALITY_SCALE = {"light": 0.6, "balanced": 1.0, "high": 1.5, "max": 2.5}


RESOLUTIONS = {"1440p": 1440, "1080p": 1080, "720p": 720}


# the same codec on each GPU maker's encoder, in OBS simple-mode names
CODEC_ENCODERS = {
    "nvenc": {"av1": "nvenc_av1", "hevc": "nvenc_hevc", "h264": "nvenc"},
    "amd": {"av1": "amd_av1", "hevc": "amd_hevc", "h264": "amd"},
    "qsv": {"av1": "qsv_av1", "hevc": "qsv_hevc", "h264": "qsv"},
}


CODEC_RANK = {"av1": 3, "hevc": 2, "h264": 1}


def codec_of(encoder: str) -> str:
    return "av1" if "av1" in encoder else "hevc" if "hevc" in encoder else "h264"


def choose_encoder(best: str, wanted: str) -> str:
    """The encoder for the codec picked in Settings, never newer than what the GPU can do."""
    if wanted not in CODEC_RANK or best == "x264":
        return best
    if CODEC_RANK[wanted] > CODEC_RANK[codec_of(best)]:
        return best
    maker = best.split("_")[0]
    return CODEC_ENCODERS.get(maker, {}).get(wanted, best)


def output_size(width: int, height: int, resolution: str) -> tuple[int, int]:
    """Scaled-down recording size for a resolution choice (never bigger than the screen)."""
    target = RESOLUTIONS.get(resolution)
    if not target or target >= height:
        return width, height
    return int(round(width * target / height / 2)) * 2, target


def buffer_memory_mb(cfg: dict, width: int, height: int, encoder: str) -> int:
    """About how much disk space the last minutes take with these settings."""
    ow, oh = output_size(width, height, cfg.get("resolution", "native"))
    bitrate = pick_bitrate(encoder, ow, oh, int(cfg.get("fps", 60)), cfg.get("quality", "balanced"))
    voice = bool(cfg.get("voice_track", True))
    return int(bitrate * int(cfg["buffer_minutes"]) * 60 / 8 / 1000 * (1.6 if voice else 1.25))


def gpu_names() -> list[str]:
    if not runtime.IS_WINDOWS:
        return []
    r = media.run_quiet(["powershell", "-NoProfile", "-Command",
                   "(Get-CimInstance Win32_VideoController).Name"])
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def pick_encoder(names: list[str], failed: list[str] | tuple = ()) -> str:
    """Best encoder across all GPUs, so a discrete card wins over the CPU's built-in graphics.
    failed: encoders that wouldn't start on this PC before; the next one down is used instead."""
    lows = [n.lower() for n in names]
    best = next((encoder for fragment, encoder in GPU_ENCODERS if any(fragment in low for low in lows)), "x264")
    return next((e for e in [best, *fallback_encoders(best)] if e not in failed), "x264")


def fallback_encoders(encoder: str) -> list[str]:
    """What to try when an encoder won't start: the same maker's H.264 (every card that encodes at
    all has it), then the CPU. A card's name doesn't say it can encode: a laptop's GeForce MX has no
    encoder, and Quick Sync can be missing from Intel graphics; x264 runs on any PC."""
    maker = encoder.split("_")[0]
    h264 = CODEC_ENCODERS.get(maker, {}).get("h264")
    return ([h264] if h264 and h264 != encoder else []) + (["x264"] if encoder != "x264" else [])


def pick_bitrate(encoder: str, width: int, height: int, fps: int = 60, quality: str = "balanced") -> int:
    scale = (width * height) / (2560 * 1440)
    scale = max(0.5, scale) * (fps / 60) ** 0.7 * QUALITY_SCALE.get(quality, 1.0)  # motion costs less than pixels
    return int(round(BITRATE_1440P[codec_of(encoder)] * scale / 500) * 500)


# Settings → Colours: OBS colour correction for an HDR screen recorded in normal colours
# (saturation 0.6 is like ffmpeg eq=saturation=1.6)
COLOUR_BOOST = {
    "natural": None,
    "soft": {"saturation": 0.3, "contrast": 0.06},
    "vivid": {"saturation": 0.6, "contrast": 0.1},
    "max": {"saturation": 1.0, "contrast": 0.15},
}


def obs_plan(cfg: dict, width: int, height: int, encoder: str, obs_version: str, hdr: bool = False,
             white: int | None = None) -> dict:
    """The OBS settings Capture Menu wants: video size/FPS and simple-output profile keys.
    With voice_track on, recordings get 3 audio tracks: 1 = everything, 2 = game, 3 = mic.
    OBS's Simple mode only writes extra tracks with a quality preset (not "same as stream"),
    so the buffer is capped by size instead of bitrate. white is Windows' SDR white level (nits)
    on an HDR screen, so OBS's normal colours are as bright as Windows shows them."""
    encoder = choose_encoder(encoder, cfg.get("video_codec", "auto"))
    fps = int(cfg.get("fps", 60))
    quality = cfg.get("quality", "balanced")
    out_w, out_h = output_size(width, height, cfg.get("resolution", "native"))
    bitrate = pick_bitrate(encoder, out_w, out_h, fps, quality)
    buffer_s = int(cfg["buffer_minutes"]) * 60
    voice = bool(cfg.get("voice_track", True))
    major_minor = tuple(int(x) for x in re.findall(r"\d+", obs_version)[:2] or [0, 0])
    fmt = "hybrid_mp4" if major_minor >= (30, 2) else "mp4"
    hdr = hdr and codec_of(encoder) in ("hevc", "av1")      # H.264 has no 10-bit HDR
    # an HDR screen recorded in normal colours gets a light colour boost, unless Colours is Natural
    vivid = COLOUR_BOOST.get(cfg.get("colours", "vivid")) if white and not hdr else None
    return {
        "video": {"baseWidth": width, "baseHeight": height, "outputWidth": out_w,
                  "outputHeight": out_h, "fpsNumerator": fps, "fpsDenominator": 1},
        "profile": [
            ("Output", "Mode", "Simple"),
            ("SimpleOutput", "StreamEncoder", encoder),
            ("SimpleOutput", "RecEncoder", encoder),
            ("SimpleOutput", "VBitrate", str(bitrate)),
            ("SimpleOutput", "RecQuality",
             ("HQ" if quality in ("high", "max") else "Small") if voice else "Stream"),
            ("SimpleOutput", "RecTracks", "7" if voice else "1"),
            ("SimpleOutput", "RecFormat2", fmt),
            ("SimpleOutput", "RecFormat", fmt),
            ("SimpleOutput", "RecRB", "false"),     # the last minutes go to disk (BUFFER_DIR), not RAM
            ("Video", "ColorFormat", "P010" if hdr else "NV12"),
            ("Video", "ColorSpace", "2100PQ" if hdr else "709"),
            ("Video", "ColorRange", "Partial"),
        ] + ([("Video", "SdrWhiteLevel", str(white))] if white else []),
        "hdr": hdr,
        "vivid": vivid,
        "force_sdr": not hdr,   # an HDR screen in normal colours: Windows' conversion (no-op on SDR screens)
        "voice_track": voice,
        "summary": (f"{out_w}×{out_h} · {fps} FPS · {encoder.replace('_', ' ').upper()} · "
                    + (f"{quality} quality · voice on its own track" if voice else f"{bitrate} Kbps")
                    + f" · {buffer_s // 60} min" + (" · HDR" if hdr else "")
                    + (f" · {white} nits" if white else "") + (f" · {cfg.get('colours', 'vivid')} colours" if vivid else "")),
    }


def obs_exe_path() -> str | None:
    if not runtime.IS_WINDOWS:
        return None
    r = media.run_quiet(["powershell", "-NoProfile", "-Command",
                   "(Get-Process obs64 -ErrorAction SilentlyContinue | Select-Object -First 1).Path"])
    return r.stdout.strip() or None


def find_obs_exe() -> str | None:
    """obs64.exe from OBS's install record, else the default install folder."""
    if not runtime.IS_WINDOWS:
        return None
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\OBS Studio") as key:
                exe = Path(winreg.QueryValueEx(key, "")[0]) / "bin" / "64bit" / "obs64.exe"
                if exe.exists():
                    return str(exe)
        except OSError:
            continue
    exe = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "obs-studio" / "bin" / "64bit" / "obs64.exe"
    return str(exe) if exe.exists() else None


def launch_obs(exe: str | Path):
    """Starts OBS hidden in the tray, without its "did not properly shut
    down, run in Safe Mode?" question. That question waits on screen and nothing records meanwhile;
    it comes after Windows ends OBS while it's still closing (a restart with a long replay buffer).
    OBS 32 dropped --disable-shutdown-check and asks whenever it finds a run file left in .sentinel,
    so when no OBS is running those leftovers go first. The flag stays for older OBS."""
    if not obs_running():
        sentinel = Path(os.environ.get("APPDATA", str(Path.home()))) / "obs-studio" / ".sentinel"
        for f in sentinel.glob("run_*"):
            try:
                f.unlink()
                runtime.log.info("cleared OBS's unclean-shutdown mark: %s", f.name)
            except OSError:
                pass
    windows.launch_outside([str(exe), "--minimize-to-tray", "--disable-shutdown-check"],
                   cwd=str(Path(exe).parent), flags=0x00000008 | 0x00000200)  # DETACHED, NEW_PROCESS_GROUP


def start_obs() -> bool:
    """Starts OBS hidden in the tray (Capture Menu starts its recording)."""
    exe = find_obs_exe()
    if not exe:
        runtime.log.warning("OBS not found")
        return False
    launch_obs(exe)
    runtime.log.info("started OBS: %s", exe)
    return True


def obs_running() -> bool:
    if not runtime.IS_WINDOWS:
        return False
    r = media.run_quiet(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"])
    return "obs64.exe" in r.stdout.lower()

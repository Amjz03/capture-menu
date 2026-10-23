"""Capture Menu: a PS5-style Create button for Windows.

Press the hotkey while playing and a menu asks what you want:
  - save the last 30s / 1 min / ... / everything in the buffer
  - start or stop a recording
  - take a screenshot
Picked too short? Just open the menu again and pick a longer one: the new clip
still covers the earlier moment, and the first clip is kept too.
Every capture goes into a folder named after the game (or app) that was on
screen when you pressed the hotkey, like the PS5 media gallery.
After each capture a notification shows its thumbnail, and the menu's Recent
row opens a viewer to check it right away (play, scrub, delete).

Built on OBS Studio (replay buffer + WebSocket) and ffmpeg for trimming.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

# Qt Multimedia (video player + its FFmpeg backend, ~25 MB) loads the first time a video
# is opened, not at startup: most of the time the app just waits for the hotkey.
QtMultimedia = QtMultimediaWidgets = None


def load_multimedia() -> bool:
    global QtMultimedia, QtMultimediaWidgets
    if QtMultimedia is None:
        try:
            from PySide6 import QtMultimedia as mm, QtMultimediaWidgets as mmw
        except ImportError:  # viewer falls back to the default video player
            return False
        QtMultimedia, QtMultimediaWidgets = mm, mmw
    return True

import obsws_python as obsws
from obsws_python.error import OBSSDKRequestError

FROZEN = getattr(sys, "frozen", False)          # running as a built .exe
APP_DIR = Path(sys.executable if FROZEN else __file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
CONFIG_PATH = APP_DIR / "config.json"
STATE_PATH = APP_DIR / "state.json"
IS_WINDOWS = sys.platform == "win32"

DEFAULTS = {
    "hotkey": "alt+c",
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "clips_dir": str(Path.home() / "Videos" / "Clips"),
    "screenshots_dir": "",      # empty: screenshots go in clips_dir with the clips
    "language": "auto",         # auto (Windows' language) / en / ar
    "durations_seconds": [15, 30, 60, 180, 300, 900, 1800],
    "buffer_minutes": 30,
    "game_names": {},
    "controller_button": "create",
    "controller_hold_ms": 0,
    "capture_screen": "follow",  # follow (the game's screen) / main / a screen's id from screen_id()
    "mic_device": "default",    # default (Windows' microphone) / an OBS device id
    "obs_display_source": "",
    "obs_auto_setup": True,
    "double_press_seconds": 30,
    "sounds": True,
    "rumble": True,
    "storage_warn_gb": 200,
    "voice_track": True,
    "hdr": "auto",              # auto: HDR clips while Windows HDR is on for the game's screen / off
    "colours": "vivid",         # natural / soft / vivid / max: COLOUR_BOOST for an HDR screen recorded in normal colours
    "resolution": "native",     # native / 1440p / 1080p / 720p
    "fps": 60,
    "quality": "balanced",      # light / balanced / high / max
    "video_codec": "auto",      # auto (best the GPU has) / av1 / hevc / h264
    "start_with_windows": True,
    "record_indicator": "top-left",   # top-left / top-right / off
}

logging.basicConfig(
    filename=APP_DIR / "capture_menu.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
log = logging.getLogger("capture_menu")


# ---------------------------------------------------------------- language
# Every on-screen text is written in English and passed through tr(). Other languages live in
# assets/lang/<code>.json, which maps the English text to the translation ({name} fields stay).

LANGUAGES = {"en": "English", "ar": "العربية"}
LANG = "en"
_TRANSLATIONS: dict[str, str] = {}


def system_language() -> str:
    """Windows' display language, if Capture Menu has it; English otherwise."""
    if IS_WINDOWS:
        try:
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            if primary == 0x01:
                return "ar"
        except Exception:
            pass
    return "en"


def set_language(choice: str):
    global LANG, _TRANSLATIONS
    LANG = system_language() if choice not in LANGUAGES else choice
    _TRANSLATIONS = {}
    if LANG != "en":
        try:
            _TRANSLATIONS = json.loads((BUNDLE_DIR / "assets" / "lang" / f"{LANG}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.exception("could not load the %s translation", LANG)
            LANG = "en"


def tr(text: str, **fields) -> str:
    """The text in the chosen language, with {fields} filled in."""
    out = _TRANSLATIONS.get(text) or text
    return out.format(**fields) if fields else out


def is_rtl() -> bool:
    return LANG == "ar"


def lead():
    """Where a line of text starts: the left, or the right in a right-to-left language.
    Absolute, because Qt mirrors left and right again on its own in a right-to-left window."""
    return (Qt.AlignRight | Qt.AlignAbsolute) if is_rtl() else Qt.AlignLeft


def forward(key: int) -> int:
    """+1 or -1 for ← → in a row of tiles: the arrows follow the screen, which is mirrored in Arabic."""
    step = 1 if key == Qt.Key_Right else -1
    return -step if is_rtl() else step


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        cfg.update({k: v for k, v in user.items() if v not in ("", None)})
        if user.get("capture_follow_game") is False and "capture_screen" not in user:
            cfg["capture_screen"] = "main"   # up to 0.0.10 "Follow the game's screen" off kept the main screen
    return cfg


def save_config(changes: dict):
    """Writes only the given keys into config.json, keeping everything else (like the OBS password)."""
    user = {}
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    user.update(changes)
    CONFIG_PATH.write_text(json.dumps(user, indent=2, ensure_ascii=False), encoding="utf-8")


def duration_label(seconds: int | None, short: bool = False) -> str:
    if seconds is None:
        return tr("Everything")
    if seconds < 60:
        return tr("{n} sec", n=seconds)
    minutes = seconds // 60
    return tr("{n} min", n=minutes) if short or minutes != 1 else tr("1 minute")


def clock_precise(ms: int) -> str:
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms // 100 % 10}"


def clock(ms: int) -> str:
    s = ms // 1000
    h, m, s = s // 3600, s // 60 % 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------- OBS

class ObsOffline(Exception):
    pass


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
        try:
            return self.call("get_replay_buffer_status").output_active
        except OBSSDKRequestError as e:
            if e.code == 604:   # replay buffer not enabled in OBS yet (fresh install)
                return False
            raise

    def ensure_buffer(self) -> bool:
        """Starts the replay buffer if it is off. Returns True if it was already running."""
        if self.buffer_active():
            return True
        self.call("start_replay_buffer")
        return False

    def buffer_seconds(self) -> int:
        try:
            s = self.call("get_output_settings", "Replay Buffer").output_settings
            return int(s.get("max_time_sec") or 0) or self.cfg["buffer_minutes"] * 60
        except Exception:
            return self.cfg["buffer_minutes"] * 60

    def buffered_ms(self) -> int | None:
        """How long the replay buffer has been filling (None if OBS can't say)."""
        try:
            return int(self.call("get_output_status", "Replay Buffer").output_duration or 0)
        except Exception:
            return None

    def raw(self, request: str, data: dict | None = None) -> dict:
        return self.call("send", request, data, True) or {}

    def apply_plan(self, plan: dict) -> bool:
        """Applies the plan; returns True if anything changed (OBS then needs a restart)."""
        changed = False
        video = self.raw("GetVideoSettings")
        if any(video.get(k) != v for k, v in plan["video"].items()):
            self.raw("SetVideoSettings", plan["video"])
            changed = True
        for category, name, value in plan["profile"]:
            current = self.raw("GetProfileParameter", {"parameterCategory": category,
                                                       "parameterName": name}).get("parameterValue")
            if current != value:
                self.raw("SetProfileParameter", {"parameterCategory": category,
                                                 "parameterName": name, "parameterValue": value})
                changed = True
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
        target = pick_monitor_item(items, rect)
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
            log.exception("could not fit the capture to the canvas")

    def last_replay(self) -> str | None:
        try:
            return self.call("get_last_replay_buffer_replay").saved_replay_path
        except OBSSDKRequestError:
            return None

    def save_replay(self, timeout: float = 60) -> Path:
        before = self.last_replay()
        self.call("save_replay_buffer")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.3)
            path = self.last_replay()
            if path and path != before and Path(path).exists():
                wait_until_written(Path(path))
                return Path(path)
        raise TimeoutError("OBS did not report the saved replay")

    def record_status(self) -> tuple[bool, int]:
        r = self.call("get_record_status")
        return r.output_active, int(r.output_duration or 0)

    def start_record(self):
        self.call("start_record")

    def stop_record(self) -> Path:
        return Path(self.call("stop_record").output_path)

    def screenshot(self, path: Path):
        r = self.call("get_current_program_scene")
        scene = getattr(r, "scene_name", None) or r.current_program_scene_name
        with self._lock:
            self._client.send("SaveSourceScreenshot", {
                "sourceName": scene,
                "imageFormat": "png",
                "imageFilePath": str(path),
            })


def wait_until_written(path: Path, timeout: float = 30):
    """Waits until OBS has finished writing the file (its size stops changing)."""
    last, deadline = -1, time.monotonic() + timeout
    while time.monotonic() < deadline:
        size = path.stat().st_size
        if size > 0 and size == last:
            return
        last = size
        time.sleep(0.5)


# ---------------------------------------------------------------- ffmpeg

def find_tool(name: str) -> str | None:
    local = APP_DIR / f"{name}.exe"
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found or not IS_WINDOWS:
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
QUIET = 0x08000000 | 0x00004000 if IS_WINDOWS else 0   # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS


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


def cut_tail(src: Path, seconds: int | None, out: Path) -> float | None:
    """Writes the last `seconds` of src to out without re-encoding, then removes src.
    None = keep the whole file. Returns the clip length in seconds."""
    total = media_duration(src)
    if seconds is None or (total is not None and seconds >= total - 0.5):
        shutil.move(str(src), out)
        return total
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is not installed")
    r = run_quiet([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                   "-sseof", f"-{seconds}", "-i", str(src),
                   "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(out)])
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(r.stderr.strip() or "trimming failed")
    src.unlink()
    return float(seconds)


# ---------------------------------------------------------------- which game is on screen

DESKTOP = "Desktop"
# Windows shell and system windows: captures taken over these go to "Desktop"
SHELL_EXES = {
    "explorer.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "searchhost.exe", "searchapp.exe", "applicationframehost.exe", "lockapp.exe",
    "textinputhost.exe", "python.exe", "pythonw.exe",
}
# Names an exe can report that say nothing about which game it is
GENERIC_NAMES = {
    "", "unreal engine", "unrealgame", "ue4", "ue5", "bootstrappackagedgame",
    "unity", "unity player", "game", "launcher", "client", "application",
    "microsoft® windows® operating system", "microsoft windows operating system",
}
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


def safe_folder_name(name: str) -> str:
    name = re.sub(r"[™®©]", "", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")[:80].strip()
    if not name:
        return DESKTOP
    return name + "_" if name.upper() in RESERVED else name


def _exe_version_string(exe_path: str, field: str) -> str:
    """Reads ProductName / FileDescription from the exe's version info."""
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(exe_path, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(exe_path, 0, size, data):
        return ""
    ptr, n = ctypes.c_void_p(), ctypes.c_uint()
    langs = [(0x0409, 0x04B0)]
    if ver.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) \
            and n.value >= 4:
        pair = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint16 * 2)).contents
        langs.insert(0, (pair[0], pair[1]))
    for lang, codepage in langs:
        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{field}"
        if ver.VerQueryValueW(data, key, ctypes.byref(ptr), ctypes.byref(n)) and n.value:
            return ctypes.wstring_at(ptr, n.value).rstrip("\x00").strip()
    return ""


def foreground_app(cfg: dict) -> str:
    """Name of the game or app in the foreground, used as its folder name."""
    if not IS_WINDOWS:
        return DESKTOP
    try:
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = wintypes.HWND
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return DESKTOP
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe_path = ""
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if handle:
            buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                exe_path = buf.value
            kernel32.CloseHandle(handle)

        exe = Path(exe_path).name.lower()
        overrides = {k.lower(): v for k, v in cfg.get("game_names", {}).items()}
        if exe in overrides:
            return safe_folder_name(overrides[exe])
        if exe in SHELL_EXES or pid.value == os.getpid():
            return DESKTOP
        if exe_path:
            for field in ("ProductName", "FileDescription"):
                name = _exe_version_string(exe_path, field)
                if re.sub(r"[™®©]", "", name).strip().lower() not in GENERIC_NAMES:
                    return safe_folder_name(name)
        if title.value.strip():
            return safe_folder_name(title.value)
        return safe_folder_name(Path(exe_path).stem) if exe_path else DESKTOP
    except Exception:
        log.exception("could not detect the foreground app")
        return DESKTOP


# ---------------------------------------------------------------- which screen the game is on

if IS_WINDOWS:
    from ctypes import wintypes

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", ctypes.c_wchar * 32)]


def foreground_screen() -> dict | None:
    """The monitor showing the foreground window, and whether that window fills it
    (a game in fullscreen or borderless). None when it can't be told (not Windows)."""
    if not IS_WINDOWS:
        return None
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFOEXW)]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
            return None
        win, mon = wintypes.RECT(), info.rcMonitor
        user32.GetWindowRect(hwnd, ctypes.byref(win))
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        covers = (win.left <= mon.left and win.top <= mon.top
                  and win.right >= mon.right and win.bottom >= mon.bottom)
        return {"device": info.szDevice, "rect": (mon.left, mon.top, mon.right, mon.bottom),
                "fullscreen": covers and cls.value not in ("Progman", "WorkerW"),
                "own": pid.value == os.getpid()}
    except Exception:
        log.exception("could not read the foreground monitor")
        return None


def screen_for(info: dict | None) -> QtGui.QScreen:
    """The Qt screen matching a foreground_screen() result; falls back to the cursor's screen."""
    if info:
        screens = QtGui.QGuiApplication.screens()
        for s in screens:
            if s.name() == info["device"]:
                return s
        for s in screens:   # Qt keeps each screen's native top-left corner
            if (s.geometry().left(), s.geometry().top()) == info["rect"][:2]:
                return s
    return QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos()) or QtGui.QGuiApplication.primaryScreen()


def screen_id(s: QtGui.QScreen) -> str:
    """A screen's lasting name for config.json: its model and serial number (Windows' DISPLAY1, 2…
    can swap after a restart or a new cable)."""
    return f"{s.model() or s.name()}#{s.serialNumber() or s.name()}"


def screen_px_rect(s: QtGui.QScreen) -> tuple[int, int, int, int]:
    """The screen on Windows' desktop in real pixels, like foreground_screen()'s rect (Qt keeps
    the native top-left corner, but its size is scaled down by Windows' display scale)."""
    g, dpr = s.geometry(), s.devicePixelRatio()
    return g.left(), g.top(), g.left() + round(g.width() * dpr), g.top() + round(g.height() * dpr)


def screen_label(s: QtGui.QScreen) -> str:
    left, top, right, bottom = screen_px_rect(s)
    screens = QtGui.QGuiApplication.screens()
    name = s.model() or tr("Screen {n}", n=screens.index(s) + 1 if s in screens else 1)
    if s is QtGui.QGuiApplication.primaryScreen():
        return tr("{name} · {w}×{h} · main", name=name, w=right - left, h=bottom - top)
    return f"{name} · {right - left}×{bottom - top}"


def chosen_screen(choice: str) -> QtGui.QScreen | None:
    """The screen picked in Settings → Recording screen; None to follow the game (also when the
    picked screen isn't connected right now)."""
    if choice in ("", "follow"):
        return None
    if choice == "main":
        return QtGui.QGuiApplication.primaryScreen()
    screens = QtGui.QGuiApplication.screens()
    exact = [s for s in screens if screen_id(s) == choice]
    if exact:
        return exact[0]
    model = choice.split("#")[0]    # same screen on another cable or port: its model still matches
    same = [s for s in screens if (s.model() or s.name()) == model]
    return same[0] if len(same) == 1 else None


def game_screen() -> QtGui.QScreen:
    return screen_for(foreground_screen())


_ui_screen: QtGui.QScreen | None = None


def ui_screen(fresh: bool = False) -> QtGui.QScreen:
    """The screen Capture Menu's pages open on. It's picked (the game's screen) when the app is opened
    from outside: the Create button, the hotkey, the tray, a notice. Every page reached from there
    (Settings, the gallery, the viewer, and Back) stays on it. Picking it again on each page followed
    whatever window was in front once the last page had closed, often one on another monitor."""
    global _ui_screen
    if fresh or _ui_screen is None or _ui_screen not in QtGui.QGuiApplication.screens():
        _ui_screen = game_screen()
    return _ui_screen


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class _PathInfo(ctypes.Structure):     # DISPLAYCONFIG_PATH_INFO, flattened
    _fields_ = [("src_adapter", _LUID), ("src_id", ctypes.c_uint32), ("src_mode", ctypes.c_uint32),
                ("src_flags", ctypes.c_uint32), ("tgt_adapter", _LUID), ("tgt_id", ctypes.c_uint32),
                ("tgt_mode", ctypes.c_uint32), ("tech", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                ("scaling", ctypes.c_uint32), ("refresh_num", ctypes.c_uint32), ("refresh_den", ctypes.c_uint32),
                ("scanline", ctypes.c_uint32), ("available", ctypes.c_int32), ("tgt_flags", ctypes.c_uint32),
                ("flags", ctypes.c_uint32)]


class _DeviceInfoHeader(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapter", _LUID), ("id", ctypes.c_uint32)]


class _SourceName(ctypes.Structure):
    _fields_ = [("header", _DeviceInfoHeader), ("name", ctypes.c_wchar * 32)]


class _AdvancedColor(ctypes.Structure):       # ..._GET_ADVANCED_COLOR_INFO (and _2 on Windows 11 24H2)
    _fields_ = [("header", _DeviceInfoHeader), ("value", ctypes.c_uint32), ("encoding", ctypes.c_uint32),
                ("bits", ctypes.c_uint32), ("mode", ctypes.c_uint32)]


class _SdrWhite(ctypes.Structure):           # DISPLAYCONFIG_SDR_WHITE_LEVEL
    _fields_ = [("header", _DeviceInfoHeader), ("level", ctypes.c_uint32)]


def _screen_paths() -> list[tuple[str, _PathInfo]]:
    """(device name, display path) for each active screen."""
    user32 = ctypes.windll.user32
    n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
    if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(n_paths), ctypes.byref(n_modes)):  # active paths
        return []
    paths = (_PathInfo * n_paths.value)()
    modes = (ctypes.c_byte * (64 * n_modes.value))()
    if user32.QueryDisplayConfig(2, ctypes.byref(n_paths), paths, ctypes.byref(n_modes), modes, None):
        return []
    found = []
    for path in paths[:n_paths.value]:
        src = _SourceName()
        src.header.type, src.header.size = 1, ctypes.sizeof(src)       # GET_SOURCE_NAME
        src.header.adapter, src.header.id = path.src_adapter, path.src_id
        if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(src)):
            found.append((src.name, path))
    return found


def sdr_white(device: str | None = None) -> int | None:
    """Windows' "SDR content brightness" on an HDR screen (the main screen when not given), in nits.
    OBS turns HDR screens into normal colours with its own white level (300 nits): when Windows'
    is lower, whites come out grey and the whole picture looks washed out."""
    if not IS_WINDOWS:
        return None
    try:
        device = device or main_screen_device()
        for name, path in _screen_paths():
            if name != device:
                continue
            white = _SdrWhite()
            white.header.type, white.header.size = 11, ctypes.sizeof(white)  # GET_SDR_WHITE_LEVEL
            white.header.adapter, white.header.id = path.tgt_adapter, path.tgt_id
            if not ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(white)) and white.level:
                return round(white.level * 80 / 1000)                       # 1000 = 80 nits
    except Exception:
        log.exception("could not read the SDR white level")
    return None


def hdr_screens() -> dict[str, bool]:
    """Windows HDR on or off for each screen, by its device name (DISPLAY1 and so on). Empty where it
    can't be told. Windows 11 24H2 says it directly; before that, "advanced colour" on means HDR."""
    if not IS_WINDOWS:
        return {}
    try:
        user32 = ctypes.windll.user32
        found = {}
        for name, path in _screen_paths():
            color = _AdvancedColor()
            color.header.type, color.header.size = 15, ctypes.sizeof(color)    # GET_ADVANCED_COLOR_INFO_2
            color.header.adapter, color.header.id = path.tgt_adapter, path.tgt_id
            if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(color)):
                found[name] = color.mode == 2                                   # ADVANCED_COLOR_MODE_HDR
                continue
            color.header.type, color.header.size = 9, ctypes.sizeof(color) - 4  # GET_ADVANCED_COLOR_INFO
            if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(color)):
                found[name] = bool(color.value & 0b10)                          # advancedColorEnabled
        return found
    except Exception:
        log.exception("could not read the HDR state")
        return {}


def main_screen_device() -> str | None:
    """Windows' name for the main screen (the one at 0,0), like the keys of hdr_screens()."""
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = wintypes.HANDLE
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFOEXW)]
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(user32.MonitorFromPoint(wintypes.POINT(0, 0), 1), ctypes.byref(info)):
            return info.szDevice
    except Exception:
        log.exception("could not find the main screen")
    return None


def windows_hdr(device: str | None = None) -> bool:
    """Is Windows HDR on for this screen (the main screen when not given)?"""
    screens = hdr_screens()
    device = device or (main_screen_device() if IS_WINDOWS else None)
    if device in screens:
        return screens[device]
    return len(screens) == 1 and any(screens.values())


def pick_monitor_item(items: list[dict], rect: tuple[int, int, int, int]) -> dict | None:
    """OBS lists monitors like "LG ULTRAGEAR: 2560x1440 @ 0,0 (Primary Monitor)".
    Finds the one at the same desktop position as rect (then by size if positions differ)."""
    by_size = []
    for item in items:
        m = re.search(r"(\d+)x(\d+) @ (-?\d+),(-?\d+)", item.get("itemName", ""))
        if not m:
            continue
        w, h, x, y = map(int, m.groups())
        if (x, y) == rect[:2]:
            return item
        if (w, h) == (rect[2] - rect[0], rect[3] - rect[1]):
            by_size.append(item)
    return by_size[0] if len(by_size) == 1 else None


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
        log.warning("GPU trim failed, using stream copy: %s", r.stderr.strip()[-300:])
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
                log.warning("NVENC export failed, using libx264")
                encoders = ["libx264"]
        else:
            raise RuntimeError("couldn't convert the clip")
        size = out.stat().st_size / 1024 / 1024
        if size_mb is None or size <= size_mb:
            return size
        video_kbps = int(video_kbps * size_mb / size * 0.93)
    return size


# ---------------------------------------------------------------- sound levels

# Levels are how loud something sounds, in %: 100 = as recorded, 200 = twice as loud (+10 dB),
# 50 = half as loud, 0 = muted. A volume bar in the viewer sets them, in steps of 25.
VOICE_MAX, GAME_MAX, LEVEL_STEP = 400, 200, 25


def level_gain(percent: int) -> float:
    """The amplitude factor for a loudness in %: loudness doubles every 10 dB."""
    return 0.0 if percent <= 0 else 10 ** (10 * math.log2(percent / 100) / 20)


def level_text(percent: int) -> str:
    if percent == 100:
        return tr("100% · as recorded")
    return tr("Muted") if percent <= 0 else f"\u200e{percent}%"   # LRM keeps "150%" in order in Arabic


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




# ---------------------------------------------------------------- storage

def human_size(nbytes: float) -> str:
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:.1f} {tr('GB')}"     # units are translated too ("2 ميجا")
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024 ** 2:.0f} {tr('MB')}"
    return f"{max(1, round(nbytes / 1024))} {tr('KB')}"


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def safe_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text).strip().rstrip(". ")[:60]


def folder_size_gb(folder: Path) -> float:
    total = 0
    for p in folder.rglob("*"):
        if p.is_file() and ".thumbs" not in p.parts:
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total / 1024 ** 3


# ---------------------------------------------------------------- recent captures

MEDIA_EXTS = {".mp4", ".mkv", ".mov", ".flv", ".png"}
SKIP_DIRS = {".thumbs", "Shared"}   # thumbnails and share copies aren't captures

# Where captures go when Windows won't let us use the chosen folder. Windows Security's
# "Controlled folder access" guards Videos, Documents, Pictures, Music and Desktop from apps it
# doesn't know, but not the user folder itself.
FALLBACK_CLIPS_DIR = Path.home() / "Capture Menu"


def usable_folder(path: Path) -> bool:
    """Whether we can create this folder and write a file in it. Controlled folder access answers a
    blocked folder with "file not found" or "access denied", so any OSError counts as blocked."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".capture-menu-{os.getpid()}.tmp"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError as e:
        log.warning("can't use %s: %s", path, e)
        return False


def controlled_folder_access_on() -> bool:
    """Windows Security's ransomware protection (blocks unknown apps from Videos, Documents…)."""
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender"
                             r"\Windows Defender Exploit Guard\Controlled Folder Access")
        return winreg.QueryValueEx(key, "EnableControlledFolderAccess")[0] == 1
    except OSError:
        return False


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


def capture_kind(path: Path) -> str:
    parts = path.stem.split("_")
    if parts[0] == "Screenshot":
        return tr("Screenshot")
    if parts[0] == "Recording":
        return tr("Recording")
    if parts[0] == "Clip" and len(parts) >= 4 and parts[3] == "trim":
        return tr("Trimmed clip")
    if parts[0] == "Clip" and len(parts) >= 4 and parts[3].endswith("s"):
        return tr("Clip · {length}", length=duration_label(int(parts[3][:-1]), short=True))
    return tr("Clip")


def time_ago(ts: float) -> str:
    s = int(time.time() - ts)
    if s < 60:
        return tr("just now")
    if s < 3600:
        return tr("{n} min ago", n=s // 60)
    if s < 86400:
        return tr("{n} h ago", n=s // 3600)
    d = datetime.fromtimestamp(ts)
    return f"{d.day} {tr(d.strftime('%b'))}"   # month names are translated too


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
    """About how much RAM OBS's replay buffer takes with these settings."""
    ow, oh = output_size(width, height, cfg.get("resolution", "native"))
    bitrate = pick_bitrate(encoder, ow, oh, int(cfg.get("fps", 60)), cfg.get("quality", "balanced"))
    voice = bool(cfg.get("voice_track", True))
    return int(bitrate * int(cfg["buffer_minutes"]) * 60 / 8 / 1000 * (1.6 if voice else 1.25))


def gpu_names() -> list[str]:
    if not IS_WINDOWS:
        return []
    r = run_quiet(["powershell", "-NoProfile", "-Command",
                   "(Get-CimInstance Win32_VideoController).Name"])
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def pick_encoder(names: list[str]) -> str:
    """Best encoder across all GPUs, so a discrete card wins over the CPU's built-in graphics."""
    lows = [n.lower() for n in names]
    for fragment, encoder in GPU_ENCODERS:
        if any(fragment in low for low in lows):
            return encoder
    return "x264"


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
            ("SimpleOutput", "RecRB", "true"),
            ("SimpleOutput", "RecRBTime", str(buffer_s)),
            # OBS drops the oldest video once either limit is hit. With a quality preset (voice
            # on) OBS records at constant quality, not at our bitrate, so busy scenes can run
            # well above it: leave room so "Last 30m" really holds 30 minutes. The cap is only
            # a ceiling; RAM in use is what the game actually produces.
            ("SimpleOutput", "RecRBSize",
             str(int(bitrate * buffer_s / 8 / 1000 * (2.5 if voice else 1.25)))),
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


_state_cache: tuple[float, dict] | None = None
_state_lock = threading.Lock()


def load_state() -> dict:
    """state.json, kept in memory until the file changes (it's read on every tile paint)."""
    global _state_cache
    with _state_lock:
        try:
            mtime = STATE_PATH.stat().st_mtime
        except OSError:
            return {}
        if _state_cache is None or _state_cache[0] != mtime:
            try:
                _state_cache = (mtime, json.loads(STATE_PATH.read_text(encoding="utf-8")))
            except Exception:
                return {}
        return json.loads(json.dumps(_state_cache[1]))   # a copy callers may change


def save_state(state: dict):
    global _state_cache
    with _state_lock:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        _state_cache = (STATE_PATH.stat().st_mtime, json.loads(json.dumps(state)))


def obs_exe_path() -> str | None:
    if not IS_WINDOWS:
        return None
    r = run_quiet(["powershell", "-NoProfile", "-Command",
                   "(Get-Process obs64 -ErrorAction SilentlyContinue | Select-Object -First 1).Path"])
    return r.stdout.strip() or None


def find_obs_exe() -> str | None:
    """obs64.exe from OBS's install record, else the default install folder."""
    if not IS_WINDOWS:
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


def launch_outside(cmd: list[str], cwd: str | None = None, flags: int = 0) -> subprocess.Popen:
    """Starts a program that isn't ours (OBS, Explorer, the update installer) without handing it Capture
    Menu's own DLL folder. The .exe build puts _internal on the DLL search path, ahead of System32, and a
    child process inherits that: OBS then loaded _internal\\VCRUNTIME140.dll and held it open, so the next
    update couldn't replace it."""
    if not (IS_WINDOWS and FROZEN):
        return subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
    k32 = ctypes.windll.kernel32
    buf = ctypes.create_unicode_buffer(1024)
    ours = buf.value if k32.GetDllDirectoryW(1024, buf) else None
    bundle = os.path.normcase(str(BUNDLE_DIR))
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if p and not os.path.normcase(p).startswith(bundle))
    k32.SetDllDirectoryW(None)        # the child gets Windows' normal search order
    try:
        return subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags)
    finally:
        k32.SetDllDirectoryW(ours)    # and we keep ours


def launch_obs(exe: str | Path):
    """Starts OBS hidden in the tray with the replay buffer on, without its "did not properly shut
    down, run in Safe Mode?" question. That question waits on screen and nothing records meanwhile;
    it comes after Windows ends OBS while it's still closing (a restart with a long replay buffer).
    OBS 32 dropped --disable-shutdown-check and asks whenever it finds a run file left in .sentinel,
    so when no OBS is running those leftovers go first. The flag stays for older OBS."""
    if not obs_running():
        sentinel = Path(os.environ.get("APPDATA", str(Path.home()))) / "obs-studio" / ".sentinel"
        for f in sentinel.glob("run_*"):
            try:
                f.unlink()
                log.info("cleared OBS's unclean-shutdown mark: %s", f.name)
            except OSError:
                pass
    launch_outside([str(exe), "--startreplaybuffer", "--minimize-to-tray", "--disable-shutdown-check"],
                   cwd=str(Path(exe).parent), flags=0x00000008 | 0x00000200)  # DETACHED, NEW_PROCESS_GROUP


def start_obs() -> bool:
    """Starts OBS hidden in the tray with the replay buffer on."""
    exe = find_obs_exe()
    if not exe:
        log.warning("OBS not found")
        return False
    launch_obs(exe)
    log.info("started OBS: %s", exe)
    return True


def obs_running() -> bool:
    if not IS_WINDOWS:
        return False
    r = run_quiet(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"])
    return "obs64.exe" in r.stdout.lower()


# ---------------------------------------------------------------- logic

class Controller(QtCore.QObject):
    toast = QtCore.Signal(str, str)        # text, kind: info / ok / error
    captured = QtCore.Signal(str, str)     # detail line, path of the new capture
    trimmed = QtCore.Signal(str)           # path of a freshly trimmed clip
    remixed = QtCore.Signal(str)           # path of a clip whose voice / game levels changed
    recording = QtCore.Signal(bool)        # manual recording started / stopped
    shared = QtCore.Signal(str, str)       # detail line, path of the share-ready copy
    copy_file = QtCore.Signal(str)         # put this file on the clipboard (main thread)
    storage = QtCore.Signal(dict)          # {"used_gb", "free_gb", "over", "low"}
    library_changed = QtCore.Signal()
    status = QtCore.Signal(dict)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.obs = Obs(cfg)
        self.best_encoder: str | None = None     # found during OBS setup; Settings uses it
        self.screen_px: tuple[int, int] | None = None
        # A folder Windows won't let us use (Controlled folder access, a missing drive) never stops the
        # app: captures go to FALLBACK_CLIPS_DIR for now, and `blocked` says which folder was refused.
        # Nothing is written to config.json, so the chosen folder is used again once it's allowed.
        self.blocked: Path | None = None
        self.clips_dir = Path(cfg["clips_dir"])
        if not usable_folder(self.clips_dir):
            self.blocked, self.clips_dir = self.clips_dir, FALLBACK_CLIPS_DIR
            self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir = Path(cfg["screenshots_dir"]) if cfg.get("screenshots_dir") else self.clips_dir
        if self.shots_dir != self.clips_dir and not usable_folder(self.shots_dir):
            self.blocked = self.blocked or self.shots_dir
            self.shots_dir = self.clips_dir
        # where captures live: the clips folder, plus the screenshots folder when it's somewhere else
        self.roots = [self.clips_dir] + ([self.shots_dir] if self.clips_dir not in
                                         (self.shots_dir, *self.shots_dir.parents) else [])
        self._busy = threading.Lock()
        self.record_game: str | None = None
        self.thumbs_dir = self.clips_dir / ".thumbs"
        self.thumbs_dir.mkdir(exist_ok=True)
        if IS_WINDOWS:
            ctypes.windll.kernel32.SetFileAttributesW(str(self.thumbs_dir), 0x02)  # hidden
        self.previews_dir = self.thumbs_dir / "previews"
        self.previews_dir.mkdir(exist_ok=True)
        self.recent: list[Path] = self._scan_recent()
        self._lengths_file = self.thumbs_dir / "lengths.json"
        self._lengths_lock = threading.Lock()
        self.lengths: dict[Path, float | None] = self._load_lengths()
        self._warned: set[str] = set()
        self.last_storage: dict = {}
        threading.Thread(target=self._remake_hdr_thumbs, daemon=True).start()

    def _remake_hdr_thumbs(self):
        """Until 0.0.16 OBS's HDR clips weren't taken for HDR, so their thumbnails and previews came
        out grey and washed out. Once per clips folder: make those again in normal colours."""
        done = self.thumbs_dir / "hdr-thumbs-v2"
        if done.exists():
            return
        try:
            fixed = False
            for p in self.all_captures():
                if is_hdr(p):
                    (self.thumbs_dir / (hashlib.md5(str(p).encode()).hexdigest() + ".jpg")).unlink(missing_ok=True)
                    self.preview_path(p).unlink(missing_ok=True)
                    make_thumb(p, self.thumbs_dir)
                    fixed = True
            done.touch()
            if fixed:
                safe_emit(self.library_changed)
        except Exception:
            log.exception("could not remake the HDR thumbnails")

    def preview_path(self, path: Path) -> Path:
        return self.previews_dir / (hashlib.md5(str(path).encode()).hexdigest() + ".mp4")

    def all_captures(self) -> list[Path]:
        files = {p for root in self.roots for p in root.rglob("*")   # a set: one folder may hold the other
                 if p.suffix.lower() in MEDIA_EXTS and not SKIP_DIRS & set(p.parts)}
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def _scan_recent(self, limit: int = 30) -> list[Path]:
        return self.all_captures()[:limit]

    # ---- favorites (kept in state.json, relative to the clips folder)
    def _fav_key(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.clips_dir))
        except ValueError:
            return str(path)

    def favorites(self) -> set[str]:
        return set(load_state().get("favorites", []))

    def is_favorite(self, path: Path) -> bool:
        return self._fav_key(path) in self.favorites()

    # ---- titles and notes (also in state.json; the file name never changes)
    def meta(self, path: Path) -> dict:
        return load_state().get("meta", {}).get(self._fav_key(path), {})

    def title_of(self, path: Path) -> str | None:
        return self.meta(path).get("title")

    def set_meta(self, path: Path, title: str, note: str):
        state = load_state()
        all_meta = state.setdefault("meta", {})
        entry = {k: v.strip() for k, v in (("title", title), ("note", note)) if v.strip()}
        if entry:
            all_meta[self._fav_key(path)] = entry
        else:
            all_meta.pop(self._fav_key(path), None)
        save_state(state)
        self.library_changed.emit()

    def toggle_favorite(self, path: Path) -> bool:
        state = load_state()
        favs = set(state.get("favorites", []))
        key = self._fav_key(path)
        favs.symmetric_difference_update({key})
        state["favorites"] = sorted(favs)
        save_state(state)
        self.library_changed.emit()
        return key in favs

    # ---- voice and game levels of one clip (the clip keeps its separate game and mic tracks)
    def mix_of(self, path: Path) -> tuple[int, int]:
        """Voice and game loudness of a clip in %, 100 = as recorded."""
        state, key = load_state(), self._fav_key(path)
        if key in state.get("levels", {}):
            m = state["levels"][key]
            return int(m.get("voice", 100)), int(m.get("game", 100))
        old = state.get("mix", {}).get(key)   # 0.0.2 kept dB; same loudness, nearest step
        if old:
            pct = lambda db: int(round(100 * 2 ** (db / 10) / LEVEL_STEP) * LEVEL_STEP)
            return pct(old.get("voice", 0)), pct(old.get("game", 0))
        return 100, 100

    def set_mix(self, path: Path, voice: int, game: int):
        self._bg(self._set_mix, path, voice, game)

    def _set_mix(self, path: Path, voice: int, game: int):
        tmp = path.with_name(path.name + ".part")   # not a capture, so the gallery never lists it
        try:
            remix_audio(path, voice, game, tmp)
            st = path.stat()
            os.replace(tmp, path)
            os.utime(path, (st.st_atime, st.st_mtime))     # same place in Recent and the gallery
            self.preview_path(path).unlink(missing_ok=True)   # a 720p preview copy has the old sound
            state = load_state()
            key = self._fav_key(path)
            state.get("mix", {}).pop(key, None)
            levels = state.setdefault("levels", {})
            if (voice, game) != (100, 100):
                levels[key] = {"voice": voice, "game": game}
            else:
                levels.pop(key, None)
            save_state(state)
            self.toast.emit(tr("Sound saved · your voice {voice} · game {game}",
                               voice=level_text(voice), game=level_text(game)), "ok")
        finally:
            tmp.unlink(missing_ok=True)
            self.remixed.emit(str(path))   # the viewer reloads the clip, saved or not

    # ---- storage warning (nothing is ever deleted automatically)
    def check_storage(self):
        def run():
            used = sum(folder_size_gb(root) for root in self.roots)
            free = shutil.disk_usage(self.clips_dir).free / 1024 ** 3
            limit = float(self.cfg.get("storage_warn_gb") or 0)
            info = {"used_gb": used, "free_gb": free, "limit_gb": limit,
                    "over": bool(limit) and used > limit, "low": free < 20}
            self.last_storage = info
            self.storage.emit(info)
            for flag, text in (("over", tr("Captures use {used} GB, over your {limit} GB limit"
                                           " · delete some in the gallery", used=f"{used:.0f}", limit=f"{limit:.0f}")),
                               ("low", tr("Only {free} GB free on this drive · delete some captures",
                                          free=f"{free:.0f}"))):
                if info[flag] and flag not in self._warned:
                    self._warned.add(flag)
                    self.toast.emit(text, "error")
                elif not info[flag]:
                    self._warned.discard(flag)
        threading.Thread(target=run, daemon=True).start()

    # ---- share & copy
    def share(self, src: Path, preset: str, without_voice: bool):
        self._bg(self._share, src, preset, without_voice, exclusive=False)

    def _share(self, src: Path, preset: str, without_voice: bool):
        info = SHARE_PRESETS[preset]
        folder = src.parent / "Shared"
        folder.mkdir(exist_ok=True)
        name = safe_filename(self.title_of(src) or "") or src.stem
        out = folder / f"{name}_{preset}{'_novoice' if without_voice else ''}.mp4"
        last = [-10]

        def progress(pct):
            if pct - last[0] >= 10:   # a notice every 10 %, not every frame
                last[0] = pct
                self.toast.emit(tr("Preparing for {target} · {pct}%", target=tr(info["label"]), pct=pct), "info")
        progress(0)
        size = export_for_share(src, out, info["size_mb"], without_voice, progress)
        self.copy_file.emit(str(out))
        make_thumb(out, self.thumbs_dir)
        voice = tr(" · without your voice") if without_voice else ""
        self.shared.emit(f"{tr(info['label'])} · {size:.1f} MB{voice}", str(out))

    def copy(self, path: Path):
        if is_hdr(path):   # Discord, WhatsApp and most players show HDR grey and washed out
            self.share(path, "phone", False)
            return
        self.copy_file.emit(str(path))
        self.toast.emit(tr("Copied · paste it with Ctrl+V · {name}", name=path.name), "ok")

    # ---- microphone
    def toggle_mic(self):
        def run():
            muted = self.obs.mic_muted()
            if muted is None:
                self.toast.emit(tr("No microphone in OBS · add one under Settings → Audio"), "error")
                return
            self.obs.set_mic_muted(not muted)
            self.toast.emit(tr("Mic off · your voice won't be recorded") if not muted else
                            tr("Mic on · your voice is recorded"), "info")
            self.refresh_status()
        self._bg(run, exclusive=False)

    def recent_items(self) -> list[Path]:
        self.recent = [p for p in self.recent if p.exists()]
        return self.recent

    def thumb(self, path: Path) -> Path | None:
        t = self.thumbs_dir / (hashlib.md5(str(path).encode()).hexdigest() + ".jpg")
        return t if t.exists() else None

    def _load_lengths(self) -> dict:
        """Clip lengths measured before, still valid if the file hasn't changed since."""
        try:
            saved = json.loads(self._lengths_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        lengths = {}
        for path, (mtime, seconds) in saved.items():
            p = Path(path)
            try:
                if p.stat().st_mtime == mtime:
                    lengths[p] = seconds
            except OSError:
                pass
        return lengths

    def save_lengths(self):
        with self._lengths_lock:
            data = {}
            for p, secs in list(self.lengths.items()):
                try:
                    data[str(p)] = [p.stat().st_mtime, secs]
                except OSError:
                    pass
            self._lengths_file.write_text(json.dumps(data), encoding="utf-8")

    def length_of(self, path: Path) -> float | None:
        """Cached clip length in seconds (None until known)."""
        return self.lengths.get(path)

    def _done(self, text: str, path: Path):
        make_thumb(path, self.thumbs_dir)
        if path.suffix.lower() != ".png":
            self.lengths[path] = media_duration(path)
            self.save_lengths()
        self.recent.insert(0, path)
        self.captured.emit(text, str(path))
        self.check_storage()

    def delete(self, path: Path) -> bool:
        """Moves a capture to the Recycle Bin."""
        moved = QtCore.QFile.moveToTrash(str(path))
        if isinstance(moved, tuple):
            moved = moved[0]
        if not moved:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                return False
        if self.is_favorite(path):
            self.toggle_favorite(path)
        if self.meta(path):
            self.set_meta(path, "", "")
        if t := self.thumb(path):
            t.unlink(missing_ok=True)
        self.preview_path(path).unlink(missing_ok=True)
        self.recent = [p for p in self.recent if p != path]
        return True

    def delete_many(self, paths: list[Path]) -> tuple[int, int]:
        """Recycle Bin for several captures; returns (how many, bytes freed)."""
        done = freed = 0
        for p in paths:
            size = file_size(p)
            if self.delete(p):
                done, freed = done + 1, freed + size
        self.check_storage()
        return done, freed

    def trim(self, src: Path, start_ms: int, end_ms: int, replace: bool):
        self._bg(self._trim, src, start_ms, end_ms, replace)

    def _trim(self, src: Path, start_ms: int, end_ms: int, replace: bool):
        out = src.parent / f"Clip_{self._stamp()}_trim{src.suffix}"
        mode = trim_clip(src, start_ms, end_ms, out)
        length = clock((end_ms - start_ms))
        if self.meta(src):
            m = self.meta(src)
            self.set_meta(out, m.get("title", ""), m.get("note", ""))
        if replace:
            self.delete(src)
        note = "" if mode == "precise" else tr(" · fast cut")
        self._done(tr("Length {length}", length=length) + note, out)
        self.trimmed.emit(str(out))

    @staticmethod
    def reveal(path: Path):
        if IS_WINDOWS:
            launch_outside(["explorer", f"/select,{path}"])
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.parent)))

    @staticmethod
    def open_external(path: Path):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def folder_for(self, game: str, root: Path | None = None) -> Path:
        folder = (root or self.clips_dir) / game
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # OBS calls and trimming run in the background so the menu never freezes
    def _bg(self, fn, *args, exclusive: bool = True):
        def run():
            if exclusive and not self._busy.acquire(blocking=False):
                self.toast.emit(tr("Hang on, still saving the last clip…"), "info")
                return
            try:
                fn(*args)
            except ObsOffline:
                self.toast.emit(tr("Can't reach OBS · make sure it's running, then try again"), "error")
            except Exception as e:
                log.exception("action failed")
                self.toast.emit(tr("Something went wrong: {error}", error=e), "error")
            finally:
                if exclusive:
                    self._busy.release()
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _stamp() -> str:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # ---- status
    def refresh_status(self):
        def run():
            try:
                rec, ms = self.obs.record_status()
                active = self.obs.buffer_active()
                st = {"online": True, "buffer": active, "buffer_seconds": self.obs.buffer_seconds(),
                      "buffered_ms": self.obs.buffered_ms() if active else 0,
                      "recording": rec, "record_ms": ms, "mic_muted": self.obs.mic_muted()}
            except Exception:
                st = {"online": False}
            self.status.emit(st)
        threading.Thread(target=run, daemon=True).start()

    def apply_mic(self):
        """The microphone picked in Settings. Only once it was picked here, so a microphone chosen
        in OBS itself is left alone until then."""
        wanted = self.cfg.get("mic_device", "default")
        state = load_state()
        if not state.get("mic_picked") or state.get("mic_device") == wanted:
            return
        if self.obs.mic_devices() is None:
            return      # no microphone in OBS (yet): try again next start
        if self.obs.set_mic_device(wanted):
            log.info("microphone: %s", wanted)
        state["mic_device"] = wanted
        save_state(state)

    def auto_setup(self, width: int, height: int):
        """First run (or a new monitor/GPU): configure OBS for this PC, then restart it once."""
        encoder = pick_encoder(gpu_names())
        self.best_encoder = encoder
        version = self.obs.raw("GetVersion").get("obsVersion", "0")
        # OBS records at the main screen's size, so that screen's HDR decides (a game on another
        # screen is converted by OBS either way)
        hdr = self.cfg.get("hdr", "auto") == "auto" and windows_hdr()
        plan = obs_plan(self.cfg, width, height, encoder, version, hdr,
                        sdr_white() if windows_hdr() else None)
        log.info("OBS plan: %s (Windows HDR %s)", plan["summary"], "on" if hdr else "off")
        if self.blocked:
            # OBS writes its replays to Videos by default, which Controlled folder access blocks for
            # OBS too: let it write next to our captures (the files are moved into place afterwards)
            incoming = self.thumbs_dir / "incoming"
            incoming.mkdir(parents=True, exist_ok=True)
            plan["profile"].append(("SimpleOutput", "FilePath", str(incoming)))
            plan["summary"] += f" · {incoming}"
        state = load_state()
        if state.get("obs_setup") == plan["summary"]:
            self.obs.set_colours(plan["force_sdr"], plan["vivid"])   # live: keeps the colours up to date
            return
        recording, _ = self.obs.record_status()
        if recording:
            return   # never interrupt a recording; try again next start
        self.toast.emit(tr("Setting up OBS · {summary}", summary=plan["summary"]), "info")
        if self.obs.buffer_active():
            self.obs.call("stop_replay_buffer")
            for _ in range(20):
                time.sleep(0.25)
                if not self.obs.buffer_active():
                    break
        changed = self.obs.apply_plan(plan)
        if changed and not self.restart_obs():
            self.obs.ensure_buffer()   # keep capturing with the old settings until OBS restarts
            self.toast.emit(tr("OBS is set up · restart OBS once to apply it"), "info")
        else:
            self.obs.ensure_buffer()
            self.toast.emit(tr("OBS is ready · {summary}", summary=plan["summary"]), "ok")
        state["obs_setup"] = plan["summary"]
        save_state(state)

    def restart_obs(self) -> bool:
        """Closes OBS the polite way (like clicking ✕) and starts it again with the buffer on."""
        path = obs_exe_path()
        if not path:
            return False
        run_quiet(["taskkill", "/IM", "obs64.exe"])
        for _ in range(80):
            time.sleep(0.25)
            if not obs_running():
                break
        else:
            return False
        launch_obs(path)
        for _ in range(60):
            time.sleep(0.5)
            try:
                self.obs.ensure_buffer()
                return True
            except Exception:
                continue
        return False

    def start_following(self):
        """Every 2 s: make sure OBS records the screen picked in Settings, or else the monitor a
        fullscreen game is on."""
        self._following = threading.Lock()
        self._follow_timer = QtCore.QTimer(self, interval=2000, timeout=self._follow_tick)
        self._follow_timer.start()

    def _follow_tick(self):
        screen = chosen_screen(self.cfg.get("capture_screen", "follow"))
        if screen is not None:     # a screen picked in Settings: always that one
            info = {"rect": screen_px_rect(screen), "fullscreen": True}
        else:
            info = foreground_screen()
            if not info or info["own"]:
                return
        # ask OBS only when the game's screen changed, or every 10 s to catch a vanished monitor
        key = (info["rect"], info["fullscreen"])
        now = time.monotonic()
        if key == getattr(self, "_follow_last", None) and now - getattr(self, "_follow_at", 0) < 10:
            return
        if not self._following.acquire(blocking=False):
            return
        self._follow_last, self._follow_at = key, now

        def run():
            try:
                # a fullscreen game moves the capture; anything else only fixes a capture
                # that points at a monitor that's gone (e.g. switched to "TV only")
                name = self.obs.capture_monitor(info["rect"], only_if_missing=not info["fullscreen"])
                if name:
                    log.info("capture moved to %s", name)
                    self.toast.emit(tr("Recording this screen · {name}", name=name), "info")
            except ObsOffline:
                pass
            except OBSSDKRequestError as e:
                if e.code != 207:    # 207: OBS is still starting; the next check (2 s later) works
                    log.exception("could not follow the game's screen")
            except Exception:
                log.exception("could not follow the game's screen")
            finally:
                self._following.release()
        threading.Thread(target=run, daemon=True).start()

    def startup(self, screen_size: tuple[int, int] | None = None):
        self.screen_px = screen_size

        def run():
            if IS_WINDOWS and not obs_running() and start_obs():
                for _ in range(60):    # OBS takes a few seconds at sign-in
                    time.sleep(0.5)
                    try:
                        self.obs.call("get_version")
                        break
                    except Exception:
                        continue
            self.check_storage()
            for p in self.recent[:8]:  # thumbnails and lengths for the Recent row
                make_thumb(p, self.thumbs_dir)
                if p.suffix.lower() != ".png" and p not in self.lengths:
                    self.lengths[p] = media_duration(p)
            self.save_lengths()
            try:
                self.apply_mic()
            except ObsOffline:
                pass
            except Exception:
                log.exception("couldn't pick the microphone in OBS")
            if screen_size and self.cfg.get("obs_auto_setup", True):
                try:
                    self.auto_setup(*screen_size)
                except ObsOffline:
                    pass
                except Exception:
                    log.exception("OBS auto setup failed")
                    self.toast.emit(tr("Couldn't set up OBS automatically · see README for the manual steps"),
                                    "error")
            try:
                if not self.obs.ensure_buffer():
                    self.toast.emit(tr("Turned on the OBS replay buffer"), "ok")
            except Exception:
                self.toast.emit(tr("OBS isn't running. Start it to use Capture Menu"), "error")
            self.refresh_status()   # e.g. a recording still running after a restart
            log.info("start-up done")
        threading.Thread(target=run, daemon=True).start()

    # ---- save what just happened
    def save_clip(self, seconds: int | None, game: str = DESKTOP):
        self._bg(self._save_clip, seconds, game)

    def _save_clip(self, seconds: int | None, game: str):
        if not self.obs.ensure_buffer():
            self.toast.emit(tr("The replay buffer was off, so I turned it on. "
                               "Clips are collected from now on"), "error")
            return
        self.toast.emit(tr("Saving…"), "info")
        saved = self.obs.save_replay()
        suffix = "all" if seconds is None else f"{seconds}s"
        out = self.folder_for(game) / f"Clip_{self._stamp()}_{suffix}{saved.suffix}"
        length = cut_tail(saved, seconds, out) or float(seconds or 0)
        detail = (tr("Everything · {length}", length=clock(int(length * 1000)))
                  if seconds is None or length < seconds - 1
                  else tr("Last {length}", length=duration_label(seconds)))
        self._done(detail, out)

    # ---- manual recording
    def toggle_record(self, game: str = DESKTOP):
        self._bg(self._toggle_record, game, exclusive=False)

    def _toggle_record(self, game: str):
        recording, _ = self.obs.record_status()
        if not recording:
            self.obs.start_record()
            self.record_game = game  # the recording goes to the game it started in
            self.recording.emit(True)
            self.toast.emit(tr("Recording started · open the menu and choose Stop to finish"), "rec")
            return
        path = self.obs.stop_record()
        self.recording.emit(False)
        wait_until_written(path)
        game = self.record_game or game
        self.record_game = None
        dest = self.folder_for(game) / f"Recording_{self._stamp()}{path.suffix}"
        shutil.move(str(path), dest)
        length = media_duration(dest) or 0
        self._done(tr("Length {length}", length=clock(int(length * 1000))), dest)

    # ---- screenshot
    def screenshot(self, game: str = DESKTOP):
        self._bg(self._screenshot, game, exclusive=False)

    def _screenshot(self, game: str):
        path = self.folder_for(game, self.shots_dir) / f"Screenshot_{self._stamp()}.png"
        self.obs.screenshot(path)
        wait_until_written(path, timeout=5)
        self._done("", path)

    def open_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.clips_dir)))


# ---------------------------------------------------------------- global hotkey

class Hotkey(QtCore.QObject):
    pressed = QtCore.Signal(str)   # name of the game that was in the foreground

    MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
    NAMED = {"space": 0x20, "tab": 0x09, "pause": 0x13, "insert": 0x2D, "home": 0x24,
             "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "printscreen": 0x2C}

    def __init__(self, spec: str, detect_game):
        super().__init__()
        self.spec = spec
        self.detect_game = detect_game

    def _parse(self) -> tuple[int, int]:
        mods, vk = 0x4000, 0  # MOD_NOREPEAT
        for part in self.spec.lower().replace(" ", "").split("+"):
            if part in self.MODS:
                mods |= self.MODS[part]
            elif part in self.NAMED:
                vk = self.NAMED[part]
            elif len(part) >= 2 and part[0] == "f" and part[1:].isdigit():
                vk = 0x6F + int(part[1:])
            elif len(part) == 1 and part.isalnum():
                vk = ord(part.upper())
        if not vk:
            raise ValueError(f"Unrecognised hotkey: {self.spec}")
        return mods, vk

    def start(self) -> bool:
        if not IS_WINDOWS:
            return False
        from ctypes import wintypes
        mods, vk = self._parse()
        ready, ok = threading.Event(), [False]

        def loop():
            user32 = ctypes.windll.user32
            ok[0] = bool(user32.RegisterHotKey(None, 1, mods, vk))
            ready.set()
            if not ok[0]:
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    self.pressed.emit(self.detect_game())

        threading.Thread(target=loop, daemon=True).start()
        ready.wait(3)
        return ok[0]


# ---------------------------------------------------------------- game controller

# SDL GameController button numbers. SDL reads the DualSense, Xbox and most other pads
# with one layout, so "a" is Cross on a DualSense and A on an Xbox controller.
PAD_BUTTONS = {
    "a": 0, "cross": 0, "b": 1, "circle": 1, "x": 2, "square": 2, "y": 3, "triangle": 3,
    "create": 4, "back": 4, "view": 4, "select": 4, "ps": 5, "guide": 5, "xbox": 5,
    "options": 6, "start": 6, "menu": 6, "l3": 7, "r3": 8, "l1": 9, "lb": 9, "r1": 10, "rb": 10,
    "up": 11, "down": 12, "left": 13, "right": 14,
    "share": 15, "mute": 15, "mic": 15, "touchpad": 20,
}
A, B, X, Y, L1, R1, UP, DOWN, LEFT, RIGHT = 0, 1, 2, 3, 9, 10, 11, 12, 13, 14
DIRECTIONS = {UP, DOWN, LEFT, RIGHT}


def parse_pad_combo(spec: str) -> frozenset[int]:
    """'create' or 'l1+r1' -> the set of SDL button numbers."""
    combo = set()
    for part in spec.lower().replace(" ", "").split("+"):
        if part not in PAD_BUTTONS:
            raise ValueError(f"Unknown controller button: {part}")
        combo.add(PAD_BUTTONS[part])
    return frozenset(combo)


class PadState:
    """Turns raw "buttons held now" snapshots into presses: edge detection,
    an optional hold time for the open button, and key-repeat for directions."""

    REPEAT_DELAY, REPEAT_EVERY = 0.35, 0.11

    def __init__(self, combo: frozenset[int], hold_ms: int):
        self.combo, self.hold = combo, hold_ms / 1000
        self.prev: set[int] = set()
        self.combo_since: float | None = None
        self.combo_fired = False
        self.next_repeat: dict[int, float] = {}

    def step(self, held: set[int], now: float) -> tuple[bool, list[int]]:
        """Returns (open button triggered, buttons pressed this step)."""
        triggered = False
        if self.combo <= held:
            if self.combo_since is None:
                self.combo_since, self.combo_fired = now, False
            if not self.combo_fired and now - self.combo_since >= self.hold:
                triggered = self.combo_fired = True
        else:
            self.combo_since = None
        presses = []
        for b in sorted(held - self.prev):
            if b not in self.combo:
                presses.append(b)
                if b in DIRECTIONS:
                    self.next_repeat[b] = now + self.REPEAT_DELAY
        for b in list(self.next_repeat):
            if b not in held:
                del self.next_repeat[b]
            elif now >= self.next_repeat[b]:
                presses.append(b)
                self.next_repeat[b] = now + self.REPEAT_EVERY
        self.prev = set(held)
        return triggered, presses


class Gamepad(QtCore.QObject):
    """Reads every connected controller in the background, even while a game has focus."""

    activated = QtCore.Signal()
    pressed = QtCore.Signal(int)
    used = QtCore.Signal(str)        # "playstation" or "xbox": the pad that was just pressed
    connected = QtCore.Signal(str, bool)   # controller name, connected (False: it went away)

    STICK = 20000   # left stick acts as a d-pad past this deflection

    RUMBLES = {"capture": (0x3000, 0x7000, 120), "record": (0x6000, 0x2000, 220)}

    def __init__(self, cfg: dict):
        super().__init__()
        self.state = PadState(parse_pad_combo(cfg["controller_button"]),
                              int(cfg["controller_hold_ms"]))
        self._rumble: tuple[int, int, int] | None = None

    def rumble(self, kind: str = "capture"):
        """Asks the reader thread for a short buzz (SDL calls must stay on that thread)."""
        self._rumble = self.RUMBLES.get(kind, self.RUMBLES["capture"])

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import sdl2
        except Exception:
            log.warning("controller support off: pysdl2 isn't installed")
            return
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_PS5_PLAYER_LED, b"0")  # leave the lights alone
        # Windows.Gaming.Input and RawInput need window messages handled on this thread, which never
        # happens here; with them on, closing a video in the viewer could hang forever (the player waits
        # on the audio device). HIDAPI still reads PlayStation pads and XInput the Xbox ones.
        sdl2.SDL_SetHint(b"SDL_JOYSTICK_WGI", b"0")
        sdl2.SDL_SetHint(b"SDL_JOYSTICK_RAWINPUT", b"0")
        if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER) != 0:
            log.warning("controller support off: %s", sdl2.SDL_GetError())
            return
        log.info("controller support on, waiting for a controller")
        pads, kinds, last, names = {}, {}, {}, {}
        busy_until = 0.0
        playstation = {sdl2.SDL_CONTROLLER_TYPE_PS3, sdl2.SDL_CONTROLLER_TYPE_PS4,
                       sdl2.SDL_CONTROLLER_TYPE_PS5}
        event = sdl2.SDL_Event()
        while True:
            while sdl2.SDL_PollEvent(ctypes.byref(event)):
                if event.type == sdl2.SDL_CONTROLLERDEVICEADDED:
                    pad = sdl2.SDL_GameControllerOpen(event.cdevice.which)
                    if pad:
                        jid = sdl2.SDL_JoystickInstanceID(sdl2.SDL_GameControllerGetJoystick(pad))
                        pads[jid] = pad
                        kinds[jid] = ("playstation" if sdl2.SDL_GameControllerGetType(pad) in playstation
                                      else "xbox")
                        name = (sdl2.SDL_GameControllerName(pad) or b"Controller").decode(errors="replace")
                        names[jid] = name
                        log.info("controller connected: %s", name)
                        self.connected.emit(name, True)
                elif event.type == sdl2.SDL_CONTROLLERDEVICEREMOVED:
                    pad = pads.pop(event.cdevice.which, None)
                    if pad:
                        sdl2.SDL_GameControllerClose(pad)
                        name = names.pop(event.cdevice.which, "Controller")
                        log.info("controller disconnected: %s", name)
                        self.connected.emit(name, False)
            held, fresh_kind = set(), None
            for jid, pad in pads.items():
                mine = {b for b in range(21) if sdl2.SDL_GameControllerGetButton(pad, b)}
                x = sdl2.SDL_GameControllerGetAxis(pad, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
                y = sdl2.SDL_GameControllerGetAxis(pad, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
                if abs(x) > self.STICK and abs(x) > abs(y):
                    mine.add(RIGHT if x > 0 else LEFT)
                elif abs(y) > self.STICK:
                    mine.add(DOWN if y > 0 else UP)
                if mine - last.get(jid, set()):
                    fresh_kind = kinds.get(jid, "xbox")
                last[jid] = mine
                held |= mine
            if fresh_kind:
                self.used.emit(fresh_kind)
            triggered, presses = self.state.step(held, time.monotonic())
            if triggered:
                self.activated.emit()
            for b in presses:
                self.pressed.emit(b)
            if self._rumble is not None:
                low, high, ms = self._rumble
                self._rumble = None
                for pad in pads.values():
                    sdl2.SDL_GameControllerRumble(pad, low, high, ms)
            now = time.monotonic()
            if held or presses or triggered:
                busy_until = now + 3
            # 60 Hz while in use; 30 Hz when idle still catches the quickest tap (~60 ms);
            # with no controller plugged in, only watch for one being connected
            time.sleep(1 / 60 if now < busy_until else 1 / 30 if pads else 0.25)


def pad_key(button: int, menu: "Menu", viewer: "Viewer", gallery: "Gallery | None" = None,
            settings: "Settings | None" = None) -> int | None:
    """Which key a controller button stands for in whatever is on screen."""
    OPTIONS = 6
    if settings is not None and settings.isVisible():
        return {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down, LEFT: Qt.Key_Left,
                RIGHT: Qt.Key_Right, Y: Qt.Key_S, X: Qt.Key_R}.get(button)
    if viewer.isVisible():
        if viewer.editing:          # typing needs the keyboard; the pad can only cancel
            return {B: Qt.Key_Escape}.get(button)
        if viewer.sounding:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down,
                    LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right, X: Qt.Key_P, Y: Qt.Key_M}
        elif viewer.sharing:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right}
        elif viewer.trimming:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right,
                    X: Qt.Key_I, Y: Qt.Key_O, L1: Qt.Key_P, R1: Qt.Key_P}
        else:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right,
                    UP: Qt.Key_Up, DOWN: Qt.Key_Down, L1: Qt.Key_A, R1: Qt.Key_D, X: Qt.Key_T, Y: Qt.Key_M,
                    OPTIONS: Qt.Key_E, 7: Qt.Key_V}   # 7 = L3: Sound, Y: the small buttons
        return keys.get(button)
    if gallery is not None and gallery.isVisible():
        keys = {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down,
                LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right, L1: Qt.Key_BracketLeft,
                R1: Qt.Key_BracketRight, Y: Qt.Key_F, X: Qt.Key_Space, OPTIONS: Qt.Key_Delete,
                7: Qt.Key_S}
        return keys.get(button)
    if menu.isVisible():
        keys = {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down,
                LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right, X: Qt.Key_S, Y: Qt.Key_V, R1: Qt.Key_T}
        return keys.get(button)
    return None


class InputMode(QtCore.QObject):
    """What the player is using right now, so on-screen hints show the right buttons."""

    changed = QtCore.Signal(str)    # "keyboard", "playstation" or "xbox"

    def __init__(self):
        super().__init__()
        self.mode = "keyboard"
        self.synthetic = False      # key events we send on behalf of the controller

    def set(self, mode: str):
        if mode != self.mode:
            self.mode = mode
            self.changed.emit(mode)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress and not self.synthetic:
            self.set("keyboard")
        return False


INPUT = InputMode()

PAD_NAMES = {
    "playstation": {0: "✕", 1: "◯", 2: "▢", 3: "△", 4: "Create", 5: "PS", 6: "Options", 7: "L3",
                    8: "R3", 9: "L1", 10: "R1", 11: "↑", 12: "↓", 13: "←", 14: "→", 15: "Mute",
                    20: "Touchpad"},
    "xbox": {0: "A", 1: "B", 2: "X", 3: "Y", 4: "View", 5: "Xbox", 6: "Menu", 7: "LS", 8: "RS",
             9: "LB", 10: "RB", 11: "↑", 12: "↓", 13: "←", 14: "→", 15: "Share", 20: "Touchpad"},
}


def pad_combo_name(spec: str, kind: str) -> str:
    try:
        combo = parse_pad_combo(spec)
    except ValueError:
        return spec
    return " + ".join(PAD_NAMES[kind].get(b, str(b)) for b in sorted(combo))


def send_key(window: QtWidgets.QWidget, key: int):
    focus = QtWidgets.QApplication.focusWidget()
    target = focus if focus is not None and focus.window() is window else window
    INPUT.synthetic = True
    try:
        QtWidgets.QApplication.sendEvent(
            target, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, Qt.NoModifier))
    finally:
        INPUT.synthetic = False


def safe_emit(signal, *args):
    """Emit from a worker thread; quietly skip if the window is already gone (app quitting)."""
    try:
        signal.emit(*args)
    except RuntimeError:
        pass


class PressSequencer(QtCore.QObject):
    """One press opens the bar; two quick presses save the last N seconds right away,
    like the PS5's easy-clip shortcut. The single press waits `window_ms` to be sure."""

    def __init__(self, window_ms: int, on_single, on_double, is_open):
        super().__init__()
        self.on_single, self.on_double, self.is_open = on_single, on_double, is_open
        self.window_ms = window_ms
        self.game = DESKTOP
        self.timer = QtCore.QTimer(self, singleShot=True, interval=max(1, window_ms),
                                   timeout=lambda: self.on_single(self.game))

    def press(self, game: str):
        if self.is_open() or self.window_ms <= 0:
            self.timer.stop()
            self.on_single(game)          # closing never waits
        elif self.timer.isActive():
            self.timer.stop()
            self.on_double(self.game)
        else:
            self.game = game              # the game on screen at the first press
            self.timer.start()


class Sounds:
    """Short cues when something is saved (assets/sounds, replaceable with your own .wav)."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.effects = {}

    def play(self, name: str):
        path = ASSETS / "sounds" / f"{name}.wav"
        if not self.enabled or not path.exists():
            return
        if IS_WINDOWS:   # Windows plays a .wav itself: no audio stack kept loaded in this app
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        if name not in self.effects:
            if not load_multimedia():
                return
            fx = QtMultimedia.QSoundEffect()
            fx.setSource(QtCore.QUrl.fromLocalFile(str(path)))
            fx.setVolume(0.55)
            self.effects[name] = fx
        self.effects[name].play()


# ---------------------------------------------------------------- UI

def trim_memory():
    """While the app only waits for the hotkey, give back what it doesn't need: Qt's cache of drawn
    pixmaps (refilled as pages are drawn), source lines kept for tracebacks, free heap. Its idle pages
    go back to Windows too; they stay in RAM's standby list, so the menu still opens instantly."""
    import gc, linecache
    gc.collect()
    linecache.clearcache()        # PySide6 reads every module imported after it into this cache
    QtGui.QPixmapCache.clear()    # up to 10 MB of style and icon pixmaps
    if IS_WINDOWS:
        k32 = ctypes.windll.kernel32
        k32.GetProcessHeap.restype = ctypes.c_void_p
        k32.HeapCompact.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.HeapCompact(k32.GetProcessHeap(), 0)     # decommits the heap's large free blocks
        k32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
        k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    else:
        try:
            ctypes.CDLL(None).malloc_trim(0)           # glibc keeps freed heap otherwise
        except (OSError, AttributeError):
            pass


def bring_to_front(w: QtWidgets.QWidget):
    """Windows only lets the app that got the last input steal focus. A controller
    press isn't keyboard input, so briefly join the foreground thread's input queue."""
    w.raise_()
    w.activateWindow()
    if not IS_WINDOWS:
        return
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = int(w.winId())
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(ctypes.c_void_p(fg), None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(fg_thread, me, True))
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if attached:
        user32.AttachThreadInput(fg_thread, me, False)


def hide_from_capture(w: QtWidgets.QWidget):
    """Keeps the window out of recordings and screenshots (Windows 10 2004+)."""
    if IS_WINDOWS:
        ctypes.windll.user32.SetWindowDisplayAffinity(int(w.winId()), 0x11)  # WDA_EXCLUDEFROMCAPTURE


class _AccentPolicy(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WindowCompositionData(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


GLASS_TINT = 0x70            # how much of the near-black tint lies over the blur (0-255)
GLASS_SHEET = 96             # and how dark the page paints over that; 250 without glass


def glass(w: QtWidgets.QWidget) -> bool:
    """Frosted glass behind a page, like the PS5: the game shows through, blurred and dimmed.
    Windows' own acrylic blur (Windows 10 1803+), drawn by the system, so it costs the game nothing.
    False where it isn't available; the page then stays solid."""
    if not IS_WINDOWS or os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen"):
        return False
    try:
        tint = (GLASS_TINT << 24) | (NIGHT[2] << 16) | (NIGHT[1] << 8) | NIGHT[0]   # AABBGGRR
        accent = _AccentPolicy(4, 2, tint, 0)                                 # ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = _WindowCompositionData(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
                                      ctypes.sizeof(accent))                  # WCA_ACCENT_POLICY
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(int(w.winId()), ctypes.byref(data)))
    except Exception:
        log.exception("glass background not available")
        return False


def sheet_color(w: QtWidgets.QWidget) -> QtGui.QColor:
    """The page's own dark layer: light over glass, nearly solid without it."""
    return QtGui.QColor(*NIGHT, GLASS_SHEET if getattr(w, "glassy", False) else 250)


def dress(w: QtWidgets.QWidget, frosted: bool = True):
    """What lives on a page's native window: kept out of captures, glass behind it. Done when the page
    is made, and again on opening it after release_window() let the window go."""
    if getattr(w, "dressed", False):
        return
    hide_from_capture(w)
    if frosted:
        w.glassy = glass(w)
    w.dressed = True


def release_window(w: QtWidgets.QWidget):
    """A hidden page keeps a picture of itself the size of the screen (about 15 MB at 1440p, 33 MB at 4K)
    for as long as its native window lives. Letting the window go gives that back; opening the page
    makes a new one, dressed again."""
    if w.isVisible():
        return
    w.destroy()
    w.dressed = False


# ---- look: the PS5's night blue; white is the focus colour, red only means recording
INK = "#f4f6fb"
MUTED = "rgba(236,240,250,0.76)"
FAINT = "rgba(236,240,250,0.58)"
NIGHT = (7, 10, 20)         # every surface sits on this blue-black, like the PS5's menus
PANEL = "rgba(24,29,44,0.92)"   # a raised card: notices, dialogs
DARK = "#0d1120"            # ink on a white (focused) surface
RED = "#ff453a"
GREEN = "#32d74b"
BLUE = "#2f7bf5"            # PlayStation blue: a switch that's on
AMBER = "#ffb340"
FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'
DISPLAY = '"Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif'

ASSETS = BUNDLE_DIR / "assets"

# Interface icons come from Lucide (ISC licence, assets/LUCIDE-LICENSE.txt).
ICON_FILES = {
    "camera": "camera", "rewind": "history", "record": "circle-dot", "stop": "circle-stop",
    "folder": "folder", "play": "play", "pause": "pause", "scissors": "scissors",
    "trash": "trash-2", "external": "external-link", "left": "chevron-left",
    "right": "chevron-right", "close": "x", "image": "image",
    "share": "share-2", "copy": "copy", "star": "star", "mic": "mic", "mic-off": "mic-off",
    "gallery": "layout-grid", "drive": "hard-drive", "settings": "settings",
    "volume": "volume-2", "volume-off": "volume-x", "maximize": "maximize", "minimize": "minimize",
    "pencil": "pencil", "audio": "audio-lines", "export": "upload", "more": "ellipsis",
    "gamepad": "gamepad-2", "info": "info", "file-video": "file-video", "select": "square-check-big",
}
_icon_cache: dict = {}


def icon_pixmap(name: str, size: int, color: str = INK) -> QtGui.QPixmap:
    key = (name, size, color)
    if key not in _icon_cache:
        from PySide6.QtSvg import QSvgRenderer
        svg = (ASSETS / "icons" / f"{ICON_FILES[name]}.svg").read_text(encoding="utf-8")
        svg = svg.replace("currentColor", color)
        renderer = QSvgRenderer(QtCore.QByteArray(svg.encode()))
        dpr = 3.0
        pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(dpr)
        _icon_cache[key] = pm
    return _icon_cache[key]


def qicon(name: str, color: str = INK) -> QtGui.QIcon:
    return QtGui.QIcon(icon_pixmap(name, 18, color))


def rounded_pixmap(path: Path | None, w: int, h: int, radius: int = 10, dpr: float = 2.0) -> QtGui.QPixmap:
    """The image cropped to fill w×h with rounded corners (dark placeholder if missing)."""
    out = QtGui.QPixmap(int(w * dpr), int(h * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    p = QtGui.QPainter(out)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    clip = QtGui.QPainterPath()
    clip.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(clip)
    src = QtGui.QPixmap(str(path)) if path else QtGui.QPixmap()
    if src.isNull():
        p.fillRect(0, 0, w, h, QtGui.QColor(255, 255, 255, 18))
    else:
        scaled = src.scaled(int(w * dpr), int(h * dpr), Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        p.drawPixmap(QtCore.QPointF((w - scaled.width() / dpr) / 2, (h - scaled.height() / dpr) / 2),
                     scaled)
    p.end()
    return out


def font(px: float, weight: QtGui.QFont.Weight = QtGui.QFont.Normal, display: bool = False) -> QtGui.QFont:
    f = QtGui.QFont()
    f.setFamilies(["Segoe UI Variable Display" if display else "Segoe UI Variable Text",
                   "Segoe UI", "Inter", "Noto Sans"])
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def short_clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# Button prompts come from PromptFont by Shinmera (Yukari Hafner), SIL OFL 1.1,
# https://shinmera.com/promptfont (assets/PROMPTFONT-LICENSE.txt).
_prompt_family: str | None = None
_glyphs: dict[str, str] | None = None


def prompt_family() -> str:
    global _prompt_family
    if _prompt_family is None:
        fid = QtGui.QFontDatabase.addApplicationFont(str(ASSETS / "promptfont.ttf"))
        families = QtGui.QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _prompt_family = families[0] if families else ""
    return _prompt_family


def glyph(name: str) -> str:
    global _glyphs
    if _glyphs is None:
        _glyphs = json.loads((ASSETS / "promptfont-glyphs.json").read_text(encoding="utf-8"))
    return _glyphs.get(name, "")


KEY_NAMES = {"←": "left", "→": "right", "↑": "up", "↓": "down", "Enter": "enter", "Esc": "escape",
             "Space": "space", "Del": "delete", "Alt": "alt", "Ctrl": "control", "Shift": "shift"}
PAD_GLYPHS = {
    "playstation": {0: "sony-a", 1: "sony-b", 2: "sony-x", 3: "sony-y", 4: "sony-dualsense-share",
                    5: "icon-playstation", 6: "sony-dualsense-options", 7: "sony-left-stick",
                    8: "sony-right-stick", 9: "sony-left-shoulder", 10: "sony-right-shoulder",
                    20: "sony-dualsense-touchpad"},
    "xbox": {0: "xbox-a", 1: "xbox-b", 2: "xbox-x", 3: "xbox-y", 4: "xbox-view", 5: "icon-xbox",
             6: "xbox-menu", 9: "xbox-left-shoulder", 10: "xbox-right-shoulder"},
}


def token_glyphs(token: str, mode: str) -> list[str]:
    """Hint token -> PromptFont glyph names (or "t:<text>" for plain text).
    "k:Enter" / "k:← →" / "k:1–8" are keys; A B X Y, L1 R1 L1R1, DPAD_LR / DPAD_UD are pad buttons."""
    if token.startswith("k:"):
        out = []
        for piece in token[2:].split():
            if "–" in piece:
                lo, hi = piece.split("–")
                out += [f"keyboard-{lo.lower()}", "t:–", f"keyboard-{hi.lower()}"]
            else:
                out.append("keyboard-" + KEY_NAMES.get(piece, piece.lower()))
        return out
    kind = "playstation" if mode == "playstation" else "xbox"
    pad = {"A": [0], "B": [1], "X": [2], "Y": [3], "L1": [9], "R1": [10], "L1R1": [9, 10]}
    if token in pad:
        return [PAD_GLYPHS[kind][b] for b in pad[token]]
    if token == "OPT":
        return [PAD_GLYPHS[kind][6]]
    if token == "L3":   # PromptFont has no Xbox stick press
        return ["sony-left-stick"] if kind == "playstation" else ["t:LS"]
    if token == "DPAD_U":
        return ["dpad-up" if kind == "playstation" else "xbox-dpad-up"]
    if token == "DPAD":
        return ["dpad-fill" if kind == "playstation" else "xbox-dpad"]
    if token in ("DPAD_LR", "DPAD_UD"):
        suffix = "left-right" if token == "DPAD_LR" else "up-down"
        return [f"dpad-{suffix}" if kind == "playstation" else f"xbox-dpad-{suffix}"]
    return [f"t:{token}"]


def _glyph_parts(token: str, mode: str) -> list[tuple[QtGui.QFont, str]]:
    parts = []
    for name in token_glyphs(token, mode):
        char = "" if name.startswith("t:") else glyph(name)
        if char:
            f = QtGui.QFont(prompt_family())
            f.setPixelSize(22)
            parts.append((f, char))
        else:
            parts.append((font(12, QtGui.QFont.DemiBold),
                          name[2:] if name.startswith("t:") else name.split("-", 1)[-1].upper()))
    return parts


def glyph_width(token: str, mode: str) -> float:
    """How wide draw_glyph() draws this button prompt."""
    return sum(QtGui.QFontMetrics(f).horizontalAdvance(text) + (2 if i else 0)
               for i, (f, text) in enumerate(_glyph_parts(token, mode)))


def draw_glyph(p: QtGui.QPainter, x: float, cy: float, token: str, mode: str,
               color: str | QtGui.QColor = INK) -> float:
    """Draws one button prompt at x (vertically centred on cy); returns its width."""
    width = 0.0
    p.save()
    p.setPen(QtGui.QColor(color))
    for i, name in enumerate(token_glyphs(token, mode)):
        char = "" if name.startswith("t:") else glyph(name)
        if char:
            f = QtGui.QFont(prompt_family())
            f.setPixelSize(22)
            text = char
        else:
            f = font(12, QtGui.QFont.DemiBold)
            text = name[2:] if name.startswith("t:") else name.split("-", 1)[-1].upper()
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text)
        x0 = x + width + (2 if i else 0)
        p.drawText(QtCore.QRectF(x0, cy - 14, w + 1, 28), Qt.AlignCenter, text)
        width += w + (2 if i else 0)
    p.restore()
    return width


def glyph_html(names: list[str], px: int = 17) -> str:
    """Inline PromptFont glyphs for rich-text labels."""
    family = prompt_family()
    parts = []
    for n in names:
        char = glyph(n)
        parts.append(f'<span style="font-family:\'{family}\'; font-size:{px}px">{char}</span>'
                     if char else n.split("-")[-1].upper())
    return "&nbsp;".join(parts)


class HintBar(QtWidgets.QWidget):
    """A row of button prompts with labels, drawn for the current input device."""

    GAP, ITEM_GAP = 7, 20

    def __init__(self):
        super().__init__()
        self.items: list[tuple[str, str]] = []
        self.mode = "keyboard"
        self.setFixedHeight(28)

    def set_items(self, items: list[tuple[str, str]], mode: str):
        self.items, self.mode = [(glyph, tr(label)) for glyph, label in items], mode
        self.setFixedWidth(int(self._layout(None)) + 2)
        self.update()

    def _layout(self, p: QtGui.QPainter | None) -> float:
        x, cy = 0.0, self.height() / 2
        scratch = None
        if p is None:   # measure on a throwaway painter
            scratch = QtGui.QPixmap(1, 1)
            p = QtGui.QPainter(scratch)
        rtl = is_rtl()   # right to left: the first prompt sits on the right, each label left of its button
        for i, (glyph, label) in enumerate(reversed(self.items) if rtl else self.items):
            if i:
                x += self.ITEM_GAP
            if glyph and not rtl:
                x += draw_glyph(p, x, cy, glyph, self.mode) + self.GAP
            p.setFont(font(14))
            p.setPen(QtGui.QColor(236, 240, 250, 205))
            w = p.fontMetrics().horizontalAdvance(label)
            p.drawText(QtCore.QRectF(x, 0, w + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, label)
            x += w
            if glyph and rtl:
                x += self.GAP + draw_glyph(p, x + self.GAP, cy, glyph, self.mode)
        if scratch is not None:
            p.end()
        return x

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        self._layout(p)


class HoverFocus:
    """Hover only lends the white highlight: the item under the mouse lights up, and when the mouse
    leaves, the highlight goes back to where it was. A click (or a key) keeps it where it is."""

    def hover_in(self):
        before = QtWidgets.QApplication.focusWidget()
        if before is not self:
            self._lent = True
            self._lent_from = before
        self.setFocus(Qt.MouseFocusReason)

    def hover_out(self):
        lent, before = getattr(self, "_lent", False), getattr(self, "_lent_from", None)
        self.keep_focus()
        if not lent or not self.hasFocus():
            return                          # clicked, or a key moved on meanwhile: that stays
        if before is not None and before.isVisible() and before.window() is self.window():
            before.setFocus(Qt.MouseFocusReason)
        else:
            self.clearFocus()

    def keep_focus(self):
        self._lent, self._lent_from = False, None


MOTION_MS = 180       # how long the focus takes to grow into place; 0 jumps (the render tools use that)


class Grow:
    """The PS5's focus: the focused item grows a little and lights up, smoothly, and settles back
    when the focus moves on. self.grow runs from 0 (at rest) to 1 (focused)."""

    grow = 0.0

    def grow_to(self, on: bool):
        end = 1.0 if on else 0.0
        anim = getattr(self, "_grow_anim", None)
        if anim is None:
            anim = self._grow_anim = QtCore.QVariantAnimation(self)
            anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
            anim.valueChanged.connect(self._on_grow)
        anim.stop()
        if not MOTION_MS or not self.isVisible() or self.grow == end:
            self._on_grow(end)
            return
        anim.setDuration(MOTION_MS)
        anim.setStartValue(self.grow)
        anim.setEndValue(end)
        anim.start()

    def _on_grow(self, value):
        self.grow = float(value)
        self.update()


def grown(r: QtCore.QRectF, amount: float) -> QtCore.QRectF:
    """r made larger by amount (0.06 = 6 %) around its centre."""
    dx, dy = r.width() * amount / 2, r.height() * amount / 2
    return r.adjusted(-dx, -dy, dx, dy)


def paint_focus(p: QtGui.QPainter, r: QtCore.QRectF, radius: float, t: float = 1.0, ring: bool = True):
    """The PS5's focus frame around r: a soft white glow and, for pictures, a white ring.
    t fades it in (0-1) as the item grows."""
    if t <= 0.01:
        return
    p.save()
    p.setBrush(Qt.NoBrush)
    for out, width, alpha in ((8, 8, 10), (6, 5, 20), (4.5, 3, 34)):     # the glow, softest outside
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(alpha * t)), width))
        p.drawRoundedRect(r.adjusted(-out, -out, out, out), radius + out, radius + out)
    if ring:
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(255 * t)), 3))
        p.drawRoundedRect(r.adjusted(-3.5, -3.5, 3.5, 3.5), radius + 3.5, radius + 3.5)
    p.restore()


class Card(Grow, HoverFocus, QtWidgets.QAbstractButton):
    """Base for the bar's focusable tiles: hover, and the focus that grows the tile and rings it."""

    RADIUS = 16
    PAD = 12                                  # room around the tile to grow into, with its ring and glow
    SCALE = 0.08                              # how much bigger the focused tile is
    BELOW = 0                                 # room under the tile for its label

    def __init__(self, w: int, h: int):
        super().__init__()
        self.setFixedSize(w + 2 * self.PAD, h + 2 * self.PAD + self.BELOW)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.focused_cb = None
        self.active = False                 # keeps the ring while its popover is open
        self.hover_focus = lambda: True

    def tile(self) -> QtCore.QRectF:
        """Where the tile sits at rest."""
        return QtCore.QRectF(self.PAD, self.PAD, self.width() - 2 * self.PAD,
                             self.height() - 2 * self.PAD - self.BELOW)

    def lit(self) -> float:
        """How focused it looks, 0-1: it grows into focus, and stays lit while its popover is open."""
        return 1.0 if self.active else self.grow

    def shown(self) -> QtCore.QRectF:
        """Where the tile is drawn: grown as far as its focus has come."""
        return grown(self.tile(), self.SCALE * self.lit())

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.grow_to(True)
        if self.focused_cb:
            self.focused_cb(self)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.grow_to(False)

    def enterEvent(self, e):
        super().enterEvent(e)
        if self.hover_focus():
            self.hover_in()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if self.hover_focus():
            self.hover_out()

    def mousePressEvent(self, e):
        self.keep_focus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        self.keep_focus()
        super().keyPressEvent(e)

    def radius(self) -> float:
        """The corner radius as drawn, growing with the tile."""
        return self.RADIUS * self.shown().width() / self.tile().width()

    def paint_ring(self, p: QtGui.QPainter):
        paint_focus(p, self.shown(), self.radius(), self.lit())


class ActionCard(Card):
    """An icon tile with its name underneath. The focused one grows and turns white, like the PS5's
    Create menu."""

    SIZE = 100
    BELOW = 44

    def __init__(self, icon: str, label: str, hint: str = ""):
        super().__init__(self.SIZE + 12, self.SIZE)
        self.icon_name, self.label, self.hint = icon, label, hint
        self.icon_color = INK
        self.tint: QtGui.QColor | None = None

    def tile(self) -> QtCore.QRectF:
        return QtCore.QRectF((self.width() - self.SIZE) / 2, self.PAD, self.SIZE, self.SIZE)

    def set_state(self, icon: str, label: str, icon_color: str = INK, tint: QtGui.QColor | None = None):
        self.icon_name, self.label, self.icon_color, self.tint = icon, label, icon_color, tint
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r, t, radius = self.shown(), self.lit(), self.radius()
        focused = self.hasFocus() or self.active
        paint_focus(p, r, radius, t, ring=False)
        p.setPen(Qt.NoPen)
        p.setBrush(self.tint if self.tint is not None else QtGui.QColor(255, 255, 255, 34 if self.underMouse() else 20))
        p.drawRoundedRect(r, radius, radius)
        if t > 0.01:      # the white comes in as the tile grows
            white = QtGui.QColor(INK)
            white.setAlphaF(t)
            p.setBrush(white)
            p.drawRoundedRect(r, radius, radius)
        color = (DARK if self.icon_color == INK else self.icon_color) if focused else self.icon_color
        size = 32 * r.width() / self.SIZE
        p.drawPixmap(QtCore.QRectF(r.center().x() - size / 2, r.center().y() - size / 2, size, size).toRect(),
                     icon_pixmap(self.icon_name, 34, color))
        text_r = QtCore.QRectF(0, self.tile().bottom() + 14, self.width(), 18)
        p.setPen(QtGui.QColor(INK) if focused else QtGui.QColor(236, 240, 250, 205))
        p.setFont(font(14, QtGui.QFont.DemiBold if focused else QtGui.QFont.Normal))
        p.drawText(text_r, Qt.AlignHCenter | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(tr(self.label), Qt.ElideRight, self.width()))
        if self.hint:
            p.setPen(QtGui.QColor(236, 240, 250, 150))
            p.setFont(font(13))
            p.drawText(text_r.translated(0, 17), Qt.AlignHCenter | Qt.AlignVCenter, tr(self.hint))


def draw_capture_tile(p: QtGui.QPainter, r: QtCore.QRectF, pixmap: QtGui.QPixmap, path: Path | None,
                      length: float | None, favorite: bool, dim: int = 0, radius: int = 10,
                      marked: bool = False, selecting: bool = False):
    """A capture thumbnail with its badges: length (or screenshot) and a favourite star.
    selecting: every tile shows the circle that a pick fills in."""
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    p.drawPixmap(r, pixmap, QtCore.QRectF(pixmap.rect()))     # r may be grown past the picture's own size
    if dim:
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, dim))
        p.drawRoundedRect(r, radius, radius)
    p.setFont(font(11, QtGui.QFont.DemiBold))
    is_shot = path is not None and path.suffix.lower() == ".png"
    label = "" if is_shot or length is None else short_clock(length)
    if is_shot or label:
        text_w = p.fontMetrics().horizontalAdvance(label) if label else 0
        bw = text_w + 14 + (18 if is_shot and label else 0) if label else 22
        badge = QtCore.QRectF(r.right() - bw - 6, r.bottom() - 26, bw, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 150))
        p.drawRoundedRect(badge, 5, 5)
        x = badge.left() + 4
        if is_shot:
            p.drawPixmap(QtCore.QPointF(x, badge.top() + 3), icon_pixmap("image", 14))
            x += 18
        if label:
            p.setPen(QtGui.QColor(INK))
            p.drawText(QtCore.QRectF(x, badge.top(), badge.right() - x - 3, 20), Qt.AlignCenter, label)
    if marked:   # picked for "delete selected": white frame + check in the corner
        p.setPen(QtGui.QPen(QtGui.QColor(INK), 3))
        p.setBrush(QtGui.QColor(0, 0, 0, 90))
        p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), radius, radius)
        c = QtCore.QPointF(r.right() - 17, r.top() + 17)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(INK))
        p.drawEllipse(c, 11, 11)
        p.setPen(QtGui.QPen(QtGui.QColor(DARK), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QtGui.QPolygonF([c + QtCore.QPointF(-5, 0), c + QtCore.QPointF(-1.5, 3.5),
                                        c + QtCore.QPointF(5, -4)]))
    elif selecting:
        c = QtCore.QPointF(r.right() - 17, r.top() + 17)
        p.setPen(QtGui.QPen(QtGui.QColor(INK), 2))
        p.setBrush(QtGui.QColor(0, 0, 0, 120))
        p.drawEllipse(c, 10, 10)
    if favorite:
        star = QtCore.QRectF(r.left() + 6, r.top() + 6, 22, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 165))
        p.drawRoundedRect(star, 6, 6)
        p.drawPixmap(QtCore.QPointF(star.left() + 4, star.top() + 4), icon_pixmap("star", 14, "#ffd34d"))


class ThumbCard(Card):
    RADIUS = 14
    W, H = 178, 100
    BELOW = 44

    def __init__(self):
        super().__init__(self.W, self.H)
        self.path: Path | None = None
        self.pixmap = QtGui.QPixmap()
        self.length: float | None = None
        self.favorite = False
        self.caption, self.when = "", ""

    def set_capture(self, path: Path, thumb: Path | None, length: float | None, favorite: bool = False):
        self.path, self.length, self.favorite = path, length, favorite
        self.pixmap = rounded_pixmap(thumb, self.W, self.H, self.RADIUS)
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        focused = self.hasFocus() or self.active
        dim = int((50 if self.underMouse() else 100) * (1 - self.lit()))   # quieter until focused, like the PS5
        draw_capture_tile(p, self.shown(), self.pixmap, self.path, self.length, self.favorite, dim, self.radius())
        self.paint_ring(p)
        if focused and self.path is not None:   # the focused capture says what it is, nothing else does
            text = QtCore.QRectF(self.PAD, self.tile().bottom() + 14, self.width() - 2 * self.PAD, 18)
            p.setPen(QtGui.QColor(INK))
            p.setFont(font(14, QtGui.QFont.DemiBold))
            p.drawText(text, lead() | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(self.caption, Qt.ElideRight, int(text.width())))
            p.setPen(QtGui.QColor(236, 240, 250, 165))
            p.setFont(font(13))
            p.drawText(text.translated(0, 19), lead() | Qt.AlignVCenter, self.when)

BAR_STYLE = f"""
QLabel {{ color: {INK}; background: transparent; }}
#game {{ font-family: {DISPLAY}; font-size: 30px; font-weight: 600; }}
#status {{ color: {MUTED}; font-size: 15px; }}
#caption {{ color: {INK}; font-size: 17px; font-weight: 600; }}
#focusInfo {{ color: {FAINT}; font-size: 15px; }}
#storage {{ color: {AMBER}; font-size: 15px; }}
QPushButton#back {{
    color: {INK}; font-size: 14px; font-weight: 600; border: none; border-radius: 20px;
    background: rgba(255,255,255,16); padding: 0 18px 0 12px; min-height: 40px;
}}
QPushButton#back:hover {{ background: rgba(255,255,255,40); }}
"""


def chip_label(seconds: int | None) -> str:
    """PS5 wording: Full Video, Last 15s, Last 1m, Last 30m."""
    if seconds is None:
        return tr("Full video")
    if seconds < 60:
        return tr("Last {n}s", n=seconds)
    if seconds < 3600:
        return tr("Last {n}m", n=seconds // 60)
    return tr("Last {n}h", n=seconds // 3600)


class Chip(Grow, HoverFocus, QtWidgets.QAbstractButton):
    """A pill in the Save recent gameplay row; the focused one grows and turns white, like the PS5."""

    H = 44
    PAD = 9           # room to grow into

    def __init__(self, text: str):
        super().__init__()
        self.setText(text)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.dimmed = False      # longer than what the buffer holds so far
        self.danger = False      # a delete waiting for its second press
        self.setFont(font(15, QtGui.QFont.DemiBold))
        self._fit()

    def _fit(self):
        self.setFixedSize(QtGui.QFontMetrics(self.font()).horizontalAdvance(tr(self.text())) + 44 + 2 * self.PAD,
                          self.H + 2 * self.PAD)

    def setText(self, text: str):
        super().setText(text)
        self._fit()
        self.update()

    def enterEvent(self, e):
        super().enterEvent(e)
        self.hover_in()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self.hover_out()

    def mousePressEvent(self, e):
        self.keep_focus()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        self.keep_focus()
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.grow_to(True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.grow_to(False)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        g = self.grow
        r = QtCore.QRectF(self.rect()).adjusted(self.PAD - 4 * g, self.PAD - 2 * g, 4 * g - self.PAD, 2 * g - self.PAD)
        radius = r.height() / 2
        focused = self.hasFocus()
        paint_focus(p, r, radius, self.grow, ring=False)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 105, 97, 150) if self.danger else QtGui.QColor(255, 255, 255, 46), 1))
        p.setBrush(QtGui.QColor(255, 255, 255, 34 if self.underMouse() else 14))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        if self.grow > 0.01:
            fill = QtGui.QColor("#ff6961" if self.danger else INK)
            fill.setAlphaF(self.grow)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r, radius, radius)
        text = QtGui.QColor(DARK) if focused else QtGui.QColor("#ff8a82" if self.danger else INK)
        if self.dimmed and not focused:
            text.setAlpha(110)
        p.setPen(text)
        p.drawText(r, Qt.AlignCenter, tr(self.text()))


class Menu(QtWidgets.QWidget):
    """The Create bar: docks along the bottom of the screen so the game stays in view."""

    BAR_H = 316
    PICK_H = 246            # the bar is slimmer while choosing a duration
    HEADROOM = 90           # fade above the bar

    def __init__(self, ctl: Controller, viewer: "Viewer"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.ctl = ctl
        self.viewer = viewer
        self.gallery = None          # set by main(); "All captures" opens it
        self.settings = None         # set by main()
        self.game = DESKTOP
        self.picking = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(BAR_STYLE)
        self.setFont(font(13))
        dress(self, frosted=False)
        # chip order follows the PS5: Full video first, then shortest to longest
        self.options: list[int | None] = [None] + sorted(ctl.cfg["durations_seconds"])[:8]
        self.last_choice = self.options.index(60) if 60 in self.options else 1

        self.bar = QtWidgets.QWidget(self)
        lay = QtWidgets.QVBoxLayout(self.bar)
        lay.setContentsMargins(64, 26, 64, 22)
        lay.setSpacing(18)

        # header: which game and what the replay buffer holds
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(18)
        self.game_label = QtWidgets.QLabel(objectName="game")
        self.status = QtWidgets.QLabel(objectName="status")
        self.status.setTextFormat(Qt.RichText)
        head.addWidget(self.game_label, 0, Qt.AlignBaseline)
        head.addWidget(self.status, 0, Qt.AlignBaseline)
        self.storage_label = QtWidgets.QLabel(objectName="storage")
        self.storage_label.hide()
        head.addWidget(self.storage_label, 0, Qt.AlignBaseline)
        head.addStretch()
        lay.addLayout(head)

        # main row: actions, then recent captures
        self.main_row = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.main_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.save_card = ActionCard("rewind", "Save recent", "last 30 min")
        self.shot_card = ActionCard("camera", "Screenshot")
        self.rec_card = ActionCard("record", "Record")
        self.mic_card = ActionCard("mic", "Mic on")
        self.mic_card.clicked.connect(self.ctl.toggle_mic)
        self.save_card.clicked.connect(self.open_picker)
        self.shot_card.clicked.connect(self._screenshot)
        self.rec_card.clicked.connect(lambda: self._act(self.ctl.toggle_record, self.game))
        for c in (self.save_card, self.shot_card, self.rec_card, self.mic_card):
            row.addWidget(c, 0, Qt.AlignTop)
        row.addSpacing(28)
        self.thumbs = [ThumbCard() for _ in range(8)]
        for i, t in enumerate(self.thumbs):
            t.clicked.connect(lambda _=False, i=i: self._view(i))
            row.addWidget(t, 0, Qt.AlignTop)
        self.empty_label = QtWidgets.QLabel(tr("Your captures will show up here"), objectName="focusInfo")
        self.empty_label.setFixedHeight(ActionCard.SIZE + 2 * Card.PAD)
        row.addWidget(self.empty_label, 0, Qt.AlignTop)
        row.addSpacing(4)
        self.all_card = ActionCard("gallery", "All captures")
        self.all_card.clicked.connect(self.open_gallery)
        row.addWidget(self.all_card, 0, Qt.AlignTop)
        self.settings_card = ActionCard("settings", "Settings")
        self.settings_card.clicked.connect(self.open_settings)
        row.addWidget(self.settings_card, 0, Qt.AlignTop)
        row.addStretch()
        lay.addWidget(self.main_row)

        # Save recent gameplay: a row of pills, like the PS5
        self.picker = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(self.picker)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(12)
        self.pick_caption = QtWidgets.QLabel(objectName="caption")
        self.pick_caption.setTextFormat(Qt.RichText)
        pl.addWidget(self.pick_caption)
        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(4)
        chips.addWidget(back_button(self.close_picker), 0, Qt.AlignVCenter)
        chips.addSpacing(12)
        self.chips: list[Chip] = []
        for sec in self.options:
            c = Chip(chip_label(sec))
            c.clicked.connect(lambda _=False, s=sec: self._save(s))
            chips.addWidget(c)
            self.chips.append(c)
        chips.addStretch()
        pl.addLayout(chips)
        self.picker.hide()
        lay.addWidget(self.picker)
        lay.addStretch()

        # footer: button prompts on the left, details of the focused capture on the right
        foot = QtWidgets.QHBoxLayout()
        self.hints = HintBar()
        foot.addWidget(self.hints)
        foot.addStretch()
        self.focus_info = QtWidgets.QLabel(objectName="focusInfo")
        foot.addWidget(self.focus_info)
        lay.addLayout(foot)

        for c in (self.save_card, self.shot_card, self.rec_card, self.mic_card, self.all_card,
                  self.settings_card, *self.thumbs):
            c.focused_cb = self._on_focus
            c.hover_focus = lambda: not self.picking

        self._buffer = {"active": False, "max_ms": 0, "held_ms": None}
        ctl.status.connect(self._on_status)
        self._timer = QtCore.QTimer(self, interval=1000, timeout=ctl.refresh_status)
        self._rise = QtCore.QPropertyAnimation(self.bar, b"pos", self)    # opening slides the bar up, like the PS5
        self._rise.setDuration(240)
        self._rise.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._rise.valueChanged.connect(lambda _: self.update())
        INPUT.changed.connect(lambda _: self.update_hints())
        self.update_hints()

    def update_hints(self):
        pad = INPUT.mode != "keyboard"
        if self.picking:
            items = ([("DPAD_LR", "Choose"), ("A", "Save"), ("B", "Back")] if pad else
                     [("k:← →", "Choose"), ("k:Enter", "Save"),
                      (f"k:1–{len(self.options)}", "Pick"), ("k:Esc", "Back")])
        elif pad:
            items = [("DPAD_LR", "Move"), ("A", "Select"), ("X", "Screenshot"),
                     ("Y", "View latest"), ("R1", "Trim latest"), ("B", "Close")]
        else:
            items = [("k:← →", "Move"), ("k:Enter", "Select"),
                     (f"k:1–{len(self.options)}", "Save instantly"), ("k:T", "Trim latest"), ("k:Esc", "Close")]
        self.hints.set_items(items, INPUT.mode)

    # ---- show / hide
    def toggle(self, game: str | None = None):
        self.hide_menu() if self.isVisible() else self.show_menu(game)

    def _place(self):
        """Pin the bar to the bottom edge at its current height."""
        h = self.PICK_H if self.picking else self.BAR_H
        self._rise.stop()
        self.bar.setGeometry(0, self.height() - h, self.width(), h)
        self.update()

    def show_menu(self, game: str | None = None, fresh: bool = True):
        """fresh: opened from outside (the game's screen is picked again); False when coming Back."""
        self.game = game or foreground_app(self.ctl.cfg)
        if self.viewer.isVisible():
            self.viewer.close_viewer()
        g = ui_screen(fresh).geometry()   # the screen the game is on, TV or monitor
        h = self.BAR_H + self.HEADROOM
        dress(self, frosted=False)
        self.setGeometry(g.left(), g.bottom() - h + 1, g.width(), h)
        self.game_label.setText(self.game_label.fontMetrics().elidedText(self.game, Qt.ElideRight, 420))
        self.status.setText("")
        self._set_picking(False)
        self.refresh_recent()
        self.ctl.refresh_status()
        self._timer.start()
        if fresh and MOTION_MS:
            self._rise.setStartValue(QtCore.QPoint(0, self.height()))
            self._rise.setEndValue(self.bar.pos())
            self.bar.move(0, self.height())
        self.show()
        bring_to_front(self)
        self.save_card.setFocus()
        if fresh and MOTION_MS:
            self._rise.start()

    def hide_menu(self):
        self._timer.stop()
        self.picking = False
        self.hide()

    def changeEvent(self, e):
        # clicking back into the game closes the bar, like pressing Esc
        if e.type() == QtCore.QEvent.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide_menu()
        super().changeEvent(e)

    def _act(self, fn, *args):
        self.hide_menu()
        fn(*args)

    def _screenshot(self):
        self.hide_menu()
        game = self.game
        QtCore.QTimer.singleShot(250, lambda: self.ctl.screenshot(game))  # bar gone first

    # ---- Save recent gameplay row
    def _set_picking(self, on: bool):
        self.picking = on
        self.main_row.setVisible(not on)
        self.picker.setVisible(on)
        self._place()
        self.update_hints()

    def open_picker(self):
        self._set_picking(True)
        self._refresh_picker()
        self.chips[self.last_choice].setFocus()

    def close_picker(self):
        self._set_picking(False)
        self.save_card.setFocus()

    def _save(self, seconds: int | None):
        self.last_choice = self.options.index(seconds)
        self._act(self.ctl.save_clip, seconds, self.game)

    def _refresh_picker(self):
        b = self._buffer
        if not b["active"]:
            held = tr("replay buffer is off")
        elif b["held_ms"] is None:
            held = tr("up to {length}", length=clock(b["max_ms"]))
        else:
            held = f"{clock(min(b['held_ms'], b['max_ms']))} / {clock(b['max_ms'])}"
        self.pick_caption.setText(f'{tr("Save recent gameplay")}&nbsp;&nbsp;&nbsp;'
                                  f'<span style="color:{MUTED}; font-weight:400">{held}</span>')
        for sec, chip in zip(self.options, self.chips):
            chip.dimmed = (sec is not None and b["held_ms"] is not None
                           and sec * 1000 > b["held_ms"] + 500)
            chip.update()

    # ---- content
    def refresh_recent(self):
        items = self.ctl.recent_items()
        tile = self.save_card.width()
        room = self.width() - 128 - 4 * tile - 40 - 2 * tile if self.width() > 0 else 1200
        count = max(1, min(len(self.thumbs), room // self.thumbs[0].width()))
        for i, card in enumerate(self.thumbs):
            path = items[i] if i < len(items) and i < count else None
            card.setVisible(path is not None)
            if path is not None:
                card.set_capture(path, self.ctl.thumb(path), self.ctl.length_of(path),
                                 self.ctl.is_favorite(path))
                card.caption = self.ctl.title_of(path) or capture_kind(path)
                card.when = time_ago(path.stat().st_mtime)
        self.empty_label.setVisible(not items)
        self.focus_info.setText("")

    def _on_focus(self, card: Card):
        if isinstance(card, ThumbCard) and card.path is not None:
            path = card.path
            self.focus_info.setText(f"{path.parent.name}    {human_size(file_size(path))}")
        else:
            self.focus_info.setText("")

    def show_storage(self, info: dict):
        if info.get("over"):
            self.storage_label.setText(tr("Captures {used} GB · over {limit} GB", used=f"{info['used_gb']:.0f}",
                                          limit=f"{info['limit_gb']:.0f}"))
        elif info.get("low"):
            self.storage_label.setText(tr("Only {free} GB free", free=f"{info['free_gb']:.0f}"))
        self.storage_label.setVisible(bool(info.get("over") or info.get("low")))

    def open_gallery(self):
        if self.gallery is None:
            self._act(self.ctl.open_folder)
            return
        game = self.game
        self.hide_menu()
        self.gallery.open(game, back_to=lambda: self.show_menu(game, fresh=False))

    def open_settings(self):
        if self.settings is None:
            return
        game = self.game
        self.hide_menu()
        self.settings.open(self.ctl.screen_px, back_to=lambda: self.show_menu(game, fresh=False))

    def _view(self, index: int, trim: bool = False):
        items = self.ctl.recent_items()
        if index < len(items):
            game = self.game
            self.hide_menu()
            self.viewer.open(items, index, trim=trim, back_to=lambda: self.show_menu(game, fresh=False))

    def view_capture(self, path: str, trim: bool = False):
        """A notice was clicked: its capture in the viewer. Back then comes to the bar, the same as
        opening it with Create then △ (it used to close everything)."""
        items = self.ctl.recent_items()
        p = Path(path)
        if p not in items:
            items = [p, *items]
        self.hide_menu()
        if self.gallery is not None:
            self.gallery.close_gallery()
        self.viewer.open(items, items.index(p), trim=trim, fresh=True, back_to=lambda: self.show_menu(fresh=False))

    def _on_status(self, st: dict):
        if not st.get("online"):
            off = tr("OBS isn't running")
            text = f'<span style="color:{AMBER}">{off}</span>'
        elif st["recording"]:
            text = (f'<span style="color:{RED}">●</span>&nbsp;&nbsp;<span style="color:{INK}">{tr("Recording")}'
                    f'</span>&nbsp;&nbsp;{clock(st["record_ms"])}')
        elif st["buffer"]:
            text = tr("Keeping the last {length}", length=duration_label(st["buffer_seconds"], short=True))
        else:
            text = f'<span style="color:{AMBER}">{tr("Replay buffer is off")}</span>'
        self.status.setText(text)
        if st.get("online"):
            self._buffer = {"active": st["buffer"], "max_ms": st["buffer_seconds"] * 1000,
                            "held_ms": st.get("buffered_ms")}
            self.save_card.hint = tr("last {length}", length=duration_label(st["buffer_seconds"], short=True))
            self.save_card.update()
            if st["recording"]:
                self.rec_card.set_state("stop", tr("Stop  {time}", time=clock(st["record_ms"])), RED,
                                        QtGui.QColor(255, 69, 58, 40))
            else:
                self.rec_card.set_state("record", "Record")
            muted = st.get("mic_muted")
            self.mic_card.setVisible(muted is not None)
            if muted:
                self.mic_card.set_state("mic-off", "Mic off", RED)
            else:
                self.mic_card.set_state("mic", "Mic on")
        if self.picking:
            self._refresh_picker()

    # ---- painting and input
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        top = max(0, self.bar.y() - self.HEADROOM)
        grad = QtGui.QLinearGradient(0, top, 0, self.height())
        span = max(1, self.height() - top)
        grad.setColorAt(0.0, QtGui.QColor(*NIGHT, 0))
        grad.setColorAt(min(0.9, self.HEADROOM * 0.55 / span), QtGui.QColor(*NIGHT, 120))
        grad.setColorAt(min(0.95, (self.HEADROOM + 24) / span), QtGui.QColor(*NIGHT, 238))
        grad.setColorAt(1.0, QtGui.QColor(*NIGHT, 250))
        p.fillRect(QtCore.QRect(0, top, self.width(), self.height() - top), grad)

    def mousePressEvent(self, e):
        if e.position().y() < self.bar.y():
            self.hide_menu()

    def _nav_cards(self) -> list[QtWidgets.QAbstractButton]:
        if self.picking:
            return list(self.chips)
        cards = [self.save_card, self.shot_card, self.rec_card]
        cards += [self.mic_card] if self.mic_card.isVisible() else []
        cards += [t for t in self.thumbs if t.isVisible()]
        return cards + [self.all_card, self.settings_card]

    def keyPressEvent(self, e):
        k = e.key()
        cards = self._nav_cards()
        focused = self.focusWidget()
        if k in (Qt.Key_Left, Qt.Key_Right) and focused in cards:
            j = cards.index(focused) + forward(k)
            cards[max(0, min(len(cards) - 1, j))].setFocus()
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and focused in cards:
            focused.click()
        elif Qt.Key_1 <= k <= Qt.Key_9 and k - Qt.Key_1 < len(self.options):
            self._save(self.options[k - Qt.Key_1])
        elif self.picking:
            if k in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Down):
                self.close_picker()
        elif k == Qt.Key_Escape:
            self.hide_menu()
        elif k == Qt.Key_Up and focused is self.save_card:
            self.open_picker()
        elif k == Qt.Key_S:
            self._screenshot()
        elif k == Qt.Key_R:
            self.rec_card.click()
        elif k == Qt.Key_V:
            self._view(0)
        elif k == Qt.Key_T:
            self._view(0, trim=True)
        elif k in (Qt.Key_O, Qt.Key_G):
            self.all_card.click()
        elif k == Qt.Key_Comma:
            self.open_settings()
        elif k == Qt.Key_M:
            self.ctl.toggle_mic()
        else:
            super().keyPressEvent(e)


class RecIndicator(QtWidgets.QWidget):
    """A small red REC dot and timer in a corner while a manual recording runs, like the PS5.
    Clicks go straight through to the game, it never takes focus, and recordings don't show it."""

    def __init__(self, corner: str = "top-left"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        hide_from_capture(self)
        self.corner = corner
        self.started: float | None = None      # time.monotonic() when the recording began
        self.blink = True
        self.setFont(font(14, QtGui.QFont.DemiBold))
        self._tick = QtCore.QTimer(self, interval=1000, timeout=self._on_tick)

    def text(self) -> str:
        secs = int(time.monotonic() - self.started) if self.started is not None else 0
        return f"REC  {clock(secs * 1000)}"

    def set_recording(self, on: bool, elapsed_ms: int = 0):
        if self.corner == "off":
            return
        if not on:
            self.started = None
            self._tick.stop()
            self.hide()
            return
        if self.started is None or elapsed_ms:   # OBS knows the real time; trust it over our clock
            self.started = time.monotonic() - elapsed_ms / 1000
        self._place()
        self.show()
        self._tick.start()

    def sync(self, st: dict):
        """From the status poll: catches recordings started in OBS itself, or before a restart."""
        if st.get("online"):
            self.set_recording(bool(st.get("recording")), int(st.get("record_ms") or 0))

    def _place(self):
        long = self.started is not None and time.monotonic() - self.started >= 3600
        w = self.fontMetrics().horizontalAdvance("REC  0:00:00" if long else "REC  00:00") + 52  # steady width
        self.resize(w, 34)
        g = game_screen().geometry()      # follows the game to the TV and back
        x = g.left() + 16 if self.corner == "top-left" else g.left() + g.width() - w - 16
        self.move(x, g.top() + 16)

    def _on_tick(self):
        self.blink = not self.blink
        self._place()
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 26), 1))
        p.setBrush(QtGui.QColor(24, 29, 44, 215))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        dot = QtGui.QColor(RED)
        dot.setAlpha(255 if self.blink else 110)   # a slow pulse, so it reads as live
        p.setPen(Qt.NoPen)
        if self.blink:     # a soft red halo while the dot is lit
            p.setBrush(QtGui.QColor(255, 69, 58, 60))
            p.drawEllipse(QtCore.QPointF(18, r.center().y()), 9, 9)
        p.setBrush(dot)
        p.drawEllipse(QtCore.QPointF(18, r.center().y()), 5.5, 5.5)
        p.setPen(QtGui.QColor(INK))
        p.drawText(r.adjusted(32, 0, -12, 0), Qt.AlignLeft | Qt.AlignVCenter, self.text())

class Toast(QtWidgets.QWidget):
    """Top-right notice, like the PS5's: never takes focus from the game.
    A capture's notice can be clicked to view it, or its Trim button to trim it."""

    open_capture = QtCore.Signal(str, bool)    # path, straight into trim

    DOTS = {"ok": GREEN, "error": RED, "info": INK, "rec": RED}
    TITLES = {"Clip": "Clip saved", "Screenshot": "Screenshot saved",
              "Recording": "Recording saved", "Trimmed": "Trimmed clip saved"}
    hotkey = "ALT+C"
    pad_button = "create"
    thumbs_dir: Path | None = None

    def show_shared(self, detail: str, path: str):
        """The share copy is ready (and on the clipboard)."""
        self.path = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.setPixmap(rounded_pixmap(make_thumb(Path(path), self.thumbs_dir or Path(path).parent),
                                            128, 72, 11))
        self.thumb.show()
        self.title.setText(tr("Ready to share"))
        self.sub.setText(detail.replace(" · ", "  ·  "))
        self.sub.show()
        self.hint.setText(tr("Copied · paste it with Ctrl+V"))
        self.hint.show()
        self._present(7000)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        hide_from_capture(self)
        self.path: str | None = None
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QtWidgets.QFrame(objectName="toastBox")
        self.box.setStyleSheet(
            f"#toastBox {{ background: {PANEL}; border-radius: 18px;"
            f" border: 1px solid rgba(255,255,255,22); }}"
            f"QLabel {{ background: transparent; border: none; }}")
        outer.addWidget(self.box)
        lay = QtWidgets.QHBoxLayout(self.box)
        lay.setContentsMargins(12, 12, 20, 12)
        lay.setSpacing(16)
        self.thumb = QtWidgets.QLabel()
        lay.addWidget(self.thumb)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        self.title = QtWidgets.QLabel()
        self.title.setFont(font(16, QtGui.QFont.DemiBold))
        self.title.setStyleSheet(f"color: {INK};")
        self.title.setTextFormat(Qt.RichText)
        self.sub = QtWidgets.QLabel()
        self.sub.setFont(font(14))
        self.sub.setStyleSheet(f"color: {MUTED};")
        self.hint = QtWidgets.QLabel()
        self.hint.setTextFormat(Qt.RichText)
        self.hint.setFont(font(13))
        self.hint.setStyleSheet(f"color: {MUTED};")
        col.addStretch()
        for w in (self.title, self.sub, self.hint):
            w.setMaximumWidth(380)
            w.setWordWrap(True)          # long notices wrap instead of being cut off
            col.addWidget(w)
        col.addStretch()
        lay.addLayout(col)
        self.trim_btn = QtWidgets.QPushButton(" " + tr("Trim"))
        self.trim_btn.setIcon(qicon("scissors"))
        self.trim_btn.setCursor(Qt.PointingHandCursor)
        self.trim_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,22); color: {INK}; border: none; border-radius: 17px;"
            f" padding: 8px 16px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,44); }}")
        self.trim_btn.clicked.connect(lambda: self._open(trim=True))
        lay.addWidget(self.trim_btn, 0, Qt.AlignVCenter)
        self.trim_btn.hide()
        self._hide = QtCore.QTimer(self, singleShot=True, timeout=self._fade_out)
        self._slide = QtCore.QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade.finished.connect(lambda: self.hide() if self.windowOpacity() < 0.05 else None)

    def _open(self, trim: bool = False):
        if self.path:
            self.hide()
            self.open_capture.emit(self.path, trim)

    def mousePressEvent(self, e):
        if self.path:
            self._open(trim=False)    # click the notice: open it in the viewer
        else:
            self.hide()

    def show_capture(self, detail: str, path: str):
        capture = Path(path)
        self.path = path
        self.setCursor(Qt.PointingHandCursor)
        self.trim_btn.setVisible(capture.suffix.lower() != ".png")
        kind = capture.stem.split("_")[0]
        if kind == "Clip" and capture_kind(capture) == "Trimmed clip":
            kind = "Trimmed"
        thumb = make_thumb(capture, self.thumbs_dir or capture.parents[1] / ".thumbs")
        self.thumb.setPixmap(rounded_pixmap(thumb, 128, 72, 11))
        self.thumb.show()
        self.title.setText(tr(self.TITLES.get(kind, "Saved")))
        self.sub.setText("  ·  ".join(x for x in (detail, capture.parent.name) if x))
        self.sub.show()
        if INPUT.mode == "keyboard":
            keys = [f"keyboard-{KEY_NAMES.get(k.capitalize(), k.lower())}"
                    for k in self.hotkey.replace(" ", "").split("+")]
            open_html, view_html = glyph_html(keys), glyph_html(["keyboard-v"])
        else:
            try:
                combo = sorted(parse_pad_combo(self.pad_button))
            except ValueError:
                combo = []
            names = PAD_GLYPHS[INPUT.mode]
            open_html = glyph_html([names.get(b, PAD_NAMES[INPUT.mode].get(b, "?")) for b in combo])
            view_html = glyph_html([names[3]])
        self.hint.setText(tr("{open}&nbsp; then &nbsp;{view}&nbsp; to view", open=open_html, view=view_html))
        self.hint.show()
        self._present(6000)

    def show_running(self, title: str, detail: str):
        """The start-up notice: app icon, "running", and how to open it."""
        self.path = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.setPixmap(tray_icon().pixmap(44, 44))
        self.thumb.show()
        self.title.setText(title)
        self.sub.setText(detail)
        self.sub.show()
        self.hint.hide()
        self._present(5000)

    def show_message(self, text: str, kind: str = "info"):
        self.path = None
        self.trim_btn.hide()
        self.unsetCursor()
        self.thumb.hide()
        title, _, sub = text.partition(" · ")
        dot = self.DOTS.get(kind)
        self.title.setText(f'<span style="color:{dot}">●</span>&nbsp;&nbsp;{title}'
                           if kind in ("error", "rec") else title)
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        self.hint.hide()
        self._present(6000 if kind == "error" else 3500)

    def _present(self, ms: int):
        # each line gets its natural width and wraps only past 380 px (Qt would wrap far earlier)
        for w in (self.title, self.sub, self.hint):
            w.setWordWrap(False)
            natural = w.sizeHint().width()
            w.setWordWrap(True)
            w.setFixedWidth(min(natural, 380))
        # shrink back after a bigger notice (one with a thumbnail) was shown before
        for lay in (self.box.layout(), self.layout()):
            lay.invalidate()
            lay.activate()
        self.resize(self.sizeHint())
        page_open = any(w.isVisible() for w in QtWidgets.QApplication.topLevelWidgets()
                        if isinstance(w, (Menu, Viewer, Gallery, Settings)))
        g = (ui_screen() if page_open else game_screen()).geometry()   # beside the page in use
        x, y = g.right() - self.width() - 28, g.top() + 28
        self._fade.stop()
        if self.isVisible() or not MOTION_MS:
            self._slide.stop()
            self.move(x, y)
            self.setWindowOpacity(1.0)
        else:   # slides in from the edge and fades in, like the PS5's
            self.move(x + 48, y)
            self._slide.setStartValue(QtCore.QPoint(x + 48, y))
            self._slide.setEndValue(QtCore.QPoint(x, y))
            self._slide.start()
            self.setWindowOpacity(0.0)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.show()
        self.raise_()
        self._hide.start(ms)

    def _fade_out(self):
        """Time's up: the notice fades away instead of vanishing."""
        if not MOTION_MS or not self.isVisible():
            self.hide()
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()


VIEWER_STYLE = f"""
QWidget {{ font-family: {FONT}; }}
#viewer {{ background: transparent; border: none; }}
QLabel {{ color: {INK}; background: transparent; }}
#vTitle {{ font-family: {DISPLAY}; font-size: 32px; font-weight: 600; }}
#vSub, #vNote {{ color: {MUTED}; font-size: 15px; }}
#hint {{ color: {MUTED}; font-size: 15px; }}
#panelTitle {{ font-family: {DISPLAY}; font-size: 24px; font-weight: 600; }}
#panelSub {{ color: {MUTED}; font-size: 15px; }}
#info {{ color: {MUTED}; font-size: 14px; }}
#vMsg {{ color: {MUTED}; font-size: 16px; }}
#time {{ color: {MUTED}; font-size: 14px; font-family: "Cascadia Mono", Consolas, monospace; }}
#stage {{ background: transparent; }}
#videoCard {{ background: #000000; border: 1px solid rgba(255,255,255,22); border-radius: 20px; }}
#ctlBar {{ background: rgba(24,29,44,200); border-top: 1px solid rgba(255,255,255,14);
           border-bottom-left-radius: 19px; border-bottom-right-radius: 19px; }}
#footer {{ border-top: 1px solid rgba(255,255,255,16); }}
#rule {{ background: rgba(255,255,255,40); }}
#dialog {{ background: rgb(24,29,44); border: 1px solid rgba(255,255,255,26); border-radius: 22px; }}
#dim {{ background: rgba(0,0,0,150); border-radius: 20px; }}
#fieldLabel {{ font-size: 14px; font-weight: 600; }}
QPushButton {{
    color: {INK}; font-size: 15px; font-weight: 600;
    background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,30); border-radius: 23px;
    padding: 0 22px; min-height: 46px;
}}
QPushButton:hover {{ background: rgba(255,255,255,24); }}
QPushButton:disabled {{ color: rgba(236,240,250,0.28); border-color: rgba(255,255,255,14); }}
QPushButton#primary {{ background: {INK}; color: {DARK}; border: none; padding: 0 26px; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton:focus {{ border: 2px solid {INK}; padding: 0 21px; }}
QPushButton#primary:focus {{ border: 3px solid {DARK}; padding: 0 23px; }}
QPushButton#back {{ background: rgba(255,255,255,12); border: 3px solid transparent; padding: 0 18px 0 12px; }}
QPushButton#back:focus, QPushButton#round:focus, QPushButton#ctl:focus {{ border: 3px solid {INK}; }}
QPushButton#back:hover {{ background: rgba(255,255,255,32); }}
QPushButton#round {{ padding: 0; min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px;
                     border-radius: 23px; border: 3px solid transparent; background: rgba(255,255,255,12); }}
QPushButton#round:hover {{ background: rgba(255,255,255,32); }}
QPushButton#pill {{ min-height: 34px; padding: 0 16px; font-size: 13px; border-radius: 17px; }}
QPushButton#ctl {{ padding: 0; min-width: 40px; max-width: 40px; min-height: 40px; border: 3px solid transparent;
                   background: transparent; border-radius: 20px; }}
QPushButton#ctl:hover {{ background: rgba(255,255,255,24); }}
QPushButton#noteToggle {{ text-align: left; padding: 0 16px; font-weight: 400; color: {MUTED}; }}
QLineEdit {{
    color: {INK}; background: rgba(255,255,255,10); border: 1px solid rgba(255,255,255,40);
    border-radius: 14px; padding: 0 16px; min-height: 50px; font-size: 16px;
    selection-background-color: rgba(255,255,255,70);
}}
QLineEdit:focus {{ border: 2px solid {INK}; padding: 0 15px; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,46); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {INK}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: white; }}
QSlider#seek {{ border: 3px solid transparent; border-radius: 15px; padding: 0 8px; min-height: 30px; }}
QSlider#seek:focus {{ border-color: {INK}; }}
"""

# ---- the viewer's parts. One calm vocabulary: a faint surface with a hairline, round corners,
# white only for focus and for the one main action on screen.
CARD_RADIUS = 18


def paint_card(p: QtGui.QPainter, r: QtCore.QRectF, focused: bool = False, hovered: bool = False,
               radius: float = CARD_RADIUS):
    inset = 1.5 if focused else 0.5
    p.setPen(QtGui.QPen(QtGui.QColor(INK) if focused else QtGui.QColor(255, 255, 255, 26), 3 if focused else 1))
    p.setBrush(QtGui.QColor(255, 255, 255, 24 if (hovered or focused) else 12))
    p.drawRoundedRect(r.adjusted(inset, inset, -inset, -inset), radius, radius)


def toward(current: QtWidgets.QWidget, items: list[QtWidgets.QWidget], key: int) -> QtWidgets.QWidget | None:
    """Where an arrow leads from current, by where things sit on screen, the way the PS5 moves its
    highlight: the nearest item that way, in line with it before anything off to the side."""
    def box(w):
        return QtCore.QRectF(QtCore.QPointF(w.mapToGlobal(QtCore.QPoint(0, 0))), QtCore.QSizeF(w.size()))

    def gap(a0, a1, b0, b1):     # how far apart two spans are (0 when they overlap)
        return max(0.0, b0 - a1, a0 - b1)
    here = box(current)
    best, best_score = None, None
    for w in items:
        if w is current:
            continue
        r = box(w)
        d = r.center() - here.center()
        if key in (Qt.Key_Left, Qt.Key_Right):
            way, along = (d.x() if key == Qt.Key_Right else -d.x()), gap(here.left(), here.right(), r.left(), r.right())
            across = gap(here.top(), here.bottom(), r.top(), r.bottom())
        else:
            way, along = (d.y() if key == Qt.Key_Down else -d.y()), gap(here.top(), here.bottom(), r.top(), r.bottom())
            across = gap(here.left(), here.right(), r.left(), r.right())
        if way <= 2:
            continue
        score = along + 2 * across + 0.05 * abs(d.y() if key in (Qt.Key_Left, Qt.Key_Right) else d.x())
        if best_score is None or score < best_score:
            best, best_score = w, score
    return best


def mirror(w: QtWidgets.QWidget, r: QtCore.QRectF) -> QtCore.QRectF:
    """r as laid out left to right, flipped when the widget runs right to left (Arabic)."""
    if not w.isRightToLeft():
        return r
    return QtCore.QRectF(w.width() - r.x() - r.width(), r.y(), r.width(), r.height())


class ActionButton(QtWidgets.QAbstractButton):
    """A big viewer action: its icon, its name, and the button that does it (□ Trim, like the PS5).
    The main one on screen is white. With no name it's a small icon button (its name is the tooltip)."""

    H = 64

    def __init__(self, text: str, icon: str, pad: str | None = None, key: str | None = None,
                 primary: bool = False):
        super().__init__()
        self.icon_name, self.tokens, self.primary, self.danger = icon, (pad, key), primary, False
        self.icon_color: str | None = None     # e.g. a filled-in yellow star
        self.setText(text)
        self.setFont(font(17, QtGui.QFont.DemiBold))
        self.setFixedHeight(self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.NoFocus)
        INPUT.changed.connect(lambda _: self._fit())
        self._fit()

    def _token(self) -> str | None:
        pad, key = self.tokens
        return key if INPUT.mode == "keyboard" else pad

    def _parts(self) -> tuple[float, float, float]:
        """Widths of the label and the button prompt, and the whole content."""
        text_w = QtGui.QFontMetrics(self.font()).horizontalAdvance(self.text()) if self.text() else 0
        glyph_w = glyph_width(self._token(), INPUT.mode) if self._token() else 0.0
        total = 22 + (12 + text_w if text_w else 0) + (14 + glyph_w if glyph_w else 0)
        return text_w, glyph_w, total

    def _fit(self):
        total = int(self._parts()[2])
        self.setMinimumWidth(total + 56 if self.text() else max(self.H, total + 40))
        self.update()

    def setText(self, text: str):
        super().setText(text)
        if hasattr(self, "tokens"):
            self._fit()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        hover = self.underMouse()
        if self.primary:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#ffffff" if hover else INK))
            p.drawRoundedRect(r, 20, 20)
            ink = QtGui.QColor(DARK)
            if self.hasFocus():   # a dark ring inside the white
                p.setPen(QtGui.QPen(ink, 3))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(4.5, 4.5, -4.5, -4.5), 16, 16)
        elif self.danger:
            p.setPen(QtGui.QPen(QtGui.QColor(INK), 2) if self.hasFocus() else
                     QtGui.QPen(QtGui.QColor(255, 105, 97, 150), 1))
            p.setBrush(QtGui.QColor(255, 69, 58, 46))
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 20, 20)
            ink = QtGui.QColor("#ff8a82")
        else:
            paint_card(p, r, self.hasFocus(), hover, 20)
            ink = QtGui.QColor(INK)
        p.setFont(self.font())
        text_w, glyph_w, total = self._parts()
        x, cy = (self.width() - total) / 2, self.height() / 2
        icon = QtCore.QRectF(x, cy - 11, 22, 22)
        label = QtCore.QRectF(x + 34, 0, text_w + 2, self.height())
        prompt = QtCore.QRectF(x + 22 + (12 + text_w if text_w else 0) + 14, 0, glyph_w, self.height())
        p.drawPixmap(mirror(self, icon).toRect(), icon_pixmap(self.icon_name, 22, self.icon_color or ink.name()))
        p.setPen(ink)
        if text_w:
            p.drawText(mirror(self, label), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if glyph_w:
            faint = QtGui.QColor(ink)
            faint.setAlpha(150)
            draw_glyph(p, mirror(self, prompt).x(), cy, self._token(), INPUT.mode, faint)


class Switch(QtWidgets.QAbstractButton):
    """On / off, like Windows' own switches; white when on."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.NoPen if on else QtGui.QPen(QtGui.QColor(255, 255, 255, 70), 1))
        p.setBrush(QtGui.QColor(INK) if on else QtGui.QColor(255, 255, 255, 18))
        p.drawRoundedRect(QtCore.QRectF(0.5, 0.5, 45, 25), 12.5, 12.5)
        knob = 30 if on != self.isRightToLeft() else 4
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(DARK) if on else QtGui.QColor(INK))
        p.drawEllipse(QtCore.QRectF(knob, 5, 16, 16) if on else QtCore.QRectF(knob + 1, 6, 14, 14))


def icon_badge(name: str) -> QtWidgets.QLabel:
    """A round badge with an icon, the leading mark of a card."""
    b = QtWidgets.QLabel(alignment=Qt.AlignCenter)
    b.setFixedSize(46, 46)
    b.setPixmap(icon_pixmap(name, 21))
    b.setStyleSheet("background: rgba(255,255,255,16); border-radius: 23px;")
    return b


class LevelRow(QtWidgets.QWidget):
    """One card of Audio mix: what it is, a volume bar, how loud (100% = as recorded), and Mute."""

    changed = QtCore.Signal()

    def __init__(self, label: str, describe: str, maximum: int, icon: str = "mic"):
        super().__init__()
        self.setFixedHeight(96)
        self.setAttribute(Qt.WA_Hover)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(16)
        lay.addWidget(icon_badge(icon))
        names = QtWidgets.QVBoxLayout()
        names.setSpacing(2)
        self.name = QtWidgets.QLabel(tr(label))
        self.name.setFont(font(16, QtGui.QFont.DemiBold))
        self.desc = QtWidgets.QLabel(tr(describe))
        self.desc.setFont(font(14))
        self.desc.setStyleSheet(f"color: {MUTED};")
        names.addStretch()
        names.addWidget(self.name)
        names.addWidget(self.desc)
        names.addStretch()
        lay.addLayout(names)
        self.slider = LevelSlider(Qt.Horizontal)
        self.slider.setLayoutDirection(Qt.LeftToRight)   # louder to the right in every language, like the video bar
        self.slider.setRange(0, maximum)
        self.slider.setSingleStep(LEVEL_STEP)
        self.slider.setPageStep(LEVEL_STEP * 2)
        self.slider.setMinimumWidth(150)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_value)
        lay.addWidget(self.slider, 1)
        self.amount = QtWidgets.QLabel(alignment=Qt.AlignCenter)
        self.amount.setFont(font(15, QtGui.QFont.DemiBold))
        self.amount.setFixedSize(80, 44)
        lay.addWidget(self.amount)
        mute_label = QtWidgets.QLabel(tr("Mute"))
        mute_label.setFont(font(14))
        mute_label.setStyleSheet(f"color: {MUTED};")
        lay.addWidget(mute_label)
        self.mute = Switch()
        self.mute.clicked.connect(self.toggle_mute)
        lay.addWidget(self.mute)
        self._unmuted = 100

    @property
    def value(self) -> int:
        return self.slider.value()

    def set_value(self, percent: int):
        self.slider.setValue(percent)
        self._on_value(self.slider.value())

    def step(self, delta: int):
        self.slider.setValue(self.slider.value() + delta * LEVEL_STEP)

    def toggle_mute(self):
        """Mute, or back to the level it had before."""
        if self.value > 0:
            self._unmuted = self.value
            self.slider.setValue(0)
        else:
            self.slider.setValue(self._unmuted or 100)

    def _on_value(self, v: int):
        snapped = round(v / LEVEL_STEP) * LEVEL_STEP     # a drag lands on the nearest 25 %
        if snapped != v:
            self.slider.setValue(snapped)
            return
        self.amount.setText(f"‎{v}%")   # LRM keeps "150%" in order in Arabic
        muted = v == 0
        self.amount.setStyleSheet(
            f"color: {'#ff8a82' if muted else INK}; border-radius: 10px;"
            f"border: 1px solid {'rgba(255,105,97,110)' if muted else 'rgba(255,255,255,40)'};")
        self.mute.setChecked(muted)
        self.changed.emit()

    def setFocus(self, *args):
        self.slider.setFocus(*args)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        paint_card(p, QtCore.QRectF(self.rect()), self.slider.hasFocus(), self.underMouse())


class OptionCard(QtWidgets.QAbstractButton):
    """A Share setting as a card: a name, what it does, and its choices side by side.
    Enter / ✕ moves to the next choice; a click picks one."""

    picked = QtCore.Signal(object)

    def __init__(self, icon: str, title: str, choices: list[tuple[object, str]], describe):
        super().__init__()
        self.icon_name, self.title, self.choices, self.describe = icon, title, choices, describe
        self.index = 0
        self.note = ""            # replaces the description when the card can't be used
        self.setFixedHeight(150)
        self.setMinimumWidth(300)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.StrongFocus)

    @property
    def value(self):
        return self.choices[self.index][0]

    def set_value(self, value):
        self.index = next((i for i, (v, _) in enumerate(self.choices) if v == value), 0)
        self.update()
        self.picked.emit(self.value)

    def next(self):
        if self.isEnabled():
            self.set_value(self.choices[(self.index + 1) % len(self.choices)][0])

    def _segments(self) -> list[QtCore.QRectF]:
        bar = QtCore.QRectF(20, self.height() - 58, self.width() - 40, 40)
        w = (bar.width() - 8) / len(self.choices)
        return [mirror(self, QtCore.QRectF(bar.x() + 4 + i * w, bar.y() + 4, w, bar.height() - 8))
                for i in range(len(self.choices))]

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        self.setFocus(Qt.MouseFocusReason)
        for i, seg in enumerate(self._segments()):
            if seg.contains(e.position()):
                self.set_value(self.choices[i][0])
                return

    def keyPressEvent(self, e):
        e.ignore()        # the viewer moves between cards and picks with Enter

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        paint_card(p, QtCore.QRectF(self.rect()), self.hasFocus(), self.underMouse() and self.isEnabled())
        badge = mirror(self, QtCore.QRectF(20, 20, 40, 40))
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 16))
        p.drawEllipse(badge)
        p.drawPixmap(badge.adjusted(10, 10, -10, -10).toRect(), icon_pixmap(self.icon_name, 20))
        p.setPen(QtGui.QColor(INK))
        p.setFont(font(16, QtGui.QFont.DemiBold))
        flags = Qt.AlignLeft | Qt.AlignVCenter    # Qt turns this to the right in Arabic by itself
        p.drawText(mirror(self, QtCore.QRectF(74, 18, self.width() - 94, 24)), flags, self.title)
        p.setPen(QtGui.QColor(236, 240, 250, 200))
        p.setFont(font(14))
        sub = self.note or (self.describe(self.value) if callable(self.describe) else self.describe)
        p.drawText(mirror(self, QtCore.QRectF(74, 42, self.width() - 94, 22)), flags,
                   p.fontMetrics().elidedText(sub, Qt.ElideRight, self.width() - 94))
        bar = QtCore.QRectF(20, self.height() - 58, self.width() - 40, 40)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 90))
        p.drawRoundedRect(bar, 10, 10)
        p.setFont(font(14, QtGui.QFont.DemiBold))
        for i, seg in enumerate(self._segments()):
            chosen = i == self.index
            if chosen:
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor(INK) if self.hasFocus() else QtGui.QColor(255, 255, 255, 44))
                p.drawRoundedRect(seg, 7, 7)
            p.setPen(QtGui.QColor(DARK) if chosen and self.hasFocus()
                     else QtGui.QColor(INK) if chosen else QtGui.QColor(236, 240, 250, 185))
            p.drawText(seg, Qt.AlignCenter, p.fontMetrics().elidedText(self.choices[i][1], Qt.ElideRight,
                                                                         int(seg.width()) - 12))


class Timeline(QtWidgets.QWidget):
    """PS5-style trim bar: a filmstrip with start/end handles and a playhead."""

    seek = QtCore.Signal(int)       # ms
    changed = QtCore.Signal()       # start or end moved

    MIN_MS = 500
    PAD = 10

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(76)
        self.setCursor(Qt.PointingHandCursor)
        self.duration, self.start, self.end, self.pos = 1, 0, 1, 0
        self.frames: dict[int, QtGui.QPixmap] = {}
        self.slots = 12
        self._drag: str | None = None

    def reset(self, duration_ms: int):
        self.duration = max(1, duration_ms)
        self.start, self.end, self.pos = 0, self.duration, 0
        self.frames.clear()
        self.update()

    def set_frame(self, i: int, path: str):
        self.frames[i] = QtGui.QPixmap(path)
        self.update()

    def _x(self, ms: int) -> float:
        return self.PAD + (self.width() - 2 * self.PAD) * ms / self.duration

    def _ms(self, x: float) -> int:
        w = self.width() - 2 * self.PAD
        return int(max(0, min(self.duration, (x - self.PAD) / w * self.duration)))

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        h = self.height()
        strip = QtCore.QRectF(self.PAD, 8, self.width() - 2 * self.PAD, h - 16)
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(strip, 8, 8)
        p.save()
        p.setClipPath(clip)
        p.fillRect(strip, QtGui.QColor(255, 255, 255, 18))
        slot_w = strip.width() / self.slots
        for i, pm in self.frames.items():
            if pm.isNull():
                continue
            target = QtCore.QRectF(strip.x() + i * slot_w, strip.y(), slot_w + 1, strip.height())
            scaled = pm.scaled(int(target.width()) + 1, int(target.height()) + 1,
                               Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(target, scaled, QtCore.QRectF(
                (scaled.width() - target.width()) / 2, (scaled.height() - target.height()) / 2,
                target.width(), target.height()))
        x1, x2 = self._x(self.start), self._x(self.end)
        dim = QtGui.QColor(0, 0, 0, 185)
        p.fillRect(QtCore.QRectF(strip.left(), strip.top(), x1 - strip.left(), strip.height()), dim)
        p.fillRect(QtCore.QRectF(x2, strip.top(), strip.right() - x2, strip.height()), dim)
        p.restore()
        # selection frame and handles
        ink = QtGui.QColor(INK)
        p.setPen(QtGui.QPen(ink, 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(x1, strip.top() - 1, x2 - x1, strip.height() + 2), 6, 6)
        p.setPen(Qt.NoPen)
        for x in (x1, x2):
            p.setBrush(ink)
            p.drawRoundedRect(QtCore.QRectF(x - 6, 2, 12, h - 4), 5, 5)
            p.setBrush(QtGui.QColor(DARK))
            p.drawRoundedRect(QtCore.QRectF(x - 1.25, h / 2 - 9, 2.5, 18), 1.25, 1.25)
        # playhead
        xp = self._x(self.pos)
        p.setBrush(QtGui.QColor(RED))
        p.drawRoundedRect(QtCore.QRectF(xp - 1.25, 0, 2.5, h), 1.25, 1.25)

    def mousePressEvent(self, e):
        x = e.position().x()
        if abs(x - self._x(self.start)) < 12:
            self._drag = "start"
        elif abs(x - self._x(self.end)) < 12:
            self._drag = "end"
        else:
            self._drag = "pos"
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        ms = self._ms(e.position().x())
        if self._drag == "start":
            self.start = max(0, min(ms, self.end - self.MIN_MS))
            ms = self.start
            self.changed.emit()
        elif self._drag == "end":
            self.end = min(self.duration, max(ms, self.start + self.MIN_MS))
            ms = self.end
            self.changed.emit()
        self.pos = ms
        self.seek.emit(ms)  # show the frame under the handle
        self.update()

    def mouseReleaseEvent(self, _):
        self._drag = None

    def set_start(self, ms: int):
        self.start = max(0, min(ms, self.end - self.MIN_MS))
        self.changed.emit()
        self.update()

    def set_end(self, ms: int):
        self.end = min(self.duration, max(ms, self.start + self.MIN_MS))
        self.changed.emit()
        self.update()


class Viewer(QtWidgets.QWidget):
    """Check a capture right after taking it: play, scrub, trim, step through, delete."""

    preview_ready = QtCore.Signal(str, str)   # original, preview path ("" = failed)
    preview_progress = QtCore.Signal(str, int)
    frame_ready = QtCore.Signal(str, int, str)
    sound_ready = QtCore.Signal(str, str)    # clip, short remixed piece to listen to ("" = failed)
    closed = QtCore.Signal()

    def __init__(self, ctl: Controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.ctl = ctl
        self.items: list[Path] = []
        self.index = 0
        self.trimming = False
        self.sharing = False
        self.editing = False
        self.sounding = False                    # the Sound panel: voice and game levels of this clip
        self._previewing_sound = False
        self._pending_trim = False
        self._tried_preview: set[Path] = set()
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(VIEWER_STYLE)
        self.setFont(font(13))
        dress(self)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(64, 36, 64, 24)
        lay.setSpacing(16)
        self.full = False                        # only the video, nothing around it

        def button(row, text, fn, icon=None, name=""):
            label = tr(text).replace("&", "&&")   # "&" isn't a shortcut here
            b = QtWidgets.QPushButton(("  " + label) if icon and label else label, objectName=name)
            if icon:
                b.setIcon(qicon(icon, DARK if name == "primary" else INK))
                b.setIconSize(QtCore.QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            row.addWidget(b)
            return b

        # ---- header: Back, the title with Rename next to it, newer / older, close
        self.head = QtWidgets.QWidget()
        head = QtWidgets.QHBoxLayout(self.head)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(0)
        self.back_btn = back_button(self.go_back)
        head.addWidget(self.back_btn, 0, Qt.AlignTop)
        head.addSpacing(22)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(3)
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(14)
        self.title = QtWidgets.QLabel(objectName="vTitle")
        title_row.addWidget(self.title)
        self.rename_btn = button(title_row, "Rename", self.start_edit, "pencil", "pill")
        title_row.addStretch()
        titles.addLayout(title_row)
        self.sub = QtWidgets.QLabel(objectName="vSub")
        titles.addWidget(self.sub)
        self.note = QtWidgets.QLabel(objectName="vNote")
        self.note.hide()
        titles.addWidget(self.note)
        head.addLayout(titles, 1)
        self.counter = QtWidgets.QLabel(objectName="hint")
        head.addWidget(self.counter, 0, Qt.AlignTop)
        head.addSpacing(16)
        rtl = is_rtl()     # newer is to the left, or to the right in Arabic
        self.prev_btn = button(head, "", lambda: self.step(-1), "right" if rtl else "left", "round")
        head.addSpacing(10)
        self.next_btn = button(head, "", lambda: self.step(1), "left" if rtl else "right", "round")
        self.prev_btn.setToolTip(tr("Newer ({key})", key="D" if rtl else "A"))
        self.next_btn.setToolTip(tr("Older ({key})", key="A" if rtl else "D"))
        head.addSpacing(18)
        rule = QtWidgets.QFrame(objectName="rule")
        rule.setFixedSize(1, 30)
        head.addWidget(rule, 0, Qt.AlignVCenter)
        head.addSpacing(18)
        self.close_btn = button(head, "", self.close_viewer, "close", "round")
        for b in (self.prev_btn, self.next_btn, self.close_btn):
            head.setAlignment(b, Qt.AlignTop)
        self.close_btn.setToolTip(tr("Close (Esc)"))
        lay.addWidget(self.head)

        # ---- the video card: the picture, and its controls built into the bottom edge
        self.card = QtWidgets.QFrame(objectName="videoCard")
        card = QtWidgets.QVBoxLayout(self.card)
        card.setContentsMargins(1, 1, 1, 0)
        card.setSpacing(0)
        self.stage = QtWidgets.QStackedWidget(objectName="stage")
        self.image = QtWidgets.QLabel(alignment=Qt.AlignCenter)
        self.image.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)  # the picture follows the stage, never the other way
        self.msg = QtWidgets.QLabel(objectName="vMsg", alignment=Qt.AlignCenter, wordWrap=True)
        self.stage.addWidget(self.image)
        self.stage.addWidget(self.msg)
        self.player = self.video = None     # made on the first video, dropped a minute after closing
        self._frames = 0
        self._watchdog = QtCore.QTimer(self, singleShot=True, interval=2500, timeout=self._check_frames)
        self._drop_timer = QtCore.QTimer(self, singleShot=True, interval=60_000, timeout=self._drop_player)
        card.addWidget(self.stage, 1)
        self.controls = QtWidgets.QFrame(objectName="ctlBar")
        self.controls.setFixedHeight(60)
        self.controls.setLayoutDirection(Qt.LeftToRight)   # time runs left to right, like the trim filmstrip
        cl = QtWidgets.QHBoxLayout(self.controls)
        cl.setContentsMargins(16, 0, 16, 0)
        cl.setSpacing(16)
        self.play_btn = button(cl, "", self.toggle_play, "pause", "ctl")
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player and self.player.setPosition(v))
        self.time = QtWidgets.QLabel("0:00 / 0:00", objectName="time")
        cl.addWidget(self.slider, 1)
        cl.addWidget(self.time)
        self.vol_btn = button(cl, "", self.toggle_mute, "volume", "ctl")
        self.vol_btn.setToolTip(tr("Sound on / off"))
        self.full_btn = button(cl, "", self.toggle_full, "maximize", "ctl")
        self.full_btn.setToolTip(tr("Only the video"))
        card.addWidget(self.controls)
        lay.addWidget(self.card, 1)

        def panel_head(box, title: str, sub: str = "") -> QtWidgets.QLabel:
            t = QtWidgets.QLabel(tr(title), objectName="panelTitle")
            box.addWidget(t)
            s = QtWidgets.QLabel(tr(sub) if sub else "", objectName="panelSub")
            box.addWidget(s)
            box.addSpacing(6)
            return s

        # ---- Trim: the filmstrip with its start and end handles
        self.trim_panel = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(self.trim_panel)
        tl.setContentsMargins(0, 4, 0, 0)
        tl.setSpacing(2)
        trim_top = QtWidgets.QHBoxLayout()
        trim_titles = QtWidgets.QVBoxLayout()
        trim_titles.setSpacing(2)
        panel_head(trim_titles, "Trim", "Drag the handles, or mark the start and the end while it plays")
        trim_top.addLayout(trim_titles)
        trim_top.addStretch()
        self.trim_info = QtWidgets.QLabel(objectName="time")
        trim_top.addWidget(self.trim_info, 0, Qt.AlignBottom)
        tl.addLayout(trim_top)
        self.timeline = Timeline()
        self.timeline.seek.connect(self._timeline_seek)
        self.timeline.changed.connect(self._trim_labels)
        tl.addWidget(self.timeline)
        lay.addWidget(self.trim_panel)

        # ---- Audio mix: how loud your voice and the game are in this clip
        self.sound_panel = QtWidgets.QWidget()
        sdl = QtWidgets.QVBoxLayout(self.sound_panel)
        sdl.setContentsMargins(0, 4, 0, 0)
        sdl.setSpacing(2)
        self.sound_caption = panel_head(sdl, "Audio mix",
                                        "Change your voice and the game separately. 100% is as recorded")
        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(16)
        self.voice_row = LevelRow("Your voice", "Your microphone in this clip", VOICE_MAX, "mic")
        self.game_row = LevelRow("Game", "The game's sound in this clip", GAME_MAX, "gamepad")
        for r in (self.voice_row, self.game_row):
            cards.addWidget(r, 1)
        sdl.addLayout(cards)
        sdl.addSpacing(8)
        kept = QtWidgets.QHBoxLayout()
        kept.setSpacing(8)
        info = QtWidgets.QLabel()
        info.setPixmap(icon_pixmap("info", 16, "#a9a9ae"))
        kept.addWidget(info)
        kept.addWidget(QtWidgets.QLabel(tr("Both are kept on their own tracks, so you can change this again"),
                                        objectName="info"))
        kept.addStretch()
        sdl.addLayout(kept)
        lay.addWidget(self.sound_panel)

        # ---- Share / Export: where this capture is going
        self.share_panel = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self.share_panel)
        sl.setContentsMargins(0, 4, 0, 0)
        sl.setSpacing(2)
        self.share_caption = panel_head(sl, "Share / Export")
        share_cards = QtWidgets.QHBoxLayout()
        share_cards.setSpacing(16)
        self.format_card = OptionCard("file-video", tr("Format"),
                                      [("mp4", tr("MP4 for phones & apps")), ("copy", tr("Original file"))],
                                      lambda v: tr("Plays everywhere: WhatsApp, Discord, phones")
                                      if v == "mp4" else tr("The clip exactly as it was saved"))
        self.voice_card = OptionCard("mic", tr("Your voice"), [(True, tr("Include")), (False, tr("Leave out"))],
                                     lambda v: tr("Your microphone is in the video") if v
                                     else tr("Only the game's sound"))
        self.size_card = OptionCard("export", tr("Size limit"),
                                    [(None, tr("No limit"))] + [(mb, f"{mb} {tr('MB')}") for mb in (10, 50, 500)],
                                    lambda v: tr("Full quality") if v is None
                                    else tr("Discord without Nitro allows 10 MB") if v == 10
                                    else tr("Made to fit, quality drops as needed"))
        for c in (self.format_card, self.voice_card, self.size_card):
            share_cards.addWidget(c, 1)
        self.format_card.picked.connect(lambda _: self._share_cards_state())
        sl.addLayout(share_cards)
        lay.addWidget(self.share_panel)

        # ---- the main actions, then the rest as small icon buttons (△ / M walks them)
        self.actions_row = QtWidgets.QWidget()
        act = QtWidgets.QHBoxLayout(self.actions_row)
        act.setContentsMargins(0, 4, 0, 0)
        act.setSpacing(14)
        act.addStretch()
        self.trim_btn = ActionButton(tr("Trim"), "scissors", "X", "k:T")
        self.sound_btn = ActionButton(tr("Adjust audio"), "audio", "L3", "k:V")
        self.share_btn = ActionButton(tr("Share / Export"), "export", "OPT", "k:E", primary=True)
        for b, fn in ((self.trim_btn, self.enter_trim), (self.sound_btn, self.enter_sound),
                      (self.share_btn, self.enter_share)):
            b.clicked.connect(fn)
            act.addWidget(b)
        act.addSpacing(18)
        self.tools_hint = HintBar()             # △ / M: the button that walks the small ones
        act.addWidget(self.tools_hint, 0, Qt.AlignVCenter)
        self.fav_btn = ActionButton("", "star", None, "k:F")
        self.folder_chip = ActionButton("", "folder")
        self.external_chip = ActionButton("", "external")
        self.del_btn = ActionButton("", "trash", None, "k:Del")
        for b, fn, tip in ((self.fav_btn, self.toggle_favorite, tr("Favorite")),
                           (self.folder_chip, lambda: self.ctl.reveal(self.current), tr("Show in folder")),
                           (self.external_chip, self._open_external, tr("Open in your video player")),
                           (self.del_btn, self.delete_current, tr("Delete"))):
            b.clicked.connect(fn)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.TabFocus)       # walked with ← →, chosen with ✕; a click leaves the keys alone
            act.addWidget(b)
        act.addStretch()
        lay.addWidget(self.actions_row)

        # ---- footer: what the buttons do on the left, the open panel's buttons on the right
        self.footer = QtWidgets.QFrame(objectName="footer")
        foot = QtWidgets.QHBoxLayout(self.footer)
        foot.setContentsMargins(0, 14, 0, 0)
        foot.setSpacing(10)
        self.keys_hint = self.trim_hints = self.share_hints = self.sound_hints = HintBar()
        foot.addWidget(self.keys_hint)
        foot.addStretch()
        self.trim_buttons = QtWidgets.QWidget()
        trow = QtWidgets.QHBoxLayout(self.trim_buttons)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(10)
        button(trow, "Preview", self.preview_selection, "play")
        button(trow, "Cancel", self.exit_trim)
        button(trow, "Replace original", lambda: self.save_trim(replace=True))
        button(trow, "Save as new clip", lambda: self.save_trim(replace=False), "scissors", "primary")
        self.sound_buttons = QtWidgets.QWidget()
        srow = QtWidgets.QHBoxLayout(self.sound_buttons)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(10)
        button(srow, "Preview mix", self.preview_sound, "play")
        button(srow, "Cancel", self.exit_sound)
        button(srow, "Save mix", self.save_sound, None, "primary")
        self.share_buttons = QtWidgets.QWidget()
        shrow = QtWidgets.QHBoxLayout(self.share_buttons)
        shrow.setContentsMargins(0, 0, 0, 0)
        shrow.setSpacing(10)
        self.share_cancel = button(shrow, "Cancel", lambda: self._set_sharing(False))
        self.share_go = button(shrow, "Export & copy", self._do_share, "copy", "primary")
        for w in (self.trim_buttons, self.sound_buttons, self.share_buttons):
            foot.addWidget(w)
        lay.addWidget(self.footer)

        # ---- Rename: a small dialog over the dimmed video
        self.edit_dim = QtWidgets.QWidget(self, objectName="dim")
        self.edit_dim.setAttribute(Qt.WA_StyledBackground)
        self.edit_panel = QtWidgets.QFrame(self, objectName="dialog")
        el = QtWidgets.QVBoxLayout(self.edit_panel)
        el.setContentsMargins(32, 28, 32, 28)
        el.setSpacing(6)
        self.edit_heading = QtWidgets.QLabel(tr("Rename"), objectName="panelTitle")
        el.addWidget(self.edit_heading)
        el.addWidget(QtWidgets.QLabel(tr("A name you'll find easily later"), objectName="panelSub"))
        el.addSpacing(16)
        el.addWidget(QtWidgets.QLabel(tr("Title"), objectName="fieldLabel"))
        el.addSpacing(4)
        self.title_edit = QtWidgets.QLineEdit(placeholderText=tr("Title, e.g. Boss down on the first try"))
        self.note_edit = QtWidgets.QLineEdit(placeholderText=tr("Note (optional)"))
        self.title_edit.setMaxLength(80)
        self.note_edit.setMaxLength(200)
        for w in (self.title_edit, self.note_edit):
            w.returnPressed.connect(self.save_edit)
        el.addWidget(self.title_edit)
        el.addSpacing(10)
        self.note_toggle = QtWidgets.QPushButton("+  " + tr("Add a note (optional)"), objectName="noteToggle")
        self.note_toggle.setCursor(Qt.PointingHandCursor)
        self.note_toggle.clicked.connect(self._show_note_field)
        el.addWidget(self.note_toggle)
        el.addWidget(self.note_edit)
        el.addSpacing(18)
        erow = QtWidgets.QHBoxLayout()
        erow.setSpacing(10)
        erow.addStretch()
        button(erow, "Cancel", self.cancel_edit)
        button(erow, "Save title", self.save_edit, None, "primary")
        el.addLayout(erow)
        self.edit_panel.setFixedWidth(600)
        self.edit_dim.hide()
        self.edit_panel.hide()

        self._disarm = QtCore.QTimer(self, singleShot=True, timeout=self._reset_delete)
        for b in self.findChildren(QtWidgets.QPushButton):
            b.setFocusPolicy(Qt.NoFocus)  # keys go to the viewer, not to a button
        for b in (self.share_cancel, self.share_go):
            b.setFocusPolicy(Qt.StrongFocus)   # Share is walked with ← → like its cards
        INPUT.changed.connect(lambda _: (self.update_hints(), self._pick_focus()) if self.items else None)
        self.slider.setObjectName("seek")
        self.slider.setFocusPolicy(Qt.NoFocus)   # a click doesn't take the keys; the controller still lands on it
        for w in self._all_nav():
            w.installEventFilter(self)           # their keys come to the viewer, which moves the highlight
        self.preview_ready.connect(self._on_preview_ready)
        self.preview_progress.connect(self._on_preview_progress)
        self.frame_ready.connect(self._on_frame)
        self.sound_ready.connect(self._on_sound_ready)
        ctl.trimmed.connect(self._on_trimmed)
        ctl.remixed.connect(self._on_remixed)
        self._sync()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)      # the sheet: the game stays faintly visible behind it
        p.fillRect(self.rect(), sheet_color(self))

    @property
    def current(self) -> Path:
        return self.items[self.index]

    def is_video(self) -> bool:
        return bool(self.items) and self.current.suffix.lower() != ".png"

    # ---- open / close
    def open(self, items: list[Path], index: int = 0, trim: bool = False, back_to=None, fresh: bool = False):
        """fresh: opened from outside (a notice), not from another page."""
        self.back_to = back_to      # what Back returns to once no panel is open (None: just close)
        self._drop_timer.stop()
        self.items, self.index = list(items), index
        self._pending_trim = trim and items[index].suffix.lower() != ".png"
        dress(self)
        self.setGeometry(ui_screen(fresh).geometry())   # covers the game's screen, like the PS5 viewer
        self.show()
        bring_to_front(self)
        self.show_item()

    def go_back(self):
        """One step back: an open panel first, then wherever the viewer was opened from."""
        if self.editing:
            self.cancel_edit()
        elif self.full:
            self.toggle_full()
        elif self.sounding:
            self.exit_sound()
        elif self.sharing:
            self._set_sharing(False)
        elif self.trimming:
            self.exit_trim()
        elif self.del_btn.danger:
            self._reset_delete()
        else:
            back, self.back_to = getattr(self, "back_to", None), None
            self.close_viewer()
            if back:
                back()

    def close_viewer(self):
        self._release()
        self.image.clear()       # a screenshot fitted to the screen: up to 15 MB
        self.hide()
        self._drop_timer.start()
        self.closed.emit()

    def _release(self):
        self._watchdog.stop()
        if self.player:
            self.player.stop()
            self.player.setSource(QtCore.QUrl())  # let go of the file

    def _ensure_player(self) -> bool:
        self._drop_timer.stop()
        if self.player is not None:
            return True
        if not load_multimedia():
            return False
        self.video = QtMultimediaWidgets.QVideoWidget()
        self.video.setFocusPolicy(Qt.NoFocus)
        self.video.installEventFilter(self)      # if it takes the keys anyway, they still reach the viewer
        self.stage.addWidget(self.video)
        self.player = QtMultimedia.QMediaPlayer(self)
        self.audio = QtMultimedia.QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setMuted(getattr(self, "_muted", False))
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)
        # Some decoders (e.g. AV1 without GPU support) play the sound but never
        # deliver a picture and report no error, so watch for real frames.
        self.video.videoSink().videoFrameChanged.connect(self._on_frame_shown)
        return True

    def _drop_player(self):
        """Gives the decoder's memory back once the viewer has been closed for a while,
        and the window's picture of itself with it."""
        if self.isVisible():
            return
        if self.player is not None:
            self._release()
            self.stage.removeWidget(self.video)
            for obj in (self.player, self.audio, self.video):
                obj.deleteLater()
            self.player = self.audio = self.video = None
        release_window(self)

    # ---- showing a capture
    def show_item(self):
        self._release()
        self._reset_delete()
        self._set_trimming(False)
        self._set_sharing(False)
        self._set_editing(False)
        self._set_sound(False)
        path = self.current
        log.info("viewer: %s (%s) on %s", path.name, path.parent.name, self.screen().name() if self.screen() else "?")
        self._show_title()
        self.sub.setToolTip(str(path))
        self.counter.setText(tr("{n} of {total}", n=self.index + 1, total=len(self.items)))
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.items) - 1)
        self.trim_btn.setVisible(self.is_video())
        self.sound_btn.setVisible(self.is_video())
        self.controls.setVisible(self.is_video())
        self.update_hints()
        self._pick_focus(fresh=True)
        if not self.is_video():
            self.controls.hide()
            self.stage.setCurrentWidget(self.image)
            self._fit_image()
        elif not self._ensure_player():
            self._show_msg("Preview isn't available here. Use “Open in player”.")
        else:
            preview = self.ctl.preview_path(path)
            self._play(preview if preview.exists() else path)

    def _play(self, source: Path):
        self.controls.show()
        self.stage.setCurrentWidget(self.video)
        self._frames = 0
        self.player.setSource(QtCore.QUrl.fromLocalFile(str(source)))
        self.player.play()
        self._watchdog.start()

    def _on_duration(self, ms: int):
        self.slider.setRange(0, ms)
        if self._pending_trim and ms > 0:     # opened with "Trim" from the notification
            self._pending_trim = False
            QtCore.QTimer.singleShot(150, self.enter_trim)

    def _on_frame_shown(self, frame):
        if frame.isValid():
            self._frames += 1

    def _check_frames(self):
        on_video = self.player is not None and self.isVisible() and self.stage.currentWidget() is self.video
        if on_video and self._frames == 0 and self.player.position() > 0:
            log.warning("no video frames decoded; switching to a preview copy")
            self._release()
            self._on_error()

    def _fit_image(self):
        pm = QtGui.QPixmap(str(self.current))
        if not pm.isNull():
            self.image.setPixmap(pm.scaled(self.stage.size(), Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))

    def _show_msg(self, text: str):
        self.controls.hide()
        self.msg.setText(tr(text))
        self.stage.setCurrentWidget(self.msg)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        side = 24 if self.full else max(64, (self.width() - 1680) // 2)    # keep lines short on a wide TV
        self.layout().setContentsMargins(side, 24 if self.full else 36, side, 24)
        if self.items and self.stage.currentWidget() is self.image:
            QtCore.QTimer.singleShot(0, self._fit_image)    # once the layout has settled
        self._place_dialog()

    def _on_error(self, *_):
        path = self.current if self.items else None
        log.warning("playback failed for %s: %s", path.name if path else "?",
                    self.player.errorString() if self.player else "no player")
        if path is None or path in self._tried_preview or self.ctl.preview_path(path).exists():
            self._show_msg("This clip can't be previewed here.\nIt's saved fine. Use “Open in player” to watch it.")
            return
        self._tried_preview.add(path)
        self._show_msg("Preparing preview…")

        def run():
            ok = make_preview(path, self.ctl.preview_path(path),
                              lambda pct: safe_emit(self.preview_progress, str(path), pct))
            safe_emit(self.preview_ready, str(path), str(self.ctl.preview_path(path)) if ok else "")
        threading.Thread(target=run, daemon=True).start()

    def _on_preview_progress(self, path: str, pct: int):
        if self.isVisible() and self.items and str(self.current) == path:
            self.msg.setText(tr("Preparing preview…  {pct}%", pct=pct))

    def _on_preview_ready(self, path: str, preview: str):
        if not (self.isVisible() and self.items and str(self.current) == path):
            return
        if preview:
            self._play(Path(preview))
        else:
            self._show_msg("This clip can't be previewed here.\nIt's saved fine. Use “Open in player” to watch it.")

    # ---- playback
    def toggle_play(self):
        if self.player is None or self.stage.currentWidget() is not self.video:
            return
        if self.player.playbackState() == QtMultimedia.QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if self.trimming and self.player.position() >= self.timeline.end - 50:
                self.player.setPosition(self.timeline.start)
            self.player.play()

    def seek(self, ms: int):
        if self.player is not None and self.stage.currentWidget() is self.video:
            self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + ms)))

    def _on_position(self, pos: int):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.time.setText(f"{short_clock(pos / 1000)} / {short_clock(self.player.duration() / 1000)}")
        if self.trimming:
            self.timeline.pos = pos
            self.timeline.update()
            playing = self.player.playbackState() == QtMultimedia.QMediaPlayer.PlayingState
            if playing and pos >= self.timeline.end:   # stop at the end of the selection
                self.player.pause()
                self.player.setPosition(self.timeline.end)

    def _on_state(self, state):
        playing = state == QtMultimedia.QMediaPlayer.PlayingState
        self.play_btn.setIcon(qicon("pause" if playing else "play"))

    # ---- trimming
    def enter_trim(self):
        if not self.is_video() or self.player is None or self.stage.currentWidget() is not self.video:
            return
        duration = self.player.duration() or int((media_duration(self.current) or 0) * 1000)
        if duration < 1000:
            return
        self.player.pause()
        self.timeline.reset(duration)
        self.timeline.pos = self.player.position()
        self._set_trimming(True)
        self._trim_labels()
        src, slots = self.current, self.timeline.slots
        tag = hashlib.md5(str(src).encode()).hexdigest()

        def run():  # filmstrip frames, filled in as they arrive
            for i in range(slots):
                out = self.ctl.thumbs_dir / f"strip_{tag}_{i}.jpg"
                if filmstrip_frame(src, int(duration * (i + 0.5) / slots), out):
                    safe_emit(self.frame_ready, str(src), i, str(out))
        threading.Thread(target=run, daemon=True).start()

    def _on_frame(self, src: str, i: int, path: str):
        if self.trimming and str(self.current) == src:
            self.timeline.set_frame(i, path)

    def exit_trim(self):
        self._set_trimming(False)

    def _set_trimming(self, on: bool):
        self.trimming = on
        self._sync()
        if not on:
            self._pick_focus()

    def _show_title(self):
        path = self.current
        fav = self.ctl.is_favorite(path)
        self.title.setTextFormat(Qt.RichText)
        star = '<span style="color:#ffd34d">★</span>&nbsp;' if fav else ""
        meta = self.ctl.meta(path)
        name = meta.get("title") or path.parent.name
        self.title.setText(star + name.replace("&", "&amp;").replace("<", "&lt;"))
        game = f"{path.parent.name}  ·  " if meta.get("title") else ""
        self.sub.setText(f"{game}{capture_kind(path)}  ·  {time_ago(path.stat().st_mtime)}")
        self.note.setText(meta.get("note", ""))
        self.note.setVisible(bool(meta.get("note")))
        self.fav_btn.setToolTip(tr("Favorited") if fav else tr("Favorite"))
        self.fav_btn.icon_color = "#ffd34d" if fav else None
        self.fav_btn.update()

    def toggle_favorite(self):
        if self.items:
            self.ctl.toggle_favorite(self.current)
            self._show_title()

    # ---- rename
    def start_edit(self):
        if not self.items:
            return
        meta = self.ctl.meta(self.current)
        self.title_edit.setText(meta.get("title", ""))
        self.note_edit.setText(meta.get("note", ""))
        self.note_edit.setVisible(bool(meta.get("note")))
        self.note_toggle.setVisible(not meta.get("note"))
        if self.player is not None:
            self.player.pause()
        self._set_trimming(False)
        self._set_sharing(False)
        self._reset_delete()
        self._set_editing(True)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _show_note_field(self):
        self.note_toggle.hide()
        self.note_edit.show()
        self.note_edit.setFocus()
        self._place_dialog()

    def save_edit(self):
        if self.editing:
            self.ctl.set_meta(self.current, self.title_edit.text(), self.note_edit.text())
            self._set_editing(False)
            self._show_title()

    def cancel_edit(self):
        self._set_editing(False)

    def _set_editing(self, on: bool):
        self.editing = on
        self._sync()
        if not on:
            self._pick_focus()

    def enter_sound(self):
        if not self.is_video():
            return
        if audio_tracks(self.current) < 3:
            self.ctl.toast.emit(tr("This clip has no separate voice track · "
                                   "it was recorded with “Voice on its own track” off"), "info")
            return
        voice, game = self.ctl.mix_of(self.current)
        self.voice_row.set_value(voice)
        self.game_row.set_value(game)
        self._set_trimming(False)
        self._set_sharing(False)
        self._set_sound(True)
        self.voice_row.setFocus()

    def exit_sound(self):
        previewed = self._previewing_sound
        self._set_sound(False)
        if previewed:
            self.show_item()     # back to the clip as it is

    def _set_sound(self, on: bool):
        self.sounding = on
        self._previewing_sound = self._previewing_sound and on
        self._sync()
        if not on:
            self._pick_focus()

    def preview_sound(self):
        """Plays 12 seconds from here with the levels picked, before anything is saved."""
        if not self.sounding or self.player is None:
            return
        src, start = self.current, self.player.position() / 1000
        voice, game = self.voice_row.value, self.game_row.value
        showing = Path(self.player.source().toLocalFile() or src)
        picture = showing if showing != src and showing.exists() and showing.parent == self.ctl.previews_dir \
            else None   # the 720p copy, when the clip itself doesn't play here
        out = self.ctl.thumbs_dir / "sound_preview.mp4"
        self._release()          # the last preview may still be open
        self._show_msg("Preparing preview…")

        def run():
            try:
                remix_audio(src, voice, game, out, seconds=12, start=start, picture=picture)
                safe_emit(self.sound_ready, str(src), str(out))
            except Exception:
                log.exception("sound preview failed")
                safe_emit(self.sound_ready, str(src), "")
        threading.Thread(target=run, daemon=True).start()

    def _on_sound_ready(self, src: str, piece: str):
        if not (self.isVisible() and self.sounding and self.items and str(self.current) == src):
            return
        if not piece:
            self._show_msg("Couldn't make a preview of this clip.")
            return
        self._previewing_sound = True
        self._play(Path(piece))
        self.player.play()

    def save_sound(self):
        if not self.sounding:
            return
        src, voice, game = self.current, self.voice_row.value, self.game_row.value
        previewed = self._previewing_sound
        self._set_sound(False)
        if (voice, game) == self.ctl.mix_of(src):   # nothing to save
            if previewed:
                self.show_item()   # back to the clip from the preview piece
            return
        self._release()          # the file is rewritten, so let go of it
        self._show_msg("Changing the sound…")
        self.ctl.set_mix(src, voice, game)

    def _on_remixed(self, path: str):
        if self.isVisible() and self.items and str(self.current) == path:
            self.show_item()

    # ---- share
    def enter_share(self):
        if not self.items:
            return
        self._set_trimming(False)
        self._reset_delete()
        self._set_sharing(True)

    def _set_sharing(self, on: bool):
        self.sharing = on
        if on:
            video = self.is_video()
            # leaving your voice out needs the separate game-only track (voice_track in OBS)
            split = video and audio_tracks(self.current) >= 3
            for card in (self.format_card, self.voice_card, self.size_card):
                card.setVisible(video)
            self.format_card.set_value("mp4")
            self.voice_card.set_value(True)
            self.size_card.set_value(None)
            self._split = split
            self.share_caption.setText(tr("Makes a file that plays everywhere and copies it, ready to paste")
                                       if video else tr("Copies the screenshot so you can paste it anywhere"))
            self._share_cards_state()
            self.share_go.setFocus()
        self._sync()
        if not on:
            self._pick_focus()

    def _share_cards_state(self):
        """The original file is copied as it is: your voice and the size don't apply to it."""
        original = not self.is_video() or self.format_card.value == "copy"
        split = getattr(self, "_split", False)
        self.voice_card.setEnabled(split and not original)
        self.voice_card.note = ("" if split and not original else
                                tr("Not needed for the original file") if original else
                                tr("This clip has your voice and the game together"))
        self.size_card.setEnabled(not original)
        self.size_card.note = tr("Not needed for the original file") if original else ""
        for card in (self.voice_card, self.size_card):
            card.update()
        self.share_go.setText("  " + (tr("Copy") if not self.is_video() else
                                      tr("Copy file") if original else tr("Export & copy")).replace("&", "&&"))

    def _toggle_voice(self):
        self.voice_card.next()

    @property
    def without_voice(self) -> bool:
        return self.voice_card.isEnabled() and self.voice_card.value is False

    def _do_share(self, *_):
        path = self.current
        copy_only = not self.is_video() or self.format_card.value == "copy"
        size, without_voice = self.size_card.value, self.without_voice
        self._set_sharing(False)
        if copy_only:
            self.ctl.copy(path)
        else:
            self.ctl.share(path, "phone" if size is None else f"discord{size}", without_voice)

    def _share_nav(self) -> list[QtWidgets.QWidget]:
        cards = [c for c in (self.format_card, self.voice_card, self.size_card) if c.isVisible() and c.isEnabled()]
        return cards + [self.share_cancel, self.share_go]

    def _all_nav(self) -> list[QtWidgets.QWidget]:
        return [self.back_btn, self.rename_btn, self.prev_btn, self.next_btn, self.close_btn,
                self.play_btn, self.slider, self.vol_btn, self.full_btn,
                self.trim_btn, self.sound_btn, self.share_btn,
                self.fav_btn, self.folder_chip, self.external_chip, self.del_btn]

    def _nav_items(self) -> list[QtWidgets.QWidget]:
        """Everything on screen the controller's highlight can go to, like a mouse."""
        return [w for w in self._all_nav() if w.isVisible() and w.isEnabled()]

    def _pick_focus(self, fresh: bool = False):
        """With a controller the highlight sits on something on screen (Play, or Share for a picture);
        with the keyboard the viewer keeps the keys for its shortcuts. fresh: a new capture is shown."""
        if not self.isVisible() or self.trimming or self.sounding or self.sharing or self.editing:
            return
        if INPUT.mode == "keyboard":
            self.setFocus()
        elif fresh or self.focusWidget() not in self._nav_items():
            (self.play_btn if self.is_video() else self.share_btn).setFocus()

    # ---- the small buttons, only the video, sound on / off
    def toggle_more(self):
        """△ / M: the highlight jumps to the small buttons at the end of the row."""
        self.fav_btn.setFocus()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress and (obj in self._all_nav() or obj is self.video):
            self.keyPressEvent(event)        # a focused button would eat the arrows and ✕ itself
            return True
        return super().eventFilter(obj, event)

    def toggle_full(self):
        self.full = not self.full
        self._sync()
        self.resizeEvent(QtGui.QResizeEvent(self.size(), self.size()))

    def toggle_mute(self):
        self._muted = not getattr(self, "_muted", False)
        if self.player is not None:
            self.audio.setMuted(self._muted)
        self.vol_btn.setIcon(qicon("volume-off" if self._muted else "volume"))

    def _sync(self):
        """Shows what goes with the state: one panel at a time, its buttons in the footer."""
        panel = self.trimming or self.sounding or self.sharing
        full = self.full
        self.head.setVisible(not full)
        self.trim_panel.setVisible(self.trimming and not full)
        self.sound_panel.setVisible(self.sounding and not full)
        self.share_panel.setVisible(self.sharing and not full)
        self.actions_row.setVisible(not panel and not full)
        self.footer.setVisible(not full)
        self.trim_buttons.setVisible(self.trimming)
        self.sound_buttons.setVisible(self.sounding)
        self.share_buttons.setVisible(self.sharing)
        self.full_btn.setIcon(qicon("minimize" if full else "maximize"))
        self.edit_dim.setVisible(self.editing)
        self.edit_panel.setVisible(self.editing)
        if self.editing:
            self._place_dialog()
            self.edit_dim.raise_()
            self.edit_panel.raise_()
        self.update_hints()

    def _place_dialog(self):
        if not self.edit_panel.isVisible():
            return
        card = self.card.geometry()
        self.edit_dim.setGeometry(card)
        w = self.edit_panel.width()
        h = self.edit_panel.layout().totalHeightForWidth(w) if self.edit_panel.layout().hasHeightForWidth()             else self.edit_panel.sizeHint().height()
        self.edit_panel.setGeometry(card.center().x() - w // 2, card.center().y() - h // 2, w, h)

    def update_hints(self):
        pad, mode = INPUT.mode != "keyboard", INPUT.mode
        if self.editing:
            items = [("B", "Cancel")] if pad else [("k:Enter", "Save"), ("k:Esc", "Cancel")]
        elif self.sounding:
            items = ([("DPAD_UD", "Switch"), ("DPAD_LR", "Change"), ("Y", "Mute"), ("X", "Preview"), ("A", "Save"),
                      ("B", "Cancel")] if pad else
                     [("k:↑ ↓", "Switch"), ("k:← →", "Change"), ("k:M", "Mute"), ("k:P", "Preview"),
                      ("k:Enter", "Save"), ("k:Esc", "Cancel")])
        elif self.sharing:
            items = ([("DPAD_LR", "Move"), ("A", "Select"), ("B", "Back")] if pad
                     else [("k:← →", "Move"), ("k:Enter", "Select"), ("k:Esc", "Back")])
        elif self.trimming:
            items = ([("X", "Start"), ("Y", "End"), ("L1", "Preview"), ("A", "Save"), ("B", "Cancel")] if pad
                     else [("k:I", "Start"), ("k:O", "End"), ("k:P", "Preview"), ("k:Enter", "Save"),
                           ("k:Esc", "Cancel")])
        elif pad:
            items = [("DPAD", "Move"), ("A", "Select"), ("L1R1", "Newer/older"), ("B", "Back")]
        elif self.is_video():
            items = [("k:Space", "Play/pause"), ("k:A D", "Newer/older"), ("k:F", "Favorite"),
                     ("k:N", "Rename"), ("k:Esc", "Back")]
        else:
            items = [("k:A D", "Newer/older"), ("k:F", "Favorite"), ("k:N", "Rename"), ("k:Esc", "Back")]
        self.keys_hint.set_items(items, mode)
        self.tools_hint.set_items([("Y" if pad else "k:M", "")], mode)

    def _timeline_seek(self, ms: int):
        if self.player:
            self.player.pause()
            self.player.setPosition(ms)

    def _trim_labels(self):
        t = self.timeline
        self.trim_info.setText(f"{clock_precise(t.start)}  →  {clock_precise(t.end)}     "
                               + tr("{length} selected", length=clock_precise(t.end - t.start)))

    def preview_selection(self):
        if self.player:
            self.player.setPosition(self.timeline.start)
            self.player.play()

    def save_trim(self, replace: bool):
        t = self.timeline
        if t.start <= 0 and t.end >= t.duration and not replace:
            self.exit_trim()
            return
        src = self.current
        self._release()
        self._set_trimming(False)
        self._show_msg("Saving trimmed clip…")
        self.ctl.trim(src, t.start, t.end, replace)

    def _on_trimmed(self, path: str):
        if not self.isVisible():
            return
        self.items = self.ctl.recent_items()
        new = Path(path)
        self.index = self.items.index(new) if new in self.items else 0
        self.show_item()

    # ---- navigation and actions
    def step(self, delta: int):
        i = self.index + delta
        if 0 <= i < len(self.items):
            self.index = i
            self.show_item()

    def _open_external(self):
        self._release()
        self.ctl.open_external(self.current)
        self.hide()

    def delete_current(self):
        if not self.del_btn.danger:       # the highlight goes to Delete, ready to confirm
            self.del_btn.danger = True
            self.del_btn.setText(tr("Press again to delete"))
            self.del_btn.setFocus()
            self._disarm.start(3000)
            return
        self._release()
        path = self.current
        QtCore.QTimer.singleShot(200, lambda: self._finish_delete(path))  # file handle released

    def _finish_delete(self, path: Path):
        if not self.ctl.delete(path):
            self._show_msg("Couldn't delete this file. Is it open somewhere else?")
            return
        self.items.remove(path)
        if not self.items:
            self.close_viewer()
            return
        self.index = min(self.index, len(self.items) - 1)
        self.show_item()

    def _reset_delete(self):
        self.del_btn.danger = False
        self.del_btn.setText("")

    @staticmethod
    def _repolish(w):
        w.style().unpolish(w)
        w.style().polish(w)

    def keyPressEvent(self, e):
        k = e.key()
        pos = self.player.position() if self.player else 0
        if self.editing:
            if k == Qt.Key_Escape:
                self.cancel_edit()
            return
        if self.sounding:
            rows = [self.voice_row, self.game_row]
            row = next((r for r in rows if r.slider.hasFocus()), self.voice_row)
            if k in (Qt.Key_Up, Qt.Key_Down):
                rows[1 if row is self.voice_row else 0].setFocus()
            elif k in (Qt.Key_Left, Qt.Key_Right):   # only when a bar doesn't have the keys itself
                row.step(1 if k == Qt.Key_Right else -1)   # the bars run left to right everywhere
            elif k == Qt.Key_M:
                row.toggle_mute()
            elif k == Qt.Key_P:
                self.preview_sound()
            elif k in (Qt.Key_Return, Qt.Key_Enter):
                self.save_sound()
            elif k in (Qt.Key_Escape, Qt.Key_Backspace):
                self.exit_sound()
            elif k == Qt.Key_Space:
                self.toggle_play()
            return
        if self.sharing:
            nav = self._share_nav()
            focused = self.focusWidget()
            i = nav.index(focused) if focused in nav else len(nav) - 1
            if k in (Qt.Key_Left, Qt.Key_Right) and nav:
                nav[max(0, min(len(nav) - 1, i + forward(k)))].setFocus()
            elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and nav:
                item = nav[i]
                item.next() if isinstance(item, OptionCard) else item.click()
            elif k in (Qt.Key_Escape, Qt.Key_Backspace):
                self.go_back()
            return
        items = [] if self.trimming else self._nav_items()
        focused = self.focusWidget()
        if items and (focused in items or INPUT.mode != "keyboard"):   # the highlight, moved like a mouse
            if focused not in items:
                self._pick_focus(fresh=True)
                focused = self.focusWidget()
            if focused is self.slider and k in (Qt.Key_Left, Qt.Key_Right):
                self.seek(5000 if k == Qt.Key_Right else -5000)   # on the seek bar ← → move through the video
                return
            if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                nxt = toward(focused, items, k)
                if nxt is not None:
                    nxt.setFocus()
                return
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.toggle_play() if focused is self.slider else focused.click()
                return
        if self.trimming:
            handlers = {
                Qt.Key_Escape: self.exit_trim,
                Qt.Key_I: lambda: self.timeline.set_start(pos),
                Qt.Key_O: lambda: self.timeline.set_end(pos),
                Qt.Key_P: self.preview_selection,
                Qt.Key_Return: lambda: self.save_trim(replace=False),
                Qt.Key_Enter: lambda: self.save_trim(replace=False),
            }
        else:
            handlers = {
                Qt.Key_Escape: self.go_back,
                Qt.Key_A: lambda: self.step(1 if is_rtl() else -1),   # A / D (L1 / R1) go the way the arrows point
                Qt.Key_D: lambda: self.step(-1 if is_rtl() else 1),
                Qt.Key_T: self.enter_trim,
                Qt.Key_V: self.enter_sound,
                Qt.Key_Delete: self.delete_current,
                Qt.Key_E: self.enter_share,
                Qt.Key_F: self.toggle_favorite,
                Qt.Key_N: self.start_edit,
                Qt.Key_M: self.toggle_more,
                Qt.Key_F11: self.toggle_full,
                Qt.Key_C: lambda: self.ctl.copy(self.current),
            }
        handlers.update({
            Qt.Key_Space: self.toggle_play,
            Qt.Key_Left: lambda: self.seek(-5000),
            Qt.Key_Right: lambda: self.seek(5000),
        })
        if k in handlers:
            handlers[k]()
        else:
            super().keyPressEvent(e)


class TileDelegate(QtWidgets.QStyledItemDelegate):
    """Draws gallery tiles as they scroll into view, so 1000 captures cost no more than 30."""

    def __init__(self, gallery: "Gallery"):
        super().__init__(gallery)
        self.g = gallery
        self.cache: dict[str, QtGui.QPixmap] = {}   # insertion order = least recently used first

    def limit(self) -> int:
        """Two screens of tiles (each 150-600 KB): scrolling back is instant, a long gallery costs no more."""
        view, cell = self.g.grid.viewport().size(), self.g.grid.gridSize()
        return 2 * max(1, view.width() // cell.width()) * (view.height() // cell.height() + 2)

    def pixmap(self, path: Path) -> QtGui.QPixmap:
        key = str(path)
        pm = self.cache.pop(key, None)
        if pm is None:
            pm = rounded_pixmap(self.g.ctl.thumb(path), self.g.TW, self.g.TH, 14,
                                max(1.0, self.g.devicePixelRatioF()))
        self.cache[key] = pm
        limit = self.limit()
        while len(self.cache) > limit:
            self.cache.pop(next(iter(self.cache)))
        return pm

    def forget(self, path: str | None = None):
        if path is None:
            self.cache.clear()
        else:
            self.cache.pop(path, None)

    def sizeHint(self, option, index):
        return QtCore.QSize(self.g.TW + 2 * self.g.PAD, self.g.TH + self.g.PAD + 62)

    def paint(self, p: QtGui.QPainter, option, index):
        path = Path(index.data(Qt.UserRole))
        r = QtCore.QRectF(option.rect)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        # the current tile grows into focus, like the PS5, while the one before settles back
        t = self.g.grow if selected else (1 - self.g.grow) if index.row() == self.g.last_row else 0.0
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rest = QtCore.QRectF(r.x() + (r.width() - self.g.TW) / 2, r.y() + self.g.PAD, self.g.TW, self.g.TH)
        tile = grown(rest, 0.05 * t)
        radius = 14 * tile.width() / rest.width()
        ctl = self.g.ctl
        draw_capture_tile(p, tile, self.pixmap(path), path, ctl.length_of(path), ctl.is_favorite(path),
                          dim=int(70 * (1 - t)), radius=radius, marked=path in self.g.marked,
                          selecting=self.g.selecting)
        paint_focus(p, tile, radius, t)
        title, _, sub = index.data(Qt.DisplayRole).partition("\n")
        text = QtCore.QRectF(rest.left(), rest.bottom() + 14, rest.width(), 20)
        p.setPen(QtGui.QColor(INK) if selected else QtGui.QColor(236, 240, 250, 225))
        p.setFont(font(15, QtGui.QFont.DemiBold if selected else QtGui.QFont.Normal))
        p.drawText(text, lead() | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.ElideRight, int(rest.width())))
        p.setPen(QtGui.QColor(236, 240, 250, 165))
        p.setFont(font(13))
        p.drawText(text.translated(0, 21), lead() | Qt.AlignVCenter, sub)
        p.restore()


class CategoryDelegate(QtWidgets.QStyledItemDelegate):
    """Gallery sidebar rows: name on the left, count and size on the right; the current one is white."""

    def sizeHint(self, option, index):
        return QtCore.QSize(option.rect.width(), 44)

    def paint(self, p: QtGui.QPainter, option, index):
        name, count, size = index.data(Qt.UserRole)
        r = QtCore.QRectF(option.rect).adjusted(12, 0, -12, 0)
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(INK))
            p.drawRoundedRect(QtCore.QRectF(option.rect).adjusted(0, 3, 0, -3), 19, 19)
        right = f"{count}"
        p.setFont(font(13))
        p.setPen(QtGui.QColor(13, 17, 32, 150) if selected else QtGui.QColor(236, 240, 250, 150))
        rw = p.fontMetrics().horizontalAdvance(right)
        rtl = is_rtl()    # the count sits at the far end of the line from the name
        p.drawText(r, ((Qt.AlignLeft | Qt.AlignAbsolute) if rtl else Qt.AlignRight) | Qt.AlignVCenter, right)
        p.setFont(font(15, QtGui.QFont.DemiBold if selected else QtGui.QFont.Normal))
        p.setPen(QtGui.QColor(DARK) if selected else QtGui.QColor(236, 240, 250, 225))
        p.drawText(r.adjusted(rw + 12, 0, 0, 0) if rtl else r.adjusted(0, 0, -rw - 12, 0), lead() | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.ElideRight, int(r.width() - rw - 12)))
        p.restore()


GALLERY_STYLE = VIEWER_STYLE + f"""
QListWidget {{ background: transparent; border: none; outline: none; color: {INK}; }}
QListWidget#games {{ font-size: 14px; }}
QListWidget#grid {{ font-size: 12px; }}
QListWidget#grid::item {{ border-radius: 12px; padding: 6px; color: {MUTED}; }}
QListWidget#grid::item:selected {{ background: rgba(255,255,255,24); color: {INK}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,45); border-radius: 4px; min-height: 40px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


class Gallery(Grow, QtWidgets.QWidget):
    """All captures, like the PS5 Media Gallery: games on the left, their captures on the right."""

    thumb_ready = QtCore.Signal(str)
    TW, TH = 256, 144        # set from the grid's width by _fit_tiles()
    PAD = 15                 # room around a tile to grow into when it's the current one
    FAVORITES = "★  Favorites"
    last_row = -1            # the tile that had the focus before; it settles back as the new one grows
    _row = -1

    def _on_grow(self, value):
        self.grow = float(value)
        self.grid.viewport().update()

    def _regrow(self, row: int):
        """The current tile changed: it grows into focus."""
        self.last_row, self._row = self._row, row
        self.grow = 0.0
        self.grow_to(True)

    def _fit_tiles(self):
        """As many columns as fit tiles of about 350 px, sharing the width evenly, so the grid
        fills the page edge to edge. The scroll bar's room is kept either way."""
        room = self.grid.width() - 24     # the scroll bar, and the few px the list keeps at its edges
        cell = room // max(2, round(room / 380))
        if cell - 2 * self.PAD != self.TW:
            self.TW = cell - 2 * self.PAD
            self.TH = round(self.TW * 9 / 16)
            self.tiles.forget()
            self.grid.setGridSize(QtCore.QSize(cell, self.TH + self.PAD + 62))

    def __init__(self, ctl: Controller, viewer: "Viewer"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.ctl, self.viewer = ctl, viewer
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(GALLERY_STYLE)
        self.setFont(font(13))
        dress(self)
        self.cats: list[tuple[str, list[Path]]] = []
        self.items: list[Path] = []
        self.marked: set[Path] = set()
        self.by_size = False
        self.select_mode = False      # Select pressed: a click (or ✕ / Enter) picks instead of opening

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(64, 40, 64, 32)
        lay.setSpacing(24)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(back_button(self.go_back), 0, Qt.AlignTop)
        head.addSpacing(18)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(QtWidgets.QLabel(tr("Captures"), objectName="vTitle"))
        self.info = QtWidgets.QLabel(objectName="vSub")
        titles.addWidget(self.info)
        head.addLayout(titles)
        head.addStretch()
        self.sort_btn = QtWidgets.QPushButton(tr("Sort: Newest"))
        self.sort_btn.setFocusPolicy(Qt.NoFocus)
        self.sort_btn.setCursor(Qt.PointingHandCursor)
        self.sort_btn.clicked.connect(self.toggle_sort)
        head.addWidget(self.sort_btn)
        head.addSpacing(4)
        self.select_btn = QtWidgets.QPushButton("  " + tr("Select"))
        self.select_btn.setIcon(qicon("select"))
        self.select_btn.setIconSize(QtCore.QSize(18, 18))
        self.select_btn.setFocusPolicy(Qt.NoFocus)
        self.select_btn.setCursor(Qt.PointingHandCursor)
        self.select_btn.clicked.connect(self.start_selecting)
        head.addWidget(self.select_btn)
        self.all_btn = QtWidgets.QPushButton(tr("Select all"))
        self.del_btn = QtWidgets.QPushButton(tr("Delete selected"))
        self.del_btn.setIcon(qicon("trash"))
        self.clear_btn = QtWidgets.QPushButton(tr("Cancel"))
        for b, fn in ((self.all_btn, self.mark_all), (self.del_btn, self.delete_marked),
                      (self.clear_btn, self.stop_selecting)):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            b.hide()
            head.addWidget(b)
        self._disarm = QtCore.QTimer(self, singleShot=True, timeout=self._reset_delete)
        for text, icon, fn in (("", "folder", self.ctl.open_folder), ("", "close", self.close_gallery)):
            b = QtWidgets.QPushButton(text, objectName="" if text else "round")
            b.setToolTip(tr("Open the clips folder") if icon == "folder" else tr("Close (Esc)"))
            b.setIcon(qicon(icon))
            b.setIconSize(QtCore.QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(fn)
            head.addWidget(b)
        lay.addLayout(head)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(40)
        self.games = QtWidgets.QListWidget(objectName="games")
        self.games.setItemDelegate(CategoryDelegate(self.games))
        self.games.setFixedWidth(240)
        self.games.setFocusPolicy(Qt.NoFocus)        # switch games with [ ] / L1 R1 or the mouse
        self.games.currentRowChanged.connect(self._fill)
        body.addWidget(self.games)
        self.grid = QtWidgets.QListWidget(objectName="grid")
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.tiles = TileDelegate(self)
        self.grid.setItemDelegate(self.tiles)
        self.grid.setGridSize(QtCore.QSize(self.TW + 2 * self.PAD, self.TH + self.PAD + 62))
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setSpacing(4)
        self.grid.itemDoubleClicked.connect(lambda _: None if self.selecting else self.open_selected())
        self.grid.itemClicked.connect(self._clicked)
        self.grid.currentRowChanged.connect(lambda row: (self._update_info(), self._regrow(row)))
        self.grid.installEventFilter(self)
        body.addWidget(self.grid, 1)
        lay.addLayout(body, 1)
        self.hints = HintBar()
        lay.addWidget(self.hints)

        self.thumb_ready.connect(self._on_thumb)
        viewer.closed.connect(self._after_viewer)
        ctl.captured.connect(lambda *_: self.refresh() if self.isVisible() else None)
        ctl.library_changed.connect(lambda: self.refresh() if self.isVisible() else None)
        INPUT.changed.connect(lambda _: self.update_hints())
        self.update_hints()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)      # the sheet: the game stays faintly visible behind it
        p.fillRect(self.rect(), sheet_color(self))

    # ---- open / close
    def open(self, game: str | None = None, back_to=None, fresh: bool = False):
        """fresh: opened from outside (the tray), not from another page."""
        self.back_to = back_to      # what Back returns to (None: just close)
        dress(self)
        self.setGeometry(ui_screen(fresh).geometry())
        self._load(select=game)
        self.show()
        bring_to_front(self)
        self.grid.setFocus()

    @property
    def selecting(self) -> bool:
        return self.select_mode or bool(self.marked)

    def start_selecting(self):
        self.select_mode = True
        self._update_info()
        self.update_hints()
        self.grid.viewport().update()
        self.grid.setFocus()

    def stop_selecting(self):
        self.select_mode = False
        self.clear_marks()
        self.update_hints()

    def go_back(self):
        """A selection is let go first; then back to wherever the gallery was opened from."""
        if self.selecting:
            self.stop_selecting()
            return
        back, self.back_to = getattr(self, "back_to", None), None
        self.close_gallery()
        if back:
            back()

    def close_gallery(self):
        self.select_mode = False
        self.clear_marks()
        self.hide()
        self.grid.clear()        # the tiles' pixmaps go with it; reopening rebuilds them in ~0.1 s
        self.tiles.forget()
        self.items = []

    def refresh(self):
        name = self.cats[self.games.currentRow()][0] if self.cats and self.games.currentRow() >= 0 else None
        row = self.grid.currentRow()
        self._load(select=name, row=row)

    def _after_viewer(self):
        if self.isVisible():
            self.refresh()
            bring_to_front(self)
            self.grid.setFocus()

    # ---- content
    def _load(self, select: str | None = None, row: int = 0):
        everything = self.ctl.all_captures()
        self.marked &= set(everything)
        favs = self.ctl.favorites()
        by_game: dict[str, list[Path]] = {}
        for p in everything:   # already newest first, so games are ordered by latest capture
            by_game.setdefault(p.parent.name, []).append(p)
        games = list(by_game.items())
        if self.by_size:   # biggest games first, and inside each list the biggest captures first
            games.sort(key=lambda kv: sum(file_size(p) for p in kv[1]), reverse=True)
        self.cats = [("All", everything),
                     (self.FAVORITES, [p for p in everything if self.ctl._fav_key(p) in favs]),
                     *games]
        if self.by_size:
            self.cats = [(n, sorted(ps, key=file_size, reverse=True)) for n, ps in self.cats]
        self.games.blockSignals(True)
        self.games.clear()
        for name, items in self.cats:
            size = human_size(sum(file_size(p) for p in items))
            item = QtWidgets.QListWidgetItem(f"{name}   {len(items)}  ·  {size}")
            item.setData(Qt.UserRole, (self._cat_name(name), len(items), size))
            self.games.addItem(item)
        names = [c[0] for c in self.cats]
        self.games.setCurrentRow(names.index(select) if select in names else 0)
        self.games.blockSignals(False)
        self._fill(self.games.currentRow(), row)

    def _fill(self, cat_row: int, select_row: int = 0):
        if cat_row < 0 or cat_row >= len(self.cats):
            return
        self.items = list(self.cats[cat_row][1])
        self.grid.clear()
        missing = []
        for p in self.items:
            title = self.ctl.title_of(p) or capture_kind(p)
            title = title if len(title) <= 30 else title[:29] + "…"
            item = QtWidgets.QListWidgetItem(f"{title}\n{time_ago(p.stat().st_mtime)}  ·  {human_size(file_size(p))}")
            item.setData(Qt.UserRole, str(p))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.grid.addItem(item)
            if self.ctl.thumb(p) is None or (p.suffix.lower() != ".png" and self.ctl.length_of(p) is None):
                missing.append(p)
        if self.items:
            self.grid.setCurrentRow(max(0, min(select_row, len(self.items) - 1)))
        self._update_info()
        if missing:
            def run():   # thumbnails and lengths for captures not seen yet
                for p in missing:
                    make_thumb(p, self.ctl.thumbs_dir)
                    if p.suffix.lower() != ".png" and p not in self.ctl.lengths:
                        self.ctl.lengths[p] = media_duration(p)
                    safe_emit(self.thumb_ready, str(p))
                self.ctl.save_lengths()
            threading.Thread(target=run, daemon=True).start()

    def _on_thumb(self, path: str):
        self.tiles.forget(path)
        self.grid.viewport().update()

    def _update_info(self):
        name = self.cats[self.games.currentRow()][0] if self.cats else ""
        count = len(self.items)
        size = human_size(sum(file_size(p) for p in self.items))
        storage = self.ctl.last_storage
        used = "  ·  " + tr("{used} GB used in total", used=f"{storage['used_gb']:.0f}") if storage else ""
        captures = tr("1 capture") if count == 1 else tr("{n} captures", n=count)
        text = f"{self._cat_name(name)}  ·  {captures}  ·  {size}{used}"
        if self.marked:
            text = (tr("{n} selected", n=len(self.marked)) + "  ·  "
                    f"{human_size(sum(file_size(p) for p in self.marked))}  ·  {text}")
        self.info.setText(text)
        picking = self.selecting
        self.select_btn.setVisible(not picking)
        self.sort_btn.setVisible(not picking)
        for b in (self.all_btn, self.del_btn, self.clear_btn):
            b.setVisible(picking)
        self.del_btn.setEnabled(bool(self.marked))
        self.all_btn.setText(tr("Select none") if self.items and self.marked == set(self.items) else tr("Select all"))
        self.update_hints()
        if not self.del_btn.property("danger"):
            self.del_btn.setText(tr("Delete {n}", n=len(self.marked)))

    @classmethod
    def _cat_name(cls, name: str) -> str:
        return tr("Favorites") if name == cls.FAVORITES else tr("All") if name == "All" else name

    # ---- sort, select, delete many
    def toggle_sort(self):
        self.by_size = not self.by_size
        self.sort_btn.setText(tr("Sort: Largest") if self.by_size else tr("Sort: Newest"))
        self.refresh()

    def _clicked(self, item):
        if self.selecting or QtWidgets.QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_mark()       # while selecting a click picks; Ctrl+click always does, like Explorer

    def toggle_mark(self):
        row = self.grid.currentRow()
        if 0 <= row < len(self.items):
            p = self.items[row]
            self.marked.symmetric_difference_update({p})
            self.grid.viewport().update()
            self._reset_delete()
            self._update_info()

    def mark_all(self):
        self.marked = set(self.items) if self.marked != set(self.items) else set()
        self.grid.viewport().update()
        self._reset_delete()
        self._update_info()

    def clear_marks(self):
        if self.marked:
            self.marked.clear()
            self.grid.viewport().update()
        self._reset_delete()
        self._update_info()

    def delete_marked(self):
        if not self.marked:
            return
        if not self.del_btn.property("danger"):   # first press arms, second press deletes
            favs = sum(self.ctl.is_favorite(p) for p in self.marked)
            note = (" " + (tr("(incl. 1 favorite)") if favs == 1 else tr("(incl. {n} favorites)", n=favs))
                    if favs else "")
            self.del_btn.setProperty("danger", True)
            self.del_btn.setText(tr("Press again to delete {n}", n=len(self.marked)) + note)
            Viewer._repolish(self.del_btn)
            self._disarm.start(4000)
            return
        count, freed = self.ctl.delete_many(sorted(self.marked))
        self.marked.clear()
        self._reset_delete()
        self.ctl.toast.emit(tr("Deleted 1 capture · {size} freed, it's in the Recycle Bin", size=human_size(freed))
                            if count == 1 else
                            tr("Deleted {n} captures · {size} freed, they're in the Recycle Bin",
                               n=count, size=human_size(freed)), "ok")
        self.refresh()

    def _reset_delete(self):
        self.del_btn.setProperty("danger", False)
        Viewer._repolish(self.del_btn)
        self.del_btn.setText(tr("Delete {n}", n=len(self.marked)))

    # ---- actions
    def open_selected(self):
        row = self.grid.currentRow()
        if 0 <= row < len(self.items):
            self.viewer.open(self.items, row)

    def step_game(self, delta: int):
        row = max(0, min(self.games.count() - 1, self.games.currentRow() + delta))
        self.games.setCurrentRow(row)

    def toggle_favorite(self):
        row = self.grid.currentRow()
        if 0 <= row < len(self.items):
            self.ctl.toggle_favorite(self.items[row])
            self.grid.viewport().update()
            if self.cats[self.games.currentRow()][0] == self.FAVORITES:
                self.refresh()

    def update_hints(self):
        pad = INPUT.mode != "keyboard"
        if self.selecting:
            self.hints.set_items(
                [("DPAD_LR", "Move"), ("A", "Select"), ("OPT", "Delete selected"), ("B", "Done")] if pad
                else [("k:← →", "Move"), ("k:Enter", "Select"), ("k:Ctrl A", "Select all"),
                      ("k:Del", "Delete selected"), ("k:Esc", "Done")], INPUT.mode)
            return
        self.hints.set_items(
            [("DPAD_LR", "Move"), ("A", "Open"), ("X", "Select"), ("OPT", "Delete selected"),
             ("L1R1", "Game"), ("Y", "Favorite"), ("B", "Back")] if pad
            else [("k:← →", "Move"), ("k:Enter", "Open"), ("k:Space", "Select"), ("k:Del", "Delete selected"),
                  ("k:[ ]", "Game"), ("k:S", "Sort"), ("k:F", "Favorite"), ("k:Esc", "Back")], INPUT.mode)

    def eventFilter(self, obj, event):
        if obj is self.grid and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
                self.mark_all()
                return True
            return self._key(event.key())
        if obj is self.grid and event.type() == QtCore.QEvent.Resize:
            self._fit_tiles()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e):
        if not self._key(e.key()):
            super().keyPressEvent(e)

    def _key(self, k: int) -> bool:
        open_or_pick = self.toggle_mark if self.selecting else self.open_selected
        actions = {Qt.Key_Escape: self.go_back,
                   Qt.Key_Return: open_or_pick,
                   Qt.Key_Enter: open_or_pick, Qt.Key_BracketLeft: lambda: self.step_game(-1),
                   Qt.Key_BracketRight: lambda: self.step_game(1), Qt.Key_F: self.toggle_favorite,
                   Qt.Key_Space: self.toggle_mark, Qt.Key_Delete: self.delete_marked,
                   Qt.Key_S: self.toggle_sort}
        if k in actions:
            actions[k]()
            return True
        return False


# ---------------------------------------------------------------- settings

# Starting with Windows: a Task Scheduler task that runs the moment you sign in. The Startup folder
# and the registry Run list both wait half a minute or more, one app at a time, and Windows sometimes
# skips entries in them. The Run entry stays as a backup; a second copy quietly does nothing.
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Capture Menu"


def logon_task_name() -> str:
    """One task per Windows user (task names are shared by everyone on the PC)."""
    return f"Capture Menu ({os.environ.get('USERNAME', 'user')})"


def set_logon_task(on: bool):
    """Adds or removes the sign-in task. Returns quietly if Task Scheduler refuses."""
    name = logon_task_name()
    if not on:
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True,
                       creationflags=0x08000000)
        return
    from xml.sax.saxutils import escape
    user = escape(f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\"))
    exe, args = ((sys.executable, "") if FROZEN else
                 (str(Path(sys.executable).with_name("pythonw.exe")), f'"{APP_DIR / "capture_menu.py"}"'))
    # no time limit (the default stops a task after 3 days), runs on battery, normal priority (not 7)
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Starts Capture Menu when you sign in</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>5</Priority></Settings>
  <Actions Context="Author"><Exec><Command>{escape(exe)}</Command><Arguments>{escape(args)}</Arguments>
    <WorkingDirectory>{escape(str(APP_DIR))}</WorkingDirectory></Exec></Actions>
</Task>"""
    file = Path(tempfile.gettempdir()) / "capture-menu-task.xml"
    try:
        file.write_text(xml, encoding="utf-16")
        done = subprocess.run(["schtasks", "/Create", "/TN", name, "/XML", str(file), "/F"],
                              capture_output=True, creationflags=0x08000000)
        if done.returncode:
            log.warning("couldn't add the sign-in task: %s", done.stderr.decode(errors="replace").strip())
    finally:
        file.unlink(missing_ok=True)


def startup_shortcut() -> Path:
    """Where versions up to 0.0.8 started from; only removed now."""
    return (Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / "Capture Menu.lnk")


def start_command() -> str:
    if FROZEN:
        return f'"{sys.executable}"'
    return f'"{Path(sys.executable).with_name("pythonw.exe")}" "{APP_DIR / "capture_menu.py"}"'


def starts_with_windows() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except OSError:
        return startup_shortcut().exists()


def set_start_with_windows(on: bool):
    """Adds or removes the sign-in task and the Run entry (and the old Startup shortcut either way)."""
    if not IS_WINDOWS:
        return
    import winreg
    startup_shortcut().unlink(missing_ok=True)
    set_logon_task(on)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, start_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        log.exception("couldn't change start with Windows")


def update_start_with_windows():
    """At start: moves older setups (a Startup shortcut, a Run entry alone) to the sign-in task,
    and keeps the path current."""
    # only the installed CaptureMenu.exe: a copy run from source (a test, a developer) must not point
    # Windows at itself. The Python version gets this from Setup.cmd, which updates run again.
    if IS_WINDOWS and FROZEN and starts_with_windows():
        set_start_with_windows(True)


def restart_app():
    """Starts a fresh copy (it picks up config.json) and quits this one."""
    args = sys.argv[1:] if FROZEN else [str(Path(__file__).resolve()), *sys.argv[1:]]
    args = [a for a in args if a != "--restarted"] + ["--restarted"]
    QtCore.QProcess.startDetached(sys.executable, args, str(APP_DIR))
    QtWidgets.QApplication.quit()


# ---------------------------------------------------------------- updates (only when asked)

APP_VERSION = "0.0.24"     # the release workflow stamps this from the version being released
REPO = "Amjz03/capture-menu"


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def latest_release(timeout: float = 10) -> dict:
    """The newest release on GitHub: its version, page, and the Setup.exe to download."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": f"CaptureMenu/{APP_VERSION}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    asset = next((a for a in data.get("assets", []) if a.get("name") == "CaptureMenu-Setup.exe"), None)
    return {"version": str(data.get("tag_name", "")).lstrip("v"), "page": data.get("html_url", ""),
            "url": asset["browser_download_url"] if asset else None, "size": asset["size"] if asset else 0}


def download_update(url: str, size: int, out: Path, on_progress=None):
    """Downloads Setup.exe to `out`, reporting 0-99 %; a short download is thrown away."""
    import urllib.request
    tmp = out.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": f"CaptureMenu/{APP_VERSION}"})
    done, shown = 0, -1
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            pct = min(99, done * 100 // size) if size else 0
            if on_progress and pct != shown:
                shown = pct
                on_progress(pct)
    if size and tmp.stat().st_size != size:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("the download was incomplete")
    os.replace(tmp, out)


def run_update_installer(exe: Path):
    """The installer stops this copy, installs over it (settings kept) and starts the new one."""
    launch_outside([str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], flags=0x00000008)
    QtWidgets.QApplication.quit()


def hotkey_from_event(e: QtGui.QKeyEvent) -> str | None:
    """A key press -> "ctrl+shift+f9" style text for config.json, or None for a lone modifier."""
    names = {Qt.Key_Space: "space", Qt.Key_Tab: "tab", Qt.Key_Pause: "pause", Qt.Key_Insert: "insert",
             Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "pageup",
             Qt.Key_PageDown: "pagedown", Qt.Key_Print: "printscreen"}
    k = e.key()
    if Qt.Key_F1 <= k <= Qt.Key_F24:
        key = f"f{k - Qt.Key_F1 + 1}"
    elif k in names:
        key = names[k]
    elif Qt.Key_A <= k <= Qt.Key_Z or Qt.Key_0 <= k <= Qt.Key_9:
        key = chr(k).lower()
    else:
        return None
    mods = [n for flag, n in ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
                              (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "win")) if e.modifiers() & flag]
    if not mods and not key.startswith("f"):
        return None     # a bare letter would fire while typing in chat
    return "+".join(mods + [key])


class SettingRow(HoverFocus, QtWidgets.QWidget):
    """One line in Settings: name and explanation on the left, its value on the right.
    Choices change with ← → (or a click), switches flip, actions (folder, shortcut) open with Enter."""

    changed = QtCore.Signal()
    H = 72

    def __init__(self, key: str, label: str, kind: str, choices: list | None = None, describe=None,
                 custom=None, display=None):
        super().__init__()
        self.key, self.label, self.kind = key, tr(label), kind
        self.custom = custom                  # names a value typed into config.json that isn't a choice
        self.choices = [(v, tr(t)) for v, t in choices or []]     # [(value, text)]
        self.describe = (lambda v: tr(describe(v))) if describe else (lambda v: "")
        self.display = display                # how an action's value reads, e.g. a folder that's not set
        self.value = None
        self.listening = False                # waiting for a new keyboard shortcut
        self.on_activate = None
        self.setFixedHeight(self.H)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)

    def set_value(self, value, emit: bool = False):
        values = [c[0] for c in self.choices]
        if self.kind == "choice" and values and value not in values:   # e.g. 45 min typed into config.json
            numeric = isinstance(value, (int, float)) and all(isinstance(c, (int, float)) for c in values)
            if numeric and self.custom:     # keep it, in order, so saving doesn't quietly change it
                self.choices = sorted(self.choices + [(value, self.custom(value))], key=lambda c: c[0])
            else:
                value = min(values, key=lambda c: abs(c - value)) if numeric else values[0]
        self.value = value
        self.update()
        if emit:
            self.changed.emit()

    def text(self) -> str:
        if self.kind == "bool":
            return tr("On") if self.value else tr("Off")
        if self.kind == "choice":
            return dict(self.choices).get(self.value, str(self.value))
        if self.listening:
            return tr("Press the new keys…")
        if self.display:
            return self.display(self.value)
        if self.key == "hotkey":
            return " + ".join(p.upper() if len(p) <= 3 and p[0] == "f" or len(p) == 1 else p.capitalize()
                              for p in str(self.value).split("+"))
        return str(self.value)

    def step(self, delta: int):
        if self.kind == "bool":
            self.set_value(not self.value, emit=True)
        elif self.kind == "choice":
            values = [c[0] for c in self.choices]
            i = values.index(self.value) if self.value in values else 0
            self.set_value(values[max(0, min(len(values) - 1, i + delta))], emit=True)

    def activate(self):
        if self.kind == "action":
            if self.on_activate:
                self.on_activate(self)
        elif self.kind == "bool":
            self.step(1)
        else:   # Enter on a choice moves to the next one and wraps, like a console menu
            values = [c[0] for c in self.choices]
            i = values.index(self.value) if self.value in values else 0
            self.set_value(values[(i + 1) % len(values)], emit=True)

    def keyPressEvent(self, e):
        self.keep_focus()
        self.window().keyPressEvent(e)   # the page decides; the scroll area would eat the arrows

    def enterEvent(self, e):
        super().enterEvent(e)
        self.hover_in()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if not self.listening:           # waiting for a new shortcut: stay put
            self.hover_out()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        parent = self.parent()
        while parent is not None and not isinstance(parent, QtWidgets.QScrollArea):
            parent = parent.parent()
        if parent is not None and e.reason() != Qt.MouseFocusReason:   # the mouse never scrolls the page
            parent.ensureWidgetVisible(self, 0, 40)
        self.update()
        self.parent().update()     # the card hides the lines next to the focused row

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.listening = False
        self.update()
        self.parent().update()

    def mousePressEvent(self, e):
        self.keep_focus()
        if self.kind == "choice" and e.position().x() < self._value_rect().left() + 28:
            self.step(-1)
        elif self.kind == "choice":
            self.step(1)
        else:
            self.activate()

    def _value_rect(self) -> QtCore.QRectF:
        if is_rtl():    # mirrored: the value on the left, the name on the right
            return QtCore.QRectF(16, 0, 284, self.height())
        return QtCore.QRectF(self.width() - 300, 0, 284, self.height())

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        focused = self.hasFocus()
        r = QtCore.QRectF(self.rect()).adjusted(0, 2, 0, -2)
        if focused:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(INK))
            p.drawRoundedRect(r, 16, 16)
        elif self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 14))
            p.drawRoundedRect(r, 16, 16)
        ink = QtGui.QColor(DARK) if focused else QtGui.QColor(INK)
        soft = QtGui.QColor(13, 17, 32, 165) if focused else QtGui.QColor(236, 240, 250, 185)
        desc = self.describe(self.value)
        left = QtCore.QRectF(322 if is_rtl() else 18, 0, self.width() - 340, self.height())
        p.setPen(ink)
        p.setFont(font(16, QtGui.QFont.DemiBold if focused else QtGui.QFont.Normal))
        if desc:
            p.drawText(left.adjusted(0, 13, 0, 0), lead() | Qt.AlignTop, self.label)
            p.setPen(soft)
            p.setFont(font(14))
            p.drawText(left.adjusted(0, 39, 0, 0), lead() | Qt.AlignTop,
                       p.fontMetrics().elidedText(desc, Qt.ElideRight, int(left.width())))
        else:
            p.drawText(left, lead() | Qt.AlignVCenter, self.label)
        v = self._value_rect()
        if self.kind == "bool":     # a switch
            track = QtCore.QRectF(v.left() if is_rtl() else v.right() - 46, v.center().y() - 13, 46, 26)
            on = bool(self.value) != is_rtl()   # the knob sits toward the line's end when on
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(BLUE) if self.value else (QtGui.QColor(13, 17, 32, 60) if focused
                                                        else QtGui.QColor(255, 255, 255, 50)))
            p.drawRoundedRect(track, 13, 13)
            p.setBrush(QtGui.QColor("white"))
            p.drawEllipse(QtCore.QPointF(track.right() - 13 if on else track.left() + 13, track.center().y()), 10, 10)
            return
        p.setFont(font(15, QtGui.QFont.DemiBold if focused else QtGui.QFont.Normal))
        p.setPen(ink if focused or self.listening else QtGui.QColor(236, 240, 250, 220))
        if self.kind == "choice":   # a pill with ‹ › on every row, so it's clear the value can change
            values = [c[0] for c in self.choices]
            i = values.index(self.value) if self.value in values else 0
            pill = QtCore.QRectF(v.left(), v.center().y() - 19, v.width(), 38)
            p.save()
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(13, 17, 32, 22) if focused else QtGui.QColor(255, 255, 255, 16))
            p.drawRoundedRect(pill, 19, 19)
            p.restore()
            arrow = DARK if focused else INK
            for name, x, can in (("left", pill.left() + 10, i > 0),
                                 ("right", pill.right() - 28, i < len(values) - 1)):
                p.setOpacity((1.0 if focused else 0.6) if can else 0.16)
                p.drawPixmap(QtCore.QPointF(x, pill.center().y() - 9), icon_pixmap(name, 18, arrow))
            p.setOpacity(1.0)
            p.drawText(pill.adjusted(34, 0, -34, 0), Qt.AlignCenter,
                       p.fontMetrics().elidedText(self.text(), Qt.ElideRight, int(pill.width() - 68)))
        else:   # a folder, the shortcut, updates: the value, then › like a button that opens something
            edge = (Qt.AlignLeft | Qt.AlignAbsolute) if is_rtl() else Qt.AlignRight
            room = 0 if self.listening else 26     # room for the ›
            text_rect = v.adjusted(room, 0, 0, 0) if is_rtl() else v.adjusted(0, 0, -room, 0)
            text = p.fontMetrics().elidedText(self.text(), Qt.ElideMiddle, int(text_rect.width()))
            p.drawText(text_rect, edge | Qt.AlignVCenter, text)
            if not self.listening:
                p.setOpacity(1.0 if focused else 0.6)
                x = v.left() if is_rtl() else v.right() - 18
                p.drawPixmap(QtCore.QPointF(x, v.center().y() - 9),
                             icon_pixmap("left" if is_rtl() else "right", 18, DARK if focused else INK))
                p.setOpacity(1.0)


def back_button(on_click) -> QtWidgets.QPushButton:
    """"Back": one step back to where you came from (Esc and ◯ / B do the same)."""
    b = QtWidgets.QPushButton(" " + tr("Back"), objectName="back")
    b.setIcon(qicon("right" if is_rtl() else "left"))   # points to where the line starts
    b.setIconSize(QtCore.QSize(18, 18))
    b.setFocusPolicy(Qt.NoFocus)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tr("Back (Esc)"))
    b.clicked.connect(on_click)
    return b


class LevelSlider(QtWidgets.QSlider):
    """A volume bar. ← → (and the mouse) move it; every other key goes on to the window."""

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            super().keyPressEvent(e)
        else:
            e.ignore()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.parent().update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.parent().update()


class SectionTitle(QtWidgets.QLabel):
    def __init__(self, text: str):
        text = tr(text)
        super().__init__(text.capitalize() if text.isupper() else text)   # the keys are capitals
        self.setStyleSheet(f"color: {INK}; font-size: 20px; font-weight: 600; padding: 30px 10px 12px 10px;")


class SettingsCard(QtWidgets.QWidget):
    """A section's rows on their own darker panel, so they read clearly over any game,
    with thin lines between them."""

    def __init__(self):
        super().__init__()
        self.rows = QtWidgets.QVBoxLayout(self)
        self.rows.setContentsMargins(6, 6, 6, 6)
        self.rows.setSpacing(0)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1))
        p.setBrush(QtGui.QColor(24, 29, 44, 175))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 22, 22)
        rows = [self.rows.itemAt(i).widget() for i in range(self.rows.count())]
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 16), 1))
        for above, below in zip(rows, rows[1:]):
            if not (above.hasFocus() or below.hasFocus()):
                y = below.geometry().top() + 0.5
                p.drawLine(QtCore.QPointF(24, y), QtCore.QPointF(self.width() - 24, y))


class Settings(QtWidgets.QWidget):
    """Everything in config.json that a player would want to change, on one page.
    Nothing is written until Save; then the app restarts itself (and OBS if recording changed)."""

    encoder_ready = QtCore.Signal(str)
    mics_ready = QtCore.Signal(object)       # Obs.mic_devices(), or None
    update_event = QtCore.Signal(dict)       # what the update check / download is doing

    def __init__(self, ctl: Controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.ctl = ctl
        self.restart = restart_app          # tests swap this out
        self.encoder: str | None = None
        self.screen_px = (2560, 1440)
        self.setObjectName("viewer")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(GALLERY_STYLE + "QScrollArea, #rows { background: transparent; border: none; }")
        self.setFont(font(13))
        dress(self)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(64, 40, 64, 32)
        lay.setSpacing(18)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(back_button(self.go_back), 0, Qt.AlignTop)
        head.addSpacing(18)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(QtWidgets.QLabel(tr("Settings"), objectName="vTitle"))
        self.info = QtWidgets.QLabel(objectName="vSub")
        titles.addWidget(self.info)
        head.addLayout(titles)
        head.addStretch()
        self.defaults_btn = QtWidgets.QPushButton(tr("Restore defaults"))
        self.cancel_btn = QtWidgets.QPushButton(tr("Cancel"))
        self.save_btn = QtWidgets.QPushButton(tr("Save"), objectName="primary")
        for b, fn in ((self.defaults_btn, self.restore_defaults), (self.cancel_btn, self.close_settings),
                      (self.save_btn, self.save)):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            head.addWidget(b, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        holder = QtWidgets.QWidget(objectName="rows")
        outer = QtWidgets.QHBoxLayout(holder)
        outer.setContentsMargins(0, 0, 0, 0)
        column = QtWidgets.QWidget(objectName="rows")
        column.setMaximumWidth(920)
        self.rows_layout = QtWidgets.QVBoxLayout(column)
        self.rows_layout.setContentsMargins(0, 0, 12, 0)
        self.rows_layout.setSpacing(0)
        column.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        outer.addWidget(column, 1)
        outer.addStretch(0)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll, 1)

        foot = QtWidgets.QHBoxLayout()
        self.hints = HintBar()
        foot.addWidget(self.hints)
        foot.addStretch()
        self.memory = QtWidgets.QLabel(objectName="vSub")
        foot.addWidget(self.memory)
        lay.addLayout(foot)

        self.rows: list[SettingRow] = []
        self.update: dict = {"state": "idle"}
        self.mics: tuple | None | str = "checking"   # Obs.mic_devices() once OBS has answered
        self.install = run_update_installer     # tests swap this out
        self._build_rows()
        self.update_event.connect(self._on_update_event)
        self.encoder_ready.connect(self._on_encoder)
        self.mics_ready.connect(self._on_mics)
        INPUT.changed.connect(lambda _: self.update_hints())
        self.update_hints()

    # ---- the rows
    def _row(self, *args, **kw) -> SettingRow:
        row = SettingRow(*args, **kw)
        row.changed.connect(self._refresh)
        self.card.rows.addWidget(row)
        self.rows.append(row)
        return row

    def _section(self, title: str):
        """A title, then a card that the next rows go into."""
        self.rows_layout.addWidget(SectionTitle(title))
        self.card = SettingsCard()
        self.rows_layout.addWidget(self.card)

    def _build_rows(self):
        self._section("RECORDING")
        self.res_row = self._row("resolution", "Resolution", "choice", [("native", "Native")],
                                 lambda v: "Lower uses less RAM and space; Native looks sharpest")
        self._row("fps", "Frame rate", "choice", [(30, "30 FPS"), (60, "60 FPS"), (120, "120 FPS")],
                  lambda v: "60 is smooth for every game; 120 for fast shooters on a high-refresh screen",
                  custom=lambda v: tr("{n} FPS", n=v))
        self._row("quality", "Quality", "choice",
                  [("light", "Light"), ("balanced", "Balanced"), ("high", "High"), ("max", "Max")],
                  self._quality_text)
        self.codec_row = self._row("video_codec", "Video format", "choice",
                                   [("auto", "Auto"), ("av1", "AV1"), ("hevc", "HEVC"), ("h264", "H.264")],
                                   self._codec_text)
        self._row("buffer_minutes", "Replay buffer", "choice",
                  [(m, tr("{n} min", n=m)) for m in (5, 10, 15, 30, 60)], self._buffer_text,
                  custom=lambda v: tr("{n} min", n=v))
        self._row("voice_track", "Voice on its own track", "bool",
                  describe=lambda v: "So you can share a clip with or without your voice")
        self._row("hdr", "HDR", "choice", [("auto", "Auto"), ("off", "Off")],
                  lambda v: "HDR clips while Windows HDR is on. Shared copies get normal colours"
                  if v == "auto" else "Always normal colours (SDR)")
        self._row("colours", "Colours", "choice",
                  [("natural", "Natural"), ("soft", "Soft"), ("vivid", "Vivid"), ("max", "Max")],
                  lambda v: "Colours exactly as Windows shows them" if v == "natural"
                  else "More colour and contrast when an HDR screen is recorded in normal colours")
        self._row("record_indicator", "Recording indicator", "choice",
                  [("top-left", "Top left"), ("top-right", "Top right"), ("off", "Off")],
                  lambda v: "A small REC timer while you record by hand. It never shows up in captures"
                  if v != "off" else "Nothing on screen while recording")
        self._section("DEVICES")
        # the screens and microphones are filled in by open(): they change while the app runs
        self.screen_row = self._row("capture_screen", "Recording screen", "choice",
                                    [("follow", "Follow the game")], self._screen_text)
        self.mic_row = self._row("mic_device", "Microphone", "choice",
                                 [("default", "Same as Windows")], self._mic_text)
        self._section("CONTROLS")
        hk = self._row("hotkey", "Keyboard shortcut", "action",
                       describe=lambda v: "Opens the menu. Press Enter, then the new keys")
        hk.on_activate = self._listen_hotkey
        self._row("controller_button", "Controller button", "choice",
                  [("create", "Create / View"), ("ps", "PS / Xbox button"), ("touchpad", "Touchpad"),
                   ("mute", "Mute / Share"), ("l3+r3", "L3 + R3")],
                  lambda v: "The button that opens the menu, like Create on the PS5")
        self._row("controller_hold_ms", "Open the menu with", "choice", [(0, "A press"), (400, "A hold")],
                  lambda v: "Hold keeps a quick tap for the game, if it uses the same button",
                  custom=lambda v: tr("A hold ({n} ms)", n=v))
        self._row("double_press_seconds", "Double-press to save", "choice",
                  [(0, "Off"), (15, "15 sec"), (30, "30 sec"), (60, "1 min"), (120, "2 min")],
                  lambda v: "Press twice quickly to save without opening the menu" if v else
                  "Double-pressing does nothing extra", custom=lambda v: tr("{n} sec", n=v))
        self._row("rumble", "Rumble", "bool", describe=lambda v: "A short buzz on the controller when something is saved")
        self._row("sounds", "Sounds", "bool", describe=lambda v: "A short sound when something is saved")
        self._section("LIBRARY")
        # a folder Windows refused shows where captures really go (the setting itself is kept)
        in_use = lambda v: str(self.ctl.clips_dir) if self.ctl.blocked and v == str(self.ctl.blocked) else v
        folder = self._row("clips_dir", "Clips folder", "action",
                           describe=lambda v: "Windows Security protects the folder you picked, so captures "
                                              "are saved here"
                           if in_use(v) != v else "Clips and recordings, a folder per game",
                           display=in_use)
        folder.on_activate = self._pick_folder
        shots = self._row("screenshots_dir", "Screenshots folder", "action",
                          describe=lambda v: "A folder per game here too",
                          display=lambda v: v or tr("Same as the clips folder"))
        shots.on_activate = self._pick_folder
        self._row("storage_warn_gb", "Warn me when captures pass", "choice",
                  [(0, "Never"), (50, "50 GB"), (100, "100 GB"), (200, "200 GB"), (500, "500 GB"),
                   (1000, "1 TB")], lambda v: "Only a notice. Nothing is ever deleted for you",
                  custom=lambda v: tr("{n} GB", n=v))
        self._section("GENERAL")
        self._row("start_with_windows", "Start with Windows", "bool",
                  describe=lambda v: "Capture Menu and OBS start when you sign in")
        self._row("language", "Language", "choice",
                  [("auto", "Same as Windows"), *LANGUAGES.items()],
                  lambda v: "Capture Menu restarts in the new language when you save")
        # not a setting: "_" keeps it out of config.json
        self.update_row = self._row("_update", "Updates", "action", describe=lambda v: self._update_describe(),
                                    display=lambda v: self._update_value())
        self.update_row.on_activate = lambda row: self.check_or_install()
        self.rows_layout.addStretch()

    def _plan_cfg(self) -> dict:
        return dict(self.ctl.cfg, **self.values())

    def _quality_text(self, v) -> str:
        cfg = self._plan_cfg()
        w, h = output_size(*self.screen_px, cfg["resolution"])
        enc = choose_encoder(self.encoder or "nvenc_av1", cfg["video_codec"])
        kbps = pick_bitrate(enc, w, h, int(cfg["fps"]), v or "balanced")
        return tr("About {kbps} Kbps. Higher is sharper in fast motion and makes bigger files", kbps=f"{kbps:,}")

    def _codec_text(self, v) -> str:
        if self.encoder is None:
            return "Checking your graphics card…"
        best = codec_of(self.encoder).upper().replace("H264", "H.264")
        used = codec_of(choose_encoder(self.encoder, v)).upper().replace("H264", "H.264")
        if v == "auto":
            return tr("{codec}, the best your graphics card can record. Shared copies are always H.264", codec=best)
        if used != (v or "").upper().replace("H264", "H.264"):
            return tr("Your graphics card can't record this, so {codec} is used", codec=used)
        return "H.264 plays everywhere; AV1 and HEVC make smaller files" if v == "h264" else \
            "Smaller files than H.264 at the same quality. Shared copies are always H.264"

    def _screen_text(self, v) -> str:
        if v == "follow":
            return "Records the monitor or TV the game is on"
        if chosen_screen(v) is None:
            return "Not connected now, so the game's screen is recorded"
        return "Always records this screen, wherever the game is"

    def _mic_text(self, v) -> str:
        if self.mics == "checking":
            return "Asking OBS which microphones it can use…"
        if self.mics == "offline":
            return "OBS isn't running, so its microphones can't be listed"
        if self.mics is None:
            return "OBS has no microphone yet · add one in OBS under Settings → Audio"
        if v == "default":
            return "The microphone Windows uses. Your voice goes on its own track"
        if v not in dict(self.mics[1]):
            return "Not connected now"
        return "Your voice is recorded from this microphone"

    def _fill_screens(self, current: str):
        """Follow the game, then every screen connected now (and the saved one, if it isn't)."""
        choices = [("follow", tr("Follow the game"))]
        choices += [(screen_id(s), screen_label(s)) for s in QtGui.QGuiApplication.screens()]
        if current not in dict(choices):
            choices.append((current, tr("A screen that isn't connected")))
        self.screen_row.choices = choices

    def _fill_mics(self, current: str):
        choices = [("default", tr("Same as Windows"))]
        if isinstance(self.mics, tuple):
            choices += list(self.mics[1])
        if current not in dict(choices):
            choices.append((current, tr("Checking…") if self.mics == "checking" else
                            tr("Picked before") if self.mics == "offline" else
                            tr("A microphone that isn't connected")))
        self.mic_row.choices = choices

    def _on_mics(self, found):
        dirty = "mic_device" in self.changes()
        self.mics = found
        value = self.mic_row.value if dirty else self._saved()["mic_device"]
        self._fill_mics(value)
        self.mic_row.set_value(value)
        self._refresh()

    def _saved(self) -> dict:
        """The settings as they are now, in the rows' terms."""
        cfg = dict(self.ctl.cfg)
        if IS_WINDOWS:
            cfg["start_with_windows"] = starts_with_windows()
        if cfg.get("capture_screen") == "main":
            cfg["capture_screen"] = screen_id(QtGui.QGuiApplication.primaryScreen())
        if isinstance(self.mics, tuple) and not load_state().get("mic_picked"):
            cfg["mic_device"] = self.mics[0]    # never picked here: show the one OBS records now
        return cfg

    def _buffer_text(self, v) -> str:
        mb = buffer_memory_mb(dict(self._plan_cfg(), buffer_minutes=v or 30), *self.screen_px,
                              choose_encoder(self.encoder or "nvenc_av1", self._plan_cfg()["video_codec"]))
        return tr("The longest clip you can save. Uses about {gb} GB of RAM", gb=f"{mb / 1024:.1f}")

    def values(self) -> dict:
        return {r.key: r.value for r in self.rows if not r.key.startswith("_")}

    # ---- updates: checked and installed only when the player asks
    def _update_value(self) -> str:
        u, state = self.update, self.update["state"]
        if state == "checking":
            return tr("Checking…")
        if state == "available":
            return tr("Version {version} is available", version=u["version"])
        if state in ("downloading", "ready"):
            return tr("Downloading… {pct}%", pct=u.get("pct", 99))
        if state == "latest":
            return tr("Up to date")
        return tr("Version {version}", version=APP_VERSION)

    def _update_describe(self) -> str:
        state = self.update["state"]
        if state == "available":
            return (tr("Press Enter to download and install it. Your settings and captures stay") if FROZEN
                    else tr("Press Enter to open the download page"))
        if state == "latest":
            return tr("You have the newest version, {version}", version=APP_VERSION)
        if state == "error":
            return tr("Couldn't reach GitHub · check your internet, then press Enter to try again")
        if state in ("downloading", "ready"):
            return tr("Capture Menu closes and installs it when the download finishes")
        if state == "checking":
            return ""
        return tr("Press Enter to look for a new version. Nothing is installed unless you say so")

    def check_or_install(self):
        state = self.update["state"]
        if state in ("checking", "downloading", "ready"):
            return
        if state == "available":
            self._install_update()
            return
        self.update = {"state": "checking"}
        self._refresh()

        def run():
            try:
                rel = latest_release()
                newer = version_tuple(rel["version"]) > version_tuple(APP_VERSION)
                safe_emit(self.update_event, dict(rel, state="available" if newer else "latest"))
            except Exception:
                log.exception("update check failed")
                safe_emit(self.update_event, {"state": "error"})
        threading.Thread(target=run, daemon=True).start()

    def _install_update(self):
        rel = dict(self.update)
        if not FROZEN or not rel.get("url"):   # the Python version updates from the zip on GitHub
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(rel.get("page") or f"https://github.com/{REPO}/releases/latest"))
            return
        self.update = dict(rel, state="downloading", pct=0)
        self._refresh()
        out = Path(tempfile.gettempdir()) / f"CaptureMenu-Setup-{rel['version']}.exe"

        def run():
            try:
                download_update(rel["url"], rel["size"], out,
                                lambda pct: safe_emit(self.update_event, dict(rel, state="downloading", pct=pct)))
                safe_emit(self.update_event, dict(rel, state="ready", file=str(out)))
            except Exception:
                log.exception("update download failed")
                safe_emit(self.update_event, {"state": "error"})
        threading.Thread(target=run, daemon=True).start()

    def _on_update_event(self, info: dict):
        self.update = info
        self._refresh()
        if info["state"] == "ready":
            log.info("installing version %s from %s", info.get("version"), info["file"])
            self.install(Path(info["file"]))

    def _refresh(self):
        for r in self.rows:
            r.update()
        cfg = self._plan_cfg()
        enc = choose_encoder(self.encoder or "nvenc_av1", cfg["video_codec"])
        w, h = output_size(*self.screen_px, cfg["resolution"])
        mb = buffer_memory_mb(cfg, *self.screen_px, enc)
        self.memory.setText(tr("Recording {w}×{h} at {fps} FPS  ·  replay buffer about {gb} GB of RAM",
                               w=w, h=h, fps=cfg["fps"], gb=f"{mb / 1024:.1f}"))
        dirty = self.changes()
        self.info.setText((tr("1 unsaved change") if len(dirty) == 1 else
                           tr("{n} unsaved changes", n=len(dirty))) if dirty else tr("Changes apply when you save"))

    def changes(self) -> dict:
        current = self._saved()
        return {k: v for k, v in self.values().items() if current.get(k) != v}

    # ---- open / close
    def open(self, screen_px: tuple[int, int] | None = None, back_to=None, fresh: bool = False):
        """fresh: opened from outside (the tray), not from another page."""
        self.back_to = back_to      # what Back returns to (None: just close)
        if screen_px:
            self.screen_px = screen_px
        w, h = self.screen_px
        self.res_row.choices = [("native", tr("Native  {w}×{h}", w=w, h=h))] + [
            (k, k) for k, v in RESOLUTIONS.items() if v < h]
        cfg = self._saved()
        self._fill_screens(cfg["capture_screen"])
        self.mics = "checking"
        self._fill_mics(cfg["mic_device"])
        for r in self.rows:
            r.set_value(cfg.get(r.key, DEFAULTS.get(r.key)))

        def ask_obs():
            try:
                found = self.ctl.obs.mic_devices()
            except Exception:
                found = "offline"
            safe_emit(self.mics_ready, found)
        threading.Thread(target=ask_obs, daemon=True).start()
        if self.encoder is None:
            self.encoder = getattr(self.ctl, "best_encoder", None)
        if self.encoder is None:
            threading.Thread(target=lambda: safe_emit(self.encoder_ready, pick_encoder(gpu_names())),
                             daemon=True).start()
        self._refresh()
        dress(self)
        self.setGeometry(ui_screen(fresh).geometry())
        self.show()
        bring_to_front(self)
        self.rows[0].setFocus()

    def _on_encoder(self, enc: str):
        self.encoder = enc
        self._refresh()

    def go_back(self):
        """Leaves without saving, back to wherever Settings was opened from."""
        back, self.back_to = getattr(self, "back_to", None), None
        self.close_settings()
        if back:
            back()

    def close_settings(self):
        self.hide()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), sheet_color(self))

    # ---- actions
    def restore_defaults(self):
        for r in self.rows:
            if r.key in DEFAULTS:
                r.set_value(DEFAULTS[r.key])
        self._refresh()

    def save(self):
        changes = self.changes()
        if not changes:
            self.close_settings()
            return
        save_config(changes)
        if "start_with_windows" in changes:
            set_start_with_windows(bool(changes["start_with_windows"]))
        if "mic_device" in changes:      # from now on the microphone is picked here (see apply_mic)
            state = load_state()
            state["mic_picked"] = True
            save_state(state)
        self.ctl.cfg.update(changes)
        log.info("settings saved: %s", ", ".join(changes))
        self.hide()
        self.restart()

    def _listen_hotkey(self, row: SettingRow):
        row.listening = True
        row.update()

    def _pick_folder(self, row: SettingRow):
        clips = self.values().get("clips_dir")
        path = QtWidgets.QFileDialog.getExistingDirectory(self, row.label, str(row.value or clips or ""))
        if path:
            path = str(Path(path))
            # screenshots in the clips folder are the default, stored as "not set"
            row.set_value("" if row.key == "screenshots_dir" and path == clips else path, emit=True)
        bring_to_front(self)
        row.setFocus()

    def update_hints(self):
        pad = INPUT.mode != "keyboard"
        self.hints.set_items(
            [("DPAD_UD", "Move"), ("DPAD_LR", "Change"), ("A", "Select"), ("Y", "Save"),
             ("X", "Defaults"), ("B", "Back")] if pad
            else [("k:↑ ↓", "Move"), ("k:← →", "Change"), ("k:Enter", "Select"), ("k:S", "Save"),
                  ("k:Esc", "Back")], INPUT.mode)

    def keyPressEvent(self, e):
        row = self.focusWidget() if isinstance(self.focusWidget(), SettingRow) else None
        k = e.key()
        if row is not None and row.listening:
            if k == Qt.Key_Escape:
                row.listening = False
                row.update()
                return
            spec = hotkey_from_event(e)
            if spec:
                row.listening = False
                row.set_value(spec, emit=True)
            return
        if k in (Qt.Key_Up, Qt.Key_Down):
            i = self.rows.index(row) if row in self.rows else -1
            j = max(0, min(len(self.rows) - 1, i + (1 if k == Qt.Key_Down else -1)))
            self.rows[j].setFocus()
        elif k in (Qt.Key_Left, Qt.Key_Right) and row is not None:
            row.step(1 if k == Qt.Key_Right else -1)
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and row is not None:
            row.activate()
        elif k == Qt.Key_S:
            self.save()
        elif k == Qt.Key_R:
            self.restore_defaults()
        elif k == Qt.Key_Escape:
            self.go_back()
        else:
            super().keyPressEvent(e)


def tray_icon() -> QtGui.QIcon:
    pm = QtGui.QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor("#1c1c21"))
    p.drawRoundedRect(4, 4, 56, 56, 16, 16)
    p.setPen(QtGui.QPen(QtGui.QColor(INK), 4))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(32, 32), 15, 15)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor(RED))
    p.drawEllipse(QtCore.QPointF(32, 32), 7, 7)
    p.end()
    return QtGui.QIcon(pm)


def promote_tray_icon():
    """Windows 11 hides new tray icons behind the ^ arrow. Show ours next to the clock, once:
    if the player hides it again later, that choice is kept."""
    if not IS_WINDOWS or load_state().get("tray_promoted"):
        return
    import winreg
    exe = Path(sys.executable).name.lower()
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings")
    except OSError:
        return   # Windows 10: icons are shown with Settings → Taskbar instead
    found = False
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            name = winreg.EnumKey(root, i)
            try:
                with winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                    path = str(winreg.QueryValueEx(key, "ExecutablePath")[0]).lower()
                    if path.endswith("\\" + exe) or path.endswith("/" + exe):
                        winreg.SetValueEx(key, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        found = True
            except OSError:
                continue
    if found:
        state = load_state()
        state["tray_promoted"] = True
        save_state(state)


def install_crash_log():
    import faulthandler
    import traceback

    def log_error(kind, value, tb):
        log.critical("unhandled error:\n%s", "".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = log_error
    threading.excepthook = lambda a: log_error(a.exc_type, a.exc_value, a.exc_traceback)
    try:
        faulthandler.enable(open(APP_DIR / "crash.log", "a", encoding="utf-8"))   # hard crashes too
    except OSError:
        pass


def watch_for_freezes(app: QtWidgets.QApplication, seconds: float = 6.0) -> QtCore.QTimer:
    """If the interface stops responding, writes where it is stuck to crash.log (once per freeze),
    so a freeze that can't be reproduced on demand can still be found."""
    import faulthandler
    beat = [time.monotonic()]
    timer = QtCore.QTimer(app, interval=500, timeout=lambda: beat.__setitem__(0, time.monotonic()))
    timer.start()

    def run():
        written = False
        while True:
            time.sleep(1)
            stale = time.monotonic() - beat[0]
            if stale > seconds and not written:
                written = True
                log.error("the interface hasn't responded for %.0f s; where it's stuck is in crash.log", stale)
                try:
                    with open(APP_DIR / "crash.log", "a", encoding="utf-8") as f:
                        f.write(f"\n--- not responding for {stale:.0f} s, {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                        faulthandler.dump_traceback(f, all_threads=True)
                except OSError:
                    pass
            elif stale < 2:
                if written:
                    log.info("the interface responds again")
                written = False
    threading.Thread(target=run, daemon=True, name="freeze-watch").start()
    return timer


def main():
    install_crash_log()
    log.info("starting: %s %s", sys.executable, " ".join(sys.argv))
    cfg = load_config()
    set_language(cfg.get("language", "auto"))
    app = QtWidgets.QApplication(sys.argv)
    if is_rtl():
        app.setLayoutDirection(Qt.RightToLeft)   # Arabic: the whole interface mirrors, like the PS5 does
    app.setQuitOnLastWindowClosed(False)
    app._freeze_watch = watch_for_freezes(app)
    app.setWindowIcon(tray_icon())
    restarted = "--restarted" in sys.argv

    # one copy at a time: starting it again (or Windows starting it twice) quietly does nothing
    lock = QtCore.QLockFile(str(Path(QtCore.QDir.tempPath()) / "capture-menu.lock"))
    lock.setStaleLockTime(0)   # never by age; a lock left by a crashed copy is still taken over
    if not lock.tryLock(8000 if restarted else 0):   # after Save, wait for the old copy to quit
        log.info("already running, exiting")
        return
    app.aboutToQuit.connect(lock.unlock)
    threading.Thread(target=update_start_with_windows, daemon=True).start()   # schtasks takes a moment
    problems: list[str] = []

    ctl = Controller(cfg)
    # Where captures went instead, said once and calmly: it all works, there's nothing to do.
    # (Windows Security's settings stay the user's: we don't ask anyone to change them.)
    moved_notice = None
    if ctl.blocked and load_state().get("fallback_told") != str(ctl.blocked):
        moved_notice = (tr("Your captures are saved in {fallback} · Windows Security protects {folder}",
                           fallback=ctl.clips_dir, folder=ctl.blocked.parent)
                        if controlled_folder_access_on() else
                        tr("Your captures are saved in {fallback} · {folder} can't be used",
                           fallback=ctl.clips_dir, folder=ctl.blocked))
    viewer = Viewer(ctl)
    menu = Menu(ctl, viewer)
    gallery = Gallery(ctl, viewer)
    menu.gallery = gallery
    settings = Settings(ctl)
    menu.settings = settings
    toast = Toast()
    toast.thumbs_dir = ctl.thumbs_dir
    rec_dot = RecIndicator(cfg.get("record_indicator", "top-left"))
    ctl.recording.connect(rec_dot.set_recording)
    ctl.status.connect(rec_dot.sync)
    toast.hotkey = cfg["hotkey"].upper()
    toast.pad_button = cfg["controller_button"]
    app.installEventFilter(INPUT)   # any real key press switches the hints back to the keyboard
    ctl.toast.connect(toast.show_message)
    ctl.captured.connect(toast.show_capture)
    ctl.captured.connect(lambda *_: menu.refresh_recent())
    ctl.shared.connect(toast.show_shared)

    toast.open_capture.connect(menu.view_capture)
    ctl.storage.connect(menu.show_storage)
    ctl.library_changed.connect(menu.refresh_recent)

    def to_clipboard(path: str):
        # a file on the clipboard, like Ctrl+C in Explorer: paste into Discord, WhatsApp, a chat
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(path)])
        QtGui.QGuiApplication.clipboard().setMimeData(mime)
    ctl.copy_file.connect(to_clipboard)

    tray = QtWidgets.QSystemTrayIcon(tray_icon())
    tray.setToolTip(tr("Capture Menu is running · {keys} to open", keys=cfg["hotkey"].upper()))
    tm = QtWidgets.QMenu()
    tm.addAction(tr("Open menu"), lambda: menu.show_menu())
    tm.addAction(tr("Open gallery"), lambda: gallery.open(fresh=True))
    tm.addAction(tr("Open clips folder"), ctl.open_folder)
    tm.addAction(tr("Settings"), lambda: settings.open(ctl.screen_px, fresh=True))

    def check_updates():
        settings.open(ctl.screen_px, fresh=True)
        settings.update_row.setFocus()
        settings.check_or_install()
    tm.addAction(tr("Check for updates"), check_updates)
    tm.addSeparator()
    tm.addAction(tr("Quit"), app.quit)
    tray.setContextMenu(tm)
    tray.activated.connect(lambda r: menu.show_menu()
                           if r == QtWidgets.QSystemTrayIcon.Trigger else None)
    tray.show()
    for delay in (3000, 30000):   # Windows registers the icon a moment after it first shows
        QtCore.QTimer.singleShot(delay, promote_tray_icon)

    def open_or_close(game: str):
        if settings.isVisible():
            settings.close_settings()
        elif viewer.isVisible():
            viewer.close_viewer()
        elif gallery.isVisible():
            gallery.close_gallery()
        elif menu.isVisible():
            menu.hide_menu()
        else:
            menu.show_menu(game)

    quick = int(cfg.get("double_press_seconds") or 0)
    presses = PressSequencer(
        350 if quick else 0, open_or_close,
        lambda game: ctl.save_clip(quick, game),
        lambda: menu.isVisible() or viewer.isVisible() or gallery.isVisible() or settings.isVisible())

    sounds = Sounds(bool(cfg.get("sounds", True)))
    ctl.captured.connect(lambda _d, path: sounds.play("shutter" if path.endswith(".png") else "capture"))
    ctl.recording.connect(lambda on: sounds.play("record") if on else None)

    def pad_press(button: int):
        key = pad_key(button, menu, viewer, gallery, settings)
        if key is not None:
            send_key(settings if settings.isVisible() else viewer if viewer.isVisible()
                     else gallery if gallery.isVisible() else menu, key)

    try:
        gamepad = Gamepad(cfg)
        gamepad.activated.connect(lambda: presses.press(foreground_app(cfg)))
        if cfg.get("rumble", True):
            # buzz the controller only when it's what the player is using
            ctl.captured.connect(lambda *_: gamepad.rumble("capture") if INPUT.mode != "keyboard" else None)
            ctl.recording.connect(lambda on: gamepad.rumble("record") if on and INPUT.mode != "keyboard"
                                  else None)
        gamepad.pressed.connect(pad_press)
        gamepad.used.connect(INPUT.set)
        gamepad.connected.connect(lambda name, on: toast.show_message(
            tr("Controller connected · {name}", name=name) if on else
            tr("Controller disconnected · {name}", name=name), "ok" if on else "info"))
        gamepad.start()
    except ValueError as e:
        problems.append(tr("{problem} · pick another controller button in Settings", problem=e))

    hotkey = Hotkey(cfg["hotkey"], lambda: foreground_app(cfg))
    hotkey.pressed.connect(presses.press)
    registered = hotkey.start()
    for _ in range(20 if restarted and IS_WINDOWS else 0):   # the old copy may still be letting go
        if registered:
            break
        time.sleep(0.25)
        registered = hotkey.start()
    if IS_WINDOWS and not registered:
        problems.append(tr("{keys} is taken by another app · "
                           "use the controller or the tray icon, and pick other keys in Settings",
                           keys=cfg["hotkey"].upper()))
    keys = " + ".join(k.upper() if len(k) == 1 or k[0] == "f" and k[1:].isdigit() else k.capitalize()
                      for k in cfg["hotkey"].split("+"))   # alt+c -> Alt + C
    pad_name = cfg["controller_button"].replace("+", " + ").title()
    if problems:
        toast.show_message(problems[0], "error")
    else:
        toast.show_running(tr("Settings saved") if restarted else tr("Capture Menu is running"),
                           tr("Press {keys} or {button} to open", keys=keys, button=pad_name))
    if moved_notice:
        def tell_moved():
            toast.show_message(moved_notice, "info")
            save_state(load_state() | {"fallback_told": str(ctl.blocked)})
        QtCore.QTimer.singleShot(7000, tell_moved)   # after the notice above has been read
    # once everything has been closed for a while, give memory back (once per idle stretch): a page
    # that has been open since holds a native window again, so even a quick look counts
    pages = (menu, viewer, gallery, settings)

    def idle_check():
        if any(w.isVisible() for w in pages) or not any(w.testAttribute(Qt.WA_WState_Created) for w in pages):
            return
        for w in (menu, gallery, settings):
            release_window(w)
        if viewer.player is None:    # otherwise the viewer lets its window go with the player
            release_window(viewer)
        trim_memory()
    QtCore.QTimer(app, interval=90_000, timeout=idle_check).start()

    primary = app.primaryScreen()
    native = primary.size() * primary.devicePixelRatio()
    ctl.startup((native.width(), native.height()))
    ctl.start_following()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

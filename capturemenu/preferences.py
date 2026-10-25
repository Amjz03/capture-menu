"""Default settings and configuration/state persistence."""
from __future__ import annotations

from pathlib import Path
import json
import threading

from . import runtime


CONFIG_PATH = runtime.APP_DIR / "config.json"


STATE_PATH = runtime.APP_DIR / "state.json"


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
    "mic_on": True,             # the microphone is recorded (the menu's Mic button turns it off until the next start)
    "hdr": "auto",              # auto: HDR clips while Windows HDR is on for the game's screen / off
    "colours": "vivid",         # natural / soft / vivid / max: COLOUR_BOOST for an HDR screen recorded in normal colours
    "resolution": "native",     # native / 1440p / 1080p / 720p
    "fps": 60,
    "quality": "balanced",      # light / balanced / high / max
    "video_codec": "auto",      # auto (best the GPU has) / av1 / hevc / h264
    "start_with_windows": True,
    "record_indicator": "top-left",   # top-left / top-right / off
}


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

"""Default settings and configuration/state persistence."""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import threading

from . import runtime


CONFIG_PATH = runtime.APP_DIR / "config.json"


STATE_PATH = runtime.APP_DIR / "state.json"


DEFAULTS = {
    "hotkey": "alt+c",
    "hotkey_screenshot": "",    # keys that take a screenshot without the menu ("": none)
    "hotkey_record": "",        # keys that start / stop a recording without the menu ("": none)
    "obs_host": "localhost",
    "obs_port": 4456,
    "obs_password": "",
    "clips_dir": str(Path.home() / "Videos" / "Capture Menu Clips"),
    "screenshots_dir": "",      # empty: screenshots go in clips_dir with the clips
    "library_dirs": [],         # clips folders used before: what's in them still shows in the gallery
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


# What load_config had to put right, for main() to say once: "unreadable" (config.json isn't valid JSON:
# the defaults are used and the file is kept as config.broken.json), or the names of the settings whose
# value couldn't be used (the default is used for those). None: the file was fine.
CONFIG_PROBLEM: str | list[str] | None = None


def _read_user_config() -> dict | None:
    """config.json as written, {} when there's none, None when it can't be read as settings. A file edited
    by hand with a typo in it must never stop the app from starting: the OBS password and port are still
    picked out of it, so the recording goes on."""
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError) as e:
        runtime.log.error("config.json can't be read: %s", e)
        return None
    try:
        user = json.loads(text)
        if isinstance(user, dict):
            return user
        runtime.log.error("config.json isn't a list of settings")
    except ValueError as e:
        runtime.log.error("config.json isn't valid JSON: %s", e)
    return None


def _salvage() -> dict:
    """The OBS password and port from a config.json that isn't valid JSON any more."""
    found = {}
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return found
    if m := re.search(r'"obs_password"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        try:
            found["obs_password"] = json.loads(f'"{m.group(1)}"')
        except ValueError:
            pass
    if m := re.search(r'"obs_port"\s*:\s*(\d+)', text):
        found["obs_port"] = int(m.group(1))
    return found


def _usable(default, value):
    """value as the kind of thing the default is, or None when it can't be one."""
    if isinstance(default, bool):
        return value if isinstance(value, bool) else None
    if isinstance(default, int):
        if isinstance(value, bool):
            return None
        try:
            return int(value) if float(value) == int(float(value)) else None
        except (TypeError, ValueError):
            return None
    if isinstance(default, str):
        return value if isinstance(value, str) else None
    if default == []:                 # library_dirs: folders
        return value if isinstance(value, list) and all(isinstance(v, str) for v in value) else None
    if isinstance(default, list):     # durations_seconds: whole seconds, at least one
        if not isinstance(value, list) or not value:
            return None
        try:
            lengths = [int(v) for v in value if not isinstance(v, bool)]
        except (TypeError, ValueError):
            return None
        return lengths if len(lengths) == len(value) and all(n > 0 for n in lengths) else None
    if isinstance(default, dict):
        return value if isinstance(value, dict) else None
    return value


def load_config() -> dict:
    global CONFIG_PROBLEM
    CONFIG_PROBLEM = None
    cfg = dict(DEFAULTS)
    user = _read_user_config()
    if user is None:
        CONFIG_PROBLEM = "unreadable"
        try:
            shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_name("config.broken.json"))
        except OSError:
            pass
        user = _salvage()
    if user:
        cfg.update({k: v for k, v in user.items() if v not in ("", None)})
        wrong = []
        for key, default in DEFAULTS.items():
            value = _usable(default, cfg[key])
            if value is None:
                wrong.append(key)
                value = default
            cfg[key] = value
        if int(cfg["buffer_minutes"]) < 1:
            wrong.append("buffer_minutes")
            cfg["buffer_minutes"] = DEFAULTS["buffer_minutes"]
        if wrong:
            runtime.log.warning("config.json: unusable values for %s, using the defaults", ", ".join(wrong))
            CONFIG_PROBLEM = CONFIG_PROBLEM or wrong
        if cfg.get("controller_button") == "l3+r3":   # no longer a choice (games use L3 and R3): Create
            cfg["controller_button"] = "create"
        if user.get("capture_follow_game") is False and "capture_screen" not in user:
            cfg["capture_screen"] = "main"   # up to 0.0.10 "Follow the game's screen" off kept the main screen
    if Path(cfg["clips_dir"]) == OLD_CLIPS_DIR:   # the old default, written out: the new one (move_old_clips)
        cfg["clips_dir"] = DEFAULTS["clips_dir"]
    return cfg


OLD_CLIPS_DIR = Path.home() / "Videos" / "Clips"   # the default folder up to 0.0.40


def move_old_clips(new: Path, old: Path | None = None):
    """Up to 0.0.40 captures went to Videos\\Clips; now Videos\\Capture Menu Clips. What's in the old folder moves
    over (the same drive: renamed, never copied). Favorites and titles are kept relative to the folder, so they
    come along. Anything that can't move now (open somewhere, or a name already in the new folder) stays and
    moves on a later start; nothing is overwritten or deleted."""
    old = old or OLD_CLIPS_DIR
    if not old.is_dir() or old == new:
        return
    if not new.exists():
        try:
            old.rename(new)                      # the whole folder in one step
            runtime.log.info("moved %s to %s", old, new)
            return
        except OSError as e:
            runtime.log.warning("couldn't move %s in one go (%s): moving what's in it", old, e)
            new.mkdir(parents=True, exist_ok=True)
    _merge(old, new)


def _merge(old: Path, new: Path):
    for item in list(old.iterdir()):
        target = new / item.name
        try:
            if not target.exists():
                item.rename(target)
            elif item.is_dir() and target.is_dir():   # a game folder in both: what's inside
                _merge(item, target)
            else:
                runtime.log.warning("not moved, %s is in both folders", item.name)
        except OSError as e:
            runtime.log.warning("not moved yet: %s (%s)", item, e)
    try:
        old.rmdir()                              # only once it's empty
    except OSError:
        pass


def save_config(changes: dict):
    """Writes only the given keys into config.json, keeping everything else (like the OBS password)."""
    user = _read_user_config()
    if user is None:          # not valid JSON (load_config kept a copy as config.broken.json): start it again
        user = _salvage()
    user.update(changes)
    write_atomic(CONFIG_PATH, json.dumps(user, indent=2, ensure_ascii=False))


def write_atomic(path: Path, text: str):
    """A write that can't leave half a file: a full copy next to it, then swapped in one step."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


_state_cache: tuple[float, dict] | None = None


_state_lock = threading.Lock()


def _read_state() -> dict:
    global _state_cache
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


def _write_state(state: dict):
    global _state_cache
    write_atomic(STATE_PATH, json.dumps(state, indent=2))
    _state_cache = (STATE_PATH.stat().st_mtime, json.loads(json.dumps(state)))


def load_state() -> dict:
    """state.json, kept in memory until the file changes (it's read on every tile paint)."""
    with _state_lock:
        return _read_state()


def peek_state() -> dict:
    """The state as it is now, not copied: only to read (a gallery paint asks for it per tile)."""
    with _state_lock:
        try:
            mtime = STATE_PATH.stat().st_mtime
        except OSError:
            return {}
        if _state_cache is None or _state_cache[0] != mtime:
            _read_state()                  # loads the file into the cache
        return _state_cache[1] if _state_cache else {}


def update_state(change):
    """Reads, changes (change(state) edits the dict) and writes state.json with nothing in between, so two
    changes at once both stay (a favorite and a recording, say)."""
    with _state_lock:
        state = _read_state()
        result = change(state)
        _write_state(state)
        return result


def rekey_library(old: Path, new: Path):
    """The clips folder changed from old to new. Favorites, titles and sound levels are kept by a capture's
    path inside the clips folder (or its whole path when it's somewhere else), so each one is written again
    for the new folder: captures left in the old folder keep theirs, and so do ones already in the new."""
    def key_for(key: str) -> str:
        path = Path(key)
        path = path if path.is_absolute() else old / path
        try:
            return str(path.relative_to(new))
        except ValueError:
            return str(path)

    def change(state):
        if "favorites" in state:
            state["favorites"] = sorted({key_for(k) for k in state["favorites"]})
        for table in ("meta", "levels", "mix"):
            if table in state:
                state[table] = {key_for(k): v for k, v in state[table].items()}
    if old != new:
        update_state(change)


def save_state(state: dict):
    with _state_lock:
        _write_state(state)

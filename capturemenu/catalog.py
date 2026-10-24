"""Capture folder validation, names, sizes and relative-time labels."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import re
import time

from . import language, runtime


# ---------------------------------------------------------------- storage

def human_size(nbytes: float) -> str:
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:.1f} {language.tr('GB')}"     # units are translated too ("2 ميجا")
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024 ** 2:.0f} {language.tr('MB')}"
    return f"{max(1, round(nbytes / 1024))} {language.tr('KB')}"


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
        runtime.log.warning("can't use %s: %s", path, e)
        return False


def controlled_folder_access_on() -> bool:
    """Windows Security's ransomware protection (blocks unknown apps from Videos, Documents…)."""
    if not runtime.IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender"
                             r"\Windows Defender Exploit Guard\Controlled Folder Access")
        return winreg.QueryValueEx(key, "EnableControlledFolderAccess")[0] == 1
    except OSError:
        return False


def capture_kind(path: Path) -> str:
    parts = path.stem.split("_")
    if parts[0] == "Screenshot":
        return language.tr("Screenshot")
    if parts[0] == "Recording":
        return language.tr("Recording")
    if parts[0] == "Clip" and len(parts) >= 4 and parts[3] == "trim":
        return language.tr("Trimmed clip")
    if parts[0] == "Clip" and len(parts) >= 4 and parts[3].endswith("s"):
        return language.tr("Clip · {length}", length=language.duration_label(int(parts[3][:-1]), short=True))
    return language.tr("Clip")


def time_ago(ts: float) -> str:
    s = int(time.time() - ts)
    if s < 60:
        return language.tr("just now")
    if s < 3600:
        return language.tr("{n} min ago", n=s // 60)
    if s < 86400:
        return language.tr("{n} h ago", n=s // 3600)
    d = datetime.fromtimestamp(ts)
    return f"{d.day} {language.tr(d.strftime('%b'))}"   # month names are translated too

"""Translations, RTL direction and user-facing time labels."""
from __future__ import annotations

from PySide6.QtCore import Qt
import ctypes
import json

from . import runtime


# ---------------------------------------------------------------- language
# Every on-screen text is written in English and passed through tr(). Other languages live in
# assets/lang/<code>.json, which maps the English text to the translation ({name} fields stay).

LANGUAGES = {"en": "English", "ar": "العربية"}


LANG = "en"


_TRANSLATIONS: dict[str, str] = {}


def system_language() -> str:
    """Windows' display language, if Capture Menu has it; English otherwise."""
    if runtime.IS_WINDOWS:
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
            _TRANSLATIONS = json.loads((runtime.BUNDLE_DIR / "assets" / "lang" / f"{LANG}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            runtime.log.exception("could not load the %s translation", LANG)
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

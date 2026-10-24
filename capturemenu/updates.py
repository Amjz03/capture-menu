"""GitHub release lookup and verified installer download/handoff."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile

from . import version, windows


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def latest_release(timeout: float = 10) -> dict:
    """The newest release on GitHub: its version, page, and the Setup.exe to download."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{version.REPO}/releases/latest",
                                 headers={"User-Agent": f"CaptureMenu/{version.APP_VERSION}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    asset = next((a for a in data.get("assets", []) if a.get("name") == "CaptureMenu-Setup.exe"), None)
    return {"version": str(data.get("tag_name", "")).lstrip("v"), "page": data.get("html_url", ""),
            "url": asset["browser_download_url"] if asset else None, "size": asset["size"] if asset else 0,
            "digest": asset.get("digest") if asset else None}


def update_sha256(size: int, digest: str) -> str:
    """Require the SHA-256 supplied by GitHub over HTTPS; older assets may lack it."""
    if type(size) is not int or size <= 0:
        raise ValueError("missing or invalid installer size")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("missing or invalid installer SHA-256")
    return digest.split(":", 1)[1].lower()


def verify_update(exe: Path, size: int, digest: str):
    expected = update_sha256(size, digest)
    with exe.open("rb") as f:
        length = os.fstat(f.fileno()).st_size
        actual = hashlib.file_digest(f, "sha256").hexdigest()
    if length != size or actual != expected:
        raise RuntimeError("installer integrity check failed")


def download_update(url: str, size: int, out: Path, on_progress=None, *, digest: str):
    """Download to a unique partial file; promote it only after size and SHA-256 match."""
    import urllib.request
    update_sha256(size, digest)
    if not isinstance(url, str) or not re.fullmatch(
            rf"https://github\.com/{re.escape(version.REPO)}/releases/download/[^/?#]+/CaptureMenu-Setup\.exe", url):
        raise ValueError("unexpected installer URL")
    req = urllib.request.Request(url, headers={"User-Agent": f"CaptureMenu/{version.APP_VERSION}"})
    done, shown = 0, -1
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=out.parent, prefix=out.name, suffix=".part", delete=False) as f:
            tmp = Path(f.name)
            with urllib.request.urlopen(req, timeout=30) as r:
                if not r.geturl().startswith("https://"):
                    raise ValueError("installer download requires HTTPS")
                while chunk := r.read(1 << 16):
                    done += len(chunk)
                    if done > size:
                        raise RuntimeError("installer exceeds expected size")
                    f.write(chunk)
                    pct = min(99, done * 100 // size)
                    if on_progress and pct != shown:
                        shown = pct
                        on_progress(pct)
        verify_update(tmp, size, digest)
        os.replace(tmp, out)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def run_update_installer(exe: Path, *, size: int, digest: str):
    """Recheck immediately before launch; leave Capture Menu running if launch fails."""
    verify_update(exe, size, digest)
    windows.launch_outside([str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], flags=0x00000008)
    QtWidgets.QApplication.quit()

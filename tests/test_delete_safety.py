"""Recycling failures must preserve captures, metadata and truthful UI outcomes."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore
import hashlib
from capturemenu import capture_controller, media, preferences, runtime, ui_gallery, ui_viewer
from PySide6 import QtWidgets

app = QtWidgets.QApplication([])
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    preferences.STATE_PATH = root / "state.json"
    with patch.object(capture_controller.Controller, "_remake_hdr_thumbs"):
        ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(root / "Clips")))
    ctl.check_storage = lambda: None
    clip = ctl.clips_dir / "Screenshot_test.png"
    clip.write_bytes(b"fixture")
    ctl.toggle_favorite(clip)
    ctl.set_meta(clip, "Keep me", "important")
    ctl.recent = [clip]
    thumb = ctl.thumbs_dir / (hashlib.md5(str(clip).encode()).hexdigest() + ".jpg")
    thumb.write_bytes(b"thumb")
    preview = ctl.preview_path(clip); preview.write_bytes(b"preview")
    saved_state = preferences.STATE_PATH.read_bytes()
    for outcome in (False, (False, ""), OSError("denied"), RuntimeError("Qt failure")):
        kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
        with patch.object(QtCore.QFile, "moveToTrash", **kwargs):
            assert ctl.delete(clip) is False
        assert clip.read_bytes() == b"fixture" and thumb.exists() and preview.exists()
        assert ctl.recent == [clip] and preferences.STATE_PATH.read_bytes() == saved_state
    print("failed recycling preserves capture, metadata, favorites and caches PASS")

    # Fake recycling moves only these fixtures to another disposable directory.
    recycled = root / "recycled"; recycled.mkdir()
    def recycle(path):
        src = Path(path); dest = recycled / f"{len(list(recycled.iterdir()))}-{src.name}"
        src.rename(dest)
        return True, str(dest)
    with patch.object(QtCore.QFile, "moveToTrash", side_effect=recycle):
        assert ctl.delete(clip)
    assert not clip.exists() and not thumb.exists() and not preview.exists()
    assert not ctl.is_favorite(clip) and not ctl.meta(clip) and not ctl.recent
    print("successful recycling cleanup PASS")

    # A file locked for a moment (antivirus scanning a new capture) goes on a later try.
    clip.write_bytes(b"fixture")
    tries = []
    def locked_once(path):
        tries.append(path)
        return recycle(path) if len(tries) > 1 else False
    with patch.object(QtCore.QFile, "moveToTrash", side_effect=locked_once), patch("time.sleep"):
        assert ctl.delete(clip) and len(tries) == 2 and not clip.exists()
    print("briefly locked file recycled on retry PASS")

    # Once recycled, a cache cleanup error must not report that the capture failed to move.
    clip.write_bytes(b"fixture")
    with patch.object(QtCore.QFile, "moveToTrash", return_value=True), \
         patch.object(ctl, "is_favorite", side_effect=OSError("metadata locked")):
        assert ctl.delete(clip)

    gallery = ui_gallery.Gallery(ctl, ui_viewer.Viewer(ctl))
    gallery.refresh = lambda: None  # avoid multimedia work; exercise the real deletion UI handler
    notices = []
    ctl.toast.connect(lambda text, kind: notices.append((text, kind)))
    for total, successes in ((2, 0), (2, 1), (2, 2), (1, 1)):
        paths = [ctl.clips_dir / f"Screenshot_{i}.png" for i in range(total)]
        for p in paths: p.write_bytes(b"fixture")
        gallery.marked = set(paths)
        gallery.del_btn.setProperty("danger", True)
        def mixed(path):
            if Path(path) in paths[:successes]:
                return recycle(path)
            return False, ""
        with patch.object(QtCore.QFile, "moveToTrash", side_effect=mixed):
            gallery.delete_marked()
        text, kind = notices[-1]
        assert kind == ("ok" if successes == total else "error"), notices
        assert "freed" not in text and "Deleted" not in text
        assert gallery.marked == set(paths[successes:])
        if successes == 0:
            assert "No captures" in text
        elif successes < total:
            assert "Moved 1 of 2 captures" in text and "1 could not be moved" in text
        else:
            assert f"Moved {successes} capture" in text
    print("zero, partial, single and full gallery outcomes PASS")

    # Trim replacement still produces a new clip when recycling the original fails.
    clip.write_bytes(b"original")
    trim_events = []
    ctl.toast.connect(lambda *_: trim_events.append("warning"))
    with patch.object(media, "trim_clip", return_value="precise"), \
         patch.object(ctl, "delete", return_value=False), \
         patch.object(ctl, "_done", side_effect=lambda *_: trim_events.append("capture")) as done:
        ctl._trim(clip, 0, 1000, replace=True)
        done.assert_called_once()
    assert clip.read_bytes() == b"original" and notices[-1][1] == "error"
    assert trim_events == ["capture", "warning"], "capture success must not obscure the recycling warning"
    print("trim replacement failure preserves original PASS")

    # Native Windows failure without recycling or deleting any real capture.
    if runtime.IS_WINDOWS:
        missing = root / "does-not-exist.png"
        assert ctl.delete(missing) is False
        print("Windows QFile.moveToTrash missing-file failure PASS")
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(clip), 0x80000000, 0, None, 3, 0, None)
        assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
        try:
            assert ctl.delete(clip) is False
            assert clip.exists()
        finally:
            kernel.CloseHandle(handle)
        assert clip.read_bytes() == b"original"
        print("Windows QFile.moveToTrash locked disposable file preserves bytes PASS")

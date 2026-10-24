"""A recording is moved only once OBS has finished writing it: never copied half-written."""
import sys, threading, time, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore
from capturemenu import capture_controller, media, preferences

app = QtCore.QCoreApplication([])
tmp = Path(tempfile.mkdtemp())
obs_dir = tmp / "obs"; obs_dir.mkdir()
expected = b"".join(bytes([i]) * 4096 for i in range(4))

def write_like_obs(path, ready):
    """Like OBS's hybrid MP4: fragments over a second apart (the size stands still between them)."""
    with open(path, "wb") as f:
        for i in range(4):
            f.write(bytes([i]) * 4096); f.flush()
            if i == 0:
                ready.set()
            time.sleep(1.2)

def start_writing(path):
    ready = threading.Event()
    writer = threading.Thread(target=write_like_obs, args=(path, ready)); writer.start(); ready.wait()
    return writer

part = obs_dir / "2026-10-24 10-59-34.mp4"
writer = start_writing(part)
assert media.open_elsewhere(part), "a file OBS has open is busy"
assert not media.wait_until_written(part, timeout=0.8), "not done while it's still open"
assert media.wait_until_written(part, timeout=15) and not writer.is_alive()
assert not media.open_elsewhere(part) and part.read_bytes() == expected
print("waits for OBS to close the file PASS")

rec = obs_dir / "rec.mp4"
class FakeObs:
    rec = True
    def record_status(self): return self.rec, 0
    def stop_record(self):   # OBS returns the path at once and keeps writing for a few seconds
        self.rec = False
        start_writing(rec)
        return rec
with patch.object(capture_controller.Controller, "_remake_hdr_thumbs"):
    ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips")))
ctl.obs = FakeObs(); ctl.check_storage = lambda: None
ctl._toggle_record("Game")
saved = list((tmp / "Clips" / "Game").glob("Recording_*.mp4"))
assert len(saved) == 1 and saved[0].read_bytes() == expected and not rec.exists(), saved
print("recording moved whole, never half-written PASS")

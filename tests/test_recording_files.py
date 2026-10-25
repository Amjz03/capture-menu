"""A file OBS is still writing is never read half-written; the last minutes live in files OBS
splits its recording into, and clips and recordings join only finished ones."""
import sys, threading, time, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore
from capturemenu import capture_controller, media, obs_client, preferences

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


# ---- the last minutes on disk
obs_client.BUFFER_DIR = tmp / "Buffer"
preferences.STATE_PATH = tmp / "state.json"
C = capture_controller.Controller
seg = lambda name, start, end: (obs_client.BUFFER_DIR / name, start, end)
now = 10_000.0
a, b, c, d = seg("a.mp4", now - 200, now - 140), seg("b.mp4", now - 100, now - 40),     seg("c.mp4", now - 40, now - 0.5), seg("d.mp4", now - 0.4, now)
assert C._last_run([a, b, c, d]) == [b, c, d], "OBS restarted between a and b: a doesn't join on"
assert C._since([b, c], now - 30) == ([c[0]], 10.0)
assert C._since([b, c], now - 70) == ([b[0], c[0]], 30.0)
assert C._since([b, c], None) == ([b[0], c[0]], 0.0)
print("which files hold the last seconds PASS")

class FakeObs:
    def __init__(self): self.splits = 0
    def buffer_active(self): return True
    def split(self): self.splits += 1
with patch.object(C, "_remake_hdr_thumbs"):
    ctl = C(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips"), buffer_minutes=5))
ctl.obs = FakeObs(); ctl.check_storage = lambda: None; ctl._done = lambda text, path: done.append((text, path))
joined, done = [], []
media.join = lambda files, inpoint, out: joined.append((files, inpoint, out.name))
media.media_duration = lambda p: 30.0
segments = [[a, b, c], [a, b, c, d]]     # the split: OBS starts d once c is finished
C._segments = classmethod(lambda cls: segments.pop(0) if len(segments) > 1 else segments[0])
capture_controller.time.time = lambda: now
ctl._save_clip(30, "Game")
assert ctl.obs.splits == 1 and joined[-1][:2] == ([c[0]], 9.5), joined
assert joined[-1][2].startswith("Clip_") and joined[-1][2].endswith("_30s.mp4") and done[-1][0] == "Last 30 sec", (joined, done)
print("a clip joins finished files only PASS")

segments = [[a, b, c, d]]
ctl._toggle_record("Game")
assert preferences.load_state()["recording"] == {"since": now, "game": "Game"} and not joined[1:]
capture_controller.time.time = lambda: now + 90
d2 = (d[0], d[1], now + 89.5)          # d went on until the split
segments = [[a, b, c, d2], [a, b, c, d2, seg("e.mp4", now + 89.6, now + 90)]]
ctl._toggle_record("Desktop")
assert joined[-1][0] == [d[0]] and abs(joined[-1][1] - 0.4) < 1e-6 and joined[-1][2].startswith("Recording_"), joined
assert "recording" not in preferences.load_state() and done[-1][0] == "Length 00:30" and done[-1][1].parent.name == "Game", done
print("a recording is everything since Start, in the game it started in PASS")

# old files go; the newest (being written) and a running recording's stay
obs_client.BUFFER_DIR.mkdir(exist_ok=True)
for s_ in (a, b, c, d):
    s_[0].write_bytes(b"x")
capture_controller.time.time = lambda: now
segments = [[a, b, c, d]]
preferences.save_state({"recording": {"since": now - 150, "game": "Game"}})
ctl._prune()
assert a[0].exists() and b[0].exists(), "a recording since now-150 keeps them"
preferences.save_state({})
ctl.cfg["buffer_minutes"] = 1
ctl._prune()
assert not a[0].exists() and b[0].exists() and c[0].exists() and d[0].exists(), "b holds part of the last minute"
print("old minutes deleted, nothing newer PASS")

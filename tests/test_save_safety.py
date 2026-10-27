"""Saving can't lose what was saved: one Stop at a time, a name nothing else has, no pruning while a save joins,
a failed join removes only its own file, state changes at once all stay, a write that breaks leaves the old
file, an OBS that can't say whether it streams isn't restarted, and a screenshot that never came isn't "saved"."""
import sys, threading, time, tempfile, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from PySide6 import QtCore
from capturemenu import capture_controller, media, obs_client, preferences

app = QtCore.QCoreApplication([])
tmp = Path(tempfile.mkdtemp())
obs_client.BUFFER_DIR = tmp / "Buffer"; obs_client.BUFFER_DIR.mkdir()
preferences.STATE_PATH = tmp / "state.json"
C = capture_controller.Controller


class FakeObs:
    def __init__(self): self.splits = 0; self.shots = []
    def buffer_active(self): return True
    def split(self): self.splits += 1
    def screenshot(self, path): self.shots.append(path)


with patch.object(C, "_remake_hdr_thumbs"):
    ctl = C(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips"), shots_dir=str(tmp / "Shots"), buffer_minutes=5))
ctl.obs = FakeObs(); ctl.check_storage = lambda: None
done, toasts = [], []
ctl._done = lambda text, path: done.append(path)
ctl.toast.connect(lambda text, kind: toasts.append((text, kind)))
now = 10_000.0
capture_controller.time.time = lambda: now
seg = lambda name, start, end: (obs_client.BUFFER_DIR / name, start, end)
a, b = seg("a.mp4", now - 400, now - 310), seg("b.mp4", now - 300, now - 1)
for s in (a, b):
    s[0].write_bytes(b"x")
C._segments = classmethod(lambda cls: [a, b, seg("c.mp4", now, now + 1)])
ctl._finished_segments = lambda: [a, b]

# ---- QA03-01: a second Stop while the first joins is turned away; it can't join (or delete) the same files
preferences.update_state(lambda s: s.update(recording={"since": now - 350, "game": "Game"}))
release, joins = threading.Event(), []
def slow_join(files, inpoint, out):
    joins.append(out); release.wait(5); out.write_bytes(b"rec")
real_join, media.join = media.join, slow_join
first = threading.Thread(target=ctl._toggle_record, args=("Game",)); first.start()
while not joins: time.sleep(0.01)
ctl._toggle_record("Game")                     # the double click
assert len(joins) == 1 and "still saving" in toasts[-1][0], (joins, toasts)
# ---- QA02-001: meanwhile the minute's prune leaves every file alone (the save picked a, which is past 5 min)
ctl._prune()
assert a[0].exists(), "a file a save is joining is never pruned"
release.set(); first.join()
assert joins[0].read_bytes() == b"rec" and "recording" not in preferences.load_state()
ctl._prune()
assert not a[0].exists(), "and goes once the save is done"
print("one Stop at a time, no pruning while saving PASS")

# ---- QA07-001 / QA04-02: names in the same second never repeat, nor hit a file that's there
media.join = real_join
p1 = ctl._new_path(tmp, "Clip_2026-10-27_10-00-00_trim", ".mp4"); p1.write_bytes(b"1")
p2 = ctl._new_path(tmp, "Clip_2026-10-27_10-00-00_trim", ".mp4")
s1 = ctl._new_path(tmp, "Screenshot_2026-10-27_10-00-00", ".png")    # not written yet...
s2 = ctl._new_path(tmp, "Screenshot_2026-10-27_10-00-00", ".png")    # ...still a different name
assert p2 != p1 and p2.name == "Clip_2026-10-27_10-00-00_trim_2.mp4" and s1 != s2, (p1, p2, s1, s2)
from capturemenu import catalog
assert catalog.capture_kind(p2) == "Trimmed clip" and catalog.capture_kind(s2) == "Screenshot"
print("unique names PASS")

# ---- a join that fails removes only its own file, never one already there
keep = tmp / "Recording_keep.mp4"; keep.write_bytes(b"saved before")
media.find_tool = (lambda real: lambda name: real(name) or "ffmpeg")(media.find_tool)
real_run = media.run_quiet
media.run_quiet = lambda cmd, **k: type("R", (), {"returncode": 1, "stderr": "boom"})()
try:
    media.join([a[0]], 0, keep)
    raise AssertionError("the join failed")
except RuntimeError:
    pass
media.run_quiet = real_run
assert keep.read_bytes() == b"saved before" and not list(tmp.glob("*.part")), list(tmp.iterdir())
print("failed join keeps others' files PASS")

# ---- QA10-01: a favorite and a recording changed at once both stay
preferences.save_state({})
barrier = threading.Barrier(8)
def fav(i):
    barrier.wait(); ctl.toggle_favorite(tmp / f"clip{i}.mp4")
threads = [threading.Thread(target=fav, args=(i,)) for i in range(7)]
for t in threads: t.start()
barrier.wait(); preferences.update_state(lambda s: s.update(recording={"since": 1, "game": "G"}))
for t in threads: t.join()
st = preferences.load_state()
assert len(st["favorites"]) == 7 and st["recording"]["game"] == "G", st
print("state changes at once all stay PASS")

# ---- QA10-02: a write that breaks halfway leaves the last good file
good = json.loads(preferences.STATE_PATH.read_text(encoding="utf-8"))
real_write = Path.write_text
def half(self, text, *a, **k):
    real_write(self, text[:9], *a, **k); raise OSError("disk full")
with patch.object(Path, "write_text", half):
    try:
        preferences.update_state(lambda s: s.update(more=1))
    except OSError:
        pass
assert json.loads(preferences.STATE_PATH.read_text(encoding="utf-8")) == good
print("a broken write keeps the old file PASS")

# ---- QA16-02: OBS answers but can't say whether it streams: counts as streaming, so it isn't closed
from obsws_python.error import OBSSDKRequestError
o = obs_client.Obs.__new__(obs_client.Obs)
o.raw = lambda *a, **k: (_ for _ in ()).throw(OBSSDKRequestError("GetStreamStatus", 700, "unknown"))
assert o.streaming() is True
killed = []
capture_controller.media.run_quiet = lambda cmd, **k: killed.append(cmd)
with patch.object(obs_client, "obs_running", lambda: True), patch.object(obs_client, "obs_exe_path", lambda: "obs64.exe"):
    ctl.obs = o
    assert ctl.restart_obs() is False and not killed, killed
capture_controller.media.run_quiet = real_run
print("unknown stream: not restarted PASS")

# ---- QA04-01: OBS never wrote the screenshot: no "saved", an error instead
ctl.obs = FakeObs()
media.wait_until_written = lambda path, timeout=30: False
done.clear()
ctl._screenshot("Game")
assert not done and toasts[-1][1] == "error", toasts[-1]
print("screenshot not written PASS")

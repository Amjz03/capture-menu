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

# ---- QA08-001: three tries still over the limit: an error, no "ready to share" with a file too big
src = tmp / "Clips" / "Game" / "Clip_2026-10-27_10-00-00_30s.mp4"; src.parent.mkdir(parents=True, exist_ok=True)
src.write_bytes(b"v")
over = tmp / "over.mp4"
real = (media.run_ffmpeg, media.media_duration, media.video_height, media.audio_tracks, media.has_encoder, media.sdr_filter)
media.run_ffmpeg = lambda cmd, *a, **k: (Path(cmd[-1]).write_bytes(b"\0" * (11 * 1024 * 1024)), 0)[1]
media.media_duration, media.video_height, media.audio_tracks = (lambda p: 30.0), (lambda p: 1080), (lambda p: 1)
media.has_encoder, media.sdr_filter = (lambda n: False), (lambda s, vf: vf)
try:
    media.export_for_share(src, over, 10, False)
    raise AssertionError("11 MB for a 10 MB limit isn't a success")
except RuntimeError as e:
    assert "10 MB" in str(e) and not over.exists(), e
(media.run_ffmpeg, media.media_duration, media.video_height, media.audio_tracks, media.has_encoder, media.sdr_filter) = real
print("over the size limit fails PASS")

# ---- QA08-003: two clips with one title make two share copies
other = src.with_name("Clip_2026-10-27_11-00-00_30s.mp4"); other.write_bytes(b"w")
ctl.set_meta(src, "Boss fight", ""); ctl.set_meta(other, "Boss fight", "")
outs = []
real_export, media.export_for_share = media.export_for_share, lambda s, o, *a, **k: (outs.append(o), o.write_bytes(s.read_bytes()), 1.0)[-1]
real_thumb, media.make_thumb = media.make_thumb, lambda *a: None
ctl._share(src, "discord10", False); ctl._share(other, "discord10", False); ctl._share(src, "discord10", False)
assert outs[0] != outs[1] and outs[2] == outs[0] and outs[0].name.startswith("Boss fight_"), outs
media.export_for_share, media.make_thumb = real_export, real_thumb
print("same title, own share copy PASS")

# ---- QA01-001: Stop that OBS doesn't carry out is reported, so Quit can ask instead of leaving it recording
o = obs_client.Obs.__new__(obs_client.Obs)
o.record_status = lambda: (True, 0)
o.call = lambda *a, **k: None
assert o.stop_buffer(wait=0.3) is False
o.record_status = lambda: (False, 0)
assert o.stop_buffer() is True
print("stop result reported PASS")

# ---- QA16-01: the screen switched but fitting it failed: the next check (same screen) fits it again
o = obs_client.Obs.__new__(obs_client.Obs)
o.cfg = {"obs_display_source": "Display Capture"}
fits = []
def raw(req, data=None):
    if req == "GetInputPropertiesListPropertyItems":
        return {"propertyItems": [{"itemValue": "m1", "itemName": "Screen 1: 0,0"}]}
    if req == "GetInputSettings":
        return {"inputSettings": {"monitor_id": o_current[0]}}
    if req == "SetInputSettings":
        o_current[0] = data["inputSettings"]["monitor_id"]; return {}
    if req == "GetVideoSettings":
        fits.append(1)
        if len(fits) == 1:
            raise RuntimeError("OBS busy")
        return {"baseWidth": 1920, "baseHeight": 1080}
    return {"sceneName": "S", "sceneItemId": 1}
o_current = ["m0"]
o.raw = raw
from capturemenu import windows as win
real_pick, win.pick_monitor_item = win.pick_monitor_item, lambda items, rect: items[0]
assert o.capture_monitor((0, 0, 1920, 1080)) and "Display Capture" in o.unfitted
o.capture_monitor((0, 0, 1920, 1080))
assert len(fits) == 2 and "Display Capture" not in o.unfitted, fits
win.pick_monitor_item = real_pick
print("failed fit tried again PASS")

# ---- QA14-001: with an L3+R3 combo, L3 alone still does what L3 does (on release); the combo isn't a press
from capturemenu import input_devices
st = input_devices.PadState(frozenset({7, 8}), 0)
assert st.step({7}, 0.0) == (False, []) and st.step(set(), 0.1) == (False, [7]), "L3 alone"
assert st.step({7}, 1.0) == (False, []) and st.step({7, 8}, 1.05)[0] and st.step(set(), 1.2) == (False, []), "the combo"
one = input_devices.PadState(frozenset({4}), 0)
assert one.step({4}, 0.0)[0] and one.step(set(), 0.1) == (False, []), "a one-button combo is never a press too"
print("combo buttons alone PASS")

# ---- QA20-03: a length measured before the file changed is dropped, and never saved under the new time
import os as _os
clip = tmp / "Clips" / "Game" / "Clip_2026-10-27_12-00-00_30s.mp4"; clip.write_bytes(b"c")
_os.utime(clip, (1000, 1000))
ctl._lengths_file.write_text(json.dumps({str(clip): [1000, 3.0]}), encoding="utf-8")
with patch.object(C, "_remake_hdr_thumbs"):
    c2 = C(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips"), buffer_minutes=5))
assert c2.length_of(clip) == 3.0
_os.utime(clip, (2000, 2000))                      # changed in place
c2.save_lengths()
with patch.object(C, "_remake_hdr_thumbs"):
    c3 = C(dict(preferences.DEFAULTS, clips_dir=str(tmp / "Clips"), buffer_minutes=5))
assert c3.length_of(clip) is None and c2.length_of(clip) is None, "measured again, not the old 3 s"
print("stale length dropped PASS")

# ---- QA20-01: reading favorites and titles doesn't copy the whole state each time
calls = []
real_read = preferences._read_state
preferences._read_state = lambda: (calls.append(1), real_read())[1]
for _ in range(50):
    ctl.is_favorite(clip); ctl.title_of(clip)
preferences._read_state = real_read
assert len(calls) <= 1, len(calls)
print("tile reads don't copy the state PASS")

# ---- a combo counts on one controller only (L1 on one pad, R1 on another isn't it); L3 + R3 is no longer offered
pair = input_devices.PadState(frozenset({9, 10}), 0)
assert pair.step({9, 10}, 0.0, together=False) == (False, []), "split over two controllers: nothing"
pair = input_devices.PadState(frozenset({9, 10}), 0)
assert pair.step({9, 10}, 0.0, together=True)[0], "on one controller: it opens"
cfg_file = tmp / "config.json"; cfg_file.write_text(json.dumps({"controller_button": "l3+r3"}), encoding="utf-8")
with patch.object(preferences, "CONFIG_PATH", cfg_file):
    assert preferences.load_config()["controller_button"] == "create"
print("combo on one controller PASS")

# ---- the clips folder: "Capture Menu Clips" for a new install; who used "Clips" before keeps it
home = tmp / "home"; (home / "Videos" / "Clips").mkdir(parents=True)
empty_cfg = tmp / "empty_config.json"; empty_cfg.write_text("{}", encoding="utf-8")
fresh_state = tmp / "no_state.json"
with patch.object(Path, "home", lambda: home), patch.object(preferences, "CONFIG_PATH", empty_cfg), \
        patch.dict(preferences.DEFAULTS, clips_dir=str(home / "Videos" / "Capture Menu Clips")):
    with patch.object(preferences, "STATE_PATH", fresh_state):
        assert Path(preferences.load_config()["clips_dir"]).name == "Capture Menu Clips", "a new install"
    used = tmp / "used_state.json"; used.write_text("{}", encoding="utf-8")
    with patch.object(preferences, "STATE_PATH", used):
        assert Path(preferences.load_config()["clips_dir"]) == home / "Videos" / "Clips", "an old install keeps it"
print("clips folder name PASS")

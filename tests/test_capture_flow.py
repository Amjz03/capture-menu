import sys, time, shutil, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, catalog, media, obs_client, preferences, runtime, windows

# folder names
for raw, want in [("Cyberpunk 2077™", "Cyberpunk 2077"), ('Half-Life: Alyx', "Half-Life Alyx"),
                  ("  Game. ", "Game"), ("CON", "CON_"), ("", "Desktop"), ("a/b\\c?", "a b c")]:
    got = windows.safe_folder_name(raw); assert got == want, (raw, got)
if not runtime.IS_WINDOWS:
    assert windows.foreground_app({}) == "Desktop"   # non-Windows fallback (on Windows: whatever is in front)

tmp = Path(tempfile.mkdtemp())
preferences.STATE_PATH = tmp / "state.json"
master = tmp / "master.mp4"
subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=320x180:rate=30","-f","lavfi","-i","sine",
                "-t","120","-g","30","-c:v","libx264","-preset","ultrafast","-c:a","aac",str(master)],check=True)
# the last minutes as OBS leaves them: 40 s files, a new one started at every split
obs_client.BUFFER_DIR = tmp / "Buffer"; obs_client.BUFFER_DIR.mkdir()
pieces = []
for i in range(3):
    p = obs_client.BUFFER_DIR / f"seg{i}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(i * 40), "-t", "40", "-i", str(master), "-c", "copy", str(p)], check=True)
    pieces.append(p)
clock = [1000.0]
segs = [(pieces[0], clock[0] - 120, clock[0] - 80), (pieces[1], clock[0] - 80, clock[0] - 40)]
capture_controller.Controller._segments = classmethod(lambda cls: list(segs))
capture_controller.time.time = lambda: clock[0]
class FakeObs:
    def buffer_active(self): return True
    def split(self):    # the file being written is finished; the next one starts
        segs.append((pieces[2], segs[-1][2], clock[0])); clock[0] += 1
        segs.append((obs_client.BUFFER_DIR / "next.mp4", clock[0], clock[0]))
    def screenshot(self, path): path.write_bytes(b"png")
_segments_split = FakeObs.split
def split(self):
    while segs and segs[-1][0].name == "next.mp4":
        segs.pop()
    if segs[-1][0] == pieces[2]:
        segs.pop()
    _segments_split(self)
FakeObs.split = split
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp/"Clips"))); ctl.obs = FakeObs()
msgs = []; ctl.toast.connect(lambda t,k: msgs.append(t))

ctl._save_clip(30, "Cyberpunk 2077"); time.sleep(1.1)
first = next((ctl.clips_dir / "Cyberpunk 2077").glob("Clip_*"))
assert 29 <= media.media_duration(first) <= 32 and all(p.exists() for p in pieces), media.media_duration(first)
ctl._save_clip(60, "Cyberpunk 2077")
ctl._save_clip(30, "Elden Ring")
ctl._screenshot("Elden Ring")
ctl._toggle_record("Valorant"); clock[0] += 20; ctl._toggle_record("Desktop")   # stopped from desktop -> still Valorant
ctl._save_clip(None, "Desktop")
tree = {d.name: sorted(f.name.split("_")[0] for f in d.iterdir()) for d in sorted(ctl.clips_dir.iterdir()) if d.name != ".thumbs"}
print(tree); print(*msgs, sep="\n")
assert tree == {"Cyberpunk 2077": ["Clip", "Clip"], "Desktop": ["Clip"],
                "Elden Ring": ["Clip", "Screenshot"], "Valorant": ["Recording"]}, tree
print("PASS")

# recent list + thumbnails
caps = []; ctl.captured.connect(lambda t, p: caps.append(p))
ctl._save_clip(30, "Elden Ring")
assert caps and Path(caps[0]) == ctl.recent_items()[0]
assert ctl.thumb(Path(caps[0])) is not None, "clip thumbnail missing"
shot = next((ctl.clips_dir / "Elden Ring").glob("Screenshot_*"))
assert catalog.capture_kind(Path(caps[0])) == "Clip · 30 sec" and catalog.capture_kind(shot) == "Screenshot"
fresh = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp/"Clips")))
assert len(fresh.recent_items()) == 7, fresh.recent_items()   # rescan finds everything
assert fresh.delete(Path(caps[0])) and not Path(caps[0]).exists()
print("recent/thumb/delete PASS")

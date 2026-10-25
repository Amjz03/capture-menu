import sys, time, shutil, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import capture_controller, catalog, preferences, runtime, windows

# folder names
for raw, want in [("Cyberpunk 2077™", "Cyberpunk 2077"), ('Half-Life: Alyx', "Half-Life Alyx"),
                  ("  Game. ", "Game"), ("CON", "CON_"), ("", "Desktop"), ("a/b\\c?", "a b c")]:
    got = windows.safe_folder_name(raw); assert got == want, (raw, got)
if not runtime.IS_WINDOWS:
    assert windows.foreground_app({}) == "Desktop"   # non-Windows fallback (on Windows: whatever is in front)

tmp = Path(tempfile.mkdtemp()); src = tmp / "obs_out"; src.mkdir()
master = tmp / "master.mp4"
subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=320x180:rate=30","-f","lavfi","-i","sine",
                "-t","120","-g","30","-c:v","libx264","-preset","ultrafast","-c:a","aac",str(master)],check=True)
class FakeObs:
    n = 0; rec = False
    def ensure_buffer(self): return True
    def buffer_active(self): return True
    def save_replay(self):
        self.n += 1; p = src/f"Replay {self.n}.mp4"; shutil.copy(master, p); return p
    def record_status(self): return self.rec, 0
    def start_record(self): self.rec = True
    def stop_record(self):
        self.rec = False; p = src/"rec.mp4"; shutil.copy(master, p); return p
    def screenshot(self, path): path.write_bytes(b"png")
ctl = capture_controller.Controller(dict(preferences.DEFAULTS, clips_dir=str(tmp/"Clips"))); ctl.obs = FakeObs()
msgs = []; ctl.toast.connect(lambda t,k: msgs.append(t))

ctl._save_clip(30, "Cyberpunk 2077"); time.sleep(1.1)
ctl._save_clip(60, "Cyberpunk 2077")
ctl._save_clip(30, "Elden Ring")
ctl._screenshot("Elden Ring")
ctl._toggle_record("Valorant"); ctl._toggle_record("Desktop")   # stopped from desktop -> still Valorant
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

# A clips folder Windows won't let us use (Controlled folder access blocking Videos, a missing drive)
# doesn't stop the app: captures go to a fallback folder, OBS is pointed there too, and config.json
# keeps the chosen folder. A fake OBS; the real one isn't touched. Usage: test_blocked_folder.py REPO
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
from PySide6 import QtCore
app = QtCore.QCoreApplication([])

work = Path(tempfile.mkdtemp())
cm.STATE_PATH = work / "state.json"
cm.CONFIG_PATH = work / "config.json"
cm.FALLBACK_CLIPS_DIR = work / "Capture Menu"
(work / "Videos").write_text("")            # a file where the folder should be: making it fails,
blocked = work / "Videos" / "Clips"           # like Controlled folder access refusing it
assert not cm.usable_folder(blocked)
assert cm.usable_folder(work / "ok")

cm.CONFIG_PATH.write_text(json.dumps({"clips_dir": str(blocked)}))
ctl = cm.Controller(cm.load_config())
assert ctl.blocked == blocked, ctl.blocked
assert ctl.clips_dir == cm.FALLBACK_CLIPS_DIR == ctl.shots_dir and ctl.clips_dir.is_dir()
assert ctl.thumbs_dir.is_dir() and ctl.folder_for("Overwatch").is_dir()
assert json.loads(cm.CONFIG_PATH.read_text())["clips_dir"] == str(blocked)   # used again once allowed
print("blocked clips folder: no crash, captures go to the fallback PASS")

ctl2 = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(work / "Clips"), screenshots_dir=str(blocked)))
assert ctl2.blocked == blocked and ctl2.clips_dir == work / "Clips" and ctl2.shots_dir == ctl2.clips_dir
print("blocked screenshots folder: screenshots go with the clips PASS")


class FakeObs:
    def __init__(self): self.applied = None
    def raw(self, req, data=None): return {"obsVersion": "31.0.0"} if req == "GetVersion" else {}
    def record_status(self): return False, 0
    def buffer_active(self): return False
    def apply_plan(self, plan): self.applied = plan; return False
    def ensure_buffer(self): pass


fine = cm.Controller(dict(cm.DEFAULTS, clips_dir=str(work / "Fine")))
assert fine.blocked is None
for c, expect in ((ctl, True), (fine, False)):
    c.obs = FakeObs(); c.toast = type("T", (), {"emit": lambda *a: None})()
    c.auto_setup(2560, 1440)
    paths = [v for cat, name, v in c.obs.applied["profile"] if name == "FilePath"]
    if expect:
        assert paths == [str(ctl.thumbs_dir / "incoming")] and Path(paths[0]).is_dir(), paths
    else:
        assert paths == [], paths    # the clips folder is fine: OBS keeps its own folder
print("OBS saves next to the fallback folder only when the clips folder is blocked PASS")

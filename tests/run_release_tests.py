"""Deterministic release gate: python tests/run_release_tests.py [test_name.py ...]."""
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
GATE = (
    "test_modules.py",
    "test_delete_safety.py", "test_recording_files.py", "test_update_integrity.py", "test_updates.py",
    "test_translations.py", "test_obs_launch.py", "test_obs_setup.py", "test_buffer_repair.py", "test_keep_recording.py", "test_welcome.py", "test_phone_link.py", "test_save_safety.py",
    "test_follow_screen.py", "test_controller.py", "test_settings.py",
    "test_devices.py", "test_folders_language.py", "test_blocked_folder.py", "test_startup.py",
)
# These need a desktop, real OS integration, FFmpeg/GPU, or performance baselines.
# Keep them visible; a new test must be explicitly classified before a release can pass.
MANUAL = {
    "test_background.py": "starts the full app and a second instance",
    "test_start_with_windows.py": "writes registry and scheduled tasks",
    "test_sdl.py": "physical controller reader smoke test",
    "test_hover.py": "desktop pointer/focus",
    "test_one_screen.py": "desktop display geometry",
    "test_rec_indicator.py": "desktop overlay geometry",
    "test_performance.py": "FFmpeg and machine-dependent timing",
    "test_caching.py": "FFmpeg",
    "test_capture_flow.py": "FFmpeg capture pipeline",
    "test_gallery_select.py": "desktop media UI",
    "test_hdr.py": "FFmpeg HDR/GPU",
    "test_share_favorites.py": "FFmpeg media export",
    "test_sound_levels.py": "FFmpeg audio",
    "test_titles_gallery.py": "FFmpeg, multimedia UI and native recycling",
    "test_trim.py": "FFmpeg, multimedia UI and screenshot output argument",
    "test_viewer_gallery_ui.py": "FFmpeg and multimedia UI",
    "test_viewer_fixes.py": "FFmpeg and multimedia UI",
}
BOOTSTRAP = r'''
import runpy, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import obsws_python as obsws
from capturemenu import catalog, preferences, windows
root = Path(sys.argv[1])
preferences.DEFAULTS["clips_dir"] = str(root / "Clips")
catalog.FALLBACK_CLIPS_DIR = root / "Fallback"
def blocked(*args, **kwargs):
    raise OSError("external integration disabled in release tests")
obsws.ReqClient = blocked
windows.launch_outside = blocked
windows.set_start_with_windows = blocked
windows.starts_with_windows = lambda: preferences.DEFAULTS["start_with_windows"]
windows.promote_tray_icon = lambda: None
# Nothing a test reaches may change the PC: no registry writes, no scheduled tasks.
import subprocess, winreg
for name in ("SetValue", "SetValueEx", "CreateKey", "CreateKeyEx", "DeleteKey", "DeleteKeyEx", "DeleteValue"):
    setattr(winreg, name, blocked)
class GuardedPopen(subprocess.Popen):   # a subclass: asyncio subclasses Popen too; subprocess.run uses it
    def __init__(self, cmd, *args, **kwargs):
        if Path(str(cmd[0] if isinstance(cmd, (list, tuple)) else str(cmd).split()[0])).stem.lower() in ("schtasks", "reg"):
            blocked()
        super().__init__(cmd, *args, **kwargs)
subprocess.Popen = GuardedPopen
test = sys.argv[2]
sys.argv = [test, str(root)]
runpy.run_path(test, run_name="__main__")
'''


def main():
    discovered = {p.name for p in (REPO / "tests").glob("test_*.py")}
    classified = set(GATE) | MANUAL.keys()
    if discovered != classified:
        raise SystemExit(f"Update test classification: {discovered ^ classified}")
    selected = sys.argv[1:] or GATE
    if set(selected) - set(GATE):
        raise SystemExit("Only isolated gate tests can be selected")
    failures = []
    for name in selected:
        with tempfile.TemporaryDirectory(prefix="CaptureMenu-tests-") as folder:
            root = Path(folder)
            for filename in ("capture_menu.py", "VERSION"):
                shutil.copy2(REPO / filename, root / filename)
            shutil.copytree(REPO / "capturemenu", root / "capturemenu", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(REPO / "assets", root / "assets")
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                       TEMP=folder, TMP=folder, APPDATA=folder, LOCALAPPDATA=folder)
            # APPDATA isolation must not hide dependencies installed with pip --user.
            env["PYTHONPATH"] = os.pathsep.join([*site.getsitepackages(), site.getusersitepackages()])
            try:
                result = subprocess.run([sys.executable, "-c", BOOTSTRAP, folder, str(REPO / "tests" / name)],
                                        cwd=root.parent, env=env, capture_output=True, text=True, encoding="utf-8",
                                        errors="replace", timeout=90)
                if result.returncode:
                    failures.append(name)
                    print(f"FAIL {name}\n{result.stdout}\n{result.stderr}", flush=True)
                else:
                    print(f"PASS {name}\n{result.stdout.rstrip()}", flush=True)
            except subprocess.TimeoutExpired:
                failures.append(name)
                print(f"FAIL {name}: timed out after 90 seconds", flush=True)
    print(f"{len(selected) - len(failures)}/{len(selected)} gate scripts passed; {len(MANUAL)} manual/integration scripts excluded.")
    for name, reason in MANUAL.items():
        print(f"NOT RUN {name}: {reason}")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())

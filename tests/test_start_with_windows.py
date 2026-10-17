import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
if not cm.IS_WINDOWS:
    print("start with Windows SKIP (not Windows)"); sys.exit(0)
import winreg
# a throwaway key and APPDATA, so the real Run list and Startup folder are never touched
cm.RUN_KEY = r"Software\CaptureMenuTest\Run"
os.environ["APPDATA"] = tempfile.mkdtemp()
def run_value():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cm.RUN_KEY) as key:
            return winreg.QueryValueEx(key, cm.RUN_NAME)[0]
    except OSError:
        return None
try:
    assert not cm.starts_with_windows()
    cm.update_start_with_windows()
    assert run_value() is None, "turned off stays off"

    # 0.0.8 and older: a Startup shortcut moves to the Run list at start
    lnk = cm.startup_shortcut(); lnk.parent.mkdir(parents=True); lnk.write_bytes(b"old")
    assert cm.starts_with_windows()
    cm.update_start_with_windows()
    assert not lnk.exists() and run_value() == cm.start_command(), run_value()
    assert "capture_menu.py" in run_value() or run_value() == f'"{sys.executable}"'

    cm.set_start_with_windows(False)
    assert run_value() is None and not cm.starts_with_windows()
    cm.set_start_with_windows(False)          # twice is fine
    cm.set_start_with_windows(True)
    assert cm.starts_with_windows() and not lnk.exists()
    print("start with Windows PASS")
finally:
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\CaptureMenuTest\Run")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\CaptureMenuTest")

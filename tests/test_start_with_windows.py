import sys, os, tempfile, subprocess
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
if not cm.IS_WINDOWS:
    print("start with Windows SKIP (not Windows)"); sys.exit(0)
import winreg
# a throwaway key, task and APPDATA, so the real Run list, tasks and Startup folder are never touched
cm.RUN_KEY = r"Software\CaptureMenuTest\Run"
cm.FROZEN = True    # act like the installed CaptureMenu.exe (a source copy leaves Windows alone)
cm.logon_task_name = lambda: "Capture Menu test (delete me)"
os.environ["APPDATA"] = tempfile.mkdtemp()
def run_value():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cm.RUN_KEY) as key:
            return winreg.QueryValueEx(key, cm.RUN_NAME)[0]
    except OSError:
        return None
def task_xml():
    done = subprocess.run(["schtasks", "/Query", "/TN", cm.logon_task_name(), "/XML"], capture_output=True)
    return done.stdout.decode("mbcs", errors="replace") if done.returncode == 0 else None
try:
    assert not cm.starts_with_windows()
    cm.update_start_with_windows()
    assert run_value() is None and task_xml() is None, "turned off stays off"

    # 0.0.8 and older: a Startup shortcut moves to the sign-in task (and the Run list) at start
    lnk = cm.startup_shortcut(); lnk.parent.mkdir(parents=True); lnk.write_bytes(b"old")
    assert cm.starts_with_windows()
    cm.update_start_with_windows()
    assert not lnk.exists() and run_value() == cm.start_command(), run_value()
    xml = task_xml()
    assert xml and "<LogonTrigger>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml, xml
    assert "<Priority>5</Priority>" in xml and "<DisallowStartIfOnBatteries>false" in xml, xml
    assert ("capture_menu.py" in xml) != cm.FROZEN and str(cm.APP_DIR) in xml

    cm.set_start_with_windows(False)
    assert run_value() is None and task_xml() is None and not cm.starts_with_windows()
    cm.set_start_with_windows(False)          # twice is fine
    cm.set_start_with_windows(True)
    assert cm.starts_with_windows() and task_xml() and not lnk.exists()
    print("start with Windows PASS")
finally:
    subprocess.run(["schtasks", "/Delete", "/TN", cm.logon_task_name(), "/F"], capture_output=True)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\CaptureMenuTest\Run")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\CaptureMenuTest")

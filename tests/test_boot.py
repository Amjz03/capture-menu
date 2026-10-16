import sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import capture_menu as cm
log_file = cm.APP_DIR / "capture_menu.log"
before = log_file.read_text() if log_file.exists() else ""
cm.install_crash_log()
threading.Thread(target=lambda: 1 / 0).start(); time.sleep(0.3)
for h in cm.logging.getLogger().handlers: h.flush()
after = log_file.read_text()[len(before):]
assert "unhandled error" in after and "ZeroDivisionError" in after, after
assert cm.find_obs_exe() is None and cm.start_obs() is False   # not Windows here
print("boot PASS")

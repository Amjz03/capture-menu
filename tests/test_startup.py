import sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import logging
from capturemenu import diagnostics, obs_client, runtime
runtime.configure_logging()
log_file = runtime.APP_DIR / "capture_menu.log"
before = log_file.read_text() if log_file.exists() else ""
diagnostics.install_crash_log()
threading.Thread(target=lambda: 1 / 0).start(); time.sleep(0.3)
for h in logging.getLogger().handlers: h.flush()
after = log_file.read_text()[len(before):]
assert "unhandled error" in after and "ZeroDivisionError" in after, after
if not runtime.IS_WINDOWS:   # on Windows this would start the real OBS
    assert obs_client.find_obs_exe() is None and obs_client.start_obs() is False
print("boot PASS")

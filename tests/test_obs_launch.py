import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import obs_client, windows
# OBS 32 asks "Run in Safe Mode?" when a run file is left in .sentinel; starting OBS clears them first
os.environ["APPDATA"] = tempfile.mkdtemp()
sentinel = Path(os.environ["APPDATA"]) / "obs-studio" / ".sentinel"; sentinel.mkdir(parents=True)
launched = []
windows.launch_outside = lambda args, **kw: launched.append(args)

left = sentinel / "run_6ef7c484"; left.write_text("")
obs_client.obs_running = lambda: True                      # never touch the file of an OBS that's running
obs_client.launch_obs(r"C:\obs\bin\64bit\obs64.exe")
assert left.exists()

obs_client.obs_running = lambda: False
obs_client.launch_obs(r"C:\obs\bin\64bit\obs64.exe")
assert not left.exists(), "a leftover from an unclean shutdown goes"
assert launched[-1] == [r"C:\obs\bin\64bit\obs64.exe", "--minimize-to-tray",
                        "--disable-shutdown-check"], launched[-1]
print("obs launch PASS")

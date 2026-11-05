import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from capturemenu import obs_client, runtime, windows
# OBS 32 asks "Run in Safe Mode?" when a run file is left in .sentinel; starting OBS clears them first
obs_client.OBS_CONFIG = Path(tempfile.mkdtemp())
sentinel = obs_client.OBS_CONFIG / ".sentinel"; sentinel.mkdir(parents=True)
launched = []
windows.launch_outside = lambda args, **kw: launched.append(args)
real_running = obs_client.obs_running

left = sentinel / "run_6ef7c484"; left.write_text("")
obs_client.obs_running = lambda: True                      # never touch the file of an OBS that's running
obs_client.launch_obs(r"C:\obs\bin\64bit\obs64.exe")
assert left.exists()

obs_client.obs_running = lambda: False
obs_client.launch_obs(r"C:\obs\bin\64bit\obs64.exe")
assert not left.exists(), "a leftover from an unclean shutdown goes"
assert launched[-1] == [r"C:\obs\bin\64bit\obs64.exe", "--portable", "--multi", "--minimize-to-tray",
                        "--disable-shutdown-check"], launched[-1]
print("obs launch PASS")

# the player's own OBS runs too: only ours (told apart by where its .exe is) counts and is ever closed
obs_client.obs_running = real_running
runtime.IS_WINDOWS = True
obs_client.OBS_DIR = Path(r"C:\Users\p\AppData\Local\CaptureMenu\OBS")
obs_client.OBS_EXE = obs_client.OBS_DIR / "bin" / "64bit" / "obs64.exe"
paths = {111: r"C:\Program Files\obs-studio\bin\64bit\obs64.exe", 222: r"c:\users\p\appdata\local\capturemenu\obs\bin\64bit\OBS64.EXE",
         333: r"D:\Games\NotCaptureMenu\OBS\bin\64bit\obs64.exe"}
windows.process_path = lambda pid: paths.get(pid, "")
commands = []
def run_quiet(cmd, **kw):
    commands.append(cmd)
    class R: stdout = '"obs64.exe","111","Console","1","300,000 K"\r\n"obs64.exe","222","Console","1","250,000 K"\r\n"obs64.exe","333","Console","1","90,000 K"\r\n'
    return R()
obs_client.media.run_quiet = run_quiet
assert obs_client.obs_pids() == [222] and obs_client.obs_running()
commands.clear(); obs_client.close_obs()
assert commands[-1] == ["taskkill", "/PID", "222"] and not any("111" in c for c in commands), commands
commands.clear(); obs_client.close_obs(force=True)
assert commands[-1] == ["taskkill", "/F", "/PID", "222"], commands
del paths[222]
assert not obs_client.obs_running(), "the player's OBS alone isn't ours"
commands.clear(); obs_client.close_obs()
assert not any(c[0] == "taskkill" for c in commands), commands
print("only our OBS PASS")

# updating from 0.0.41: the player's own OBS still records our buffer; only that recording stops
appdata = Path(tempfile.mkdtemp()); os.environ["APPDATA"] = str(appdata)
ws = appdata / "obs-studio" / "plugin_config" / "obs-websocket"; ws.mkdir(parents=True)
(ws / "config.json").write_text('{"server_enabled": true, "server_port": 4455, "server_password": "x"}')
stopped, made = [], []
class Theirs:
    def __init__(self, cfg): made.append(cfg)
    def buffer_active(self): return True
    def stop_buffer(self): stopped.append(1)
real_obs, obs_client.Obs = obs_client.Obs, Theirs
obs_client.stop_old_buffer(4456)
assert stopped and made[-1]["obs_port"] == 4455, made
stopped.clear(); obs_client.stop_old_buffer(4455)          # same port as ours: that's ours, leave it
assert not stopped
obs_client.Obs = real_obs
print("old buffer stopped PASS")

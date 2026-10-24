"""Import, resource-layout and dependency checks for source and frozen packages."""
import ast
import importlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from PySide6 import QtCore, QtWidgets
from capturemenu import input_devices, preferences, runtime, version, windows

assert runtime.APP_DIR == root and runtime.ASSETS == root / "assets"
assert preferences.CONFIG_PATH == root / "config.json" and preferences.STATE_PATH == root / "state.json"
assert version.APP_VERSION == (root / "VERSION").read_text().strip().lstrip("v")
assert len((root / "capture_menu.py").read_text().splitlines()) <= 10
assert not (root / "capture_menu.log").exists()
assert input_devices._input_mode is None

modules = sorted(p.stem for p in (root / "capturemenu").glob("*.py") if p.stem != "__init__")
with patch("threading.Thread.start", side_effect=AssertionError("thread started during import")), \
     patch("subprocess.Popen", side_effect=AssertionError("process started during import")), \
     patch("logging.basicConfig", side_effect=AssertionError("logging configured during import")):
    for name in modules:
        importlib.import_module("capturemenu." + name)
    import capture_menu
assert QtWidgets.QApplication.instance() is None
assert input_devices._input_mode is None and not (root / "capture_menu.log").exists()
print("all modules import without starting threads, processes, logging or QApplication PASS")

graph = {}
for name in modules:
    tree = ast.parse((root / "capturemenu" / f"{name}.py").read_text(encoding="utf-8"))
    graph[name] = {alias.name for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 1
                   and node.module is None for alias in node.names}
def visit(name, trail=()):
    assert name not in trail, (trail, name)
    for dependency in graph[name]:
        visit(dependency, (*trail, name))
for name in modules:
    visit(name)
print("module dependency graph is acyclic PASS")

with patch.object(QtCore.QProcess, "startDetached", return_value=True) as start, \
     patch.object(QtWidgets.QApplication, "quit"):
    windows.restart_app()
    assert start.call_args.args[1][0] == str(root / "capture_menu.py")
    assert start.call_args.args[2] == str(root)
print("source restart targets the thin entry point PASS")

# Import fresh copies in a simulated installed layout; never build or launch an installer.
with tempfile.TemporaryDirectory() as folder:
    install = Path(folder)
    shutil.copytree(root / "capturemenu", install / "capturemenu", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(root / "capture_menu.py", install / "capture_menu.py")
    probe = r'''
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
if sys.argv[2] == "frozen":
    sys.frozen = True
    sys.executable = str(root / "CaptureMenu.exe")
    sys._MEIPASS = str(root / "_internal")
from capturemenu import runtime, preferences
import capture_menu
assert runtime.APP_DIR == root
assert runtime.BUNDLE_DIR == (root / "_internal" if sys.argv[2] == "frozen" else root)
assert runtime.ASSETS == runtime.BUNDLE_DIR / "assets"
assert preferences.CONFIG_PATH == root / "config.json"
assert preferences.STATE_PATH == root / "state.json"
assert not (root / "capture_menu.log").exists()
'''
    for mode in ("source", "frozen"):
        subprocess.run([sys.executable, "-B", "-c", probe, str(install), mode], check=True, timeout=30)
print("relocated source and frozen executable/resource paths PASS")

# Exercise composition in Arabic without registering hotkeys, touching OBS/startup settings,
# showing a tray icon, or entering the long-running desktop event loop.
from capturemenu import app as application, capture_controller, diagnostics

def inspect_app():
    app = QtWidgets.QApplication.instance()
    assert app.layoutDirection() == QtCore.Qt.RightToLeft
    pages = {w.property("captureMenuPage"): w for w in app.topLevelWidgets() if w.property("captureMenuPage")}
    assert set(pages) == {"menu", "viewer", "gallery", "settings"}, pages
    assert pages["menu"].gallery is pages["gallery"]
    assert pages["menu"].settings is pages["settings"]
    assert input_devices.input_mode() is input_devices.input_mode()
    return 0

cfg = dict(preferences.DEFAULTS, clips_dir=str(root / "StartupClips"), language="ar")
with patch.object(preferences, "load_config", return_value=cfg), \
     patch("threading.Thread.start"), \
     patch.object(diagnostics, "install_crash_log"), \
     patch.object(diagnostics, "watch_for_freezes", return_value=None), \
     patch.object(QtWidgets.QSystemTrayIcon, "show"), \
     patch.object(QtCore.QLockFile, "tryLock", return_value=True), \
     patch.object(input_devices.Gamepad, "start"), \
     patch.object(input_devices.Hotkey, "start", return_value=True), \
     patch.object(capture_controller.Controller, "startup"), \
     patch.object(capture_controller.Controller, "start_following"), \
     patch.object(QtWidgets.QApplication, "exec", side_effect=inspect_app):
    try:
        application.main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("main did not exit with the event loop's result")
print("startup composition and Arabic/RTL wiring PASS (OS integrations mocked)")

import runpy
with patch.object(application, "main") as launch:
    runpy.run_path(str(root / "capture_menu.py"), run_name="__main__")
    launch.assert_called_once()
print("thin entry point delegates to app.main PASS")

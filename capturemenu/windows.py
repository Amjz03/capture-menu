"""Windows display, process, window and startup integration."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from pathlib import Path
import ctypes
import os
import re
import subprocess
import sys
import tempfile

from . import language, preferences, runtime


# ---------------------------------------------------------------- which game is on screen

DESKTOP = "Desktop"


# Windows shell and system windows: captures taken over these go to "Desktop"
SHELL_EXES = {
    "explorer.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "searchhost.exe", "searchapp.exe", "applicationframehost.exe", "lockapp.exe",
    "textinputhost.exe", "python.exe", "pythonw.exe",
}


# Names an exe can report that say nothing about which game it is
GENERIC_NAMES = {
    "", "unreal engine", "unrealgame", "ue4", "ue5", "bootstrappackagedgame",
    "unity", "unity player", "game", "launcher", "client", "application",
    "microsoft® windows® operating system", "microsoft windows operating system",
}


RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


def safe_folder_name(name: str) -> str:
    name = re.sub(r"[™®©]", "", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")[:80].strip()
    if not name:
        return DESKTOP
    return name + "_" if name.upper() in RESERVED else name


def _exe_version_string(exe_path: str, field: str) -> str:
    """Reads ProductName / FileDescription from the exe's version info."""
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(exe_path, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(exe_path, 0, size, data):
        return ""
    ptr, n = ctypes.c_void_p(), ctypes.c_uint()
    langs = [(0x0409, 0x04B0)]
    if ver.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) \
            and n.value >= 4:
        pair = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint16 * 2)).contents
        langs.insert(0, (pair[0], pair[1]))
    for lang, codepage in langs:
        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{field}"
        if ver.VerQueryValueW(data, key, ctypes.byref(ptr), ctypes.byref(n)) and n.value:
            return ctypes.wstring_at(ptr, n.value).rstrip("\x00").strip()
    return ""


def foreground_app(cfg: dict) -> str:
    """Name of the game or app in the foreground, used as its folder name."""
    if not runtime.IS_WINDOWS:
        return DESKTOP
    try:
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = wintypes.HWND
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return DESKTOP
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe_path = ""
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if handle:
            buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                exe_path = buf.value
            kernel32.CloseHandle(handle)

        exe = Path(exe_path).name.lower()
        overrides = {k.lower(): v for k, v in cfg.get("game_names", {}).items()}
        if exe in overrides:
            return safe_folder_name(overrides[exe])
        if exe in SHELL_EXES or pid.value == os.getpid():
            return DESKTOP
        if exe_path:
            for field in ("ProductName", "FileDescription"):
                name = _exe_version_string(exe_path, field)
                if re.sub(r"[™®©]", "", name).strip().lower() not in GENERIC_NAMES:
                    return safe_folder_name(name)
        if title.value.strip():
            return safe_folder_name(title.value)
        return safe_folder_name(Path(exe_path).stem) if exe_path else DESKTOP
    except Exception:
        runtime.log.exception("could not detect the foreground app")
        return DESKTOP


# ---------------------------------------------------------------- which screen the game is on

if runtime.IS_WINDOWS:
    from ctypes import wintypes

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", ctypes.c_wchar * 32)]


def foreground_screen() -> dict | None:
    """The monitor showing the foreground window, and whether that window fills it
    (a game in fullscreen or borderless). None when it can't be told (not Windows)."""
    if not runtime.IS_WINDOWS:
        return None
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFOEXW)]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
            return None
        win, mon = wintypes.RECT(), info.rcMonitor
        user32.GetWindowRect(hwnd, ctypes.byref(win))
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        covers = (win.left <= mon.left and win.top <= mon.top
                  and win.right >= mon.right and win.bottom >= mon.bottom)
        return {"device": info.szDevice, "rect": (mon.left, mon.top, mon.right, mon.bottom),
                "fullscreen": covers and cls.value not in ("Progman", "WorkerW"),
                "own": pid.value == os.getpid()}
    except Exception:
        runtime.log.exception("could not read the foreground monitor")
        return None


def screen_for(info: dict | None) -> QtGui.QScreen:
    """The Qt screen matching a foreground_screen() result; falls back to the cursor's screen."""
    if info:
        screens = QtGui.QGuiApplication.screens()
        for s in screens:
            if s.name() == info["device"]:
                return s
        for s in screens:   # Qt keeps each screen's native top-left corner
            if (s.geometry().left(), s.geometry().top()) == info["rect"][:2]:
                return s
    return QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos()) or QtGui.QGuiApplication.primaryScreen()


def screen_id(s: QtGui.QScreen) -> str:
    """A screen's lasting name for config.json: its model and serial number (Windows' DISPLAY1, 2…
    can swap after a restart or a new cable)."""
    return f"{s.model() or s.name()}#{s.serialNumber() or s.name()}"


def screen_px_rect(s: QtGui.QScreen) -> tuple[int, int, int, int]:
    """The screen on Windows' desktop in real pixels, like foreground_screen()'s rect (Qt keeps
    the native top-left corner, but its size is scaled down by Windows' display scale)."""
    g, dpr = s.geometry(), s.devicePixelRatio()
    return g.left(), g.top(), g.left() + round(g.width() * dpr), g.top() + round(g.height() * dpr)


def screen_label(s: QtGui.QScreen) -> str:
    left, top, right, bottom = screen_px_rect(s)
    screens = QtGui.QGuiApplication.screens()
    name = s.model() or language.tr("Screen {n}", n=screens.index(s) + 1 if s in screens else 1)
    if s is QtGui.QGuiApplication.primaryScreen():
        return language.tr("{name} · {w}×{h} · main", name=name, w=right - left, h=bottom - top)
    return f"{name} · {right - left}×{bottom - top}"


def chosen_screen(choice: str) -> QtGui.QScreen | None:
    """The screen picked in Settings → Recording screen; None to follow the game (also when the
    picked screen isn't connected right now)."""
    if choice in ("", "follow"):
        return None
    if choice == "main":
        return QtGui.QGuiApplication.primaryScreen()
    screens = QtGui.QGuiApplication.screens()
    exact = [s for s in screens if screen_id(s) == choice]
    if exact:
        return exact[0]
    model = choice.split("#")[0]    # same screen on another cable or port: its model still matches
    same = [s for s in screens if (s.model() or s.name()) == model]
    return same[0] if len(same) == 1 else None


def game_screen() -> QtGui.QScreen:
    return screen_for(foreground_screen())


_ui_screen: QtGui.QScreen | None = None


def ui_screen(fresh: bool = False) -> QtGui.QScreen:
    """The screen Capture Menu's pages open on. It's picked (the game's screen) when the app is opened
    from outside: the Create button, the hotkey, the tray, a notice. Every page reached from there
    (Settings, the gallery, the viewer, and Back) stays on it. Picking it again on each page followed
    whatever window was in front once the last page had closed, often one on another monitor."""
    global _ui_screen
    if fresh or _ui_screen is None or _ui_screen not in QtGui.QGuiApplication.screens():
        _ui_screen = game_screen()
    return _ui_screen


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class _PathInfo(ctypes.Structure):     # DISPLAYCONFIG_PATH_INFO, flattened
    _fields_ = [("src_adapter", _LUID), ("src_id", ctypes.c_uint32), ("src_mode", ctypes.c_uint32),
                ("src_flags", ctypes.c_uint32), ("tgt_adapter", _LUID), ("tgt_id", ctypes.c_uint32),
                ("tgt_mode", ctypes.c_uint32), ("tech", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                ("scaling", ctypes.c_uint32), ("refresh_num", ctypes.c_uint32), ("refresh_den", ctypes.c_uint32),
                ("scanline", ctypes.c_uint32), ("available", ctypes.c_int32), ("tgt_flags", ctypes.c_uint32),
                ("flags", ctypes.c_uint32)]


class _DeviceInfoHeader(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapter", _LUID), ("id", ctypes.c_uint32)]


class _SourceName(ctypes.Structure):
    _fields_ = [("header", _DeviceInfoHeader), ("name", ctypes.c_wchar * 32)]


class _AdvancedColor(ctypes.Structure):       # ..._GET_ADVANCED_COLOR_INFO (and _2 on Windows 11 24H2)
    _fields_ = [("header", _DeviceInfoHeader), ("value", ctypes.c_uint32), ("encoding", ctypes.c_uint32),
                ("bits", ctypes.c_uint32), ("mode", ctypes.c_uint32)]


class _SdrWhite(ctypes.Structure):           # DISPLAYCONFIG_SDR_WHITE_LEVEL
    _fields_ = [("header", _DeviceInfoHeader), ("level", ctypes.c_uint32)]


def _screen_paths() -> list[tuple[str, _PathInfo]]:
    """(device name, display path) for each active screen."""
    user32 = ctypes.windll.user32
    n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
    if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(n_paths), ctypes.byref(n_modes)):  # active paths
        return []
    paths = (_PathInfo * n_paths.value)()
    modes = (ctypes.c_byte * (64 * n_modes.value))()
    if user32.QueryDisplayConfig(2, ctypes.byref(n_paths), paths, ctypes.byref(n_modes), modes, None):
        return []
    found = []
    for path in paths[:n_paths.value]:
        src = _SourceName()
        src.header.type, src.header.size = 1, ctypes.sizeof(src)       # GET_SOURCE_NAME
        src.header.adapter, src.header.id = path.src_adapter, path.src_id
        if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(src)):
            found.append((src.name, path))
    return found


def sdr_white(device: str | None = None) -> int | None:
    """Windows' "SDR content brightness" on an HDR screen (the main screen when not given), in nits.
    OBS turns HDR screens into normal colours with its own white level (300 nits): when Windows'
    is lower, whites come out grey and the whole picture looks washed out."""
    if not runtime.IS_WINDOWS:
        return None
    try:
        device = device or main_screen_device()
        for name, path in _screen_paths():
            if name != device:
                continue
            white = _SdrWhite()
            white.header.type, white.header.size = 11, ctypes.sizeof(white)  # GET_SDR_WHITE_LEVEL
            white.header.adapter, white.header.id = path.tgt_adapter, path.tgt_id
            if not ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(white)) and white.level:
                return round(white.level * 80 / 1000)                       # 1000 = 80 nits
    except Exception:
        runtime.log.exception("could not read the SDR white level")
    return None


def hdr_screens() -> dict[str, bool]:
    """Windows HDR on or off for each screen, by its device name (DISPLAY1 and so on). Empty where it
    can't be told. Windows 11 24H2 says it directly; before that, "advanced colour" on means HDR."""
    if not runtime.IS_WINDOWS:
        return {}
    try:
        user32 = ctypes.windll.user32
        found = {}
        for name, path in _screen_paths():
            color = _AdvancedColor()
            color.header.type, color.header.size = 15, ctypes.sizeof(color)    # GET_ADVANCED_COLOR_INFO_2
            color.header.adapter, color.header.id = path.tgt_adapter, path.tgt_id
            if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(color)):
                found[name] = color.mode == 2                                   # ADVANCED_COLOR_MODE_HDR
                continue
            color.header.type, color.header.size = 9, ctypes.sizeof(color) - 4  # GET_ADVANCED_COLOR_INFO
            if not user32.DisplayConfigGetDeviceInfo(ctypes.byref(color)):
                found[name] = bool(color.value & 0b10)                          # advancedColorEnabled
        return found
    except Exception:
        runtime.log.exception("could not read the HDR state")
        return {}


def main_screen_device() -> str | None:
    """Windows' name for the main screen (the one at 0,0), like the keys of hdr_screens()."""
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = wintypes.HANDLE
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFOEXW)]
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(user32.MonitorFromPoint(wintypes.POINT(0, 0), 1), ctypes.byref(info)):
            return info.szDevice
    except Exception:
        runtime.log.exception("could not find the main screen")
    return None


def windows_hdr(device: str | None = None) -> bool:
    """Is Windows HDR on for this screen (the main screen when not given)?"""
    screens = hdr_screens()
    device = device or (main_screen_device() if runtime.IS_WINDOWS else None)
    if device in screens:
        return screens[device]
    return len(screens) == 1 and any(screens.values())


def pick_monitor_item(items: list[dict], rect: tuple[int, int, int, int]) -> dict | None:
    """OBS lists monitors like "LG ULTRAGEAR: 2560x1440 @ 0,0 (Primary Monitor)".
    Finds the one at the same desktop position as rect (then by size if positions differ)."""
    by_size = []
    for item in items:
        m = re.search(r"(\d+)x(\d+) @ (-?\d+),(-?\d+)", item.get("itemName", ""))
        if not m:
            continue
        w, h, x, y = map(int, m.groups())
        if (x, y) == rect[:2]:
            return item
        if (w, h) == (rect[2] - rect[0], rect[3] - rect[1]):
            by_size.append(item)
    return by_size[0] if len(by_size) == 1 else None


def launch_outside(cmd: list[str] | str, cwd: str | None = None, flags: int = 0) -> subprocess.Popen:
    """Starts a program that isn't ours (OBS, Explorer, the update installer) without handing it Capture
    Menu's own DLL folder. The .exe build puts _internal on the DLL search path, ahead of System32, and a
    child process inherits that: OBS then loaded _internal\\VCRUNTIME140.dll and held it open, so the next
    update couldn't replace it."""
    if not (runtime.IS_WINDOWS and runtime.FROZEN):
        return subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
    k32 = ctypes.windll.kernel32
    buf = ctypes.create_unicode_buffer(1024)
    ours = buf.value if k32.GetDllDirectoryW(1024, buf) else None
    bundle = os.path.normcase(str(runtime.BUNDLE_DIR))
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if p and not os.path.normcase(p).startswith(bundle))
    k32.SetDllDirectoryW(None)        # the child gets Windows' normal search order
    try:
        return subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags)
    finally:
        k32.SetDllDirectoryW(ours)    # and we keep ours


# ---------------------------------------------------------------- settings

# Starting with Windows: a Task Scheduler task that runs the moment you sign in. The Startup folder
# and the registry Run list both wait half a minute or more, one app at a time, and Windows sometimes
# skips entries in them. The Run entry stays as a backup; a second copy quietly does nothing.
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


RUN_NAME = "Capture Menu"


def logon_task_name() -> str:
    """One task per Windows user (task names are shared by everyone on the PC)."""
    return f"Capture Menu ({os.environ.get('USERNAME', 'user')})"


def set_logon_task(on: bool):
    """Adds or removes the sign-in task. Returns quietly if Task Scheduler refuses."""
    name = logon_task_name()
    if not on:
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True,
                       creationflags=0x08000000)
        return
    from xml.sax.saxutils import escape
    user = escape(f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\"))
    exe, args = ((sys.executable, "") if runtime.FROZEN else
                 (str(Path(sys.executable).with_name("pythonw.exe")), f'"{runtime.APP_DIR / "capture_menu.py"}"'))
    # no time limit (the default stops a task after 3 days), runs on battery, normal priority (not 7)
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Starts Capture Menu when you sign in</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>5</Priority></Settings>
  <Actions Context="Author"><Exec><Command>{escape(exe)}</Command><Arguments>{escape(args)}</Arguments>
    <WorkingDirectory>{escape(str(runtime.APP_DIR))}</WorkingDirectory></Exec></Actions>
</Task>"""
    file = Path(tempfile.gettempdir()) / "capture-menu-task.xml"
    try:
        file.write_text(xml, encoding="utf-16")
        done = subprocess.run(["schtasks", "/Create", "/TN", name, "/XML", str(file), "/F"],
                              capture_output=True, creationflags=0x08000000)
        if done.returncode:
            runtime.log.warning("couldn't add the sign-in task: %s", done.stderr.decode(errors="replace").strip())
    finally:
        file.unlink(missing_ok=True)


def startup_shortcut() -> Path:
    """Where versions up to 0.0.8 started from; only removed now."""
    return (Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / "Capture Menu.lnk")


def start_command() -> str:
    if runtime.FROZEN:
        return f'"{sys.executable}"'
    return f'"{Path(sys.executable).with_name("pythonw.exe")}" "{runtime.APP_DIR / "capture_menu.py"}"'


def starts_with_windows() -> bool:
    if not runtime.IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except OSError:
        return startup_shortcut().exists()


def set_start_with_windows(on: bool):
    """Adds or removes the sign-in task and the Run entry (and the old Startup shortcut either way)."""
    if not runtime.IS_WINDOWS:
        return
    import winreg
    startup_shortcut().unlink(missing_ok=True)
    set_logon_task(on)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, start_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        runtime.log.exception("couldn't change start with Windows")


def update_start_with_windows():
    """At start: moves older setups (a Startup shortcut, a Run entry alone) to the sign-in task,
    and keeps the path current."""
    # only the installed CaptureMenu.exe: a copy run from source (a test, a developer) must not point
    # Windows at itself. The Python version gets this from Setup.cmd, which updates run again.
    if runtime.IS_WINDOWS and runtime.FROZEN and starts_with_windows():
        # another copy that still exists keeps it: running a copy from Downloads or a test build must
        # not point Windows at a file that may be deleted later
        other = registered_command().split('"')[1:2]
        if other and Path(other[0]) != Path(sys.executable) and Path(other[0]).exists():
            return
        set_start_with_windows(True)


def registered_command() -> str:
    """The Run entry's command line ("" when there is none)."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, RUN_NAME)[0])
    except OSError:
        return ""


def restart_app():
    """Starts a fresh copy (it picks up config.json) and quits this one."""
    args = sys.argv[1:] if runtime.FROZEN else [str(runtime.APP_DIR / "capture_menu.py"), *sys.argv[1:]]
    args = [a for a in args if a != "--restarted"] + ["--restarted"]
    QtCore.QProcess.startDetached(sys.executable, args, str(runtime.APP_DIR))
    QtWidgets.QApplication.quit()


def promote_tray_icon():
    """Windows 11 hides new tray icons behind the ^ arrow. Show ours next to the clock, once:
    if the player hides it again later, that choice is kept."""
    if not runtime.IS_WINDOWS or preferences.load_state().get("tray_promoted"):
        return
    import winreg
    exe = Path(sys.executable).name.lower()
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings")
    except OSError:
        return   # Windows 10: icons are shown with Settings → Taskbar instead
    found = False
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            name = winreg.EnumKey(root, i)
            try:
                with winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                    path = str(winreg.QueryValueEx(key, "ExecutablePath")[0]).lower()
                    if path.endswith("\\" + exe) or path.endswith("/" + exe):
                        winreg.SetValueEx(key, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        found = True
            except OSError:
                continue
    if found:
        state = preferences.load_state()
        state["tray_promoted"] = True
        preferences.save_state(state)

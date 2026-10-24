"""Global hotkey, gamepad navigation, input hints and sounds."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_menu import Menu
    from .ui_viewer import Viewer
    from .ui_gallery import Gallery
    from .ui_settings import Settings

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
import ctypes
import threading
import time

from . import runtime, windows


# ---------------------------------------------------------------- global hotkey

class Hotkey(QtCore.QObject):
    pressed = QtCore.Signal(str)   # name of the game that was in the foreground

    MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
    NAMED = {"space": 0x20, "tab": 0x09, "pause": 0x13, "insert": 0x2D, "home": 0x24,
             "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "printscreen": 0x2C}

    def __init__(self, spec: str, detect_game):
        super().__init__()
        self.spec = spec
        self.detect_game = detect_game

    def _parse(self) -> tuple[int, int]:
        mods, vk = 0x4000, 0  # MOD_NOREPEAT
        for part in self.spec.lower().replace(" ", "").split("+"):
            if part in self.MODS:
                mods |= self.MODS[part]
            elif part in self.NAMED:
                vk = self.NAMED[part]
            elif len(part) >= 2 and part[0] == "f" and part[1:].isdigit():
                vk = 0x6F + int(part[1:])
            elif len(part) == 1 and part.isalnum():
                vk = ord(part.upper())
        if not vk:
            raise ValueError(f"Unrecognised hotkey: {self.spec}")
        return mods, vk

    def start(self) -> bool:
        if not runtime.IS_WINDOWS:
            return False
        from ctypes import wintypes
        mods, vk = self._parse()
        ready, ok = threading.Event(), [False]

        def loop():
            user32 = ctypes.windll.user32
            ok[0] = bool(user32.RegisterHotKey(None, 1, mods, vk))
            ready.set()
            if not ok[0]:
                return
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    self.pressed.emit(self.detect_game())

        threading.Thread(target=loop, daemon=True).start()
        ready.wait(3)
        return ok[0]


# ---------------------------------------------------------------- game controller

# SDL GameController button numbers. SDL reads the DualSense, Xbox and most other pads
# with one layout, so "a" is Cross on a DualSense and A on an Xbox controller.
PAD_BUTTONS = {
    "a": 0, "cross": 0, "b": 1, "circle": 1, "x": 2, "square": 2, "y": 3, "triangle": 3,
    "create": 4, "back": 4, "view": 4, "select": 4, "ps": 5, "guide": 5, "xbox": 5,
    "options": 6, "start": 6, "menu": 6, "l3": 7, "r3": 8, "l1": 9, "lb": 9, "r1": 10, "rb": 10,
    "up": 11, "down": 12, "left": 13, "right": 14,
    "share": 15, "mute": 15, "mic": 15, "touchpad": 20,
}


A, B, X, Y, L1, R1, UP, DOWN, LEFT, RIGHT = 0, 1, 2, 3, 9, 10, 11, 12, 13, 14


DIRECTIONS = {UP, DOWN, LEFT, RIGHT}


def parse_pad_combo(spec: str) -> frozenset[int]:
    """'create' or 'l1+r1' -> the set of SDL button numbers."""
    combo = set()
    for part in spec.lower().replace(" ", "").split("+"):
        if part not in PAD_BUTTONS:
            raise ValueError(f"Unknown controller button: {part}")
        combo.add(PAD_BUTTONS[part])
    return frozenset(combo)


class PadState:
    """Turns raw "buttons held now" snapshots into presses: edge detection,
    an optional hold time for the open button, and key-repeat for directions."""

    REPEAT_DELAY, REPEAT_EVERY = 0.35, 0.11

    def __init__(self, combo: frozenset[int], hold_ms: int):
        self.combo, self.hold = combo, hold_ms / 1000
        self.prev: set[int] = set()
        self.combo_since: float | None = None
        self.combo_fired = False
        self.next_repeat: dict[int, float] = {}

    def step(self, held: set[int], now: float) -> tuple[bool, list[int]]:
        """Returns (open button triggered, buttons pressed this step)."""
        triggered = False
        if self.combo <= held:
            if self.combo_since is None:
                self.combo_since, self.combo_fired = now, False
            if not self.combo_fired and now - self.combo_since >= self.hold:
                triggered = self.combo_fired = True
        else:
            self.combo_since = None
        presses = []
        for b in sorted(held - self.prev):
            if b not in self.combo:
                presses.append(b)
                if b in DIRECTIONS:
                    self.next_repeat[b] = now + self.REPEAT_DELAY
        for b in list(self.next_repeat):
            if b not in held:
                del self.next_repeat[b]
            elif now >= self.next_repeat[b]:
                presses.append(b)
                self.next_repeat[b] = now + self.REPEAT_EVERY
        self.prev = set(held)
        return triggered, presses


class Gamepad(QtCore.QObject):
    """Reads every connected controller in the background, even while a game has focus."""

    activated = QtCore.Signal()
    pressed = QtCore.Signal(int)
    used = QtCore.Signal(str)        # "playstation" or "xbox": the pad that was just pressed
    connected = QtCore.Signal(str, bool)   # controller name, connected (False: it went away)

    STICK = 20000   # left stick acts as a d-pad past this deflection

    RUMBLES = {"capture": (0x3000, 0x7000, 120), "record": (0x6000, 0x2000, 220)}

    def __init__(self, cfg: dict):
        super().__init__()
        self.state = PadState(parse_pad_combo(cfg["controller_button"]),
                              int(cfg["controller_hold_ms"]))
        self._rumble: tuple[int, int, int] | None = None

    def rumble(self, kind: str = "capture"):
        """Asks the reader thread for a short buzz (SDL calls must stay on that thread)."""
        self._rumble = self.RUMBLES.get(kind, self.RUMBLES["capture"])

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import sdl2
        except Exception:
            runtime.log.warning("controller support off: pysdl2 isn't installed")
            return
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_HIDAPI_PS5_PLAYER_LED, b"0")  # leave the lights alone
        # Windows.Gaming.Input and RawInput need window messages handled on this thread, which never
        # happens here; with them on, closing a video in the viewer could hang forever (the player waits
        # on the audio device). HIDAPI still reads PlayStation pads and XInput the Xbox ones.
        sdl2.SDL_SetHint(b"SDL_JOYSTICK_WGI", b"0")
        sdl2.SDL_SetHint(b"SDL_JOYSTICK_RAWINPUT", b"0")
        if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER) != 0:
            runtime.log.warning("controller support off: %s", sdl2.SDL_GetError())
            return
        runtime.log.info("controller support on, waiting for a controller")
        pads, kinds, last, names = {}, {}, {}, {}
        busy_until = 0.0
        playstation = {sdl2.SDL_CONTROLLER_TYPE_PS3, sdl2.SDL_CONTROLLER_TYPE_PS4,
                       sdl2.SDL_CONTROLLER_TYPE_PS5}
        event = sdl2.SDL_Event()
        while True:
            while sdl2.SDL_PollEvent(ctypes.byref(event)):
                if event.type == sdl2.SDL_CONTROLLERDEVICEADDED:
                    pad = sdl2.SDL_GameControllerOpen(event.cdevice.which)
                    if pad:
                        jid = sdl2.SDL_JoystickInstanceID(sdl2.SDL_GameControllerGetJoystick(pad))
                        pads[jid] = pad
                        kinds[jid] = ("playstation" if sdl2.SDL_GameControllerGetType(pad) in playstation
                                      else "xbox")
                        name = (sdl2.SDL_GameControllerName(pad) or b"Controller").decode(errors="replace")
                        names[jid] = name
                        runtime.log.info("controller connected: %s", name)
                        self.connected.emit(name, True)
                elif event.type == sdl2.SDL_CONTROLLERDEVICEREMOVED:
                    pad = pads.pop(event.cdevice.which, None)
                    if pad:
                        sdl2.SDL_GameControllerClose(pad)
                        name = names.pop(event.cdevice.which, "Controller")
                        runtime.log.info("controller disconnected: %s", name)
                        self.connected.emit(name, False)
            held, fresh_kind = set(), None
            for jid, pad in pads.items():
                mine = {b for b in range(21) if sdl2.SDL_GameControllerGetButton(pad, b)}
                x = sdl2.SDL_GameControllerGetAxis(pad, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
                y = sdl2.SDL_GameControllerGetAxis(pad, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
                if abs(x) > self.STICK and abs(x) > abs(y):
                    mine.add(RIGHT if x > 0 else LEFT)
                elif abs(y) > self.STICK:
                    mine.add(DOWN if y > 0 else UP)
                if mine - last.get(jid, set()):
                    fresh_kind = kinds.get(jid, "xbox")
                last[jid] = mine
                held |= mine
            if fresh_kind:
                self.used.emit(fresh_kind)
            triggered, presses = self.state.step(held, time.monotonic())
            if triggered:
                self.activated.emit()
            for b in presses:
                self.pressed.emit(b)
            if self._rumble is not None:
                low, high, ms = self._rumble
                self._rumble = None
                for pad in pads.values():
                    sdl2.SDL_GameControllerRumble(pad, low, high, ms)
            now = time.monotonic()
            if held or presses or triggered:
                busy_until = now + 3
            # 60 Hz while in use; 30 Hz when idle still catches the quickest tap (~60 ms);
            # with no controller plugged in, only watch for one being connected
            time.sleep(1 / 60 if now < busy_until else 1 / 30 if pads else 0.25)


def pad_key(button: int, menu: "Menu", viewer: "Viewer", gallery: "Gallery | None" = None,
            settings: "Settings | None" = None) -> int | None:
    """Which key a controller button stands for in whatever is on screen."""
    OPTIONS = 6
    if settings is not None and settings.isVisible():
        return {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down, LEFT: Qt.Key_Left,
                RIGHT: Qt.Key_Right, Y: Qt.Key_S, X: Qt.Key_R}.get(button)
    if viewer.isVisible():
        if viewer.editing:          # typing needs the keyboard; the pad can only cancel
            return {B: Qt.Key_Escape}.get(button)
        if viewer.sounding:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down,
                    LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right, X: Qt.Key_P, Y: Qt.Key_M}
        elif viewer.sharing:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right}
        elif viewer.trimming:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right,
                    X: Qt.Key_I, Y: Qt.Key_O, L1: Qt.Key_P, R1: Qt.Key_P}
        else:
            keys = {A: Qt.Key_Return, B: Qt.Key_Escape, LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right,
                    UP: Qt.Key_Up, DOWN: Qt.Key_Down, L1: Qt.Key_A, R1: Qt.Key_D, X: Qt.Key_T, Y: Qt.Key_M,
                    OPTIONS: Qt.Key_E, 7: Qt.Key_V}   # 7 = L3: Sound, Y: the small buttons
        return keys.get(button)
    if gallery is not None and gallery.isVisible():
        keys = {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down,
                LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right, L1: Qt.Key_BracketLeft,
                R1: Qt.Key_BracketRight, Y: Qt.Key_F, X: Qt.Key_Space, OPTIONS: Qt.Key_Delete,
                7: Qt.Key_S}
        return keys.get(button)
    if menu.isVisible():
        keys = {A: Qt.Key_Return, B: Qt.Key_Escape, UP: Qt.Key_Up, DOWN: Qt.Key_Down,
                LEFT: Qt.Key_Left, RIGHT: Qt.Key_Right, X: Qt.Key_S, Y: Qt.Key_V, R1: Qt.Key_T}
        return keys.get(button)
    return None


class InputMode(QtCore.QObject):
    """What the player is using right now, so on-screen hints show the right buttons."""

    changed = QtCore.Signal(str)    # "keyboard", "playstation" or "xbox"

    def __init__(self):
        super().__init__()
        self.mode = "keyboard"
        self.synthetic = False      # key events we send on behalf of the controller

    def set(self, mode: str):
        if mode != self.mode:
            self.mode = mode
            self.changed.emit(mode)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress and not self.synthetic:
            self.set("keyboard")
        return False


_input_mode = None


def input_mode() -> InputMode:
    """Create the shared event filter on the UI thread when the interface first needs it."""
    global _input_mode
    if _input_mode is None:
        _input_mode = InputMode()
    return _input_mode


PAD_NAMES = {
    "playstation": {0: "✕", 1: "◯", 2: "▢", 3: "△", 4: "Create", 5: "PS", 6: "Options", 7: "L3",
                    8: "R3", 9: "L1", 10: "R1", 11: "↑", 12: "↓", 13: "←", 14: "→", 15: "Mute",
                    20: "Touchpad"},
    "xbox": {0: "A", 1: "B", 2: "X", 3: "Y", 4: "View", 5: "Xbox", 6: "Menu", 7: "LS", 8: "RS",
             9: "LB", 10: "RB", 11: "↑", 12: "↓", 13: "←", 14: "→", 15: "Share", 20: "Touchpad"},
}


def pad_combo_name(spec: str, kind: str) -> str:
    try:
        combo = parse_pad_combo(spec)
    except ValueError:
        return spec
    return " + ".join(PAD_NAMES[kind].get(b, str(b)) for b in sorted(combo))


def send_key(window: QtWidgets.QWidget, key: int):
    focus = QtWidgets.QApplication.focusWidget()
    target = focus if focus is not None and focus.window() is window else window
    input_mode().synthetic = True
    try:
        QtWidgets.QApplication.sendEvent(
            target, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, Qt.NoModifier))
    finally:
        input_mode().synthetic = False


class PressSequencer(QtCore.QObject):
    """One press opens the bar; two quick presses save the last N seconds right away,
    like the PS5's easy-clip shortcut. The single press waits `window_ms` to be sure."""

    def __init__(self, window_ms: int, on_single, on_double, is_open):
        super().__init__()
        self.on_single, self.on_double, self.is_open = on_single, on_double, is_open
        self.window_ms = window_ms
        self.game = windows.DESKTOP
        self.timer = QtCore.QTimer(self, singleShot=True, interval=max(1, window_ms),
                                   timeout=lambda: self.on_single(self.game))

    def press(self, game: str):
        if self.is_open() or self.window_ms <= 0:
            self.timer.stop()
            self.on_single(game)          # closing never waits
        elif self.timer.isActive():
            self.timer.stop()
            self.on_double(self.game)
        else:
            self.game = game              # the game on screen at the first press
            self.timer.start()


class Sounds:
    """Short cues when something is saved (assets/sounds, replaceable with your own .wav)."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.effects = {}

    def play(self, name: str):
        path = runtime.ASSETS / "sounds" / f"{name}.wav"
        if not self.enabled or not path.exists():
            return
        if runtime.IS_WINDOWS:   # Windows plays a .wav itself: no audio stack kept loaded in this app
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        if name not in self.effects:
            if not runtime.load_multimedia():
                return
            fx = runtime.QtMultimedia.QSoundEffect()
            fx.setSource(QtCore.QUrl.fromLocalFile(str(path)))
            fx.setVolume(0.55)
            self.effects[name] = fx
        self.effects[name].play()


def hotkey_from_event(e: QtGui.QKeyEvent) -> str | None:
    """A key press -> "ctrl+shift+f9" style text for config.json, or None for a lone modifier."""
    names = {Qt.Key_Space: "space", Qt.Key_Tab: "tab", Qt.Key_Pause: "pause", Qt.Key_Insert: "insert",
             Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "pageup",
             Qt.Key_PageDown: "pagedown", Qt.Key_Print: "printscreen"}
    k = e.key()
    if Qt.Key_F1 <= k <= Qt.Key_F24:
        key = f"f{k - Qt.Key_F1 + 1}"
    elif k in names:
        key = names[k]
    elif Qt.Key_A <= k <= Qt.Key_Z or Qt.Key_0 <= k <= Qt.Key_9:
        key = chr(k).lower()
    else:
        return None
    mods = [n for flag, n in ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
                              (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "win")) if e.modifiers() & flag]
    if not mods and not key.startswith("f"):
        return None     # a bare letter would fire while typing in chat
    return "+".join(mods + [key])

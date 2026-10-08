"""Global hotkeys that report both press and release, so a key can be held to talk (ADR 0017).

    combos     "<ctrl>+<alt>+v" text (pynput's spelling) <-> Combo, and a readable label
    ChordTracker  pure: feed it key downs and ups, it says when a combo starts and ends
    backends   CarbonBackend (macOS: RegisterEventHotKey, no Accessibility permission needed)
               PynputBackend (Windows, X11: a keyboard listener feeding a ChordTracker)

Callbacks may run on any thread; the controller only emits Qt signals from them.
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

MODIFIERS = ("ctrl", "alt", "shift", "cmd")
NAMED_KEYS = (
    "space", "enter", "tab", "esc", "backspace", "delete", "up", "down", "left", "right",
    "home", "end", "page_up", "page_down", *(f"f{i}" for i in range(1, 13)),
)  # fmt: skip
_ALIASES = {"control": "ctrl", "option": "alt", "opt": "alt", "command": "cmd", "super": "cmd", "win": "cmd",
            "return": "enter", "escape": "esc", "spacebar": "space"}  # fmt: skip


@dataclass(frozen=True)
class Combo:
    mods: frozenset[str]
    key: str

    @property
    def keys(self) -> frozenset[str]:
        return self.mods | {self.key}


def parse_combo(text: str) -> Combo:
    """'<ctrl>+<alt>+v' (or 'Ctrl+Alt+V') -> Combo. Raises ValueError on anything unusable."""
    parts = [p.strip().strip("<>").lower() for p in text.split("+") if p.strip()]
    parts = [_ALIASES.get(p, p) for p in parts]
    mods = frozenset(p for p in parts if p in MODIFIERS)
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        raise ValueError(f"'{text}' needs exactly one key besides the modifiers")
    key = keys[0]
    if not (key in NAMED_KEYS or (len(key) == 1 and key.isascii() and key.isprintable())):
        raise ValueError(f"'{text}': unknown key '{key}'")
    if not mods:
        raise ValueError(f"'{text}' needs at least one modifier, or it would fire while you type")
    return Combo(mods, key)


def format_combo(combo: Combo | str) -> str:
    """A label for people: 'Ctrl+Alt+Space' (macOS: 'Ctrl+Option+Space')."""
    if isinstance(combo, str):
        try:
            combo = parse_combo(combo)
        except ValueError:
            return combo
    mac = sys.platform == "darwin"
    names = {"alt": "Option" if mac else "Alt", "cmd": "Cmd" if mac else "Win"}
    mods = [names.get(m, m.capitalize()) for m in MODIFIERS if m in combo.mods]
    key = combo.key.upper() if len(combo.key) == 1 else combo.key.replace("_", " ").title().replace(" ", "")
    return "+".join([*mods, key])


def to_text(combo: Combo) -> str:
    """Back to the stored spelling: '<ctrl>+<alt>+v'."""
    mods = [f"<{m}>" for m in MODIFIERS if m in combo.mods]
    key = f"<{combo.key}>" if len(combo.key) > 1 else combo.key
    return "+".join([*mods, key])


# the pure part ---------------------------------------------------------------------------------


Callback = Callable[[], None]


class ChordTracker:
    """Turns a stream of key downs and ups into combo presses and releases.

    A combo is pressed when its last key goes down with exactly its keys held (extra modifiers
    don't match, so Ctrl+Shift+Alt+V is not Ctrl+Alt+V), and released when any of its keys goes up.
    Key repeat (more downs without an up) does not press it again.
    """

    def __init__(self) -> None:
        self.down: set[str] = set()
        self._bindings: list[tuple[Combo, Callback, Callback | None]] = []
        self._active: set[Combo] = set()

    def bind(self, combo: Combo, on_press: Callback, on_release: Callback | None = None) -> None:
        self._bindings.append((combo, on_press, on_release))

    def key_down(self, key: str) -> None:
        if key in self.down:
            return  # auto-repeat
        self.down.add(key)
        for combo, on_press, _ in self._bindings:
            if combo not in self._active and key in combo.keys and self.down == set(combo.keys):
                self._active.add(combo)
                on_press()

    def key_up(self, key: str) -> None:
        self.down.discard(key)
        for combo, _, on_release in self._bindings:
            if combo in self._active and key in combo.keys:
                self._active.discard(combo)
                if on_release is not None:
                    on_release()


# pynput (Windows, X11) -------------------------------------------------------------------------


def pynput_name(key) -> str | None:
    """A pynput Key or KeyCode -> our key name, or None for keys we never bind."""
    name = getattr(key, "name", None)
    if name is not None:  # a special Key
        for m in MODIFIERS:
            if name == m or name.startswith(m + "_"):  # ctrl_l, alt_gr, cmd_r...
                return m
        return name if name in NAMED_KEYS else None
    char, vk = getattr(key, "char", None), getattr(key, "vk", None)
    if char and len(char) == 1 and char.isascii() and char.isprintable():
        return char.lower()
    # With Ctrl held, Windows reports a control character (Ctrl+V is '\x16'); the virtual key is
    # still the letter. On X11 vk is the keysym, which for ASCII is the character code too.
    if isinstance(vk, int) and 0x20 < vk < 0x7F:
        return chr(vk).lower()
    return None


class PynputBackend:
    def __init__(self, keyboard=None) -> None:
        if keyboard is None:
            from pynput import keyboard
        self._keyboard = keyboard
        self.tracker = ChordTracker()
        self._listener = None

    def register(self, combo: Combo, on_press: Callback, on_release: Callback | None = None) -> None:
        self.tracker.bind(combo, on_press, on_release)

    def start(self) -> None:
        def down(key):
            name = pynput_name(key)
            if name:
                self.tracker.key_down(name)

        def up(key):
            name = pynput_name(key)
            if name:
                self.tracker.key_up(name)

        self._listener = self._keyboard.Listener(on_press=down, on_release=up)
        self._listener.daemon = True  # must not keep the app alive on quit
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


# Carbon (macOS) --------------------------------------------------------------------------------

# ANSI virtual key codes (Events.h). Positions on a US layout; other layouts map by position.
MAC_KEYCODES = {
    **dict(zip("asdfhgzxcv", range(10), strict=True)),
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32,
    "[": 33, "i": 34, "p": 35, "enter": 36, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49, "`": 50, "backspace": 51,
    "esc": 53, "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111, "home": 115, "page_up": 116, "delete": 117,
    "end": 119, "page_down": 121, "left": 123, "right": 124, "down": 125, "up": 126,
}  # fmt: skip
MAC_MODIFIERS = {"cmd": 1 << 8, "shift": 1 << 9, "alt": 1 << 11, "ctrl": 1 << 12}


def carbon_modifiers(mods: frozenset[str]) -> int:
    return sum(MAC_MODIFIERS[m] for m in mods)


def _fourcc(s: str) -> int:
    return int.from_bytes(s.encode("ascii"), "big")


class CarbonBackend:
    """RegisterEventHotKey: the system delivers press and release to our main thread.

    Unlike a keyboard listener it sees only our combos (no keystroke stream, so no Accessibility
    permission) and runs on the Qt main thread, which Cocoa's input-source APIs require.
    """

    PRESSED, RELEASED = 5, 6  # kEventHotKeyPressed, kEventHotKeyReleased

    def __init__(self) -> None:
        import ctypes
        import ctypes.util

        self._ct = ctypes
        path = ctypes.util.find_library("Carbon") or "/System/Library/Frameworks/Carbon.framework/Carbon"
        self._carbon = ctypes.CDLL(path)

        class HotKeyID(ctypes.Structure):
            _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]

        class EventTypeSpec(ctypes.Structure):
            _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]

        self._HotKeyID, self._EventTypeSpec = HotKeyID, EventTypeSpec
        c = self._carbon
        c.GetApplicationEventTarget.restype = ctypes.c_void_p
        c.GetEventKind.argtypes = [ctypes.c_void_p]
        c.GetEventKind.restype = ctypes.c_uint32
        c.GetEventParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]  # fmt: skip
        c.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, HotKeyID, ctypes.c_void_p,
                                          ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]  # fmt: skip
        c.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        c.InstallEventHandler.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.POINTER(EventTypeSpec), ctypes.c_void_p,
                                          ctypes.POINTER(ctypes.c_void_p)]  # fmt: skip
        c.RemoveEventHandler.argtypes = [ctypes.c_void_p]
        self._HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        self._callbacks: dict[int, tuple[Callback, Callback | None]] = {}
        self._pending: list[tuple[int, Combo]] = []
        self._refs: list = []
        self._handler_ref = None
        self._proc = None  # keep the ctypes callback alive as long as Carbon may call it

    def register(self, combo: Combo, on_press: Callback, on_release: Callback | None = None) -> None:
        if combo.key not in MAC_KEYCODES:
            raise ValueError(f"no macOS key code for '{combo.key}'")
        hid = len(self._callbacks) + 1
        self._callbacks[hid] = (on_press, on_release)
        self._pending.append((hid, combo))

    def _on_event(self, _call, event, _data) -> int:
        ct = self._ct
        hk = self._HotKeyID()
        err = self._carbon.GetEventParameter(
            event, _fourcc("----"), _fourcc("hkid"), None, ct.sizeof(hk), None, ct.byref(hk)
        )
        if err == 0 and hk.id in self._callbacks:
            on_press, on_release = self._callbacks[hk.id]
            kind = self._carbon.GetEventKind(event)
            try:
                if kind == self.PRESSED:
                    on_press()
                elif kind == self.RELEASED and on_release is not None:
                    on_release()
            except Exception:  # noqa: BLE001  an exception must never unwind into Carbon
                log.exception("Hotkey callback failed")
        return 0

    def start(self) -> None:
        ct, c = self._ct, self._carbon
        target = c.GetApplicationEventTarget()
        specs = (self._EventTypeSpec * 2)(
            self._EventTypeSpec(_fourcc("keyb"), self.PRESSED), self._EventTypeSpec(_fourcc("keyb"), self.RELEASED)
        )
        self._proc = self._HANDLER(self._on_event)
        ref = ct.c_void_p()
        err = c.InstallEventHandler(target, ct.cast(self._proc, ct.c_void_p), 2, specs, None, ct.byref(ref))
        if err != 0:
            raise OSError(f"InstallEventHandler failed ({err})")
        self._handler_ref = ref
        for hid, combo in self._pending:
            out = ct.c_void_p()
            hk = self._HotKeyID(_fourcc("MRGN"), hid)
            err = c.RegisterEventHotKey(
                MAC_KEYCODES[combo.key], carbon_modifiers(combo.mods), hk, target, 0, ct.byref(out)
            )
            if err != 0:  # -9878 eventHotKeyExistsErr: another app owns this combo
                log.warning("%s is taken by another app (error %s); use the orb or pick another.",
                            format_combo(combo), err)  # fmt: skip
                continue
            self._refs.append(out)
        if not self._refs:
            raise OSError("no hotkey could be registered")

    def stop(self) -> None:
        for ref in self._refs:
            self._carbon.UnregisterEventHotKey(ref)
        self._refs.clear()
        if self._handler_ref is not None:
            self._carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = None


# choosing a backend ----------------------------------------------------------------------------


def wayland() -> bool:
    return sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland"


def default_backend():
    if sys.platform == "darwin":
        return CarbonBackend()
    return PynputBackend()


def start_hotkeys(bindings: list[tuple[str, Callback, Callback | None]], backend_factory=default_backend):
    """Register every (combo text, on_press, on_release) and start listening.

    Returns the running backend (call .stop() to release it), or None when global hotkeys can't
    work here; the reason is logged and the orb still works. A combo that doesn't parse is skipped
    with a warning, so one typo doesn't cost the other hotkey.
    """
    if wayland():
        log.warning("Wayland session: global hotkeys are blocked here. Use the orb, or log in with X11.")
        return None
    parsed = []
    for text, on_press, on_release in bindings:
        try:
            parsed.append((parse_combo(text), on_press, on_release))
        except ValueError as exc:
            log.warning("Hotkey skipped: %s", exc)
    if not parsed:
        return None
    try:
        backend = backend_factory()
        for combo, on_press, on_release in parsed:
            backend.register(combo, on_press, on_release)
        backend.start()
        return backend
    except Exception as exc:  # noqa: BLE001  (no pynput, a blocked keyboard hook, a taken combo)
        log.warning("Hotkey unavailable (%s). Use the orb instead.", exc)
        return None

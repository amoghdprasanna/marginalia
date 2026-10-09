"""Wayland: screenshots and global shortcuts through the desktop portal (ADR 0024).

Wayland lets no app read the screen or the keyboard of others. The xdg-desktop-portal service
does both on the user's behalf: the Screenshot portal returns a file, and the GlobalShortcuts
portal (KDE, GNOME 48+, Hyprland...) reports a bound shortcut's press and release.

    Portal       the two D-Bus patterns we need: a call answered by a Request.Response signal,
                 and listening for signals. JeepneyPortal is the real one; tests pass a fake.
    screenshot   portal file -> PIL image -> the part showing the screen asked about
    PortalHotkeys  a hotkeys backend (register/start/stop) on the GlobalShortcuts portal
"""
from __future__ import annotations

import logging
import secrets
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import url2pathname

from PIL import Image

from .hotkeys import Combo

log = logging.getLogger(__name__)

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT = "org.freedesktop.portal.Screenshot"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"

# Response codes of org.freedesktop.portal.Request.Response
SUCCESS, CANCELLED, FAILED = 0, 1, 2


class PortalError(RuntimeError):
    pass


def token() -> str:
    """A handle token: D-Bus object path elements allow only [A-Za-z0-9_]."""
    return "marginalia_" + secrets.token_hex(6)


def request_path(unique_name: str, handle_token: str) -> str:
    """Where the portal will put the Request object for our call (documented, so we can listen first)."""
    sender = unique_name.lstrip(":").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{handle_token}"


def unvariant(results: dict) -> dict:
    """jeepney gives a{sv} values as (signature, value) pairs; we want the values."""
    def plain(v):
        return v[1] if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str) else v

    return {k: plain(v) for k, v in results.items()}


class Portal(Protocol):
    def request(self, interface: str, method: str, signature: str, body: tuple, timeout: float) -> dict:
        """Call a portal method whose answer arrives as Request.Response; return its results.

        The last argument of `body` must be the options dict; a handle_token is added to it.
        Raises PortalError if the user cancelled or the portal failed.
        """

    def call(self, path: str, interface: str, method: str, signature: str = "", body: tuple = ()) -> Any: ...

    def listen(self, interface: str, members: tuple[str, ...], handler: Callable[[str, tuple], None]) -> None:
        """Deliver every matching signal as handler(member, body) on a background thread until close()."""

    def close(self) -> None: ...


class JeepneyPortal:
    """The real thing: the session bus through jeepney's blocking API."""

    def __init__(self) -> None:
        from jeepney.io.blocking import open_dbus_connection

        self._conn = open_dbus_connection(bus="SESSION")
        self._listeners: list[threading.Thread] = []
        self._stop = threading.Event()

    def _address(self, interface: str, path: str = PORTAL_PATH):
        from jeepney import DBusAddress

        return DBusAddress(path, bus_name=PORTAL, interface=interface)

    def _add_match(self, rule) -> None:
        from jeepney.bus_messages import message_bus

        self._conn.send_and_get_reply(message_bus.AddMatch(rule))

    def request(self, interface: str, method: str, signature: str, body: tuple, timeout: float = 60.0) -> dict:
        from jeepney import MatchRule, new_method_call

        handle = token()
        path = request_path(self._conn.unique_name, handle)
        rule = MatchRule(type="signal", interface=REQUEST, member="Response", path=path)
        self._add_match(rule)
        *args, options = body
        options = {**options, "handle_token": ("s", handle)}
        with self._conn.filter(rule) as queue:
            reply = self._conn.send_and_get_reply(new_method_call(self._address(interface), method, signature,
                                                                  (*args, options)))  # fmt: skip
            if reply.header.message_type.name == "error":
                raise PortalError(f"{method}: {reply.body}")
            try:
                signal = self._conn.recv_until_filtered(queue, timeout=timeout)
            except TimeoutError as exc:
                raise PortalError(f"{method}: no answer from the desktop portal") from exc
        code, results = signal.body
        if code != SUCCESS:
            raise PortalError(f"{method}: {'cancelled' if code == CANCELLED else 'failed'}")
        return unvariant(results)

    def call(self, path: str, interface: str, method: str, signature: str = "", body: tuple = ()) -> Any:
        from jeepney import new_method_call

        return self._conn.send_and_get_reply(new_method_call(self._address(interface, path), method, signature, body))

    def listen(self, interface: str, members: tuple[str, ...], handler) -> None:
        from jeepney import MatchRule
        from jeepney.io.blocking import open_dbus_connection

        # A second connection, so the listening thread never competes with request() for replies.
        conn = open_dbus_connection(bus="SESSION")
        rule = MatchRule(type="signal", interface=interface)
        from jeepney.bus_messages import message_bus

        conn.send_and_get_reply(message_bus.AddMatch(rule))

        def loop() -> None:
            with conn.filter(rule) as queue:
                while not self._stop.is_set():
                    try:
                        msg = conn.recv_until_filtered(queue, timeout=0.5)
                    except TimeoutError:
                        continue
                    except Exception as exc:  # noqa: BLE001  (the bus went away)
                        log.warning("Stopped listening to the desktop portal: %s", exc)
                        return
                    if msg.header.fields.get(3) in members:  # header field 3 is MEMBER
                        handler(msg.header.fields[3], msg.body)
            conn.close()

        t = threading.Thread(target=loop, name="portal-signals", daemon=True)
        t.start()
        self._listeners.append(t)

    def close(self) -> None:
        self._stop.set()
        self._conn.close()


# screenshots -----------------------------------------------------------------------------------


def uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise PortalError(f"unexpected screenshot location {uri}")
    return Path(url2pathname(parsed.path))  # decodes %20 and, on Windows, the /C:/ drive form


def crop_box(
    image_size: tuple[int, int], screen: tuple[int, int, int, int], desktop: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """The part of a whole-desktop screenshot showing one screen (all geometry logical)."""
    sx, sy, sw, sh = screen
    dx, dy, dw, dh = desktop
    kx, ky = image_size[0] / dw, image_size[1] / dh
    return (round((sx - dx) * kx), round((sy - dy) * ky), round((sx - dx + sw) * kx), round((sy - dy + sh) * ky))


def portal_screenshot(portal: Portal, timeout: float = 60.0) -> Image.Image:
    """The whole desktop, as the portal saw it. The first time, the desktop may ask you to allow it."""
    results = portal.request(SCREENSHOT, "Screenshot", "sa{sv}", ("", {"interactive": ("b", False)}), timeout)
    path = uri_to_path(str(results.get("uri", "")))
    try:
        with Image.open(path) as img:
            out = img.convert("RGB")
    finally:
        path.unlink(missing_ok=True)  # the portal leaves a copy in ~/Pictures; it's ours to clean up
    return out


# global shortcuts ------------------------------------------------------------------------------

_XKB_KEYS = {
    "space": "space", "enter": "Return", "tab": "Tab", "esc": "Escape", "backspace": "BackSpace",
    "delete": "Delete", "up": "Up", "down": "Down", "left": "Left", "right": "Right", "home": "Home",
    "end": "End", "page_up": "Page_Up", "page_down": "Page_Down", **{f"f{i}": f"F{i}" for i in range(1, 13)},
}  # fmt: skip
_XDG_MODS = {"ctrl": "CTRL", "alt": "ALT", "shift": "SHIFT", "cmd": "LOGO"}


def xdg_trigger(combo: Combo) -> str:
    """Combo -> the XDG shortcuts spelling the portal takes as preferred_trigger: 'CTRL+ALT+space'."""
    mods = [_XDG_MODS[m] for m in ("ctrl", "alt", "shift", "cmd") if m in combo.mods]
    return "+".join([*mods, _XKB_KEYS.get(combo.key, combo.key)])


class PortalHotkeys:
    """Hotkeys backend on the GlobalShortcuts portal. The desktop may show a dialog to confirm
    or change the keys the first time; what you pick there is what fires."""

    def __init__(self, portal_factory: Callable[[], Portal] = JeepneyPortal) -> None:
        self._factory = portal_factory
        self._portal: Portal | None = None
        self._bindings: dict[str, tuple[Combo, Callable, Callable | None]] = {}
        self.session: str | None = None

    def register(self, combo: Combo, on_press, on_release=None) -> None:
        self._bindings[f"shortcut{len(self._bindings) + 1}"] = (combo, on_press, on_release)

    def _on_signal(self, member: str, body: tuple) -> None:
        session, shortcut_id = body[0], body[1]
        if session != self.session or shortcut_id not in self._bindings:
            return
        _, on_press, on_release = self._bindings[shortcut_id]
        try:
            if member == "Activated":
                on_press()
            elif member == "Deactivated" and on_release is not None:
                on_release()
        except Exception:  # noqa: BLE001
            log.exception("Hotkey callback failed")

    def start(self) -> None:
        self._portal = portal = self._factory()
        options = {"session_handle_token": ("s", token())}
        created = portal.request(SHORTCUTS, "CreateSession", "a{sv}", (options,), 30)
        self.session = str(created["session_handle"])
        shortcuts = [
            (sid, {"description": ("s", f"Marginalia: {'hold to talk' if rel else 'ask'}"),
                   "preferred_trigger": ("s", xdg_trigger(combo))})
            for sid, (combo, _p, rel) in self._bindings.items()
        ]  # fmt: skip
        portal.listen(SHORTCUTS, ("Activated", "Deactivated"), self._on_signal)
        # Waits while the desktop's confirmation dialog is open, the first time only.
        portal.request(SHORTCUTS, "BindShortcuts", "oa(sa{sv})sa{sv}", (self.session, shortcuts, "", {}), 300)

    def stop(self) -> None:
        if self._portal is None:
            return
        if self.session:
            try:
                self._portal.call(self.session, SESSION, "Close")
            except Exception as exc:  # noqa: BLE001
                log.debug("Closing the shortcuts session: %s", exc)
        self._portal.close()
        self._portal, self.session = None, None

"""Wayland through the desktop portal: screenshots, global shortcuts, and the D-Bus plumbing."""

import contextlib
from types import SimpleNamespace

import pytest
from PIL import Image

from marginalia.hotkeys import parse_combo
from marginalia.wayland import (
    CANCELLED,
    SCREENSHOT,
    SHORTCUTS,
    SUCCESS,
    PortalError,
    PortalHotkeys,
    crop_box,
    portal_screenshot,
    request_path,
    token,
    unvariant,
    uri_to_path,
    xdg_trigger,
)


class FakePortal:
    def __init__(self, answers=None):
        self.answers = answers or {}
        self.requests, self.calls = [], []
        self.handler = None
        self.closed = False

    def request(self, interface, method, signature, body, timeout=60):
        self.requests.append((interface, method, signature, body))
        answer = self.answers.get(method, {})
        if isinstance(answer, Exception):
            raise answer
        return answer

    def call(self, path, interface, method, signature="", body=()):
        self.calls.append((path, interface, method))

    def listen(self, interface, members, handler):
        self.listened = (interface, members)
        self.handler = handler

    def close(self):
        self.closed = True


# plumbing --------------------------------------------------------------------------------------


def test_request_path_and_tokens():
    assert request_path(":1.42", "marginalia_ab") == "/org/freedesktop/portal/desktop/request/1_42/marginalia_ab"
    t = token()
    assert t.startswith("marginalia_") and t.replace("_", "").isalnum() and t != token()


def test_unvariant():
    assert unvariant({"uri": ("s", "file:///x"), "n": 3}) == {"uri": "file:///x", "n": 3}


def test_uri_to_path():
    assert str(uri_to_path("file:///home/me/Pictures/Screenshot%20from%20now.png")).endswith("Screenshot from now.png")
    with pytest.raises(PortalError):
        uri_to_path("https://example.com/x.png")


# screenshots -----------------------------------------------------------------------------------


def test_crop_box_picks_one_screen_of_the_desktop():
    # Two 1440x900 screens side by side, captured at 2x.
    box = crop_box((5760, 1800), (1440, 0, 1440, 900), (0, 0, 2880, 900))
    assert box == (2880, 0, 5760, 1800)


def test_portal_screenshot_reads_and_removes_the_file(tmp_path):
    shot = tmp_path / "Screenshot.png"
    Image.new("RGB", (40, 20), (1, 2, 3)).save(shot)
    portal = FakePortal({"Screenshot": {"uri": shot.as_uri()}})
    img = portal_screenshot(portal)
    assert img.size == (40, 20) and img.getpixel((0, 0)) == (1, 2, 3)
    assert not shot.exists(), "our screenshot must not pile up in the user's Pictures"
    [(_, method, signature, body)] = portal.requests
    assert (method, signature) == ("Screenshot", "sa{sv}") and body[1]["interactive"] == ("b", False)


def test_a_refused_screenshot_raises():
    with pytest.raises(PortalError):
        portal_screenshot(FakePortal({"Screenshot": PortalError("Screenshot: cancelled")}))


def test_grab_screen_portal_makes_a_snapshot_of_the_screen_asked_about(qapp, tmp_path):
    from marginalia.capture import grab_screen_portal

    shot = tmp_path / "s.png"
    screen = qapp.primaryScreen().geometry()
    Image.new("RGB", (screen.width() * 2, screen.height() * 2), (200, 0, 0)).save(shot)
    portal = FakePortal({"Screenshot": {"uri": shot.as_uri()}})
    snap = grab_screen_portal(10, 20, portal_factory=lambda: portal)
    assert snap.screen_geo == (screen.x(), screen.y(), screen.width(), screen.height())
    assert snap.cursor == (10, 20) and snap.image.size == (screen.width() * 2, screen.height() * 2)
    assert portal.closed


def test_default_grab_follows_the_session(monkeypatch):
    from marginalia import capture

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert capture.default_grab() is capture.grab_screen_portal
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert capture.default_grab() is capture.grab_screen


# shortcuts -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "trigger"),
    [
        ("<ctrl>+<alt>+<space>", "CTRL+ALT+space"),
        ("<ctrl>+<alt>+v", "CTRL+ALT+v"),
        ("<cmd>+<shift>+<enter>", "SHIFT+LOGO+Return"),
    ],
)
def test_xdg_triggers(text, trigger):
    assert xdg_trigger(parse_combo(text)) == trigger


@pytest.fixture
def bound():
    portal = FakePortal({"CreateSession": {"session_handle": "/org/freedesktop/portal/desktop/session/1_42/s"}})
    hk = PortalHotkeys(lambda: portal)
    seen = []
    hk.register(parse_combo("<ctrl>+<alt>+<space>"), lambda: seen.append("ask"))
    hk.register(parse_combo("<ctrl>+<alt>+v"), lambda: seen.append("talk"), lambda: seen.append("sent"))
    hk.start()
    return hk, portal, seen


def test_start_creates_a_session_and_binds_both_shortcuts(bound):
    hk, portal, _ = bound
    create, bind = portal.requests
    assert create[1] == "CreateSession" and bind[1] == "BindShortcuts" and bind[0] == SHORTCUTS
    session, shortcuts, parent, _options = bind[3]
    assert session == hk.session
    assert [(sid, opts["preferred_trigger"][1]) for sid, opts in shortcuts] == [
        ("shortcut1", "CTRL+ALT+space"),
        ("shortcut2", "CTRL+ALT+v"),
    ]
    assert "hold to talk" in shortcuts[1][1]["description"][1]
    assert portal.listened == (SHORTCUTS, ("Activated", "Deactivated"))


def test_press_and_release_reach_the_callbacks(bound):
    hk, portal, seen = bound
    portal.handler("Activated", (hk.session, "shortcut1", 1, {}))
    portal.handler("Activated", (hk.session, "shortcut2", 2, {}))
    portal.handler("Deactivated", (hk.session, "shortcut2", 3, {}))
    portal.handler("Deactivated", (hk.session, "shortcut1", 4, {}))  # the ask key has no release action
    assert seen == ["ask", "talk", "sent"]


def test_signals_for_other_sessions_are_ignored(bound):
    _, portal, seen = bound
    portal.handler("Activated", ("/some/other/session", "shortcut1", 1, {}))
    assert seen == []


def test_stop_closes_the_session(bound):
    hk, portal, _ = bound
    session = hk.session
    hk.stop()
    assert portal.calls == [(session, "org.freedesktop.portal.Session", "Close")] and portal.closed
    hk.stop()  # twice is harmless


def test_a_desktop_without_the_portal_fails_start():
    hk = PortalHotkeys(lambda: FakePortal({"CreateSession": PortalError("no such interface")}))
    hk.register(parse_combo("<ctrl>+<space>"), print)
    with pytest.raises(PortalError):
        hk.start()


# XWayland --------------------------------------------------------------------------------------


def test_use_xwayland():
    from marginalia.app import use_xwayland

    env = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}
    assert use_xwayland(env) and env["QT_QPA_PLATFORM"] == "xcb"
    chosen = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland"}
    assert not use_xwayland(chosen) and chosen["QT_QPA_PLATFORM"] == "wayland", "your choice wins"
    assert not use_xwayland({"XDG_SESSION_TYPE": "wayland"}), "no XWayland: leave Qt alone"
    assert not use_xwayland({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"})


# the jeepney layer, against a fake connection --------------------------------------------------


class FakeConn:
    unique_name = ":1.7"

    def __init__(self, code=SUCCESS, results=None, error=False):
        self.sent = []
        self.code, self.results, self.error = code, results or {}, error

    def send_and_get_reply(self, msg):
        self.sent.append(msg)
        kind = "error" if self.error and len(self.sent) > 1 else "method_return"
        return SimpleNamespace(header=SimpleNamespace(message_type=SimpleNamespace(name=kind)), body=("nope",))

    @contextlib.contextmanager
    def filter(self, rule):
        self.rule = rule
        yield object()

    def recv_until_filtered(self, queue, timeout=None):
        return SimpleNamespace(body=(self.code, self.results))


@pytest.fixture
def jeepney_portal():
    pytest.importorskip("jeepney")
    from marginalia.wayland import JeepneyPortal

    def make(conn):
        p = object.__new__(JeepneyPortal)
        p._conn = conn
        return p

    return make


def test_request_listens_on_the_right_path_and_unwraps_results(jeepney_portal):
    conn = FakeConn(results={"uri": ("s", "file:///tmp/x.png")})
    out = jeepney_portal(conn).request(SCREENSHOT, "Screenshot", "sa{sv}", ("", {}), 5)
    assert out == {"uri": "file:///tmp/x.png"}
    assert conn.rule.header_fields["path"].startswith("/org/freedesktop/portal/desktop/request/1_7/marginalia_")
    call = conn.sent[-1]
    assert call.header.fields  # a real jeepney message
    options = call.body[-1]
    assert options["handle_token"][1] == conn.rule.header_fields["path"].rsplit("/", 1)[-1]


def test_request_raises_when_cancelled_or_refused(jeepney_portal):
    with pytest.raises(PortalError, match="cancelled"):
        jeepney_portal(FakeConn(code=CANCELLED)).request(SCREENSHOT, "Screenshot", "sa{sv}", ("", {}), 5)
    with pytest.raises(PortalError):
        jeepney_portal(FakeConn(error=True)).request(SCREENSHOT, "Screenshot", "sa{sv}", ("", {}), 5)

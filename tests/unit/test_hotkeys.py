"""Global hotkeys: parsing combos, press and release from raw keys, choosing a backend."""

import sys
from types import SimpleNamespace

import pytest

from marginalia import hotkeys
from marginalia.hotkeys import (
    MAC_KEYCODES,
    NAMED_KEYS,
    ChordTracker,
    Combo,
    PynputBackend,
    carbon_modifiers,
    format_combo,
    parse_combo,
    pynput_name,
    start_hotkeys,
    to_text,
)

# combos ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "mods", "key"),
    [
        ("<ctrl>+<alt>+<space>", {"ctrl", "alt"}, "space"),
        ("<ctrl>+<alt>+v", {"ctrl", "alt"}, "v"),
        ("Ctrl+Option+V", {"ctrl", "alt"}, "v"),
        ("<cmd>+<shift>+<f5>", {"cmd", "shift"}, "f5"),
        ("control + return", {"ctrl"}, "enter"),
    ],
)
def test_parse(text, mods, key):
    assert parse_combo(text) == Combo(frozenset(mods), key)


@pytest.mark.parametrize("text", ["v", "<ctrl>+<alt>", "<ctrl>+a+b", "<ctrl>+<hyper>", "<ctrl>+é"])
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        parse_combo(text)


def test_round_trip_and_labels(monkeypatch):
    c = parse_combo("<alt>+<ctrl>+<page_up>")
    assert parse_combo(to_text(c)) == c
    assert to_text(c) == "<ctrl>+<alt>+<page_up>", "modifiers in a fixed order"
    monkeypatch.setattr(sys, "platform", "linux")
    assert format_combo("<ctrl>+<alt>+<space>") == "Ctrl+Alt+Space"
    assert format_combo(c) == "Ctrl+Alt+PageUp"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert format_combo("<ctrl>+<alt>+v") == "Ctrl+Option+V"
    assert format_combo("garbage") == "garbage"


# chords ----------------------------------------------------------------------------------------


@pytest.fixture
def chord():
    t = ChordTracker()
    t.events = []
    t.bind(parse_combo("<ctrl>+<alt>+v"), lambda: t.events.append("press"), lambda: t.events.append("release"))
    return t


def test_press_when_the_last_key_goes_down_release_when_any_comes_up(chord):
    for k in ("ctrl", "alt", "v"):
        chord.key_down(k)
    assert chord.events == ["press"]
    chord.key_up("alt")
    assert chord.events == ["press", "release"]
    chord.key_up("v")
    chord.key_up("ctrl")
    assert chord.events == ["press", "release"], "released once"


def test_key_repeat_does_not_press_again(chord):
    for k in ("ctrl", "alt", "v", "v", "v"):
        chord.key_down(k)
    assert chord.events == ["press"]


def test_extra_modifiers_do_not_match(chord):
    for k in ("ctrl", "alt", "shift", "v"):
        chord.key_down(k)
    assert chord.events == []


def test_order_of_modifiers_does_not_matter(chord):
    for k in ("alt", "ctrl", "v"):
        chord.key_down(k)
    assert chord.events == ["press"]


def test_press_only_bindings_have_no_release():
    t, seen = ChordTracker(), []
    t.bind(parse_combo("<ctrl>+<space>"), lambda: seen.append("ask"))
    t.key_down("ctrl")
    t.key_down("space")
    t.key_up("space")
    assert seen == ["ask"]


# pynput ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "name"),
    [
        (SimpleNamespace(name="ctrl_l"), "ctrl"),
        (SimpleNamespace(name="alt_gr"), "alt"),
        (SimpleNamespace(name="cmd_r"), "cmd"),
        (SimpleNamespace(name="space"), "space"),
        (SimpleNamespace(name="media_play_pause"), None),
        (SimpleNamespace(char="V", vk=86), "v"),
        (SimpleNamespace(char="\x16", vk=86), "v"),  # Windows: Ctrl+V arrives as a control char
        (SimpleNamespace(char=None, vk=0x76), "v"),  # X11: the keysym
        (SimpleNamespace(char=None, vk=None), None),
    ],
)
def test_pynput_names(key, name):
    assert pynput_name(key) == name


class FakeListener:
    def __init__(self, on_press, on_release):
        self.on_press, self.on_release = on_press, on_release
        self.daemon = self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_pynput_backend_feeds_the_tracker():
    b = PynputBackend(keyboard=SimpleNamespace(Listener=FakeListener))
    seen = []
    b.register(parse_combo("<ctrl>+<alt>+v"), lambda: seen.append("down"), lambda: seen.append("up"))
    b.start()
    lst = b._listener
    assert lst.started and lst.daemon, "a daemon thread must not keep the app alive on quit"
    for k in (SimpleNamespace(name="ctrl_l"), SimpleNamespace(name="alt_l"), SimpleNamespace(char="v", vk=86)):
        lst.on_press(k)
    lst.on_release(SimpleNamespace(char="v", vk=86))
    assert seen == ["down", "up"]
    b.stop()
    assert lst.stopped and b._listener is None


# starting --------------------------------------------------------------------------------------


class FakeBackend:
    def __init__(self, fail=None):
        self.bound, self.started, self.fail = [], False, fail

    def register(self, combo, on_press, on_release=None):
        self.bound.append(combo)

    def start(self):
        if self.fail:
            raise self.fail
        self.started = True


def test_start_registers_every_good_combo(caplog, monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    b = FakeBackend()
    out = start_hotkeys([("<ctrl>+<alt>+<space>", print, None), ("oops", print, None)], lambda: b)
    assert out is b and b.started and b.bound == [parse_combo("<ctrl>+<alt>+<space>")]
    assert "Hotkey skipped" in caplog.text, "one typo doesn't cost the other hotkey"


def test_start_falls_back_to_the_orb_when_the_backend_fails(caplog, monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert start_hotkeys([("<ctrl>+<space>", print, None)], lambda: FakeBackend(OSError("hook blocked"))) is None
    assert "Use the orb" in caplog.text


def test_wayland_skips_hotkeys_with_a_reason(caplog, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert start_hotkeys([("<ctrl>+<space>", print, None)], lambda: pytest.fail("not built")) is None
    assert "Wayland" in caplog.text


def test_nothing_to_bind_starts_nothing(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert start_hotkeys([("bad", print, None)], lambda: pytest.fail("not built")) is None


def test_default_backend_per_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(hotkeys, "PynputBackend", lambda: "pynput")
    monkeypatch.setattr(hotkeys, "CarbonBackend", lambda: "carbon")
    assert hotkeys.default_backend() == "pynput"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert hotkeys.default_backend() == "carbon"


# Carbon ----------------------------------------------------------------------------------------


def test_every_bindable_key_has_a_mac_key_code():
    letters_digits = "abcdefghijklmnopqrstuvwxyz0123456789"
    assert all(k in MAC_KEYCODES for k in (*NAMED_KEYS, *letters_digits))
    assert len(set(MAC_KEYCODES.values())) == len(MAC_KEYCODES), "no two keys share a code"


def test_carbon_modifier_bits():
    assert carbon_modifiers(frozenset({"ctrl", "alt"})) == 4096 + 2048
    assert carbon_modifiers(frozenset({"cmd", "shift"})) == 256 + 512


@pytest.mark.skipif(sys.platform != "darwin", reason="Carbon is macOS only")
def test_carbon_registers_and_releases_a_real_hotkey(qapp):
    b = hotkeys.CarbonBackend()
    b.register(parse_combo("<ctrl>+<alt>+<shift>+<f12>"), lambda: None, lambda: None)
    b.start()
    assert len(b._refs) == 1
    b.stop()
    assert b._refs == [] and b._handler_ref is None

"""The Settings window: shows the config, locks env-pinned fields, validates, saves, keychain."""

import pytest
from helpers import FakeKeyring
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from marginalia.config import SettingsStore, load_config
from marginalia.hotkeys import Combo
from marginalia.secrets import Keychain
from marginalia.ui import SettingsWindow
from marginalia.ui.settings import HotkeyEdit, combo_from_qt


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path / "settings.json")


@pytest.fixture
def keychain():
    return Keychain(FakeKeyring())


@pytest.fixture
def window(qtbot, store, keychain):
    w = SettingsWindow(load_config(store=store, keychain=keychain), store, keychain)
    qtbot.addWidget(w)
    return w


def test_shows_the_current_values(window):
    assert window.fields["model"].currentText() == "claude-opus-5-5"
    assert window.fields["effort"].currentText() == "medium"
    assert window.fields["hotkey"].value == "<ctrl>+<alt>+<space>"
    assert window.fields["ocr_enabled"].isChecked()


def test_saving_writes_only_what_changed(qtbot, window, store):
    window.fields["effort"].setCurrentText("low")
    window.fields["ocr_enabled"].setChecked(False)
    with qtbot.waitSignal(window.saved):
        assert window.save()
    assert store.load() == {"effort": "low", "ocr_enabled": False}
    assert load_config(store=store).effort == "low"


def test_environment_pinned_fields_are_locked_and_never_saved(qtbot, store, keychain, monkeypatch):
    monkeypatch.setenv("MARGINALIA_MODEL", "claude-sonnet-5-5")
    w = SettingsWindow(load_config(store=store, keychain=keychain), store, keychain)
    qtbot.addWidget(w)
    assert not w.fields["model"].isEnabled()
    assert "MARGINALIA_MODEL" in w.fields["model"].toolTip()
    w.save()
    assert "model" not in store.load()


def test_a_new_api_key_goes_to_the_keychain(window, keychain, store):
    window.key_edit.setText("  sk-ant-api03-newkeynewkeynewkey  ")
    assert window.save()
    assert keychain.get() == "sk-ant-api03-newkeynewkeynewkey"
    assert "sk-ant" not in store.path.read_text(encoding="utf-8"), "the key never lands in the settings file"


def test_the_key_status_never_shows_the_whole_key(qtbot, store, keychain):
    keychain.set("sk-ant-api03-abcdefghijklmnopqrstuvwxyz")
    w = SettingsWindow(load_config(store=store, keychain=keychain), store, keychain)
    qtbot.addWidget(w)
    assert "wxyz" in w.key_status.text() and "abcdefghij" not in w.key_status.text()
    assert w.key_remove.isEnabled()
    w._remove_key()
    assert keychain.get() is None and not w.key_remove.isEnabled()


def test_a_broken_keychain_is_explained(qtbot, store):
    kc = Keychain(FakeKeyring(error=RuntimeError("No recommended backend")))
    w = SettingsWindow(load_config(store=store, keychain=kc), store, kc)
    qtbot.addWidget(w)
    assert "No recommended backend" in w.key_status.text()
    w.key_edit.setText("sk-ant-x")
    assert not w.save() and w.error.isVisibleTo(w)


def test_two_identical_shortcuts_are_refused(window, store):
    window.fields["voice_hotkey"].set_value("<ctrl>+<alt>+<space>")
    assert not window.save()
    assert "different" in window.error.text() and not store.path.exists()


def test_an_unwritable_settings_file_is_reported(window, store, tmp_path):
    store.path = tmp_path / "blocker" / "settings.json"
    (tmp_path / "blocker").write_text("a file where the folder should be")
    window.fields["effort"].setCurrentText("high")
    assert not window.save()
    assert "Could not save settings" in window.error.text()


def test_closing_says_so(qtbot, window):
    window.show()
    with qtbot.waitSignal(window.closed):
        window.close()


# recording a shortcut --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "mods", "mac", "expected"),
    [
        (Qt.Key_V, Qt.ControlModifier | Qt.AltModifier, False, Combo(frozenset({"ctrl", "alt"}), "v")),
        (Qt.Key_V, Qt.MetaModifier | Qt.AltModifier, True, Combo(frozenset({"ctrl", "alt"}), "v")),
        (Qt.Key_Space, Qt.ControlModifier, True, Combo(frozenset({"cmd"}), "space")),
        (Qt.Key_F5, Qt.ShiftModifier, False, Combo(frozenset({"shift"}), "f5")),
        (Qt.Key_V, Qt.NoModifier, False, None),
        (Qt.Key_Control, Qt.ControlModifier, False, None),
    ],
)
def test_combo_from_qt(key, mods, mac, expected):
    assert combo_from_qt(key, mods, mac) == expected


@pytest.fixture
def edit(qtbot):
    e = HotkeyEdit("<ctrl>+<alt>+v")
    qtbot.addWidget(e)
    e.show()
    e.setFocus()
    return e


def test_pressing_a_chord_records_it(qtbot, edit):
    mods = Qt.MetaModifier | Qt.ShiftModifier  # Ctrl+Shift on a Mac, Win+Shift elsewhere
    with qtbot.waitSignal(edit.changed):
        QTest.keyClick(edit, Qt.Key_K, mods)
    assert edit.value.endswith("+k") and "<shift>" in edit.value


def test_a_bare_key_is_not_a_shortcut(qtbot, edit):
    with qtbot.assertNotEmitted(edit.changed):
        QTest.keyClick(edit, Qt.Key_K)
    assert "modifier" in edit.text() and edit.value == "<ctrl>+<alt>+v"


def test_backspace_clears_and_escape_keeps(qtbot, edit):
    QTest.keyClick(edit, Qt.Key_Escape)
    assert edit.value == "<ctrl>+<alt>+v"
    edit.setFocus()
    QTest.keyClick(edit, Qt.Key_Backspace)
    assert edit.value == ""

"""The setup window: one row per check, a button where there is something to fix."""

from PySide6.QtWidgets import QApplication

from marginalia.permissions import MISSING, OFF, OK, Check
from marginalia.ui import SetupWindow

CHECKS = [
    Check("api_key", "Claude API key", OK, "Set in your keychain."),
    Check("screen", "Screen Recording", MISSING, "Allow iTerm.", "Allow…"),
    Check("microphone", "Microphone", OFF, "Voice is off.", required=False),
]


def test_rows_and_fix_buttons(qtbot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show_checks(CHECKS, "iTerm")
    assert list(w.buttons) == ["screen"], "only things to fix get a button"
    with qtbot.waitSignal(w.fix_requested) as sig:
        w.buttons["screen"].click()
    assert sig.args[0].key == "screen"
    assert "iTerm" in w.intro.text()


def test_restart_is_offered_only_to_the_packaged_app(qtbot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show_checks(CHECKS, "iTerm")
    assert not w.restart.isVisibleTo(w), "from a terminal, the terminal must restart, not us"
    w.show_checks(CHECKS, "Marginalia")
    assert w.restart.isVisibleTo(w)


def test_showing_again_replaces_the_rows(qtbot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show_checks(CHECKS, "iTerm")
    w.show_checks(CHECKS[:1], "iTerm")
    QApplication.processEvents()
    assert w.buttons == {}


def test_closing_says_done(qtbot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show()
    with qtbot.waitSignal(w.done):
        w.close()

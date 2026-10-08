"""Asking by typing, end to end: capture, answer, markers, follow-ups, threads ending, errors."""

from helpers import FakeBrain, FakeOCR, ManualExecutor, ask_typed, build, make_snapshot
from PySide6.QtCore import QPoint

from marginalia.app import HISTORY_TURNS, pretty_hotkey
from marginalia.brain import BrainError
from marginalia.doubtlog import DoubtLog
from marginalia.ocr import TextLine


def test_pretty_hotkey():
    assert pretty_hotkey("<ctrl>+<alt>+<space>") == "Ctrl+Alt+Space"


def test_typed_question_gets_an_answer_and_is_journaled(qtbot, cfg):
    brain = FakeBrain(text="It is the code distance.")
    c = build(qtbot, cfg, brain=brain)
    ask_typed(qtbot, c, "what is d?")
    assert brain.asked == [("what is d?", [])]
    assert "code distance" in c.bubble.body.toPlainText() and c.bubble.isVisible()
    assert c.history == [("what is d?", "It is the code distance.")]
    assert "what is d?" in next((cfg.log_dir / "doubts").glob("*.md")).read_text()


def test_screen_is_grabbed_where_the_mouse_rested(qtbot, cfg):
    seen = []
    c = build(qtbot, cfg, grab=lambda x, y: seen.append((x, y)) or make_snapshot(cursor=(x, y)))
    c.rest.rest = (321, 123)
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    assert seen == [(321, 123)]


def test_follow_ups_carry_history_and_it_is_capped(qtbot, cfg):
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain)
    ask_typed(qtbot, c, "q0")
    for i in range(1, HISTORY_TURNS + 2):
        c._followup(f"q{i}")
        qtbot.waitUntil(lambda i=i: len(brain.asked) == i + 1)
    assert [q for q, _ in brain.asked[-1][1]] == [f"q{i}" for i in range(1, HISTORY_TURNS + 1)]
    assert len(c.history) == HISTORY_TURNS


def test_closing_the_bubble_ends_the_thread(qtbot, cfg):
    c = build(qtbot, cfg)
    ask_typed(qtbot, c, "q")
    c.bubble.dismiss()
    assert c.history == [] and not c.overlay.isVisible()


def test_a_stale_answer_is_ignored(qtbot, cfg):
    pool = ManualExecutor()
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, pool=pool)
    c.snapshot = make_snapshot()
    c.ask("first")
    c.ask("second")
    pool.run_all()  # both finish; only the newest may show
    assert c.history == [("second", brain.text)]


def test_brain_errors_show_in_the_bubble(qtbot, cfg):
    c = build(qtbot, cfg, brain=FakeBrain(error=BrainError("Rate limited by the API.")))
    ask_typed(qtbot, c, "q")
    assert "Rate limited" in c.bubble.body.toPlainText()
    assert c.history == []


def test_capture_failure_is_explained(qtbot, cfg):
    def broken(x, y):
        raise RuntimeError("The screenshot came back blank.")

    c = build(qtbot, cfg, grab=broken)
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.bubble.isVisible)
    assert "blank" in c.bubble.body.toPlainText()
    assert c.orb.isVisible() and not c._capturing


def test_orb_click_opens_the_chooser_and_toggles(qtbot, cfg):
    c = build(qtbot, cfg)
    c.orb.show()
    c._choose_mode()
    assert c.chooser.isVisible()
    c._choose_mode()
    assert not c.chooser.isVisible()


def test_markers_point_at_resolved_targets(qtbot, cfg):
    from marginalia.brain import Point

    snap = make_snapshot(cursor=(700, 450))
    from marginalia.capture import prepare

    zoom_cursor = prepare(snap).cursor_zoom
    c = build(qtbot, cfg, brain=FakeBrain(points=[Point("zoom", *zoom_cursor, None, "here")]), grab=lambda x, y: snap)
    ask_typed(qtbot, c, "q")
    assert c.overlay.isVisible()
    [(target, label)] = c.overlay.targets
    assert label == "here" and abs(target.x() - 700) <= 1 and abs(target.y() - 450) <= 1


def test_own_windows_do_not_move_the_rest_point(qtbot, cfg):
    c = build(qtbot, cfg)
    c.orb.show()
    assert c._on_own_window(c.orb.frameGeometry().center())
    assert not c._on_own_window(QPoint(-5000, -5000))


def test_eval_cases_are_saved_only_when_asked(qtbot, cfg):
    c = build(qtbot, cfg)
    ask_typed(qtbot, c, "q")
    assert not (cfg.log_dir / "cases").exists()
    cfg.save_cases = True
    ask_typed(qtbot, c, "q2")
    assert len(list((cfg.log_dir / "cases").glob("*/case.json"))) == 1


# OCR in the loop ----------------------------------------------------------------------------


def test_ocr_lines_reach_the_model_and_the_footer(qtbot, cfg):
    lines = [TextLine(0, "d = 2t + 1", (100, 100, 300, 120), 0.99), TextLine(1, "Theorem 2", (100, 140, 300, 160), 0.9)]
    brain, ocr = FakeBrain(), FakeOCR(lines)
    c = build(qtbot, cfg, brain=brain, ocr=ocr)
    ask_typed(qtbot, c, "why odd?")
    assert ocr.reads == 1, "OCR runs once per screenshot, while you type"
    assert brain.lines_seen == [lines]
    assert "2 OCR lines" in c.bubble.meta.text()


def test_a_failing_ocr_does_not_cost_the_answer(qtbot, cfg):
    brain = FakeBrain(text="Still answered.")
    c = build(qtbot, cfg, brain=brain, ocr=FakeOCR(error=RuntimeError("onnx crashed")))
    ask_typed(qtbot, c, "q")
    assert brain.lines_seen == [[]]
    assert "Still answered." in c.bubble.body.toPlainText()


def test_unavailable_ocr_is_not_run(qtbot, cfg):
    ocr = FakeOCR(available=False)
    c = build(qtbot, cfg, ocr=ocr)
    ask_typed(qtbot, c, "q")
    assert ocr.reads == 0


# robustness ------------------------------------------------------------------------------


def test_a_second_trigger_during_capture_is_ignored(qtbot, cfg):
    grabs = []

    def grab(x, y):
        grabs.append((x, y))
        return make_snapshot(cursor=(x, y))

    c = build(qtbot, cfg, grab=grab)
    c.start_ask(at_cursor=False)
    c.start_ask(at_cursor=False)  # double-click on the orb, or hotkey + orb
    qtbot.waitUntil(c.askbox.isVisible)
    qtbot.wait(200)
    assert len(grabs) == 1


def test_an_unexpected_error_is_shown_not_raised(qtbot, cfg):
    c = build(qtbot, cfg, brain=FakeBrain(error=KeyError("surprise")))
    ask_typed(qtbot, c, "q")
    assert "Something went wrong" in c.bubble.body.toPlainText()
    assert not c.orb._spin.isActive(), "the orb stops spinning"


def test_a_full_disk_does_not_lose_the_answer(qtbot, cfg, caplog):
    class FullDisk(DoubtLog):
        def add(self, *a, **kw):
            raise OSError("No space left on device")

    c = build(qtbot, cfg, log=FullDisk(cfg.log_dir))
    ask_typed(qtbot, c, "q")
    assert "code distance" in c.bubble.body.toPlainText()
    assert c.history, "the thread continues"
    assert "Could not write the journal" in caplog.text


def test_orb_spins_while_waiting_and_stops_with_the_answer(qtbot, cfg):
    pool = ManualExecutor()
    c = build(qtbot, cfg, pool=pool)
    c.snapshot = make_snapshot()
    c.ask("q")
    assert c.orb._spin.isActive()
    assert "Reading your screen" in c.bubble.status.text()
    pool.run_all()
    assert not c.orb._spin.isActive()


def test_follow_up_recaptures_the_screen_first(qtbot, cfg):
    """A lecture keeps playing: a follow-up must look at the screen as it is now."""
    grabs = []

    def grab(x, y):
        grabs.append((x, y))
        return make_snapshot(cursor=(x, y))

    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, grab=grab)
    ask_typed(qtbot, c, "q1")
    c._followup("q2")
    qtbot.waitUntil(lambda: len(brain.asked) == 2)
    assert len(grabs) == 2


def test_cancelling_a_new_question_ends_the_thread_it_hid(qtbot, cfg):
    """Bug: a new question hides the open bubble; cancelling it left the thread alive but unseen.

    The next question then silently carried the old answers as history.
    """
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain)
    ask_typed(qtbot, c, "first")
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    assert not c.bubble.isVisible(), "capturing hides the bubble"
    c.askbox.keyPressEvent(_esc())
    ask_typed(qtbot, c, "unrelated")
    assert brain.asked[-1] == ("unrelated", [])


def test_abandoning_a_streaming_answer_stops_the_orb_spinning(qtbot, cfg):
    """Bug: an answer made stale by a new capture never reset the orb, so it spun forever."""
    pool = ManualExecutor()
    c = build(qtbot, cfg, pool=pool)
    c.snapshot = make_snapshot()
    c.ask("slow one")
    assert c.orb._spin.isActive()
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    c.askbox.keyPressEvent(_esc())
    pool.run_all()  # the abandoned answer arrives late and is dropped
    assert not c.orb._spin.isActive()


def _esc():
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    return QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)


def test_capture_failure_is_explained_on_the_screen_you_asked_about(qtbot, cfg):
    """Bug: the error bubble was placed using the previous question's screen, which may be another monitor."""
    shots = [make_snapshot(origin=(5000, 0), cursor=(5100, 100))]  # last time: a monitor far to the right

    def grab(x, y):
        if shots:
            return shots.pop()
        raise RuntimeError("The screenshot came back blank.")

    c = build(qtbot, cfg, grab=grab)
    ask_typed(qtbot, c, "on the other monitor")
    c.rest.rest = (100, 100)
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(lambda: "blank" in c.bubble.body.toPlainText())
    here = c.orb.screen().geometry()
    assert here.contains(c.bubble.frameGeometry().center())
    assert c.snapshot is None, "a failed capture must not leave the old screenshot to ask about"

"""Asking by typing, end to end: capture, answer, markers, follow-ups, threads ending, errors."""

from helpers import FakeBrain, ManualExecutor, ask_typed, build, make_snapshot
from PySide6.QtCore import QPoint

from marginalia.app import HISTORY_TURNS, pretty_hotkey
from marginalia.brain import BrainError


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

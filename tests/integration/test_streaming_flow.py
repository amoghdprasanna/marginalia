"""Streaming answers through the controller: redraws, ordering, cancelling, placement."""

from helpers import FakeBrain, ManualExecutor, ask_typed, build, make_snapshot


def test_streamed_text_shows_while_the_answer_is_written(qtbot, cfg):
    c = build(qtbot, cfg)
    c.snapshot = make_snapshot()
    c.bubble.show_thinking("q")
    c._on_partial((c.request_id, "q", "The distance is"))
    qtbot.waitUntil(lambda: "The distance is" in c.bubble.body.toPlainText())
    assert c.bubble.meta.text() == "Writing…"
    assert not c.bubble.follow_wrap.isVisible() and not c.bubble.copy_btn.isVisible()


def test_streamed_text_from_an_old_question_is_dropped(qtbot, cfg):
    c = build(qtbot, cfg)
    c.snapshot = make_snapshot()
    c._on_partial((c.request_id - 1, "old", "stale words"))
    qtbot.wait(2 * 50)
    assert "stale" not in c.bubble.body.toPlainText()


def test_final_answer_is_not_overwritten_by_a_queued_redraw(qtbot, cfg):
    brain = FakeBrain(text="Final answer.", partials=["Fin", "Final ans"])
    c = build(qtbot, cfg, brain=brain)
    ask_typed(qtbot, c, "q")  # inline executor: partials and answer arrive back to back
    qtbot.wait(3 * 50)
    assert c.bubble.body.toPlainText().strip() == "Final answer."
    assert c.bubble.follow_wrap.isVisible()


def test_closing_mid_stream_stops_the_stream(qtbot, cfg):
    """An abandoned answer must stop streaming, or it keeps costing output tokens."""
    pool = ManualExecutor()
    brain = FakeBrain(partials=["a", "ab", "abc"])
    c = build(qtbot, cfg, brain=brain, pool=pool)
    c.snapshot = make_snapshot()
    c.ask("q")
    c.bubble.dismiss()
    pool.run_all()
    assert brain.delivered == [] and c.history == []


def test_streaming_bubble_slides_up_instead_of_off_screen(qtbot, cfg):
    c = build(qtbot, cfg)
    c.snapshot = make_snapshot(logical=(1440, 900))
    c.bubble.show_partial("q", "word " * 40)
    c.bubble.move(100, 850)
    c._keep_bubble_on_screen()
    assert c.bubble.frameGeometry().bottom() <= 900 - 12

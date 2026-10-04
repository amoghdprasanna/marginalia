"""The controller end to end, with fakes for the model, the screen, the mic and the threads."""

import numpy as np
import pytest
from helpers import FakeBrain, FakeStream, FakeWhisper, ImmediateExecutor, ManualExecutor, make_snapshot
from PySide6.QtCore import QPoint

from marginalia.app import HISTORY_TURNS, Controller, Services, pretty_hotkey
from marginalia.brain import BrainError
from marginalia.doubtlog import DoubtLog
from marginalia.voice import Recorder, Transcriber

pytestmark = pytest.mark.qt


def build(qtbot, cfg, *, brain=None, pool=None, voice_text=None, grab=None):
    streams = []
    services = Services(
        brain=brain or FakeBrain(),
        log=DoubtLog(cfg.log_dir),
        transcriber=None
        if voice_text is None
        else Transcriber("tiny.en", model_factory=lambda n: FakeWhisper(voice_text), problem=None),
        recorder=Recorder(stream_factory=lambda cb: streams.append(FakeStream(cb)) or streams[-1]),
        grab=grab or (lambda x, y: make_snapshot(cursor=(x, y))),
        pool=pool or ImmediateExecutor(),
    )
    c = Controller(cfg, services)
    for w in (c.orb, c.askbox, c.bubble, c.overlay, c.chooser, c.listenbox):
        qtbot.addWidget(w)
    c.streams = streams
    return c


def ask_typed(qtbot, c, question):
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    c.askbox.edit.setText(question)
    c.askbox._submit()


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


def test_voice_question_end_to_end(qtbot, cfg):
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="why is the distance odd")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    assert c.recorder.recording
    c.streams[0].push(np.full(16000, 0.1, dtype=np.float32))
    c.listenbox._send()
    assert not c.recorder.recording
    assert brain.asked[0][0] == "why is the distance odd"
    assert not c.listenbox.isVisible() and c.bubble.isVisible()


def test_silence_is_not_sent_as_a_question(qtbot, cfg):
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, voice_text="")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    c.streams[0].push(np.zeros(16000, dtype=np.float32))
    c.listenbox._send()
    assert brain.asked == [] and c.listenbox.status.text() == "Didn't catch that."


def test_cancel_stops_the_mic_and_drops_late_transcripts(qtbot, cfg):
    pool = ManualExecutor()
    brain = FakeBrain()
    c = build(qtbot, cfg, brain=brain, pool=pool, voice_text="late")
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    c.streams[0].push(np.full(16000, 0.1, dtype=np.float32))
    c.listenbox._send()
    c.listenbox.close_quietly()
    c._cancel_listening()
    pool.run_all()
    assert brain.asked == []


def test_mic_error_is_shown_not_raised(qtbot, cfg):
    def no_mic(cb):
        raise OSError("No input device")

    c = build(qtbot, cfg, voice_text="x")
    c.recorder = Recorder(stream_factory=no_mic)
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.listenbox.isVisible)
    assert "Microphone unavailable" in c.listenbox.status.text()


def test_without_voice_the_speak_path_falls_back_to_typing(qtbot, cfg):
    c = build(qtbot, cfg)  # no transcriber
    assert not c.chooser.voice_btn.isEnabled() and not c.askbox.mic.isVisibleTo(c.askbox)
    c.start_voice(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)


def test_switching_from_typing_to_voice_reuses_the_screenshot(qtbot, cfg):
    grabs = []
    c = build(qtbot, cfg, voice_text="x", grab=lambda x, y: grabs.append(1) or make_snapshot(cursor=(x, y)))
    c.start_ask(at_cursor=False)
    qtbot.waitUntil(c.askbox.isVisible)
    c.askbox._to_voice()
    assert c.listenbox.isVisible() and len(grabs) == 1


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


# streaming --------------------------------------------------------------------------------


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


def test_eval_cases_are_saved_only_when_asked(qtbot, cfg):
    c = build(qtbot, cfg)
    ask_typed(qtbot, c, "q")
    assert not (cfg.log_dir / "cases").exists()
    cfg.save_cases = True
    ask_typed(qtbot, c, "q2")
    assert len(list((cfg.log_dir / "cases").glob("*/case.json"))) == 1

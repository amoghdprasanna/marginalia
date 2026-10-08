"""Reading the journal back: the index, old pages, threads, search, reopening a screenshot."""

import json

import pytest
from helpers import make_snapshot
from PIL import Image

from marginalia.doubtlog import DoubtLog
from marginalia.journal import Entry, Journal, parse_page, to_image_px

OLD_PAGE = """# Doubts, Thursday 01 October 2026

## 16:20  do you see my terminal?

![screen](shots/20261001-162044.png)

**Yes.** A terminal with *pytest* output.

Two paragraphs, even.

<sub>claude-opus-5</sub>

---

## 16:25  and now?

![screen](shots/20261001-162501-123456.png)

Still there.

<sub>demo</sub>

---

"""


def test_parse_an_old_page():
    a, b = parse_page(OLD_PAGE, "2026-10-01")
    assert (a.id, a.question, a.model) == ("20261001-162044", "do you see my terminal?", "claude-opus-5")
    assert a.answer == "**Yes.** A terminal with *pytest* output.\n\nTwo paragraphs, even."
    assert a.time == "2026-10-01T16:20:44" and a.shot == "shots/20261001-162044.png"
    assert b.id == "20261001-162501-123456" and b.answer == "Still there."


def test_a_garbled_block_is_skipped():
    assert parse_page("# Doubts\n\n## not a heading\n\ntext\n\n---\n", "2026-10-01") == []


@pytest.fixture
def journal(tmp_path):
    return Journal(tmp_path)


def test_backfill_indexes_old_pages_once(journal):
    journal.dir.mkdir()
    (journal.dir / "2026-10-01.md").write_text(OLD_PAGE)
    (journal.dir / "notes.md").write_text("not a journal page")
    assert journal.backfill() == 2
    assert journal.backfill() == 0, "already indexed"
    assert [e.question for e in journal.entries()] == ["do you see my terminal?", "and now?"]


def test_new_entries_are_indexed_with_geometry_and_points(tmp_path, journal):
    log = DoubtLog(tmp_path)
    snap = make_snapshot(origin=(1440, 0), cursor=(1440 + 700, 450))
    log.add("q1", "a1", Image.new("RGB", (10, 10)), "m", snap=snap, points=[(1500.04, 20.0, "eq 4")])
    [e] = journal.entries()
    assert e.screen == [1440, 0, 1440, 900] and e.cursor == [2140, 450]
    assert e.points == [[1500.0, 20.0, "eq 4"]]
    assert e.thread == "" and e.thread_id == e.id == log.last_entry.id


def test_threads_group_newest_first_and_search(tmp_path, journal):
    log = DoubtLog(tmp_path)
    img = Image.new("RGB", (10, 10))
    log.add("what is the code distance?", "d", img, "m")
    first = log.last_entry.id
    log.add("why odd?", "majority vote", img, "m", thread=first)
    log.add("what is a stabilizer?", "a Pauli", img, "m")
    threads = journal.threads()
    assert [t.first.question for t in threads] == ["what is a stabilizer?", "what is the code distance?"]
    assert [e.question for e in threads[1].entries] == ["what is the code distance?", "why odd?"]
    assert threads[1].history(1) == [("why odd?", "majority vote")]
    assert [t.first.question for t in journal.threads("MAJORITY")] == ["what is the code distance?"]
    assert journal.threads("nothing like this") == []


def test_a_torn_last_line_is_ignored(tmp_path, journal):
    DoubtLog(tmp_path).add("q", "a", Image.new("RGB", (4, 4)), "m")
    with journal.index.open("a") as f:
        f.write('{"id": "half')
    assert len(journal.entries()) == 1


def test_unknown_fields_from_a_newer_version_are_ignored():
    e = Entry.from_dict({**json.loads(Entry("1", "2026-10-08T10:00:00", "q", "a", "m", "s").to_json()), "new": 1})
    assert e.question == "q"


def test_reopening_maps_the_saved_shot_onto_the_original_screen(tmp_path, journal):
    log = DoubtLog(tmp_path)
    snap = make_snapshot(logical=(1440, 900), cursor=(700, 450))
    log.add("q", "a", Image.new("RGB", (1568, 980)), "m", snap=snap)  # the resized shot, not 2880 wide
    again = journal.snapshot(journal.entries()[0])
    assert again.screen_geo == (0, 0, 1440, 900) and again.cursor == (700, 450)
    assert again.cursor_physical == pytest.approx((700 * 1568 / 1440, 450 * 980 / 900))


def test_old_entries_reopen_as_their_own_screen(tmp_path, journal):
    journal.dir.mkdir()
    (journal.dir / "shots").mkdir()
    Image.new("RGB", (800, 500)).save(journal.dir / "shots" / "20261001-162044.png")
    e = parse_page(OLD_PAGE, "2026-10-01")[0]
    snap = journal.snapshot(e)
    assert snap.screen_geo == (0, 0, 800, 500) and snap.cursor == (400, 250)


def test_a_missing_screenshot_reopens_as_nothing(journal):
    assert journal.snapshot(Entry("1", "2026-10-08T10:00:00", "q", "a", "m", "shots/gone.png")) is None


def test_points_map_to_shot_pixels():
    e = Entry("1", "t", "q", "a", "m", "s", screen=[1440, 0, 1440, 900])
    assert to_image_px(e, (1568, 980), 1440 + 720, 450) == pytest.approx((784, 490))

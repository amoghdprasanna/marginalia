from datetime import datetime

from PIL import Image

from marginalia.doubtlog import DoubtLog


def test_journal_appends_entries_under_one_daily_header(tmp_path):
    log = DoubtLog(tmp_path)
    shot = Image.new("RGB", (10, 10))
    page = log.add("what is d?", "The code distance.", shot, "claude-opus-5-5")
    log.add("why odd?", "So majority vote works.", shot, "claude-opus-5-5")
    text = page.read_text(encoding="utf-8")
    assert page.name == f"{datetime.now():%Y-%m-%d}.md"
    assert text.count("# Doubts,") == 1
    assert "what is d?" in text and "So majority vote works." in text
    shots = sorted((tmp_path / "doubts" / "shots").glob("*.png"))
    assert len(shots) == 2, "each entry keeps its own screenshot, even within the same second"
    assert all(f"shots/{s.name}" in text for s in shots)


def test_saved_case_is_ready_to_label(tmp_path):
    import json

    from helpers import make_snapshot

    snap = make_snapshot(logical=(1440, 900), origin=(1440, 0), cursor=(1440 + 700, 450))
    folder = DoubtLog(tmp_path).save_case(snap, "what is d?", "The distance.", [(1440 + 710.4, 455.6, "d")])
    case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    assert case["screen"] == [1440, 900]
    assert case["cursor"] == [700, 450], "screen-local, like eval cases"
    assert case["model_points"] == [[710, 456, "d"]]
    assert case["targets"] == [] and case["must_mention"] == []
    assert Image.open(folder / case["image"]).size == snap.image.size, "raw physical pixels, no ring"

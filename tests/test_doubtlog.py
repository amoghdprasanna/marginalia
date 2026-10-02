from datetime import datetime

from PIL import Image

from marginalia.doubtlog import DoubtLog


def test_journal_appends_entries_under_one_daily_header(tmp_path):
    log = DoubtLog(tmp_path)
    shot = Image.new("RGB", (10, 10))
    page = log.add("what is d?", "The code distance.", shot, "claude-opus-5")
    log.add("why odd?", "So majority vote works.", shot, "claude-opus-5")
    text = page.read_text()
    assert page.name == f"{datetime.now():%Y-%m-%d}.md"
    assert text.count("# Doubts,") == 1
    assert "what is d?" in text and "So majority vote works." in text
    shots = sorted((tmp_path / "doubts" / "shots").glob("*.png"))
    assert len(shots) == 2, "each entry keeps its own screenshot, even within the same second"
    assert all(f"shots/{s.name}" in text for s in shots)

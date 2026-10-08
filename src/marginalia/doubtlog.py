"""Saves every question, answer and screenshot to a dated Markdown journal you can review later."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from .capture import Snapshot
from .journal import INDEX, Entry


class DoubtLog:
    """Writes the journal: a dated Markdown page for you, and an index line for the journal browser."""

    def __init__(self, root: Path) -> None:
        self.dir = Path(root) / "doubts"
        self.cases_dir = Path(root) / "cases"
        self.last_entry: Entry | None = None

    def add(
        self,
        question: str,
        answer: str,
        screenshot: Image.Image,
        model: str,
        *,
        thread: str = "",
        snap: Snapshot | None = None,
        points: list[tuple[float, float, str]] = (),
    ) -> Path:
        now = datetime.now()
        shots = self.dir / "shots"
        shots.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d-%H%M%S-%f")  # microseconds: quick follow-ups must not collide
        screenshot.save(shots / f"{stamp}.png")
        page = self.dir / f"{now:%Y-%m-%d}.md"
        with page.open("a", encoding="utf-8") as f:
            if f.tell() == 0:
                f.write(f"# Doubts, {now:%A %d %B %Y}\n\n")
            f.write(f"## {now:%H:%M}  {question}\n\n")
            f.write(f"![screen](shots/{stamp}.png)\n\n{answer}\n\n")
            f.write(f"<sub>{model}</sub>\n\n---\n\n")
        entry = Entry(
            id=stamp,
            time=now.isoformat(),
            question=question,
            answer=answer,
            model=model,
            shot=f"shots/{stamp}.png",
            thread=thread,
            screen=list(snap.screen_geo) if snap else None,
            cursor=list(snap.cursor) if snap else None,
            points=[[round(x, 1), round(y, 1), label] for x, y, label in points],
        )
        with (self.dir / INDEX).open("a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")
        self.last_entry = entry
        return page

    def save_case(
        self, snap: Snapshot, question: str, answer: str, points: list[tuple[float, float, str]]
    ) -> Path:
        """Save a ready-to-label eval case: the raw screen (no cursor ring) and a case.json.

        Copy the folder into eval/cases/, then fill in `targets` (boxes the answer should point
        inside) and `must_mention`. `model_points` shows where the model pointed, in the same
        logical coordinates, which is often the quickest way to draw a target box.
        """
        folder = self.cases_dir / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        folder.mkdir(parents=True, exist_ok=True)
        snap.image.save(folder / "screen.png")
        gx, gy, gw, gh = snap.screen_geo
        case = {
            "image": "screen.png",
            "screen": [gw, gh],
            "cursor": [snap.cursor[0] - gx, snap.cursor[1] - gy],
            "question": question,
            "targets": [],
            "must_mention": [],
            "model_answer": answer,
            "model_points": [[round(x - gx), round(y - gy), label] for x, y, label in points],
        }
        (folder / "case.json").write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return folder

"""Saves every question, answer and screenshot to a dated Markdown journal you can review later."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image


class DoubtLog:
    def __init__(self, root: Path) -> None:
        self.dir = Path(root) / "doubts"

    def add(self, question: str, answer: str, screenshot: Image.Image, model: str) -> Path:
        now = datetime.now()
        shots = self.dir / "shots"
        shots.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d-%H%M%S")
        screenshot.save(shots / f"{stamp}.png")
        page = self.dir / f"{now:%Y-%m-%d}.md"
        with page.open("a", encoding="utf-8") as f:
            if f.tell() == 0:
                f.write(f"# Doubts, {now:%A %d %B %Y}\n\n")
            f.write(f"## {now:%H:%M}  {question}\n\n")
            f.write(f"![screen](shots/{stamp}.png)\n\n{answer}\n\n")
            f.write(f"<sub>{model}</sub>\n\n---\n\n")
        return page

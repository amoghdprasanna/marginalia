"""Reading the journal back: past questions grouped into threads, search, and reopening one (ADR 0019).

DoubtLog writes two things per answer: a Markdown page for people and a line in
`doubts/index.jsonl` for this module. Pages written before the index existed are parsed once
into it ("backfilled"), so old questions show up too, just without screen geometry or points.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image

from .capture import Snapshot

log = logging.getLogger(__name__)

INDEX = "index.jsonl"


@dataclass
class Entry:
    id: str  # the screenshot stamp, unique per answer
    time: str  # ISO local time
    question: str
    answer: str
    model: str
    shot: str  # path relative to the doubts folder
    thread: str = ""  # id of the thread's first entry; "" means a thread of its own
    screen: list[int] | None = None  # logical x, y, w, h of the screen asked about
    cursor: list[int] | None = None  # logical cursor position
    points: list[list] = field(default_factory=list)  # [[x, y, label], ...] logical, where markers flew

    @property
    def thread_id(self) -> str:
        return self.thread or self.id

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> Entry:
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class Thread:
    id: str
    entries: list[Entry]

    @property
    def first(self) -> Entry:
        return self.entries[0]

    @property
    def last(self) -> Entry:
        return self.entries[-1]

    def history(self, turns: int) -> list[tuple[str, str]]:
        return [(e.question, e.answer) for e in self.entries][-turns:]

    def matches(self, text: str) -> bool:
        t = text.lower()
        return any(t in e.question.lower() or t in e.answer.lower() for e in self.entries)


# The page format DoubtLog writes (and wrote before the index existed).
_PAGE_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_HEADING = re.compile(r"^## (\d{2}:\d{2})  (.*)$", re.M)
_SHOT = re.compile(r"!\[screen\]\((shots/([0-9-]+)\.png)\)")
_MODEL = re.compile(r"<sub>(.*?)</sub>\s*$", re.S)


def parse_page(text: str, day: str) -> list[Entry]:
    """Entries from one Markdown page. Tolerant: a block it can't read is skipped, not fatal."""
    out = []
    blocks = text.split("\n---\n")
    for block in blocks:
        head = _HEADING.search(block)
        shot = _SHOT.search(block)
        if head is None or shot is None:
            continue
        body = block[shot.end() :].strip()
        model_m = _MODEL.search(body)
        model = model_m.group(1) if model_m else ""
        answer = body[: model_m.start()].strip() if model_m else body
        stamp = shot.group(2)
        try:  # the stamp has seconds (and microseconds since 2026-10-02); fall back to the heading
            when = datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S")
        except ValueError:
            when = datetime.fromisoformat(f"{day}T{head.group(1)}")
        out.append(Entry(stamp, when.isoformat(), head.group(2).strip(), answer, model, shot.group(1)))
    return out


class Journal:
    """Everything in <log dir>/doubts, read from the index."""

    def __init__(self, root: Path) -> None:
        self.dir = Path(root) / "doubts"
        self.index = self.dir / INDEX

    def backfill(self) -> int:
        """Index the pages written before the index existed. Returns how many entries were added."""
        known = {e.id for e in self._read_index()}
        added = []
        for page in sorted(self.dir.glob("*.md")) if self.dir.exists() else []:
            m = _PAGE_DAY.match(page.name)
            if not m:
                continue
            try:
                entries = parse_page(page.read_text(encoding="utf-8"), m.group(1))
            except OSError as exc:
                log.warning("Could not read %s: %s", page, exc)
                continue
            added += [e for e in entries if e.id not in known]
        if added:
            added.sort(key=lambda e: e.time)
            with self.index.open("a", encoding="utf-8") as f:
                for e in added:
                    f.write(e.to_json() + "\n")
            log.info("Indexed %d older journal entries", len(added))
        return len(added)

    def _read_index(self) -> list[Entry]:
        try:
            lines = self.index.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in lines:
            try:
                out.append(Entry.from_dict(json.loads(line)))
            except (ValueError, TypeError):
                continue  # a half-written last line after a crash
        return out

    def entries(self) -> list[Entry]:
        return sorted(self._read_index(), key=lambda e: e.time)

    def threads(self, search: str = "") -> list[Thread]:
        """Newest thread first; with `search`, only threads where some question or answer contains it."""
        groups: dict[str, list[Entry]] = {}
        for e in self.entries():
            groups.setdefault(e.thread_id, []).append(e)
        threads = [Thread(tid, es) for tid, es in groups.items()]
        if search.strip():
            threads = [t for t in threads if t.matches(search.strip())]
        return sorted(threads, key=lambda t: t.last.time, reverse=True)

    def image(self, entry: Entry) -> Image.Image | None:
        try:
            with Image.open(self.dir / entry.shot) as img:
                return img.convert("RGB")
        except (OSError, ValueError):
            return None

    def snapshot(self, entry: Entry) -> Snapshot | None:
        """The saved screen as a Snapshot, to ask a follow-up about it.

        The shot is the resized image the model saw, so it maps onto the original logical
        screen at a different scale; Snapshot only needs the ratio. Old entries have no
        geometry: treat the image as the screen, one pixel per point.
        """
        img = self.image(entry)
        if img is None:
            return None
        if entry.screen and entry.cursor:
            return Snapshot(img, tuple(entry.screen), tuple(entry.cursor))
        return Snapshot(img, (0, 0, img.width, img.height), (img.width // 2, img.height // 2))


def to_image_px(entry: Entry, img_size: tuple[int, int], x: float, y: float) -> tuple[float, float]:
    """A logical point recorded with an entry -> pixels of its saved shot (for drawing markers)."""
    if not entry.screen:
        return (x, y)
    gx, gy, gw, gh = entry.screen
    return ((x - gx) * img_size[0] / gw, (y - gy) * img_size[1] / gh)

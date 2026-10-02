"""Measure accuracy before polishing anything else.

Each case is a folder with a screenshot and a case.json:
  image         screenshot file (any resolution; physical pixels)
  screen        [w, h] logical size of that screen (e.g. [1440, 900] for a 2x laptop)
  cursor        [x, y] logical cursor position when you asked
  question      what you asked
  targets       list of [x1, y1, x2, y2] logical boxes; a point inside any of them is a hit
  must_mention  strings the answer should contain (case-insensitive)

Build cases from your own reading: when an answer is wrong, save the screenshot from
~/Marginalia/doubts/shots and write a case for it. Then:
  python eval/run_eval.py             # all cases with the configured model
  python eval/run_eval.py --no-ocr    # compare with OCR switched off
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from marginalia.brain import ClaudeBrain, DemoBrain  # noqa: E402
from marginalia.capture import Snapshot, prepare  # noqa: E402
from marginalia.config import load_config  # noqa: E402
from marginalia.ocr import OCR  # noqa: E402
from marginalia.pointing import resolve_points  # noqa: E402

MARGIN = 12  # logical px of slack around each target box


def run_case(folder: Path, brain, ocr, hires: bool) -> dict:
    case = json.loads((folder / "case.json").read_text())
    img = Image.open(folder / case["image"]).convert("RGB")
    w, h = case["screen"]
    snap = Snapshot(img, (0, 0, w, h), tuple(case["cursor"]))
    lines = ocr.read(img) if ocr else []
    prep = prepare(snap, hires=hires)
    t0 = time.time()
    ans = brain.ask(prep, lines, case["question"], [])
    pts = resolve_points(prep, snap, lines, ans.points)

    def inside(x, y, box):
        x1, y1, x2, y2 = box
        return x1 - MARGIN <= x <= x2 + MARGIN and y1 - MARGIN <= y <= y2 + MARGIN

    first_hit = bool(pts) and any(inside(pts[0][0], pts[0][1], b) for b in case.get("targets", []))
    any_hit = any(inside(x, y, b) for x, y, _ in pts for b in case.get("targets", []))
    wanted = case.get("must_mention", [])
    mentioned = [m for m in wanted if m.lower() in ans.text.lower()]
    return {
        "case": folder.name,
        "first_point_hit": first_hit,
        "any_point_hit": any_hit,
        "mentions": f"{len(mentioned)}/{len(wanted)}",
        "seconds": round(time.time() - t0, 1),
        "points": [(round(x), round(y), label) for x, y, label in pts],
        "answer": ans.text,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="?", default=str(Path(__file__).parent / "cases"))
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--demo", action="store_true", help="check the harness itself without an API key")
    args = ap.parse_args()

    cfg = load_config(demo=args.demo, no_ocr=args.no_ocr)
    brain = DemoBrain() if cfg.demo else ClaudeBrain(cfg)
    ocr = OCR() if cfg.ocr_enabled else None
    if ocr is not None and not ocr.available:
        ocr = None
    folders = sorted(p.parent for p in Path(args.cases).glob("*/case.json"))
    results = []
    for f in folders:
        r = run_case(f, brain, ocr, cfg.hires)
        results.append(r)
        print(f"{r['case']:<32} first-hit={str(r['first_point_hit']):<5} any-hit={str(r['any_point_hit']):<5} "
              f"mentions={r['mentions']:<5} {r['seconds']}s")
    if results:
        n = len(results)
        print(f"\n{cfg.model if not cfg.demo else 'demo'}, OCR {'on' if ocr else 'off'}: "
              f"first-point hit {sum(r['first_point_hit'] for r in results)}/{n}, "
              f"any-point hit {sum(r['any_point_hit'] for r in results)}/{n}")
        out = Path(args.cases) / f"results-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Details: {out}")


if __name__ == "__main__":
    main()

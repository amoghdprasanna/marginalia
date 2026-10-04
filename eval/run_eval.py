"""Measure answer quality, speed and cost before changing prompts, models or effort.

Each case is a folder with a screenshot and a case.json:
  image         screenshot file (any resolution; physical pixels)
  screen        [w, h] logical size of that screen (e.g. [1440, 900] for a 2x laptop)
  cursor        [x, y] logical cursor position when you asked
  question      what you asked
  targets       list of [x1, y1, x2, y2] logical boxes; a point inside any of them is a hit
  must_mention  strings the answer should contain (case-insensitive)

Getting cases: set MARGINALIA_SAVE_CASES=1 and use the app normally. Every question is saved
under ~/Marginalia/cases/ with its raw screenshot and a case.json to finish labelling (fill in
targets and must_mention; model_points shows where the model pointed). Copy the good ones here.

  python eval/run_eval.py                          # every case, configured model and effort
  python eval/run_eval.py --effort low             # one setting of a sweep
  python eval/run_eval.py --model claude-sonnet-5-5 --repeat 3
  python eval/run_eval.py --no-ocr                 # does OCR earn its keep?
  python eval/run_eval.py --demo                   # check the harness itself, no API key

Every run costs real API calls (the summary prints how much). Results go to eval/results/.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from marginalia.brain import ClaudeBrain, DemoBrain, Usage
from marginalia.capture import Snapshot, prepare
from marginalia.config import load_config
from marginalia.ocr import OCR
from marginalia.pointing import resolve_points

MARGIN = 12  # logical px of slack around each target box

# USD per million tokens: (input, output, cache read). Cache writes (5-minute TTL) cost 1.25x input.
# Copied from the pricing page on 2026-10-04; check it before trusting a cost comparison.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}


def cost_usd(model: str, usage: Usage | None) -> float | None:
    """What one call cost, or None when the model's price or the usage is unknown."""
    if usage is None or model not in PRICES:
        return None
    pin, pout, pread = PRICES[model]
    tokens = usage.input_tokens * pin + usage.cache_write * pin * 1.25 + usage.cache_read * pread
    return (tokens + usage.output_tokens * pout) / 1_000_000


def _inside(x: float, y: float, box) -> bool:
    x1, y1, x2, y2 = box
    return x1 - MARGIN <= x <= x2 + MARGIN and y1 - MARGIN <= y <= y2 + MARGIN


def score(case: dict, text: str, points: list[tuple[float, float, str]]) -> dict:
    """Pointing and content checks for one answer. Points are logical, screen-local."""
    targets = case.get("targets", [])
    wanted = case.get("must_mention", [])
    return {
        "first_point_hit": bool(points) and any(_inside(points[0][0], points[0][1], b) for b in targets),
        "any_point_hit": any(_inside(x, y, b) for x, y, _ in points for b in targets),
        "mentioned": sum(m.lower() in text.lower() for m in wanted),
        "must_mention": len(wanted),
    }


def run_case(folder: Path, brain, ocr, hires: bool) -> dict:
    case = json.loads((folder / "case.json").read_text())
    img = Image.open(folder / case["image"]).convert("RGB")
    w, h = case["screen"]
    snap = Snapshot(img, (0, 0, w, h), tuple(case["cursor"]))
    lines = ocr.read(img) if ocr else []
    prep = prepare(snap, hires=hires)
    ans = brain.ask(prep, lines, case["question"], [])
    pts = resolve_points(prep, snap, lines, ans.points)
    return {
        "case": folder.name,
        **score(case, ans.text, pts),
        "first_text_s": None if ans.first_text is None else round(ans.first_text, 2),
        "seconds": round(ans.elapsed, 2),
        "model": ans.model,
        "usage": asdict(ans.usage) if ans.usage else None,
        "cost_usd": cost_usd(ans.model, ans.usage),
        "points": [(round(x), round(y), label) for x, y, label in pts],
        "answer": ans.text,
    }


def _p90(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(0.9 * (len(xs) - 1)))]


def summarize(results: list[dict]) -> dict:
    n = len(results)
    first = [r["first_text_s"] for r in results if r["first_text_s"] is not None]
    total = [r["seconds"] for r in results]
    costs = [r["cost_usd"] for r in results if r["cost_usd"] is not None]
    usages = [r["usage"] for r in results if r["usage"]]

    def mean_of(key):
        return round(statistics.mean(u[key] for u in usages)) if usages else None

    return {
        "runs": n,
        "first_point_hit": sum(r["first_point_hit"] for r in results) / n,
        "any_point_hit": sum(r["any_point_hit"] for r in results) / n,
        "must_mention": sum(r["mentioned"] for r in results) / max(1, sum(r["must_mention"] for r in results)),
        "first_text_median_s": statistics.median(first) if first else None,
        "first_text_p90_s": _p90(first) if first else None,
        "total_median_s": statistics.median(total),
        "total_p90_s": _p90(total),
        "cost_mean_usd": statistics.mean(costs) if costs else None,
        "input_tokens_mean": mean_of("input_tokens"),
        "output_tokens_mean": mean_of("output_tokens"),
        "cache_read_mean": mean_of("cache_read"),
    }


def format_summary(s: dict, label: str) -> str:
    def secs(a, b):
        return "n/a" if a is None else f"median {a:.1f}s, p90 {b:.1f}s"

    cost = "unknown (model not in PRICES)" if s["cost_mean_usd"] is None else f"${s['cost_mean_usd']:.4f} per question"
    return "\n".join(
        [
            f"{label}: {s['runs']} runs",
            f"  first-point hit  {s['first_point_hit']:.0%}",
            f"  any-point hit    {s['any_point_hit']:.0%}",
            f"  must-mention     {s['must_mention']:.0%}",
            f"  first words      {secs(s['first_text_median_s'], s['first_text_p90_s'])}",
            f"  complete         {secs(s['total_median_s'], s['total_p90_s'])}",
            f"  cost             {cost}",
            f"  tokens (mean)    in {s['input_tokens_mean']}, out {s['output_tokens_mean']}, "
            f"cache read {s['cache_read_mean']}",
        ]
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cases", nargs="?", default=str(Path(__file__).parent / "cases"))
    ap.add_argument("--model", help="override MARGINALIA_MODEL for this run")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="override MARGINALIA_EFFORT")
    ap.add_argument("--repeat", type=int, default=1, help="run each case N times (answers vary run to run)")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--demo", action="store_true", help="check the harness itself without an API key")
    args = ap.parse_args()

    cfg = load_config(demo=args.demo, no_ocr=args.no_ocr)
    cfg.model = args.model or cfg.model
    cfg.effort = args.effort or cfg.effort
    brain = DemoBrain(delay=0) if cfg.demo else ClaudeBrain(cfg)
    ocr = OCR() if cfg.ocr_enabled else None
    if ocr is not None and not ocr.available:
        ocr = None
    folders = sorted(p.parent for p in Path(args.cases).glob("*/case.json"))
    if not folders:
        raise SystemExit(f"No cases in {args.cases}")

    results = []
    for f in folders:
        for _ in range(args.repeat):
            r = run_case(f, brain, ocr, cfg.hires)
            results.append(r)
            cost = "" if r["cost_usd"] is None else f" ${r['cost_usd']:.4f}"
            print(
                f"{r['case']:<32} first-hit={str(r['first_point_hit']):<5} any-hit={str(r['any_point_hit']):<5} "
                f"mentions={r['mentioned']}/{r['must_mention']} first-words={r['first_text_s']}s "
                f"done={r['seconds']}s{cost}"
            )

    label = f"{'demo' if cfg.demo else cfg.model}, effort {cfg.effort}, OCR {'on' if ocr else 'off'}"
    summary = summarize(results)
    print("\n" + format_summary(summary, label))
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{'demo' if cfg.demo else cfg.model}-{cfg.effort}.json"
    run = {"model": cfg.model, "effort": cfg.effort, "ocr": bool(ocr), "summary": summary, "results": results}
    (out_dir / name).write_text(json.dumps(run, indent=2, ensure_ascii=False))
    print(f"Details: {out_dir / name}")


if __name__ == "__main__":
    main()

"""The eval harness's own arithmetic: hits, mentions, cost and the summary. No API calls."""

from pathlib import Path

import pytest
from run_eval import PRICES, cost_usd, run_case, score, summarize

from marginalia.brain import DemoBrain, Usage

CASES = Path(__file__).resolve().parents[1] / "eval" / "cases"


def test_score_counts_hits_with_a_margin_and_mentions():
    case = {"targets": [[100, 100, 200, 120]], "must_mention": ["distance", "(d+1)/2"]}
    s = score(case, "The code DISTANCE sets it.", [(50, 50, "miss"), (210, 110, "near enough")])
    assert s == {"first_point_hit": False, "any_point_hit": True, "mentioned": 1, "must_mention": 2}


def test_no_points_is_no_hit():
    assert not score({"targets": [[0, 0, 10, 10]]}, "x", [])["first_point_hit"]


def test_cost_prices_every_kind_of_token():
    pin, pout, pread = PRICES["claude-opus-5-5"]
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read=1_000_000, cache_write=1_000_000)
    assert cost_usd("claude-opus-5-5", u) == pytest.approx(pin + pout + pread + 1.25 * pin)


def test_cost_is_unknown_rather_than_wrong():
    assert cost_usd("some-new-model", Usage(1, 1)) is None
    assert cost_usd("claude-opus-5-5", None) is None


def test_summary_rates_and_latency():
    def r(hit, first, total, cost):
        usage = {"input_tokens": 3000, "output_tokens": 300, "cache_read": 0, "cache_write": 0}
        return {"first_point_hit": hit, "any_point_hit": hit, "mentioned": 1, "must_mention": 2,
                "first_text_s": first, "seconds": total, "cost_usd": cost, "usage": usage}

    s = summarize([r(True, 1.0, 4.0, 0.02), r(False, 2.0, 6.0, 0.04)])
    assert s["first_point_hit"] == 0.5 and s["must_mention"] == 0.5
    assert s["first_text_median_s"] == 1.5 and s["total_median_s"] == 5.0
    assert s["cost_mean_usd"] == pytest.approx(0.03) and s["input_tokens_mean"] == 3000


def test_sample_case_runs_end_to_end_in_demo_mode():
    r = run_case(CASES / "surface_code_exponent", DemoBrain(delay=0), None, hires=False)
    assert r["first_point_hit"], "the demo points at the cursor, which sits on the target"
    assert r["cost_usd"] is None and r["answer"]

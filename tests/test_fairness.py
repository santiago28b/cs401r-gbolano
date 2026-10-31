"""
NorthStar Retail — Fairness check (manual slice evaluation by loyalty tier)
CS 401R Lab 4, Task 1

Reads the same evaluation_metrics.json as tests/test_model.py
(EVAL_METRICS_PATH). churn_model.train() writes per-tier results into it under
"slice_results": recall@top10% for each tier, using the GLOBAL top-10% cutoff
(the same contact list the business would actually send).

Policy: FLAG, do not block. If the recall gap between the best and worst
loyalty tier is more than 10 percentage points, the test emits a warning
(visible in the build log through `pytest -rw`) so the human approver sees it
before approving. Tiers with fewer than MIN_SLICE_POSITIVES churners in the
validation set are reported but left out of the gap, because their recall is
too noisy to act on (Platinum has ~6 churners in a 3,000-row test set).

The tests that DO fail are contract checks: if the slice results are missing
or malformed, the fairness check never ran, and that must not read as a pass.

Run locally:
    EVAL_METRICS_PATH=/tmp/out/evaluation_metrics.json pytest tests/test_fairness.py -v -rw
"""

import json
import os
import warnings
from pathlib import Path

import pytest

TIERS = {"Bronze", "Silver", "Gold", "Platinum"}
MAX_RECALL_GAP = 0.10          # 10 percentage points
MIN_SLICE_POSITIVES = 30


class FairnessFlag(UserWarning):
    """Raised as a warning, not an error: fairness flags, it does not block."""


@pytest.fixture(scope="module")
def slice_results():
    path = os.environ.get("EVAL_METRICS_PATH", "/tmp/eval_metrics.json")
    if not Path(path).exists():
        pytest.skip(f"Evaluation metrics not found at {path} (set EVAL_METRICS_PATH).")
    with open(path) as f:
        metrics = json.load(f)
    assert "slice_results" in metrics, (
        "evaluation_metrics.json has no slice_results. churn_model.train() must "
        "put per-tier results in its metrics dict, or the fairness check cannot run.")
    return metrics["slice_results"]


def _gap(slice_results):
    usable = {t: r["recall_top10"] for t, r in slice_results.items()
              if r["positives"] >= MIN_SLICE_POSITIVES}
    if len(usable) < 2:
        return None, usable
    return max(usable.values()) - min(usable.values()), usable


class TestFairness:

    def test_every_tier_is_evaluated(self, slice_results):
        missing = TIERS - set(slice_results)
        assert not missing, f"No slice results for tiers: {sorted(missing)}"

    def test_slice_results_are_valid(self, slice_results):
        for tier, r in slice_results.items():
            assert 0.0 <= r["recall_top10"] <= 1.0, f"{tier} recall out of [0, 1]"
            assert r["n"] > 0, f"{tier} has no validation rows"
            assert 0 <= r["positives"] <= r["n"], f"{tier} positives > n"

    def test_enough_tiers_to_compare(self, slice_results):
        gap, usable = _gap(slice_results)
        assert gap is not None, (
            f"Fewer than 2 tiers have >= {MIN_SLICE_POSITIVES} churners in the "
            f"validation set ({usable}); the recall gap cannot be measured.")

    def test_recall_gap_between_tiers(self, slice_results):
        """FLAG (warning) if best-vs-worst tier recall differs by > 10 pp."""
        gap, usable = _gap(slice_results)
        if gap is None:
            pytest.skip("not enough tiers with enough churners")
        best = max(usable, key=usable.get)
        worst = min(usable, key=usable.get)
        summary = ", ".join(f"{t} {r:.1%}" for t, r in sorted(usable.items()))
        small = [t for t, r in slice_results.items() if r["positives"] < MIN_SLICE_POSITIVES]
        print(f"\nRecall@top10% by tier: {summary}; gap {gap:.1%}"
              + (f"; too small to judge: {small}" if small else ""))
        if gap > MAX_RECALL_GAP:
            warnings.warn(
                f"FAIRNESS FLAG: recall@top10% gap {gap:.1%} between {best} "
                f"({usable[best]:.1%}) and {worst} ({usable[worst]:.1%}) exceeds "
                f"{MAX_RECALL_GAP:.0%}. Review before approving this model.",
                FairnessFlag)

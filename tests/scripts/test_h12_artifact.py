"""Artifact-level tests for `scripts/l22_evidence/h12.py`: the
`compare_predictions`/`decide_verdict`/`write_artifact` pipeline, covering
the 100%-match, 99%-match (nontrivial mismatch), zero-nontrivial-sample,
and fresh-clone-reproducibility cases required by the task's test
checklist -- all using small synthetic `UnitPrediction`/`before`/`after`
data (never real oracle I/O, so these run in well under a second).

Distinct from:
  - `tests/scripts/test_h12_formulas.py` (predictor-formula arithmetic unit
    tests against hand-computed expected deltas)
  - `tests/scripts/test_h12_anticheat.py` (AST-based anti-laundering guard
    on `h12.py` itself)
  - `tests/scripts/test_l22_evidence_verdict.py` /
    `test_h12_evidence_wiring.py` (verdict.py's `h12_support_reason` /
    generator.py's side-index consumption of an H12 artifact)

Run via `bin\\oc-pytest tests/scripts/test_h12_artifact.py -v`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12  # noqa: E402


def _prediction(seed, tick, *, nontrivial=True, delta=None) -> h12.UnitPrediction:
    return h12.UnitPrediction(
        seed=seed,
        tick=tick,
        unit="all",
        regime_valid=True,
        regime_reason="test_regime",
        nontrivial=nontrivial,
        predicted_delta={"channel_a": np.asarray(delta if delta is not None else [1.0, 2.0])},
    )


def _before_after(n_ticks: int, width: int, *, mismatch_ticks: frozenset[int] = frozenset()) -> tuple[dict, dict]:
    """`before`/`after` where `after - before == [1.0, 2.0, ...]` (matching
    `_prediction`'s default delta) for every tick NOT in `mismatch_ticks`,
    and a deliberately wrong delta for every tick that IS."""
    before = {"channel_a": np.zeros((n_ticks, width))}
    after = {"channel_a": np.zeros((n_ticks, width))}
    base_delta = np.arange(1, width + 1, dtype=np.float64)
    for t in range(n_ticks):
        after["channel_a"][t] = before["channel_a"][t] + (
            base_delta + 1000.0 if t in mismatch_ticks else base_delta
        )
    return before, after


# ---------------------------------------------------------------------------
# compare_predictions: 100% match
# ---------------------------------------------------------------------------


def test_compare_predictions_100_percent_match():
    before, after = _before_after(5, 2)
    predictions = [_prediction(seed=0, tick=t) for t in range(5)]
    result = h12.compare_predictions("FakeProcess", predictions, after, before)
    assert result["total_sample_count"] == 5
    assert result["nontrivial_sample_count"] == 5
    assert result["exact_match_count"] == 5
    assert result["exact_match_rate"] == 1.0
    assert result["mismatch_examples"] == []
    assert result["trivial_mismatch_count"] == 0
    verdict, reason = h12.decide_verdict(
        result["nontrivial_sample_count"],
        result["exact_match_count"],
        result["exact_match_rate"],
        result["trivial_mismatch_count"],
        result["branches_confirmed"],
        frozenset(),  # no required branches registered for this synthetic "FakeProcess"
    )
    assert verdict == "H12_CONFIRMED"
    assert "100% exact match" in reason


# ---------------------------------------------------------------------------
# compare_predictions: nontrivial mismatch (e.g. 99/100 -> H12_FAIL)
# ---------------------------------------------------------------------------


def test_compare_predictions_single_mismatch_out_of_100_fails_no_tolerance():
    n = 100
    before, after = _before_after(n, 2, mismatch_ticks=frozenset({42}))
    predictions = [_prediction(seed=0, tick=t) for t in range(n)]
    result = h12.compare_predictions("FakeProcess", predictions, after, before)
    assert result["total_sample_count"] == n
    assert result["nontrivial_sample_count"] == n
    assert result["exact_match_count"] == n - 1
    assert result["exact_match_rate"] == 0.99
    assert len(result["mismatch_examples"]) == 1
    assert result["mismatch_examples"][0]["tick"] == 42
    assert result["mismatch_examples"][0]["channel"] == "channel_a"
    verdict, reason = h12.decide_verdict(
        result["nontrivial_sample_count"],
        result["exact_match_count"],
        result["exact_match_rate"],
        result["trivial_mismatch_count"],
        result["branches_confirmed"],
        frozenset(),
    )
    # No tolerance: 99% is still a hard H12_FAIL, never silently rounded up.
    assert verdict == "H12_FAIL"
    assert "0.990000" in reason


# ---------------------------------------------------------------------------
# compare_predictions: zero nontrivial samples
# ---------------------------------------------------------------------------


def test_compare_predictions_zero_nontrivial_samples_is_h12_fail():
    n = 10
    before = {"channel_a": np.zeros((n, 2))}
    after = {"channel_a": np.zeros((n, 2))}  # no-op deltas everywhere
    predictions = [_prediction(seed=0, tick=t, nontrivial=False, delta=[0.0, 0.0]) for t in range(n)]
    result = h12.compare_predictions("FakeProcess", predictions, after, before)
    assert result["nontrivial_sample_count"] == 0
    assert result["exact_match_rate"] is None
    verdict, reason = h12.decide_verdict(
        result["nontrivial_sample_count"],
        result["exact_match_count"],
        result["exact_match_rate"],
        result["trivial_mismatch_count"],
        result["branches_confirmed"],
        frozenset(),
    )
    assert verdict == "H12_FAIL"
    assert "nontrivial_sample_count==0" in reason


def test_compare_predictions_trivial_predictions_are_still_correctness_checked():
    """A trivial (nontrivial=False) prediction whose predicted (zero) delta
    does NOT match the actual delta must be caught as a `trivial_mismatch`
    (excluded from the headline nontrivial rate, but never silently
    ignored -- this is how a guard bug that wrongly predicts "nothing
    happens" would be caught), and it must hard-fail the verdict
    unconditionally, regardless of the nontrivial match rate."""
    n = 3
    before = {"channel_a": np.zeros((n, 2))}
    after = {"channel_a": np.zeros((n, 2))}
    after["channel_a"][1] = [5.0, 5.0]  # tick 1 actually changed, contradicting the trivial prediction
    predictions = [_prediction(seed=0, tick=t, nontrivial=False, delta=[0.0, 0.0]) for t in range(n)]
    result = h12.compare_predictions("FakeProcess", predictions, after, before)
    assert result["nontrivial_sample_count"] == 0
    assert result["trivial_mismatch_count"] == 1
    assert any(m["tick"] == 1 for m in result["trivial_mismatch_examples"])
    verdict, reason = h12.decide_verdict(
        result["nontrivial_sample_count"],
        result["exact_match_count"],
        result["exact_match_rate"],
        result["trivial_mismatch_count"],
        result["branches_confirmed"],
        frozenset(),
    )
    assert verdict == "H12_FAIL"
    assert "trivial_mismatch_count=1" in reason


# ---------------------------------------------------------------------------
# compare_predictions: index_mask scoping (the MacromolecularComplexation
# "814 false failures" regression fix)
# ---------------------------------------------------------------------------


def test_compare_predictions_index_mask_ignores_other_units_activity():
    """Two units in the SAME tick each own disjoint index slices of the
    SAME channel (mirrors MacromolecularComplexation's network_1/network_2
    both writing into the shared `substrates` array). Unit A's `index_mask`
    must scope its comparison to ONLY its own indices; a real, nonzero
    actual delta at unit B's (unmasked-by-A) indices must NOT be treated as
    a mismatch for unit A. This regression-tests the compare-scoping bug
    that previously produced false failures when a full-width compare saw
    a different unit's legitimate activity."""
    before = {"substrates": np.zeros((1, 4))}
    after = {"substrates": np.zeros((1, 4))}
    # unit A (network_1) owns indices [0, 1]; predicts delta -10 at idx0, -5 at idx1
    # unit B (network_2) owns indices [2, 3]; predicts delta -30 at idx2, -3 at idx3
    after["substrates"][0] = [-10.0, -5.0, -30.0, -3.0]
    pred_a = h12.UnitPrediction(
        seed=0,
        tick=0,
        unit="network_1",
        regime_valid=True,
        regime_reason="test",
        nontrivial=True,
        predicted_delta={"substrates": np.array([-10.0, -5.0, 0.0, 0.0])},
        index_mask={"substrates": np.array([0, 1])},
    )
    pred_b = h12.UnitPrediction(
        seed=0,
        tick=0,
        unit="network_2",
        regime_valid=True,
        regime_reason="test",
        nontrivial=True,
        predicted_delta={"substrates": np.array([0.0, 0.0, -30.0, -3.0])},
        index_mask={"substrates": np.array([2, 3])},
    )
    result = h12.compare_predictions("FakeProcess", [pred_a, pred_b], after, before)
    # Without index_mask scoping, unit A's full-width predicted_delta
    # ([-10,-5,0,0]) would mismatch the real full-width actual delta
    # ([-10,-5,-30,-3]) at indices 2/3 -- a false failure. Scoped, both
    # units match on their own indices only.
    assert result["nontrivial_sample_count"] == 2
    assert result["exact_match_count"] == 2
    assert result["exact_match_rate"] == 1.0
    assert result["mismatch_examples"] == []


# ---------------------------------------------------------------------------
# decide_verdict: incomplete required branch coverage -> H12_OBSERVED_REGIME
# ---------------------------------------------------------------------------


def test_decide_verdict_missing_required_branch_is_observed_regime_not_confirmed():
    """100% exact match on every nontrivial sample is necessary but NOT
    sufficient for H12_CONFIRMED: if a `REQUIRED_BRANCHES`-registered
    dynamical regime was never exercised (never appears in
    `branches_confirmed`), the correct verdict is the non-gating
    `H12_OBSERVED_REGIME`, not `H12_CONFIRMED` -- this is the mechanism
    that permanently caps MacromolecularComplexation (network>=2 never
    fires) and ProteinProcessingII (transferase never fires) below
    H12_CONFIRMED even at a perfect match rate."""
    verdict, reason = h12.decide_verdict(
        100,
        100,
        1.0,
        0,
        {"branch_a"},
        frozenset({"branch_a", "branch_b"}),
    )
    assert verdict == "H12_OBSERVED_REGIME"
    assert "branch_b" in reason


def test_decide_verdict_full_branch_coverage_confirms():
    verdict, reason = h12.decide_verdict(
        100,
        100,
        1.0,
        0,
        {"branch_a", "branch_b"},
        frozenset({"branch_a", "branch_b"}),
    )
    assert verdict == "H12_CONFIRMED"


# ---------------------------------------------------------------------------
# write_artifact: round-trips to disk
# ---------------------------------------------------------------------------


def test_write_artifact_round_trips_to_disk(tmp_path):
    artifact = {
        "process": "FakeProcess",
        "verdict": "H12_CONFIRMED",
        "nontrivial_sample_count": 7,
        "exact_match_rate": 1.0,
    }
    out_path = h12.write_artifact(artifact, out_dir=tmp_path)
    assert out_path == tmp_path / "FakeProcess_h12.json"
    reloaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert reloaded == artifact


# ---------------------------------------------------------------------------
# Fresh-clone reproducibility: identical inputs -> identical prediction hash
# ---------------------------------------------------------------------------


def test_predictor_hash_is_reproducible_across_independent_calls():
    """Reruns `predict_trna_aminoacylation` on frozen, hand-constructed
    synthetic inputs TWICE (simulating "fresh clone, rerun from scratch")
    and confirms the SAME per-tick-prediction hashing formula `run_h12`
    uses (channel array -> sha256, joined per unit/tick) yields a
    byte-identical digest both times -- proving no hidden nondeterminism
    (dict/set iteration order, uninitialized memory, etc.) leaks into the
    frozen prediction record before `states_after` is ever read."""
    fixture = {
        "substrateIndexs_water_0b": 0,
        "substrateIndexs_hydrogen_0b": 1,
        "speciesIndexs_enzymes_0b": np.array([0]),
        "speciesReactantByproductMatrix": np.array(
            [
                [0.0, 0.0, 1.0, 2.0, 9.0, 0.0],
                [0.0, 0.0, 2.0, 1.0, 0.0, 9.0],
            ]
        ),
        "reactionStoichiometryMatrix": np.array([[-1.0, 0.0], [0.0, -1.0], [1.0, 1.0]]),
        "reactionModificationMatrix": np.array([[1.0, 0.0], [0.0, 1.0]]),
    }
    before = {
        "freeRNAs": np.array([[5.0, 7.0], [3.0, 0.0]]),
        "aminoacylatedRNAs": np.array([[0.0, 0.0], [0.0, 0.0]]),
        "substrates": np.array([[100.0, 100.0, 100.0], [100.0, 100.0, 100.0]]),
        "enzymes": np.array([[100.0], [100.0]]),
    }

    def _hash_predictions(preds: list[h12.UnitPrediction]) -> str:
        parts = [
            f"{p.seed}:{p.tick}:{p.unit}:{p.regime_valid}:{p.nontrivial}:"
            + ",".join(
                f"{k}={h12._sha256_array(v)}"
                for k, v in sorted(p.predicted_delta.items())
                if isinstance(v, np.ndarray)
            )
            for p in preds
        ]
        return h12._sha256_bytes("\n".join(parts).encode("utf-8"))

    preds_1 = h12.predict_trna_aminoacylation(seed=0, before=before, fixture=fixture)
    preds_2 = h12.predict_trna_aminoacylation(seed=0, before=before, fixture=fixture)
    assert _hash_predictions(preds_1) == _hash_predictions(preds_2)

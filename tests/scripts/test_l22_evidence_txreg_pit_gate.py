"""Dedicated unit tests for `scripts/l22_evidence/txreg_pit_gate.py` (the
2026-09-08 rewrite of TranscriptionalRegulation's rejected L2.2
preregistration -- see
`docs/phase_f/l2_2_design_a/TRANSCRIPTIONALREGULATION_ACTIVE_WINDOW_PREREG.md`).

Most tests here use small, synthetic `CompetitionEvent` objects (never the
real 4000-tick trace, which is slow to walk) to test the PIT/KS machinery,
the post-mask renormalization, the randomized-vs-mid-P distinction, the
weight-law positive controls, and the evidence-bundle writer in isolation.
`test_extract_competition_events_against_real_genuine_trace` is the one
slower, real-trace integration test, skipped if the (gitignored,
regenerate-on-demand) trace file is not present in this checkout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_evidence import txreg_pit_gate as gate


def _event(
    *,
    tick: int = 0,
    tf_i: int = 0,
    tf_wid: str = "TF_A",
    weights: list[float],
    accessible_mask: list[bool] | None = None,
    winner_local_indices: list[int],
) -> gate.CompetitionEvent:
    return gate.CompetitionEvent(
        tick=tick,
        tf_i=tf_i,
        tf_wid=tf_wid,
        n_candidates=len(weights),
        weights=weights,
        accessible_mask=accessible_mask if accessible_mask is not None else [True] * len(weights),
        winner_local_indices=winner_local_indices,
    )


# ---------------------------------------------------------------------------
# compute_pit_values: basic correctness
# ---------------------------------------------------------------------------


def test_single_candidate_certain_winner_gets_pit_near_full_range() -> None:
    # A single ACCESSIBLE candidate that wins should map to PIT covering
    # the whole [0,1) range (mid-P exactly 0.5, randomized uniform over
    # [0,1)) since it is the only, certain, event.
    events = [_event(weights=[5.0], winner_local_indices=[0])]
    result = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert result.n_pooled_values == 1
    assert result.mid_p_pit_values == [0.5]
    assert 0.0 <= result.randomized_pit_values[0] < 1.0


def test_two_candidate_equal_weight_winner0_mid_p_is_quarter() -> None:
    # Two equally-weighted candidates: F(rank0)=0.5. Winner at rank 0 (the
    # lower-index tiebreak in the fixed descending-weight-then-index
    # ordering) -> mid-P = (0 + 0.5)/2 = 0.25.
    events = [_event(weights=[1.0, 1.0], winner_local_indices=[0])]
    result = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert result.mid_p_pit_values == pytest.approx([0.25])


def test_two_candidate_equal_weight_winner1_mid_p_is_three_quarters() -> None:
    events = [_event(weights=[1.0, 1.0], winner_local_indices=[1])]
    result = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert result.mid_p_pit_values == pytest.approx([0.75])


def test_randomized_pit_falls_within_mid_p_bin() -> None:
    # The randomized PIT for a pick must fall within [F(rank-1), F(rank)]
    # -- for the winner-0-of-two-equal test above, that is [0, 0.5).
    events = [_event(weights=[1.0, 1.0], winner_local_indices=[0])]
    result = gate.compute_pit_values(events, analysis_rng_seed=42)
    assert 0.0 <= result.randomized_pit_values[0] < 0.5


def test_randomized_pit_is_reproducible_given_same_seed() -> None:
    events = [_event(weights=[1.0, 3.0, 2.0], winner_local_indices=[1])]
    r1 = gate.compute_pit_values(events, analysis_rng_seed=777)
    r2 = gate.compute_pit_values(events, analysis_rng_seed=777)
    assert r1.randomized_pit_values == r2.randomized_pit_values


def test_randomized_pit_differs_from_mid_p_in_general() -> None:
    events = [_event(weights=[1.0, 1.0], winner_local_indices=[0])] * 5
    result = gate.compute_pit_values(events, analysis_rng_seed=1)
    # mid-P is always exactly 0.25 (deterministic); randomized values are
    # drawn continuously within [0, 0.5) and should not all coincide with
    # the mid-P value or each other.
    assert len(set(result.randomized_pit_values)) > 1
    assert not all(v == pytest.approx(0.25) for v in result.randomized_pit_values)


# ---------------------------------------------------------------------------
# Post-mask renormalization
# ---------------------------------------------------------------------------


def test_inaccessible_candidate_excluded_from_law_via_accessible_mask() -> None:
    # 3 candidates, weights [1,1,2]; candidate 2 (weight 2, the largest)
    # is INACCESSIBLE. Post-mask renormalization must score the winner
    # against the remaining {0,1} subset only (equal weights, mid-P=0.25
    # for winner 0), NOT against the full unmasked set (which would give
    # a different, lower mid-P for winner 0 since it would have to share
    # probability mass with the large excluded candidate).
    events = [
        _event(weights=[1.0, 1.0, 2.0], accessible_mask=[True, True, False], winner_local_indices=[0])
    ]
    result = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert result.mid_p_pit_values == pytest.approx([0.25])


def test_winner_not_in_accessible_mask_raises() -> None:
    # A genuine accessibility bug: the trace's real winner is a candidate
    # OC's own accessible_mask says is inaccessible. Must raise loudly,
    # never silently skip (module docstring: "a real accessibility bug
    # could otherwise hide behind a silent skip"). Deliberately a plain
    # exception class, not `assert` (which `python -O` strips entirely --
    # see `test_winner_check_survives_python_dash_o_optimization` below).
    events = [
        _event(weights=[1.0, 1.0], accessible_mask=[False, True], winner_local_indices=[0])
    ]
    with pytest.raises(gate.TxRegPitAccessibilityError, match="NOT in OC's accessible_mask"):
        gate.compute_pit_values(events, analysis_rng_seed=0)


def test_all_false_mask_with_a_winner_raises_not_silently_skipped() -> None:
    # The sharpest form of the same bug class: EVERY candidate is
    # inaccessible (accessible_local_idxs is empty), yet Karr's real
    # trace still recorded a winner. The winner-vs-mask check must run
    # BEFORE the empty-mask `continue` fast path -- otherwise this exact
    # case (the strongest possible accessibility-law disagreement) would
    # be silently swallowed by the same code path that legitimately skips
    # a genuinely-inactive event (no winner at all, see
    # `test_event_with_no_accessible_candidates_is_skipped_not_errored`).
    events = [_event(weights=[1.0, 1.0], accessible_mask=[False, False], winner_local_indices=[0])]
    with pytest.raises(gate.TxRegPitAccessibilityError, match="NOT in OC's accessible_mask"):
        gate.compute_pit_values(events, analysis_rng_seed=0)


def test_event_with_no_accessible_candidates_is_skipped_not_errored() -> None:
    events = [_event(weights=[1.0, 1.0], accessible_mask=[False, False], winner_local_indices=[])]
    result = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert result.n_pooled_values == 0


def test_winner_check_survives_python_dash_o_optimization() -> None:
    """`assert` statements are stripped entirely under `python -O`
    (`PYTHONOPTIMIZE=1`); a bare `assert` guarding this check would
    silently stop enforcing it in that mode. Prove the fail-closed
    behavior survives by re-running the all-false-mask-with-a-winner
    case in a genuinely `-O`-optimized subprocess (never trusting
    `__debug__`/source inspection as a proxy for actual runtime
    behavior)."""
    import subprocess
    import textwrap

    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(_REPO_ROOT)!r})
        from scripts.l22_evidence import txreg_pit_gate as gate

        event = gate.CompetitionEvent(
            tick=0, tf_i=0, tf_wid="TF_A", n_candidates=2,
            weights=[1.0, 1.0], accessible_mask=[False, False], winner_local_indices=[0],
        )
        try:
            gate.compute_pit_values([event], analysis_rng_seed=0)
        except gate.TxRegPitAccessibilityError:
            print("RAISED_OK")
            sys.exit(0)
        print("DID_NOT_RAISE")
        sys.exit(1)
        """
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"fail-closed accessibility check did not survive python -O "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )
    assert "RAISED_OK" in result.stdout


# ---------------------------------------------------------------------------
# Plackett-Luce sequential removal for k>1 winners
# ---------------------------------------------------------------------------


def test_two_winners_produces_two_pooled_values_via_sequential_removal() -> None:
    events = [_event(weights=[1.0, 1.0, 1.0], winner_local_indices=[0, 1])]
    result = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert result.n_pooled_values == 2
    # First pick: 3-way equal tie -> winner 0 is rank 0 of 3 -> mid-P =
    # (0 + 1/3)/2 = 1/6. Second pick (winner 1, remaining {1,2} equal) ->
    # rank 0 of remaining 2 -> mid-P = (0+0.5)/2 = 0.25.
    assert result.mid_p_pit_values == pytest.approx([1.0 / 6.0, 0.25])


# ---------------------------------------------------------------------------
# KS test on pooled values
# ---------------------------------------------------------------------------


def test_ks_statistic_and_pvalue_reported_for_nonempty_pool() -> None:
    rng = np.random.default_rng(0)
    events = []
    for _ in range(200):
        events.append(_event(weights=[1.0, 1.0], winner_local_indices=[int(rng.integers(0, 2))]))
    result = gate.compute_pit_values(events, analysis_rng_seed=1)
    assert not np.isnan(result.ks_statistic)
    assert not np.isnan(result.ks_pvalue)
    assert 0.0 <= result.ks_pvalue <= 1.0


def test_ks_nan_for_empty_pool() -> None:
    result = gate.compute_pit_values([], analysis_rng_seed=0)
    assert np.isnan(result.ks_statistic)
    assert np.isnan(result.ks_pvalue)


# ---------------------------------------------------------------------------
# Weight-law positive controls
# ---------------------------------------------------------------------------


def test_uniform_weights_positive_control_rejects_a_strongly_weight_driven_real_law() -> None:
    """Construct a synthetic scenario where the REAL winner is always the
    highest-weighted candidate (a strongly weight-driven law): under
    "uniform_weights", every candidate's weight collapses to 1 and ties
    break by ascending index -- the always-winning candidate (index 2,
    the LAST/highest index) is therefore ALWAYS ranked LAST (rank 2 of 3)
    under the artificially-flattened law, giving a constant, extreme
    mid-P of 5/6 for every one of the 60 events -- a maximally
    non-uniform pooled distribution, and a clear demonstration that the
    perturbation meaningfully distorts the scored law away from the real
    (higher-power, less degenerate) one.
    """
    events = [
        _event(tick=t, weights=[1.0, 2.0, 20.0], winner_local_indices=[2]) for t in range(60)
    ]
    real = gate.compute_pit_values(events, analysis_rng_seed=0)
    perturbed = gate.run_weight_law_positive_control(
        events, analysis_rng_seed=0, perturbation="uniform_weights"
    )
    assert all(v == pytest.approx(5.0 / 6.0) for v in perturbed.mid_p_pit_values)
    assert perturbed.ks_pvalue < real.ks_pvalue


def test_shuffled_weights_positive_control_is_deterministic_and_differs_from_real() -> None:
    events = [_event(tick=t, weights=[1.0, 2.0, 20.0], winner_local_indices=[2]) for t in range(10)]
    perturbed_a = gate.run_weight_law_positive_control(
        events, analysis_rng_seed=0, perturbation="shuffled_weights"
    )
    perturbed_b = gate.run_weight_law_positive_control(
        events, analysis_rng_seed=0, perturbation="shuffled_weights"
    )
    # Same events -> same deterministic per-event shuffle seed -> same
    # mid-P values (randomized values still differ only via the separate
    # analysis RNG, held fixed here via the same seed too).
    assert perturbed_a.mid_p_pit_values == perturbed_b.mid_p_pit_values
    real = gate.compute_pit_values(events, analysis_rng_seed=0)
    assert perturbed_a.mid_p_pit_values != real.mid_p_pit_values


def test_unknown_weight_law_perturbation_raises() -> None:
    with pytest.raises(ValueError, match="unknown perturbation"):
        gate.run_weight_law_positive_control([], analysis_rng_seed=0, perturbation="bogus")


# ---------------------------------------------------------------------------
# write_evidence_bundle
# ---------------------------------------------------------------------------


def test_write_evidence_bundle_produces_required_authority_files(tmp_path: Path) -> None:
    fake_trace = tmp_path / "TranscriptionalRegulation_4000ticks.mat"
    fake_trace.write_bytes(b"fake-trace-bytes")
    result = gate.compute_pit_values(
        [_event(weights=[1.0, 1.0], winner_local_indices=[0])], analysis_rng_seed=5
    )
    output_dir = gate.write_evidence_bundle(
        trace_path=fake_trace,
        result=result,
        positive_controls={"uniform_weights": result},
        output_dir=tmp_path / "bundle",
    )
    for name in ("result.json", "input_manifest.json", "provenance.json"):
        assert (output_dir / name).exists()

    input_manifest = json.loads((output_dir / "input_manifest.json").read_text(encoding="utf-8"))
    assert input_manifest["trace_sha256"] == gate.sha256_of_file(fake_trace)
    assert input_manifest["ledger_sha256"] is None  # no companion ledger for the fake trace

    provenance = json.loads((output_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["oc_source_sha256"] == gate.sha256_of_file(gate._OC_SOURCE_PATH)
    assert provenance["generator_module_sha256"] == gate.sha256_of_file(Path(gate.__file__))

    result_payload = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result_payload["verdict"] == "PILOT_ONLY_NOT_A_GATE_VERDICT"
    assert "positive_controls" in result_payload
    assert "uniform_weights" in result_payload["positive_controls"]


def test_write_evidence_bundle_records_real_ledger_sha_when_present(tmp_path: Path) -> None:
    fake_trace = tmp_path / "TranscriptionalRegulation_4000ticks.mat"
    fake_trace.write_bytes(b"fake-trace-bytes")
    ledger_path = tmp_path / "TranscriptionalRegulation_4000ticks.chromosome_rand_stream_ledger.json"
    ledger_path.write_text('{"fake": "ledger"}', encoding="utf-8")
    result = gate.compute_pit_values(
        [_event(weights=[1.0, 1.0], winner_local_indices=[0])], analysis_rng_seed=5
    )
    output_dir = gate.write_evidence_bundle(
        trace_path=fake_trace, result=result, positive_controls=None, output_dir=tmp_path / "bundle2"
    )
    input_manifest = json.loads((output_dir / "input_manifest.json").read_text(encoding="utf-8"))
    assert input_manifest["ledger_sha256"] == gate.sha256_of_file(ledger_path)


# ---------------------------------------------------------------------------
# extract_competition_events: real-trace integration test (slow)
# ---------------------------------------------------------------------------


def test_extract_competition_events_against_real_genuine_trace() -> None:
    trace_path = (
        _REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2_event_s000"
        / "TranscriptionalRegulation_4000ticks.mat"
    )
    if not trace_path.exists():
        pytest.skip(f"genuine trace not present in this checkout: {trace_path}")
    events = gate.extract_competition_events(trace_path)
    assert len(events) > 0
    # Every genuine competition event must have at least one real winner
    # (a TF with >1 free-copy-eligible candidate and >=1 free copy must
    # bind somewhere, since Karr never leaves a competition entirely
    # unresolved when free copies exist and at least one candidate is
    # genuinely accessible).
    assert all(event.winner_local_indices for event in events)
    result = gate.compute_pit_values(events, analysis_rng_seed=12345)
    assert result.n_events == len(events)
    assert not np.isnan(result.ks_pvalue)

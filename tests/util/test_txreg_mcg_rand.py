from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.util.txreg_mcg_rand import TxRegChromosomeLedgerRandStream, TxRegMcgRandStream

# TranscriptionalRegulation-only MATLAB RandStream('mcg16807') shim tests
# (Opus review point 6: "Add dedicated TxReg RNG/ledger tests: golden
# vectors/state/weighted sampling/under-over/missing/source tamper").
#
# Split out from tests/util/test_matlab_rng.py (which stays byte-for-byte
# identical to main) for the same reason as test_chromcond_mcg_rand.py:
# opencell/util/matlab_rng.py's file hash is a registered L2.2 provenance
# dependency for ProteinTranslocation's accepted evidence, and neither
# TxRegMcgRandStream nor TxRegChromosomeLedgerRandStream may touch that
# file (see opencell/util/txreg_mcg_rand.py's own module docstring).
#
# Source-tamper coverage for the SHARED chromosome-rand-stream ledger
# LOADER (tests/vivarium/chromosome_rand_stream_ledger.py) lives in
# tests/vivarium/test_chromosome_rand_stream_ledger.py instead -- that
# module is about a different concern (hash-binding a ledger JSON sidecar
# to its trace/source files), not this generator/replay-stream class
# itself.
#
# Sources for the golden vectors used below (live MATLAB R2026a
# `RandStream('mcg16807')` probes, already captured on disk before this
# test file existed -- reused rather than re-run, per the mandate to avoid
# unnecessary MATLAB slot usage):
# - scripts/matlab/probe_txreg_mcg_randsample.m /
#   tmp/probe_txreg_mcg_randsample_result.json: seed-0 raw rand(8) sequence
#   and the exact tick-11 weighted-without-replacement randsample(8,8,...)/
#   randsample(8,1,...) results for the real tick-11 candidate weights.


def test_mcg16807_seed0_rand8_matches_live_matlab_probe() -> None:
    """`case_c_seed0_rand8` in tmp/probe_txreg_mcg_randsample_result.json
    (live MATLAB R2026a `RandStream('mcg16807').reset(0); rand(8,1)`)."""
    s = TxRegMcgRandStream(0)
    got = s.rand(8)
    expected = np.array(
        [
            0.21895918632809036,
            0.047044616214486128,
            0.678864716868319,
            0.67929640583661222,
            0.93469289594082761,
            0.38350207748985948,
            0.51941637206795455,
            0.8309653461123655,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-15)


def test_mcg16807_seed0_weighted_randsample_n8_k8_matches_live_matlab_probe() -> None:
    """`case_a_seed0_n8_k8`: real tick-11 candidate weights (8 sites),
    seed 0, `randsample(8, 8, false, weights)` (the full batched-ordering
    call `_sample_accessible_sites_batched` actually issues)."""
    weights = np.array(
        [
            0.20000000298023224,
            0.7801949977874756,
            0.5365309715270996,
            0.7532579898834229,
            0.5,
            0.8835390210151672,
            1.1398500204086304,
            1.247849941253662,
        ],
        dtype=np.float64,
    )
    s = TxRegMcgRandStream(0)
    got = s.randsample(8, 8, False, weights)
    expected = np.array([3, 2, 7, 8, 5, 6, 1, 4], dtype=np.int64)
    np.testing.assert_array_equal(got, expected)


def test_mcg16807_seed0_weighted_randsample_n8_k1_matches_live_matlab_probe() -> None:
    """`case_b_seed0_n8_k1`: same weights as above, `k=1` (what a naive
    direct-k=1 caller would see -- distinct from the batched k=8 draw
    above, since `k==1` forces `replacement=true` per real
    `RandStream.randsample`)."""
    weights = np.array(
        [
            0.20000000298023224,
            0.7801949977874756,
            0.5365309715270996,
            0.7532579898834229,
            0.5,
            0.8835390210151672,
            1.1398500204086304,
            1.247849941253662,
        ],
        dtype=np.float64,
    )
    s = TxRegMcgRandStream(0)
    got = s.randsample(8, 1, False, weights)
    assert int(got[0]) == 3


def test_mcg16807_state_get_set_roundtrip_continues_bit_identically() -> None:
    """`.get_state()`/`.set_state()` round-trip: a fresh stream seeded with
    another stream's mid-sequence state must continue drawing exactly the
    same subsequent values as the original stream would have -- the
    process-local-class-level analogue of the SHARED chromosome stream's
    `.State` round-trip property proven live via
    `scripts/matlab/probe_l21_chromosome_randstream_state.m` (dec-006), but
    a plain unit-level property test here (no MATLAB invocation needed:
    this checks TxRegMcgRandStream's OWN state representation, not
    MATLAB's real `.State` encoding, which this class deliberately never
    claims to reproduce -- see the module docstring's "Correction
    (2026-09-05)" paragraph)."""
    original = TxRegMcgRandStream(12345)
    # Advance partway through the sequence.
    _ = original.rand(7)
    mid_state = original.get_state()
    expected_continuation = original.rand(5)

    restored = TxRegMcgRandStream(0)  # deliberately different seed
    restored.set_state(mid_state)
    got_continuation = restored.rand(5)

    np.testing.assert_array_equal(got_continuation, expected_continuation)
    # And the restored stream's own state after those 5 draws matches the
    # original's state after its own 5 draws from the same point.
    assert restored.get_state() == original.get_state()


def test_mcg16807_set_state_rejects_wrong_generator_and_out_of_range_state() -> None:
    s = TxRegMcgRandStream(1)
    with pytest.raises(ValueError):
        s.set_state({"generator": "mt19937ar", "seed": 0, "mcg_state": 1})
    with pytest.raises(ValueError):
        s.set_state({"generator": "mcg16807", "seed": 0, "mcg_state": 0})
    with pytest.raises(ValueError):
        s.set_state({"generator": "mcg16807", "seed": 0, "mcg_state": 2_147_483_647})


def test_weighted_randsample_with_replacement_hand_computed_edges() -> None:
    """Deterministic, hand-computed check of
    `_weighted_randsample_with_replacement`'s edge/bucket math, independent
    of any live-MATLAB draw sequence: weights=[1.0, 3.0] normalize to
    p=[0.25, 0.75], giving bucket edges [0.0, 0.25, 1.0]. A raw draw of
    0.1 falls in [0.0, 0.25) -> index 0 -> 1-based pick 1. A raw draw of
    0.5 falls in [0.25, 1.0) -> index 1 -> 1-based pick 2. Uses
    `TxRegChromosomeLedgerRandStream` to inject an EXACT, known raw-draw
    sequence (bypassing the LCG entirely) so this test exercises only the
    weighted-sampling ALGORITHM, not the generator."""
    stream = TxRegChromosomeLedgerRandStream([0.1, 0.5], tick_label="hand_computed")
    weights = np.array([1.0, 3.0], dtype=np.float64)
    picks = stream._weighted_randsample_with_replacement(n=2, k=2, weights=weights)  # noqa: SLF001
    np.testing.assert_array_equal(picks, np.array([1, 2], dtype=np.int64))
    stream.assert_fully_consumed()


def test_weighted_randsample_with_replacement_boundary_draw_lands_in_last_bucket() -> None:
    """A raw draw of exactly 1.0 (the forced final-edge value) must land in
    the LAST bucket, not out of range -- real MATLAB `histcounts` treats
    only the final bin as closed on both ends (see
    `TxRegMcgRandStream._weighted_randsample_with_replacement`'s own
    docstring, point 2)."""
    stream = TxRegChromosomeLedgerRandStream([1.0], tick_label="boundary")
    weights = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    picks = stream._weighted_randsample_with_replacement(n=3, k=1, weights=weights)  # noqa: SLF001
    assert int(picks[0]) == 3
    stream.assert_fully_consumed()


def test_ledger_replay_stream_exact_consumption_passes() -> None:
    stream = TxRegChromosomeLedgerRandStream([0.1, 0.2, 0.3], tick_label="exact")
    for _ in range(3):
        stream.rand()
    stream.assert_fully_consumed()  # must not raise


def test_ledger_replay_stream_exhaustion_raises_immediately() -> None:
    stream = TxRegChromosomeLedgerRandStream([0.1, 0.2], tick_label="exhaust")
    stream.rand()
    stream.rand()
    with pytest.raises(RuntimeError, match="exhausted"):
        stream.rand()


def test_ledger_replay_stream_under_consumption_raises_on_assert() -> None:
    stream = TxRegChromosomeLedgerRandStream([0.1, 0.2, 0.3], tick_label="under")
    stream.rand()  # only consume 1 of 3
    with pytest.raises(RuntimeError, match="only consumed"):
        stream.assert_fully_consumed()


def test_ledger_replay_stream_empty_ledger_is_immediately_fully_consumed() -> None:
    """A quiescent tick (0 recorded draws, per
    `scripts/matlab/reconstruct_chromosome_draw_ledger.m`'s quiescent-tick
    special case) must construct cleanly and immediately pass
    `assert_fully_consumed()` with no draws at all."""
    stream = TxRegChromosomeLedgerRandStream([], tick_label="quiescent")
    stream.assert_fully_consumed()  # must not raise
    with pytest.raises(RuntimeError, match="exhausted"):
        stream.rand()

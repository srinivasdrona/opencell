"""Tests for the DNASupercoiling process-owned (``this.randStream``) RNG
state ledger loader (state-seeded, generous-buffer design -- supersedes
the earlier finite-draw-list design, whose exhaustion under legitimate
late-tick consumption motivated this rewrite; see the module docstring in
``opencell/vivarium/dnas_process_rng_ledger.py``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install
# exists (matches the guard already established in
# test_karr_dna_supercoiling.py -- the shared venv's editable install always
# points at the main repo checkout, not whichever worktree is under test).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    _loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in _loaded.parents:
        for _mod_name in list(sys.modules):
            if _mod_name == "opencell" or _mod_name.startswith("opencell."):
                del sys.modules[_mod_name]

from opencell.vivarium.dnas_process_rng_ledger import (
    ProcessRngLedger,
    ProcessRngReplayRng,
    default_process_rng_ledger_path,
)


def _write_ledger(path: Path, *, seed: int, ticks: list[dict]) -> None:
    payload = {
        "seed": seed,
        "process_name": "DNASupercoiling",
        "rng_type": "mcg16807",
        "n_ticks": len(ticks),
        "batch_size": 1000,
        "source_ledger": "seed_000.json",
        "ticks": ticks,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tick_entry(
    *,
    tick: int,
    extended_draws: list[float],
    recorded_draws_len: int | None = None,
    process_state_before: float = 10.0,
    process_state_after_recorded: float = 20.0,
    audit_prefix_match: bool = True,
    audit_state_after_match: bool = True,
    provenance_hash: str = "deadbeef",
) -> dict:
    if recorded_draws_len is None:
        recorded_draws_len = len(extended_draws)
    return {
        "tick_zero_based": tick,
        "process_state_before": process_state_before,
        "process_state_after_recorded": process_state_after_recorded,
        "recorded_draws_len": recorded_draws_len,
        "audit_prefix_match": audit_prefix_match,
        "audit_state_after_match": audit_state_after_match,
        "batch_size": len(extended_draws),
        "extended_draws": extended_draws,
        "provenance_hash": provenance_hash,
    }


def test_default_process_rng_ledger_path_is_seed_derived() -> None:
    path0 = default_process_rng_ledger_path(0)
    path7 = default_process_rng_ledger_path(7)
    assert path0.name == "seed_000.json"
    assert path7.name == "seed_007.json"
    assert path0.parent.name == "process_rng_state_ledger"


def test_load_and_replay_draws_in_order(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_000.json"
    _write_ledger(
        ledger_path,
        seed=0,
        ticks=[
            _tick_entry(tick=0, extended_draws=[0.1, 0.2, 0.3, 0.4, 0.5]),
            _tick_entry(tick=2, extended_draws=[0.9, 0.8, 0.7]),
        ],
    )

    ledger = ProcessRngLedger.load(ledger_path)
    assert ledger.n_ticks == 2
    assert ledger.has_tick(0)
    assert ledger.has_tick(2)
    assert not ledger.has_tick(1)
    assert not ledger.has_tick(3)

    entry0 = ledger.entry_for_tick(0)
    np.testing.assert_allclose(entry0.draws, [0.1, 0.2, 0.3, 0.4, 0.5])
    assert entry0.recorded_len == 5

    replay = ProcessRngReplayRng(entry0.draws, recorded_len=entry0.recorded_len)
    np.testing.assert_allclose(replay.random(2), [0.1, 0.2])
    assert replay.random() == pytest.approx(0.3)


def test_missing_tick_raises_key_error(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_001.json"
    _write_ledger(ledger_path, seed=1, ticks=[_tick_entry(tick=0, extended_draws=[0.5, 0.6])])
    ledger = ProcessRngLedger.load(ledger_path)
    with pytest.raises(KeyError):
        ledger.entry_for_tick(5)


def test_unverified_prefix_audit_raises_value_error_on_load(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_002.json"
    _write_ledger(
        ledger_path,
        seed=2,
        ticks=[_tick_entry(tick=0, extended_draws=[0.5, 0.6], audit_prefix_match=False)],
    )
    with pytest.raises(ValueError, match="audit_prefix_match"):
        ProcessRngLedger.load(ledger_path)


def test_unverified_state_after_audit_raises_value_error_on_load(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_003.json"
    _write_ledger(
        ledger_path,
        seed=3,
        ticks=[_tick_entry(tick=0, extended_draws=[0.5, 0.6], audit_state_after_match=False)],
    )
    with pytest.raises(ValueError, match="audit_state_after_match"):
        ProcessRngLedger.load(ledger_path)


def test_empty_extended_draws_raises_value_error_on_load(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_004.json"
    _write_ledger(ledger_path, seed=4, ticks=[_tick_entry(tick=0, extended_draws=[])])
    with pytest.raises(ValueError, match="empty"):
        ProcessRngLedger.load(ledger_path)


def test_replay_rng_raises_only_when_the_generous_buffer_itself_is_exhausted() -> None:
    replay = ProcessRngReplayRng(np.asarray([0.1, 0.2]), recorded_len=1)
    replay.random(2)
    with pytest.raises(RuntimeError, match="exhausted"):
        replay.random(1)


def test_replay_rng_does_not_raise_past_the_audited_recorded_len_boundary() -> None:
    """The whole point of the state-seeded redesign: consuming MORE than
    one specific historical MATLAB run's recorded draw count is NOT an
    error, as long as the (generous) buffer itself has more real draws
    left. Only tracks exceeded_audit_boundary for diagnostics."""
    replay = ProcessRngReplayRng(np.asarray([0.1, 0.2, 0.3, 0.4, 0.5]), recorded_len=2)
    replay.random(2)
    assert not replay.exceeded_audit_boundary
    # A third draw exceeds the audited boundary (recorded_len=2) but the
    # buffer still has 3 more real draws -- must NOT raise.
    value = replay.random()
    assert value == pytest.approx(0.3)
    assert replay.exceeded_audit_boundary


def test_hash_binds_content_via_provenance_hash_field(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_005.json"
    _write_ledger(
        ledger_path,
        seed=5,
        ticks=[_tick_entry(tick=0, extended_draws=[0.11, 0.22, 0.33], provenance_hash="hash-a")],
    )
    ledger = ProcessRngLedger.load(ledger_path)
    assert ledger.entry_for_tick(0).provenance_hash == "hash-a"


# ---- MATLAB-equivalence of permutation/choice (empirically verified against
# live MATLAB in tmp/probe_randperm_algorithm.m and
# tmp/probe_randsample_algorithm.m; these tests pin the resulting Python
# formula, not re-derive it). ----


def test_permutation_is_ascending_argsort_of_n_raw_draws() -> None:
    draws = np.asarray([0.7, 0.1, 0.9, 0.3, 0.5])
    replay = ProcessRngReplayRng(draws, recorded_len=5)
    perm = replay.permutation(5)
    # Ascending argsort: index of smallest draw first.
    np.testing.assert_array_equal(perm, np.argsort(draws, kind="stable"))
    np.testing.assert_array_equal(perm, [1, 3, 4, 0, 2])
    assert replay.remaining() == 0


def test_permutation_consumes_exactly_n_draws() -> None:
    draws = np.asarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    replay = ProcessRngReplayRng(draws, recorded_len=6)
    replay.permutation(3)
    assert replay.remaining() == 3
    # Second call consumes the remaining 3.
    replay.permutation(3)
    assert replay.remaining() == 0


def test_choice_is_cumulative_weight_lookup_of_one_raw_draw() -> None:
    weights = np.asarray([5.0, 2.0, 1.0, 1.0, 1.0])  # cdf: .5 .7 .8 .9 1.0
    replay = ProcessRngReplayRng(np.asarray([0.3]), recorded_len=1)
    idx = replay.choice(5, p=weights)
    assert idx == 0  # 0.3 <= 0.5
    assert replay.remaining() == 0

    replay2 = ProcessRngReplayRng(np.asarray([0.65]), recorded_len=1)
    idx2 = replay2.choice(5, p=weights)
    assert idx2 == 1  # 0.5 < 0.65 <= 0.7

    replay3 = ProcessRngReplayRng(np.asarray([1.0]), recorded_len=1)
    idx3 = replay3.choice(5, p=weights)
    assert idx3 == 4  # boundary: draw == cdf[-1] falls in the last bin


def test_choice_consumes_exactly_one_draw() -> None:
    replay = ProcessRngReplayRng(np.asarray([0.1, 0.9]), recorded_len=2)
    replay.choice(2, p=np.asarray([1.0, 1.0]))
    assert replay.remaining() == 1


def test_choice_rejects_mismatched_weight_length() -> None:
    replay = ProcessRngReplayRng(np.asarray([0.5]), recorded_len=1)
    with pytest.raises(ValueError, match="weights length"):
        replay.choice(3, p=np.asarray([1.0, 1.0]))

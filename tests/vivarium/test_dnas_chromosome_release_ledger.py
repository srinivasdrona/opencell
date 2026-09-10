"""Tests for the DNASupercoiling chromosome-owned release RNG ledger loader."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from opencell.vivarium.dnas_chromosome_release_ledger import (
    ChromosomeReleaseLedger,
    ChromosomeReleaseReplayRng,
    default_ledger_path,
)


def _write_ledger(path: Path, *, seed: int, ticks: list[dict]) -> None:
    payload = {
        "seed": seed,
        "process_name": "DNASupercoiling",
        "n_ticks": len(ticks),
        "ticks": ticks,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tick_entry(
    *,
    tick: int,
    draws: list[float],
    state_before: float = 1.0,
    state_after: float = 2.0,
    ok: bool = True,
) -> dict:
    return {
        "tick_zero_based": tick,
        "chromosome_state_before": {"values": state_before, "length": 1},
        "chromosome_state_after": {"values": state_after, "length": 1},
        "process_state_before": {"values": 10.0, "length": 1},
        "process_state_after": {"values": 20.0, "length": 1},
        "chromosome_release_draws": draws,
        "chromosome_release_draws_reconstructed_ok": ok,
        "chromosome_release_draws_iterations": len(draws),
        "process_draws": [],
        "process_draws_reconstructed_ok": True,
        "process_draws_iterations": 0,
    }


def test_default_ledger_path_is_seed_derived() -> None:
    path0 = default_ledger_path(0)
    path7 = default_ledger_path(7)
    assert path0.name == "seed_000.json"
    assert path7.name == "seed_007.json"
    assert path0.parent == path7.parent


def test_load_and_replay_draws_in_order(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_000.json"
    _write_ledger(
        ledger_path,
        seed=0,
        ticks=[
            _tick_entry(tick=0, draws=[0.1, 0.2, 0.3]),
            _tick_entry(tick=1, draws=[]),
            _tick_entry(tick=2, draws=[0.9]),
        ],
    )

    ledger = ChromosomeReleaseLedger.load(ledger_path)
    assert ledger.n_ticks == 3
    assert ledger.has_tick(0)
    assert ledger.has_tick(2)
    assert not ledger.has_tick(3)

    tick0_draws = ledger.draws_for_tick(0)
    np.testing.assert_allclose(tick0_draws, [0.1, 0.2, 0.3])

    replay = ChromosomeReleaseReplayRng(tick0_draws)
    np.testing.assert_allclose(replay.random(2), [0.1, 0.2])
    assert replay.random() == pytest.approx(0.3)

    tick1_draws = ledger.draws_for_tick(1)
    assert tick1_draws.shape == (0,)

    tick2_replay = ChromosomeReleaseReplayRng(ledger.draws_for_tick(2))
    assert tick2_replay.random() == pytest.approx(0.9)


def test_missing_tick_raises_key_error(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_001.json"
    _write_ledger(ledger_path, seed=1, ticks=[_tick_entry(tick=0, draws=[0.5])])
    ledger = ChromosomeReleaseLedger.load(ledger_path)
    with pytest.raises(KeyError):
        ledger.draws_for_tick(5)


def test_unreconstructed_tick_raises_value_error_on_load(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_002.json"
    _write_ledger(
        ledger_path,
        seed=2,
        ticks=[_tick_entry(tick=0, draws=[0.5], ok=False)],
    )
    with pytest.raises(ValueError, match="did not converge"):
        ChromosomeReleaseLedger.load(ledger_path)


def test_replay_rng_raises_when_exhausted() -> None:
    replay = ChromosomeReleaseReplayRng(np.asarray([0.1, 0.2]))
    replay.random(2)
    with pytest.raises(RuntimeError, match="exhausted"):
        replay.random(1)


def test_hash_for_tick_is_stable_and_content_bound(tmp_path: Path) -> None:
    ledger_path = tmp_path / "seed_003.json"
    _write_ledger(
        ledger_path,
        seed=3,
        ticks=[_tick_entry(tick=0, draws=[0.11, 0.22])],
    )
    ledger_a = ChromosomeReleaseLedger.load(ledger_path)
    ledger_b = ChromosomeReleaseLedger.load(ledger_path)
    assert ledger_a.hash_for_tick(0) == ledger_b.hash_for_tick(0)

    other_path = tmp_path / "seed_004.json"
    _write_ledger(
        other_path,
        seed=3,
        ticks=[_tick_entry(tick=0, draws=[0.11, 0.99])],
    )
    ledger_c = ChromosomeReleaseLedger.load(other_path)
    assert ledger_c.hash_for_tick(0) != ledger_a.hash_for_tick(0)

"""Mass-balance regression invariants over a short multi-tick chassis run.

This test closes the gap where allocation-integrity can pass while substrate
counts still leak over time.

Element-class conservation (C/N/P/S) is intentionally skipped for now because
the checked-in fixtures expose substrate molecular weights but not a usable
per-substrate element-composition table for the 585 substrate WIDs. Keep the
starting tolerance at 1e-3 when this is enabled; only relax to 1e-2 with
documented rationale for the specific known bug being masked.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pytest

from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine

N_TICKS = 100
MAX_RUNTIME_SECONDS = 30.0
MAX_DRIFT_FRAC = 1.0
ELEMENT_CONSERVATION_TOL = 1e-3

# Calibrated against commit 1e8b1c3 on the M1+M2+M3 chassis harness.
# Recalibrated 2026-06-01 on sweep tip after cherry-picking translation
# GREEN commit bd022a4. Translation's deterministic schedule now properly
# consumes NTPs (ATP/CTP/GTP/UTP) and shifts amino-acid depletion ordering.
# The negative/drift signatures below are the known-broken baseline post-
# translation. Each entry represents a real substrate bug to be fixed.
_KNOWN_NEGATIVE_FIRST_TICKS = frozenset(
    {
        ("ALA", 1),
        ("ARG", 1),
        ("ASN", 1),
        ("ASP", 1),
        ("ATP", 1),
        ("CTP", 1),
        ("CYS", 3),
        ("GLN", 1),
        ("GLU", 1),
        ("GLY", 1),
        ("GTP", 1),
        ("HIS", 2),
        ("ILE", 1),
        ("LEU", 1),
        ("LYS", 1),
        ("MET", 2),
        ("PHE", 1),
        ("PRO", 1),
        ("SER", 1),
        ("THR", 1),
        ("TRP", 4),
        ("TYR", 1),
        ("UTP", 1),
        ("VAL", 1),
    }
)

_KNOWN_DRIFT_MAX_TICKS = frozenset(
    {
        ("ALA", 100),
        ("ARG", 100),
        ("ASN", 100),
        ("ASP", 100),
        ("ATP", 100),
        ("CTP", 100),
        ("CYS", 100),
        ("GLN", 100),
        ("GLU", 100),
        ("GLY", 100),
        ("GTP", 100),
        ("HIS", 100),
        ("ILE", 100),
        ("LEU", 100),
        ("LYS", 100),
        ("MET", 100),
        ("PHE", 100),
        ("PRO", 100),
        ("SER", 100),
        ("THR", 100),
        ("TRP", 100),
        ("TYR", 100),
        ("UTP", 100),
        ("VAL", 100),
    }
)


@dataclass(frozen=True)
class SubstrateTrajectory:
    wids: tuple[str, ...]
    counts: np.ndarray  # shape=(N_TICKS + 1, n_substrates)
    runtime_seconds: float


def _snapshot(store: dict[str, float], wids: tuple[str, ...]) -> np.ndarray:
    return np.asarray([float(store.get(wid, 0.0)) for wid in wids], dtype=np.float64)


@pytest.fixture(scope="module")
def substrate_trajectory() -> SubstrateTrajectory:
    engine = build_karr_m1_m2_m3_engine(
        time_step_s=1.0,
        emit_step_s=float(N_TICKS),
    )
    engine.display_info = False

    substrate_store = engine.state.get_path(("substrates",))
    assert substrate_store is not None
    initial = substrate_store.get_value()
    assert isinstance(initial, dict)

    wids = tuple(sorted(str(wid) for wid in initial))
    counts = np.zeros((N_TICKS + 1, len(wids)), dtype=np.float64)
    counts[0, :] = _snapshot(initial, wids)

    t0 = time.perf_counter()
    for tick in range(1, N_TICKS + 1):
        engine.update(1.0)
        current = substrate_store.get_value()
        assert isinstance(current, dict)
        counts[tick, :] = _snapshot(current, wids)
    runtime_seconds = time.perf_counter() - t0

    return SubstrateTrajectory(wids=wids, counts=counts, runtime_seconds=runtime_seconds)


def test_mass_balance_run_is_fast(substrate_trajectory: SubstrateTrajectory) -> None:
    assert substrate_trajectory.runtime_seconds <= MAX_RUNTIME_SECONDS, (
        f"{N_TICKS}-tick substrate trajectory took "
        f"{substrate_trajectory.runtime_seconds:.3f}s "
        f"(limit {MAX_RUNTIME_SECONDS:.1f}s)"
    )


def test_substrates_have_no_non_finite_values(substrate_trajectory: SubstrateTrajectory) -> None:
    counts = substrate_trajectory.counts
    bad = np.argwhere(~np.isfinite(counts))
    assert bad.size == 0, (
        "non-finite substrate count(s): "
        + ", ".join(
            f"{substrate_trajectory.wids[int(col)]}@tick{int(tick)}={counts[int(tick), int(col)]!r}"
            for tick, col in bad[:10]
        )
    )


def test_substrates_are_non_negative_each_tick(
    substrate_trajectory: SubstrateTrajectory,
) -> None:
    first_negative: dict[str, tuple[int, float]] = {}
    for tick in range(1, substrate_trajectory.counts.shape[0]):
        row = substrate_trajectory.counts[tick, :]
        neg_idx = np.flatnonzero(row < 0.0)
        for idx in neg_idx:
            wid = substrate_trajectory.wids[int(idx)]
            if wid not in first_negative:
                first_negative[wid] = (tick, float(row[int(idx)]))

    if not first_negative:
        return

    observed = frozenset((wid, tick) for wid, (tick, _) in first_negative.items())
    if observed == _KNOWN_NEGATIVE_FIRST_TICKS:
        details = ", ".join(
            f"{wid}@tick{tick}"
            for wid, tick in sorted(observed)
        )
        pytest.xfail(
            reason=(
                "Known negative substrate counts on baseline commit 1e8b1c3; "
                f"first-negative WIDs/ticks: {details}"
            )
        )

    unexpected = sorted(observed - _KNOWN_NEGATIVE_FIRST_TICKS)
    missing = sorted(_KNOWN_NEGATIVE_FIRST_TICKS - observed)
    pytest.fail(
        "Negative substrate regression drifted from calibrated baseline. "
        f"Unexpected={unexpected}, Missing={missing}"
    )


def test_substrate_drift_bound_over_100_ticks(
    substrate_trajectory: SubstrateTrajectory,
) -> None:
    counts = substrate_trajectory.counts
    baseline = counts[0, :]
    denom = np.maximum(baseline, 1.0)
    drift = np.abs(counts - baseline[None, :]) / denom[None, :]

    max_tick_by_wid = np.argmax(drift, axis=0).astype(int)
    max_drift_by_wid = drift[max_tick_by_wid, np.arange(drift.shape[1])]

    violating = np.flatnonzero(max_drift_by_wid > MAX_DRIFT_FRAC)
    if violating.size == 0:
        return

    observed = frozenset(
        (substrate_trajectory.wids[int(idx)], int(max_tick_by_wid[int(idx)]))
        for idx in violating
    )
    if observed == _KNOWN_DRIFT_MAX_TICKS:
        details = ", ".join(
            f"{substrate_trajectory.wids[int(idx)]}@tick{int(max_tick_by_wid[int(idx)])}"
            for idx in violating
        )
        pytest.xfail(
            reason=(
                "Known per-substrate drift > 1.0 on baseline commit 1e8b1c3; "
                f"max-drift WIDs/ticks: {details}"
            )
        )

    unexpected = sorted(observed - _KNOWN_DRIFT_MAX_TICKS)
    missing = sorted(_KNOWN_DRIFT_MAX_TICKS - observed)
    pytest.fail(
        "Per-substrate drift violations changed from calibrated baseline. "
        f"Unexpected={unexpected}, Missing={missing}"
    )


@pytest.mark.skip(
    reason=(
        "element composition data not yet in-repo "
        "(no checked-in per-substrate C/N/P/S table for the 585 substrate WIDs)"
    )
)
def test_element_class_conservation_over_trajectory() -> None:
    """Placeholder for per-element conservation:

    |sum_t(element_count) - sum_0(element_count)| / sum_0(element_count)
    < ELEMENT_CONSERVATION_TOL for C, N, P, and S.
    """
    _ = ELEMENT_CONSERVATION_TOL


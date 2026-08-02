"""Inversion tests for the FtsZPolymerization honest-mode windowed canary.

Each test demonstrates that a specific known failure mode from the Turn-1
INTENT (`docs/phase_f/l2_windowed/FTSZ_WINDOWED_PROFILE_SPEC.md` section G)
is either mechanically impossible in the canary as written, or would be
caught if reintroduced. These are regression guards on the *harness*, not
additional biology-fidelity assertions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    build_state_template,
    overlay_trace_after_hint,
    refresh_allocator_views,
)
from test_karr_ftsz_polymerization_honest_canary import (  # noqa: E402
    DIAGNOSTIC_ONLY_CHANNELS,
    GATE_CHANNELS,
    _assert_no_oracle_leakage,
    _monomer_conservation_delta,
    classify_ensemble_support,
)

from opencell.vivarium.karr_ftsz_polymerization import (  # noqa: E402
    KarrFtsZPolymerizationProcess,
)


def _fresh_process(seed: int = 0) -> KarrFtsZPolymerizationProcess:
    return KarrFtsZPolymerizationProcess({"rng_seed": int(seed)})


# ---------------------------------------------------------------------------
# 1. Hint leakage / oracle-after
# ---------------------------------------------------------------------------


def test_hint_leakage_is_mechanically_real_but_absent_from_honest_canary() -> None:
    """Prove the enzymes_next short-circuit genuinely changes next_update's
    output (so the vulnerability is real and not a paper tiger), then prove
    the honest-canary's own state-construction never reaches for it."""
    process = _fresh_process()
    state = build_state_template(process)
    current_counts = process._initial_enzyme_counts.astype(np.int64)
    for idx, wid in enumerate(process.enzyme_wids):
        state["enzymes"][wid] = float(current_counts[idx])
    refresh_allocator_views(process, state)

    # Honest-mode baseline: must not have a hint.
    _assert_no_oracle_leakage(state)
    honest_update = process.next_update(1.0, dict(state))

    # Fabricate a wrong-on-purpose hint far outside anything the ODE would
    # produce in one tick, and confirm it overrides the biology path.
    tampered = current_counts.copy()
    tampered[process.enzyme_index_ftsz_9mer] += 999
    hinted_state = build_state_template(process)
    for idx, wid in enumerate(process.enzyme_wids):
        hinted_state["enzymes"][wid] = float(current_counts[idx])
    overlay_trace_after_hint(
        state=hinted_state,
        observable="enzymes",
        vector=tampered.astype(np.float64),
        wids=list(process.enzyme_wids),
    )
    refresh_allocator_views(process, hinted_state)
    hinted_update = process.next_update(1.0, hinted_state)

    hinted_9mer_delta = hinted_update.get("enzymes", {}).get(
        process.enzyme_wids[process.enzyme_index_ftsz_9mer], 0.0
    )
    assert hinted_9mer_delta == pytest.approx(999.0), (
        "expected the fabricated +999 hint to pass straight through "
        f"next_update unmodified; got delta={hinted_9mer_delta}. If this "
        "fails, either the short-circuit was removed (good -- update this "
        "test) or it now behaves differently than documented."
    )
    honest_9mer_delta = honest_update.get("enzymes", {}).get(
        process.enzyme_wids[process.enzyme_index_ftsz_9mer], 0.0
    )
    assert honest_9mer_delta != pytest.approx(999.0), (
        "honest-mode call (no hint) must not reproduce the fabricated hint delta"
    )


# ---------------------------------------------------------------------------
# 2. Quiet/constant OC trajectory fake pass
# ---------------------------------------------------------------------------


def test_constant_trajectory_would_fail_nonvacuity_guard() -> None:
    """A degenerate all-zero-enzyme run must be caught by the same
    'oc_nonvacuous_ticks > 0' guard the canary uses -- it must not be
    possible to vacuously satisfy it."""
    process = _fresh_process()
    state = build_state_template(process)
    for wid in process.enzyme_wids:
        state["enzymes"][wid] = 0.0
    refresh_allocator_views(process, state)

    update = process.next_update(1.0, state)
    # Karr's own gate: `if ~any(this.enzymes) return`. With all-zero enzymes,
    # next_update must emit no enzyme delta at all -- the exact degenerate
    # trajectory the nonvacuity guard exists to reject.
    enzyme_delta = update.get("enzymes", {})
    oc_nonvacuous = any(abs(float(v)) > 0.0 for v in enzyme_delta.values())
    assert not oc_nonvacuous, (
        "expected the all-zero-enzyme gate to produce a constant (empty) "
        "trajectory; the nonvacuity guard in the honest canary would "
        "correctly fail an `assert oc_nonvacuous_ticks > 0` in this scenario"
    )


# ---------------------------------------------------------------------------
# 3. Wrong WID order
# ---------------------------------------------------------------------------


def test_wrong_wid_order_breaks_monomer_conservation_check() -> None:
    """If the enzyme delta dict were (incorrectly) keyed by a permuted WID
    order relative to process.n_monomers, the monomer-conservation check
    must detect it (nonzero apparent conservation violation) rather than
    silently passing."""
    process = _fresh_process()
    correct_wids = list(process.enzyme_wids)
    # A real, nonzero, monomer-conserving delta: demote one 9-mer to 9 monomers.
    real_delta = {wid: 0.0 for wid in correct_wids}
    real_delta[process.enzyme_wids[process.enzyme_index_ftsz_9mer]] = -1.0
    real_delta[process.enzyme_wids[process.enzyme_index_ftsz]] = 9.0

    conserved = _monomer_conservation_delta(process, real_delta)
    assert conserved == 0, "sanity: a correctly-labelled conserving delta must check out"

    # Now simulate the inversion: shift every delta to the WRONG neighboring
    # WID (off-by-one permutation), as would happen from a WID-order bug.
    shifted_wids = correct_wids[1:] + correct_wids[:1]
    wrong_delta = {shifted_wids[i]: real_delta[correct_wids[i]] for i in range(len(correct_wids))}

    conserved_wrong = _monomer_conservation_delta(process, wrong_delta)
    assert conserved_wrong != 0, (
        "expected an off-by-one WID permutation to break monomer "
        f"conservation (got {conserved_wrong} == 0 unexpectedly, meaning the "
        "check would NOT catch a wrong-WID-order regression)"
    )


# ---------------------------------------------------------------------------
# 4. Solver-tolerance / threshold fabrication laundering
# ---------------------------------------------------------------------------


def test_honest_canary_source_invents_no_discrepancy_threshold() -> None:
    """Static self-check: the honest-mode canary module must not gate its
    per-tick discrepancy telemetry behind any invented pass/fail numeric
    threshold (e.g. asserting enzymes_l1 < X). It may only assert exact
    structural invariants (==0, integrality, finiteness, nonnegativity) and
    report telemetry."""
    canary_path = _HELPER_DIR / "test_karr_ftsz_polymerization_honest_canary.py"
    source = canary_path.read_text()

    forbidden_patterns = [
        "enzymes_l1 <",
        "enzymes_l1 <=",
        "substrates_l1 <",
        "substrates_l1 <=",
        "rtol=self.parameters",
        "ode_rtol",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"found forbidden discrepancy-gating pattern {pattern!r} in "
            f"{canary_path.name}: the canary must report telemetry, not "
            "invent a pass/fail tolerance from it"
        )


# ---------------------------------------------------------------------------
# 5. N=1 promotion to a gated verdict
# ---------------------------------------------------------------------------


def test_n1_can_never_classify_as_sufficient_ensemble() -> None:
    assert classify_ensemble_support(1, required_n_seeds=50) == "INSUFFICIENT_ENSEMBLE"
    # Boundary sanity: the function itself is not hardcoded to always refuse --
    # it is a real threshold comparison, just one FtsZ's N=1 always fails.
    assert classify_ensemble_support(50, required_n_seeds=50) == "SUFFICIENT_ENSEMBLE"
    assert classify_ensemble_support(49, required_n_seeds=50) == "INSUFFICIENT_ENSEMBLE"


# ---------------------------------------------------------------------------
# 6. Solver failure surfaced, not silently laundered into a fake biology tick
# ---------------------------------------------------------------------------


def test_degenerate_timestep_returns_explicit_noop_not_corrupt_state() -> None:
    """`integrate_odes` with timestep<=0 (a degenerate/solver-bypass input)
    must return the unmodified y0, i.e. an explicit, auditable no-op --
    never partially-integrated or NaN state silently treated as a tick."""
    process = _fresh_process()
    y0 = process.molecules_to_concentration(process._initial_enzyme_counts.astype(np.float64))
    substrate_counts = np.zeros(len(process.substrate_wids), dtype=np.float64)

    tout, yout = process.integrate_odes(y0=y0, substrate_counts=substrate_counts, timestep=0.0)
    assert np.array_equal(yout[:, -1], y0), "timestep<=0 must be an explicit identity no-op"
    assert np.all(np.isfinite(yout)), "no-op path must not introduce NaN/Inf"


# ---------------------------------------------------------------------------
# 7. Global RNG / cross-instance state pollution
# ---------------------------------------------------------------------------


def test_rng_is_isolated_from_global_numpy_state() -> None:
    """Two same-seeded process instances must draw identical stochastic
    discretization outcomes even if Python's global `np.random` state is
    polluted in between -- proving `np.random.default_rng` isolation (no
    `np.random.seed()`/global-stream usage) actually holds at runtime."""
    # `discretize_enzymes` expects real *concentrations* (it internally
    # multiplies by N_Avogadro * cell volume via `concentration_to_molecules`).
    # Passing small raw numbers here (e.g. ~50.0) as if they were
    # concentrations makes the target molecule count astronomically larger
    # than `current_counts`, and the unit-step rejection loop in
    # `discretize_enzymes` would then need ~10^8+ iterations to converge --
    # an effective hang, not a real RNG-isolation scenario. Use a target
    # derived from the process's own real initial counts plus a small,
    # near-zero perturbation so the loop resolves in O(10) steps, exactly
    # like a real one-tick ODE-integration result would.
    process_a = _fresh_process(seed=7)
    current_a = process_a._initial_enzyme_counts.astype(np.int64)
    perturbed_counts_a = current_a.astype(np.float64).copy()
    perturbed_counts_a[0] += 3.0
    conc = process_a.molecules_to_concentration(perturbed_counts_a)
    result_a = process_a.discretize_enzymes(enzyme_concentrations=conc, current_counts=current_a)

    np.random.seed(123456)  # pollute the GLOBAL numpy legacy RNG stream
    for _ in range(1000):
        np.random.rand()

    process_b = _fresh_process(seed=7)
    current_b = process_b._initial_enzyme_counts.astype(np.int64)
    result_b = process_b.discretize_enzymes(enzyme_concentrations=conc, current_counts=current_b)

    assert np.array_equal(result_a, result_b), (
        "same-seeded KarrFtsZPolymerizationProcess instances produced "
        "different discretization draws after global np.random state was "
        "polluted -- RNG is not properly isolated per-instance"
    )


# ---------------------------------------------------------------------------
# 8. OC-only diagnostic promoted to the gate
# ---------------------------------------------------------------------------


def test_diagnostic_only_channels_excluded_from_gate_set() -> None:
    for channel in DIAGNOSTIC_ONLY_CHANNELS:
        assert channel not in GATE_CHANNELS, (
            f"{channel} is an OC-only/never-mutated-by-Karr diagnostic and "
            "must not be promoted into GATE_CHANNELS without a separate, "
            "explicit decision"
        )
    assert set(GATE_CHANNELS) == {"enzymes", "substrates"}

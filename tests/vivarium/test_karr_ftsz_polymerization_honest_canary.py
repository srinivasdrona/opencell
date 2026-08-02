"""FtsZPolymerization honest-mode (no-hint) windowed canary.

Turn-2 deliverable for the L2.event -> continuous/windowed reclassification
of FtsZPolymerization (see docs/phase_f/l2_windowed/FTSZ_WINDOWED_PROFILE_SPEC.md).

WHAT THIS TEST IS
- Runs `KarrFtsZPolymerizationProcess.next_update` per-tick against the only
  on-disk FtsZ trace (seed 0, 100 ticks,
  data/m1_sources/karr_native/per_process_traces_v2/FtsZPolymerization_100ticks.mat)
  with NO `trace_hint` ever populated, so the ODE / discretize / substrate-clamp
  biology path (`evolveState` equivalent) is what actually runs -- not the
  `enzymes_next` short-circuit described in
  docs/phase_f/L2_5_HONEST_MODE_HINT_LEAKAGE_FINDING.md.
- Enforces exact (zero-fudge-factor) structural invariants that hold
  unconditionally in the Karr algebra regardless of ensemble size: monomer-count
  conservation, GTP/GDP/PI/H2O/H stoichiometric self-consistency, and
  finite/nonnegative/integer emitted deltas.
- Reports raw per-tick discrepancy telemetry (OC honest-mode vs Karr) for the
  `enzymes` (primary/gate) and `substrates` (secondary/conservation) channels.
  `boundEnzymes` and the OC-only `cell.ftsz_ring_count`/`ftsz_ring_complete`
  channels are diagnostics only and are excluded from the gate set.

WHAT THIS TEST IS NOT
- It is NOT a gate. With N=1 seed / M=100 ticks on disk (catalog requires
  N_seeds=50), no distributional claim is supportable (event-style
  single-seed-ensemble refusal rules apply conceptually here too). The test
  therefore always concludes with `pytest.skip(INSUFFICIENT_ENSEMBLE ...)`
  once structural invariants have been checked -- it can fail (invariant
  violation, oracle leakage, WID mismatch) but it can never PASS/report a
  green fidelity verdict. The eventual N=50 gate must use a Karr-only
  seed-cluster / split-half null with a W1 (Wasserstein) or other
  preregistered multivariate metric -- see
  `wasserstein_over_wid_intersection` in l2_replay_common.py and the "Future
  N=50 gate contract" section of FTSZ_WINDOWED_PROFILE_SPEC.md. No such
  threshold is invented in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    audit_trace_mutated_ticks,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.vivarium.karr_ftsz_polymerization import (  # noqa: E402
    KarrFtsZPolymerizationProcess,
)

_TRACE_PROCESS_NAME = "FtsZPolymerization"
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
}

# Gate-eligible channels for the (future) N=50 verdict. `boundEnzymes` (Karr
# never mutates it for this process -- 0/100 ticks) and the OC-only derived
# `cell.ftsz_ring_count`/`ftsz_ring_complete` aggregate (no independent Karr
# ground truth channel exists for it) are diagnostics only and MUST NOT be
# promoted into this set without a separate, explicit decision.
GATE_CHANNELS = ("enzymes", "substrates")
DIAGNOSTIC_ONLY_CHANNELS = ("boundEnzymes", "cell.ftsz_ring_count", "cell.ftsz_ring_complete")

REQUIRED_N_SEEDS = (
    50  # PROCESS_CATALOG.yaml N_seeds for FtsZPolymerization (unchanged, not edited here)
)
ACTUAL_N_SEEDS = 1  # measured: identical seed-0 trace hash across every worktree + main + mirrors

_TELEMETRY_ARTIFACT = (
    _REPO_ROOT / "docs" / "phase_f" / "l2_windowed" / "ftsz_seed0_honest_mode_telemetry.json"
)


def classify_ensemble_support(n_seeds: int, required_n_seeds: int = REQUIRED_N_SEEDS) -> str:
    """Pure classification, no thresholds invented: mirrors the L2.event
    registry's own single-seed-ensemble refusal (docs/phase_f/l2_event/
    event_registry.yaml `required_n_seeds`). n_seeds < required_n_seeds can
    NEVER classify as sufficient -- there is no partial-credit branch."""
    if n_seeds < required_n_seeds:
        return "INSUFFICIENT_ENSEMBLE"
    return "SUFFICIENT_ENSEMBLE"


def _assert_no_oracle_leakage(state: dict[str, Any]) -> None:
    """Prove the honest-mode harness itself never injects a trace_hint. Combined
    with `forbid_sut_oracle_file_io` around the `next_update` call, this proves
    no oracle-after channel reaches the biology path this tick."""
    hint = state.get("trace_hint")
    assert not hint, (
        "honest-mode canary must never populate trace_hint (found: "
        f"{hint!r}); this would silently re-enable the enzymes_next "
        "short-circuit documented in L2_5_HONEST_MODE_HINT_LEAKAGE_FINDING.md"
    )


def _monomer_conservation_delta(
    process: KarrFtsZPolymerizationProcess, enzyme_delta: dict[str, float]
) -> int:
    delta_vec = np.asarray(
        [float(enzyme_delta.get(wid, 0.0)) for wid in process.enzyme_wids], dtype=np.float64
    )
    return int(np.rint(float(np.dot(process.n_monomers, delta_vec))))


def _check_substrate_stoichiometry(
    process: KarrFtsZPolymerizationProcess,
    *,
    enzyme_delta: dict[str, float],
    substrate_delta: dict[str, float],
    tick: int,
) -> None:
    """Exact (integer-arithmetic) self-consistency check derived directly from
    `apply_substrate_limits`'s own algebra (FtsZPolymerization.m:403-433;
    karr_ftsz_polymerization.py `apply_substrate_limits`), independent of any
    reimplementation of the internal clamp-loop branching:

        shortfall := PI_delta  (PI has no other source term than the
                                 GDP-shortfall hydrolysis compensation)
        H2O_delta  == -shortfall
        H_delta    == +shortfall
        GDP_delta  == -n_gdp . d_enzyme + shortfall
        GTP_delta  == -n_gtp . d_enzyme - shortfall
    """
    delta_vec = np.asarray(
        [float(enzyme_delta.get(wid, 0.0)) for wid in process.enzyme_wids], dtype=np.float64
    )
    n_gtp_dot = float(np.dot(process.n_gtp, delta_vec))
    n_gdp_dot = float(np.dot(process.n_gdp, delta_vec))

    pi_delta = float(substrate_delta.get(process.pi_wid, 0.0))
    h2o_delta = float(substrate_delta.get(process.h2o_wid, 0.0))
    h_delta = float(substrate_delta.get(process.h_wid, 0.0))
    gdp_delta = float(substrate_delta.get(process.gdp_wid, 0.0))
    gtp_delta = float(substrate_delta.get(process.gtp_wid, 0.0))

    assert pi_delta >= -1e-9, f"tick={tick}: PI shortfall proxy went negative: {pi_delta}"
    assert abs(h2o_delta - (-pi_delta)) < 1e-6, (
        f"tick={tick}: H2O_delta={h2o_delta} != -PI_delta={-pi_delta}"
    )
    assert abs(h_delta - pi_delta) < 1e-6, f"tick={tick}: H_delta={h_delta} != PI_delta={pi_delta}"
    assert abs(gdp_delta - (-n_gdp_dot + pi_delta)) < 1e-6, (
        f"tick={tick}: GDP_delta={gdp_delta} != -n_gdp.d_enzyme({-n_gdp_dot}) + PI_delta({pi_delta})"
    )
    assert abs(gtp_delta - (-n_gtp_dot - pi_delta)) < 1e-6, (
        f"tick={tick}: GTP_delta={gtp_delta} != -n_gtp.d_enzyme({-n_gtp_dot}) - PI_delta({pi_delta})"
    )


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_ftsz_polymerization_honest_mode_windowed_canary(rng_seed: int) -> None:
    from l2_replay_common import forbid_sut_oracle_file_io

    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        mutated_obs = (
            "enzymes",
            "substrates",
        )  # boundEnzymes excluded: 0/100 mutated ticks, pass-through only
        mutated_tick_counts = audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "honest-mode canary N/A: no-op trace. Per-observable nonzero-delta "
                f"counts: {mutated_tick_counts}."
            )

        process = KarrFtsZPolymerizationProcess({"rng_seed": int(rng_seed)})
        state_template = build_state_template(process)

        wids_by_observable: dict[str, list[str]] = {}
        for observable in _OBSERVABLES:
            karr_before = cell_vector(trace, "states_before", observable, 0)
            wids_by_observable[observable] = infer_wids_for_observable(
                process,
                state_template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=_OBSERVABLE_TO_WIDS_ATTR.get(observable),
            )

        # Inversion guard: wrong-WID-order. If this ever drifts, every downstream
        # exact invariant below (monomer conservation, stoichiometry) becomes
        # meaningless because `process.n_monomers`/`n_gtp`/`n_gdp` are indexed by
        # `process.enzyme_wids` order, not by whatever order infer_wids_for_observable
        # happened to return.
        assert wids_by_observable["enzymes"] == list(process.enzyme_wids), (
            "enzymes WID order drift between harness inference and process fixture "
            "order -- monomer/stoichiometry invariants below would silently "
            "validate against the wrong species."
        )

        oc_nonvacuous_ticks = 0
        telemetry: dict[str, Any] = {
            "process": _TRACE_PROCESS_NAME,
            "trace_path": str(trace_path),
            "rng_seed": int(rng_seed),
            "n_ticks": n_ticks,
            "n_seeds_available": ACTUAL_N_SEEDS,
            "n_seeds_required_by_catalog": REQUIRED_N_SEEDS,
            "ensemble_status": classify_ensemble_support(ACTUAL_N_SEEDS),
            "gate_channels": list(GATE_CHANNELS),
            "diagnostic_only_channels": list(DIAGNOSTIC_ONLY_CHANNELS),
            "karr_mutated_tick_counts": mutated_tick_counts,
            "per_tick": [],
        }

        for tick in range(n_ticks):
            state = build_state_template(process)
            _assert_no_oracle_leakage(state)

            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }
            after_vectors = {
                observable: cell_vector(trace, "states_after", observable, tick)
                for observable in _OBSERVABLES
            }

            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                )
            # Deliberately NOT calling overlay_trace_after_hint here (honest mode).
            refresh_allocator_views(process, state)
            _assert_no_oracle_leakage(state)

            with forbid_sut_oracle_file_io():
                update = process.next_update(1.0, state)

            deltas_by_label = dict(collect_count_delta_dicts(update))
            enzyme_delta = deltas_by_label.get("enzymes", {})
            substrate_delta = deltas_by_label.get("substrates", {})

            for label, deltas in deltas_by_label.items():
                for wid, delta in deltas.items():
                    delta_f = float(delta)
                    assert np.isfinite(delta_f), (
                        f"tick={tick}: non-finite delta {label}/{wid}={delta_f}"
                    )
                    assert delta_f == float(np.rint(delta_f)), (
                        f"tick={tick}: non-integral delta {label}/{wid}={delta_f}"
                    )

            monomer_delta = _monomer_conservation_delta(process, enzyme_delta)
            assert monomer_delta == 0, (
                f"tick={tick}: FtsZ total-monomer conservation violated: "
                f"n_monomers.d_enzymes={monomer_delta} (expected 0)"
            )

            if substrate_delta:
                _check_substrate_stoichiometry(
                    process, enzyme_delta=enzyme_delta, substrate_delta=substrate_delta, tick=tick
                )

            if any(abs(float(v)) > 0.0 for v in enzyme_delta.values()):
                oc_nonvacuous_ticks += 1

            from l2_replay_common import apply_count_update

            apply_count_update(state, update)

            oc_after_enzymes = project_observable_from_state(
                process=process,
                state=state,
                observable="enzymes",
                wids=wids_by_observable["enzymes"],
                bound_enzymes_before=before_vectors.get("boundEnzymes"),
            )
            oc_after_substrates = project_observable_from_state(
                process=process,
                state=state,
                observable="substrates",
                wids=wids_by_observable["substrates"],
                bound_enzymes_before=before_vectors.get("boundEnzymes"),
            )

            assert np.all(np.isfinite(oc_after_enzymes)), f"tick={tick}: non-finite enzymes state"
            assert np.all(oc_after_enzymes >= -1e-9), (
                f"tick={tick}: negative enzymes state {oc_after_enzymes}"
            )
            assert np.all(np.isfinite(oc_after_substrates)), (
                f"tick={tick}: non-finite substrates state"
            )
            assert np.all(oc_after_substrates >= -1e-9), (
                f"tick={tick}: negative substrates state {oc_after_substrates}"
            )

            karr_after_enzymes = after_vectors["enzymes"]
            karr_after_substrates = after_vectors["substrates"]
            enzymes_l1 = float(np.sum(np.abs(oc_after_enzymes - karr_after_enzymes)))
            enzymes_linf = float(np.max(np.abs(oc_after_enzymes - karr_after_enzymes)))
            substrates_l1 = float(np.sum(np.abs(oc_after_substrates - karr_after_substrates)))
            substrates_linf = float(np.max(np.abs(oc_after_substrates - karr_after_substrates)))

            telemetry["per_tick"].append(
                {
                    "tick": tick,
                    "enzymes_l1": enzymes_l1,
                    "enzymes_linf": enzymes_linf,
                    "substrates_l1": substrates_l1,
                    "substrates_linf": substrates_linf,
                }
            )

        assert oc_nonvacuous_ticks > 0, (
            "honest-mode OC trajectory is constant across all "
            f"{n_ticks} ticks (0 nonzero enzyme deltas) -- this would be a "
            "quiet/constant-trajectory fake pass; Karr's own trace is "
            f"non-vacuous ({mutated_tick_counts})."
        )
        telemetry["oc_nonvacuous_ticks"] = oc_nonvacuous_ticks

        enz_l1_values = [row["enzymes_l1"] for row in telemetry["per_tick"]]
        sub_l1_values = [row["substrates_l1"] for row in telemetry["per_tick"]]
        telemetry["summary"] = {
            "enzymes_l1_mean": float(np.mean(enz_l1_values)),
            "enzymes_l1_max": float(np.max(enz_l1_values)),
            "enzymes_l1_zero_ticks": int(sum(1 for v in enz_l1_values if v == 0.0)),
            "substrates_l1_mean": float(np.mean(sub_l1_values)),
            "substrates_l1_max": float(np.max(sub_l1_values)),
            "substrates_l1_zero_ticks": int(sum(1 for v in sub_l1_values if v == 0.0)),
        }

        _TELEMETRY_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        _TELEMETRY_ARTIFACT.write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n")

        status = classify_ensemble_support(ACTUAL_N_SEEDS)
        assert (
            status == "INSUFFICIENT_ENSEMBLE"
        )  # N=1 can never promote itself (see inversion test)
        pytest.skip(
            f"{status}: N={ACTUAL_N_SEEDS} seed(s) available, "
            f"N={REQUIRED_N_SEEDS} required by PROCESS_CATALOG.yaml for a gated "
            "verdict. Structural invariants (monomer conservation, substrate "
            "stoichiometry, finite/nonnegative/integer state) held for all "
            f"{n_ticks} honest-mode ticks; no trace_hint reached next_update. "
            f"Discrepancy telemetry (seed 0): enzymes L1 mean="
            f"{telemetry['summary']['enzymes_l1_mean']:.4f} max="
            f"{telemetry['summary']['enzymes_l1_max']:.4f} "
            f"zero-ticks={telemetry['summary']['enzymes_l1_zero_ticks']}/{n_ticks}; "
            f"substrates L1 mean={telemetry['summary']['substrates_l1_mean']:.4f} "
            f"max={telemetry['summary']['substrates_l1_max']:.4f} "
            f"zero-ticks={telemetry['summary']['substrates_l1_zero_ticks']}/{n_ticks}. "
            f"Full per-tick telemetry: {_TELEMETRY_ARTIFACT}."
        )
